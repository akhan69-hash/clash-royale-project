import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_playable_cards, get_card_list, get_card_types, get_card_at_level, api_level_to_csv_level
from utils.deck_analysis import ELIXIR_COSTS, analyze_deck
from utils.counter_suggester import get_counter_cards, detect_weaknesses, generate_counter_deck

st.set_page_config(page_title="Live API", page_icon="🌐", layout="wide")

@st.cache_data
def load_data():
    df = load_playable_cards()
    card_list = get_card_list()
    card_types = get_card_types()
    return df, card_list, card_types

df, card_list, card_types = load_data()

# ── API helpers ───────────────────────────────────────────────────────────────

def get_player(tag: str, api_key: str) -> dict | None:
    """Fetch player profile from Clash Royale API."""
    tag = tag.strip().lstrip("#").upper()
    url = f"https://api.clashroyale.com/v1/players/%23{tag}"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 403:
            st.error("❌ Invalid API key or IP not whitelisted. Check your key at developer.clashroyale.com")
        elif resp.status_code == 404:
            st.error(f"❌ Player #{tag} not found. Check the tag and try again.")
        else:
            st.error(f"❌ API error {resp.status_code}: {resp.text[:200]}")
    except requests.exceptions.Timeout:
        st.error("❌ Request timed out. Try again.")
    except Exception as e:
        st.error(f"❌ Connection error: {e}")
    return None


def get_battle_log(tag: str, api_key: str) -> list | None:
    """Fetch recent battle log."""
    tag = tag.strip().lstrip("#").upper()
    url = f"https://api.clashroyale.com/v1/players/%23{tag}/battlelog"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def match_api_card_to_local(api_name: str) -> str | None:
    """Try to match an API card name to our local card name."""
    # API uses names like "Mini P.E.K.K.A" which may differ slightly
    name_fixes = {
        "Mini P.E.K.K.A": "Mini P.E.K.K.A",
        "P.E.K.K.A": "P.E.K.K.A",
        "Goblin Giant": "Goblin Giant",
        "Spear Goblins": "Spear Goblin",
        "Archers": "Archer",
        "Barbarians": "Barbarian",
        "Bats": "Bat",
        "Skeletons": "Skeleton",
        "Goblins": "Goblins",
        "Minions": "Minion",
        "Guards": "Guard",
        "Elite Barbarians": "Elite Barbarian",
    }
    if api_name in name_fixes:
        return name_fixes[api_name]
    if api_name in card_list:
        return api_name
    return None


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("🌐 Live Player Data")
st.caption("Connect to the official Clash Royale API to pull real player stats.")

# API Key setup
with st.expander("🔑 API Key Setup (click to expand)", expanded=True):
    st.markdown("""
    **How to get your API key:**
    1. Go to [developer.clashroyale.com](https://developer.clashroyale.com)
    2. Create a free account and log in
    3. Click **Create New Key**
    4. Give it a name, set your IP address (or use `0.0.0.0/0` for testing)
    5. Copy the key and paste it below

    > ⚠️ Your key is only stored in this session — it's never saved to disk.
    """)
    api_key = st.text_input("API Key", type="password", placeholder="eyJ0eXAiOiJKV1Qi...")

st.markdown("---")

if not api_key:
    st.info("Enter your API key above to get started.")
    st.stop()

# Player lookup
st.subheader("Player Lookup")
player_tag = st.text_input("Player Tag", placeholder="#ABC123 or ABC123")

if st.button("🔍 Fetch Player", type="primary") and player_tag:
    with st.spinner("Fetching player data..."):
        player = get_player(player_tag, api_key)

    if player:
        st.success(f"✅ Found: **{player.get('name', '?')}**")

        # ── Profile overview ──────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Trophies", f"{player.get('trophies', 0):,}")
        col2.metric("Best Trophies", f"{player.get('bestTrophies', 0):,}")
        col3.metric("Wins", f"{player.get('wins', 0):,}")
        col4.metric("Losses", f"{player.get('losses', 0):,}")

        col5, col6, col7 = st.columns(3)
        total_games = player.get('wins', 0) + player.get('losses', 0)
        win_rate = round(player.get('wins', 0) / total_games * 100, 1) if total_games > 0 else 0
        col5.metric("Win Rate", f"{win_rate}%")
        col6.metric("Three Crown Wins", f"{player.get('threeCrownWins', 0):,}")
        col7.metric("Cards Found", f"{player.get('currentFavouriteCard', {}).get('name', '—')}")

        st.markdown("---")

        # ── Card collection ───────────────────────────────────────────────────
        st.subheader("Your Card Collection")

        api_cards = player.get("cards", [])
        if api_cards:
            collection_rows = []
            for api_card in api_cards:
                name = api_card.get("name", "")
                level = api_card.get("level", 0)
                max_level = api_card.get("maxLevel", 14)
                local_name = match_api_card_to_local(name)

                collection_rows.append({
                    "Card": name,
                    "Local Match": local_name or "—",
                    "Level": level,
                    "Max Level": max_level,
                    "% to Max": round(level / max_level * 100, 1),
                    "Levels to Max": max_level - level,
                    # Our stats CSV uses absolute levels (1-18); the API's "level" is
                    # relative to that card's own maxLevel -- see api_level_to_csv_level.
                    "CSV Level": api_level_to_csv_level(level, max_level),
                })

            coll_df = pd.DataFrame(collection_rows).sort_values("% to Max", ascending=False)

            # Make these real levels available to every other page for this session
            # (Deck Builder, Counter Suggester, Collection Builder) instead of a flat default.
            # Use "CSV Level" (converted), not the raw API level, since that's what
            # get_card_at_level()/analyze_deck() expect.
            st.session_state["connected_collection"] = {
                match_api_card_to_local(row["Card"]): row["CSV Level"]
                for row in collection_rows
                if match_api_card_to_local(row["Card"])
            }
            st.session_state["connected_player_name"] = player.get("name", "your account")

            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Cards in Collection", len(api_cards))
                avg_pct = round(coll_df["% to Max"].mean(), 1)
                st.metric("Avg Progress to Max", f"{avg_pct}%")
                maxed = len(coll_df[coll_df["Levels to Max"] == 0])
                st.metric("Maxed Cards", maxed)

            with col_b:
                # Top cards closest to max
                close_to_max = coll_df[coll_df["Levels to Max"] > 0].tail(10)
                fig = px.bar(
                    close_to_max,
                    x="Card", y="Levels to Max",
                    color="Levels to Max",
                    color_continuous_scale="RdYlGn_r",
                    title="Cards Closest to Max Level"
                )
                fig.update_layout(height=300, showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                coll_df[["Card", "Level", "Max Level", "% to Max", "Levels to Max"]],
                use_container_width=True,
                hide_index=True
            )

        st.markdown("---")

        # ── Current deck ──────────────────────────────────────────────────────
        st.subheader("Current Deck")
        current_deck = player.get("currentDeck", [])
        if current_deck:
            deck_names = [c.get("name", "") for c in current_deck]
            # Convert each card's API-relative level to our CSV's absolute scale.
            deck_levels = {
                c.get("name", ""): api_level_to_csv_level(c.get("level", 1), c.get("maxLevel", 14))
                for c in current_deck
            }

            local_deck = [match_api_card_to_local(n) or n for n in deck_names]
            local_levels = {match_api_card_to_local(n) or n: l for n, l in deck_levels.items()}

            analysis = analyze_deck(local_deck, local_levels)

            col1, col2, col3 = st.columns(3)
            col1.metric("Avg Elixir", analysis.get("avg_elixir", "—"))
            col2.metric("Cycle Cost", f"{analysis.get('cycle_cost', '—')} elixir")
            col3.metric("Roles Covered", len(analysis.get("roles_covered", [])))

            deck_df = pd.DataFrame([{
                "Card": c.get("name"), "Level": c.get("level"),
                "Elixir": ELIXIR_COSTS.get(match_api_card_to_local(c.get("name","")) or "", "?")
            } for c in current_deck])
            st.dataframe(deck_df, use_container_width=True, hide_index=True)

            warnings = analysis.get("warnings", [])
            if warnings:
                for w in warnings:
                    st.warning(w)

        st.markdown("---")

        # ── Battle log ────────────────────────────────────────────────────────
        st.subheader("Recent Battles")
        with st.spinner("Fetching battle log..."):
            battles = get_battle_log(player_tag, api_key)

        if battles:
            battle_rows = []
            opponent_decks = []  # parallel list: mapped local card names per battle
            for battle in battles[:20]:
                team = battle.get("team", [{}])[0]
                opponent = battle.get("opponent", [{}])[0]
                battle_rows.append({
                    "Type": battle.get("type", ""),
                    "Result": "Win" if team.get("crowns", 0) > opponent.get("crowns", 0) else "Loss",
                    "Crowns": f"{team.get('crowns',0)}-{opponent.get('crowns',0)}",
                    "Your Trophies": team.get("startingTrophies", "—"),
                    "Opponent": opponent.get("name", "?"),
                    "Opp Trophies": opponent.get("startingTrophies", "—"),
                })
                opp_cards = opponent.get("cards", [])
                mapped = [match_api_card_to_local(c.get("name", "")) for c in opp_cards]
                opponent_decks.append([c for c in mapped if c])

            battle_df = pd.DataFrame(battle_rows)
            wins = len(battle_df[battle_df["Result"] == "Win"])
            losses = len(battle_df[battle_df["Result"] == "Loss"])
            st.metric("Recent Win Rate", f"{round(wins/(wins+losses)*100,1)}% ({wins}W/{losses}L)")

            # Color result column
            st.dataframe(battle_df, use_container_width=True, hide_index=True)

            st.markdown("---")

            # ── Opponent deck picker + counter suggestions ──────────────────────
            st.subheader("Counter an Opponent You Faced")
            st.caption("Pick a real battle from your log to get counter suggestions for that opponent's deck.")

            deck_options = [
                f"#{i+1} — vs {row['Opponent']} ({row['Result']}, {len(opponent_decks[i])}/8 cards matched)"
                for i, row in enumerate(battle_rows)
                if len(opponent_decks[i]) >= 2
            ]
            valid_indices = [i for i in range(len(battle_rows)) if len(opponent_decks[i]) >= 2]

            if deck_options:
                choice = st.selectbox("Select a battle", deck_options)
                chosen_i = valid_indices[deck_options.index(choice)]
                chosen_deck = opponent_decks[chosen_i]

                unmatched = len(battles[chosen_i].get("opponent", [{}])[0].get("cards", [])) - len(chosen_deck)
                if unmatched > 0:
                    st.caption(f"⚠️ {unmatched} card(s) in this deck couldn't be matched to our local card list and are excluded below.")

                use_my_levels = st.checkbox(
                    "Use my real card levels (from the collection above) for counter suggestions",
                    value=True,
                )
                if use_my_levels:
                    card_levels = st.session_state.get("connected_collection")
                    default_level = 11
                else:
                    card_levels = None
                    default_level = st.slider("Assume suggested cards are at level", 1, 18, 11)

                col1, col2 = st.columns([1, 2])
                with col1:
                    st.markdown("**Opponent's Deck**")
                    st.dataframe(
                        pd.DataFrame({"Card": chosen_deck, "Elixir": [ELIXIR_COSTS.get(c, "?") for c in chosen_deck]}),
                        use_container_width=True, hide_index=True
                    )
                    weaknesses = detect_weaknesses(chosen_deck)
                    if weaknesses:
                        st.markdown("**Exploitable Weaknesses:**")
                        for w in weaknesses:
                            st.warning(w.replace("_", " ").replace("no ", "no ").title())

                with col2:
                    counter_df = get_counter_cards(chosen_deck, top_n=12, card_levels=card_levels, default_level=default_level)
                    if not counter_df.empty:
                        fig = px.bar(
                            counter_df.head(10),
                            x="Card", y="Counter Score",
                            color="Counter Score",
                            color_continuous_scale="Teal",
                            hover_data=["Type", "Elixir", "Level", "Reasons"],
                            title="Best Counter Cards for This Opponent"
                        )
                        fig.update_layout(height=350, showlegend=False, coloraxis_showscale=False)
                        st.plotly_chart(fig, use_container_width=True)
                        st.dataframe(
                            counter_df[["Card", "Type", "Elixir", "Level", "HP", "DPS", "Reasons"]],
                            use_container_width=True, hide_index=True
                        )

                st.markdown("---")
                st.subheader("🃏 Generated Counter Deck")
                st.caption("A full 8-card deck to answer this opponent, built from your real card levels where available.")
                deck_result = generate_counter_deck(chosen_deck, card_levels=card_levels, default_level=default_level)

                if deck_result["deck"]:
                    da = deck_result["analysis"]
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Avg Elixir", da.get("avg_elixir", "—"))
                    m2.metric("Cycle Cost", f"{da.get('cycle_cost', '—')} elixir")
                    m3.metric("Combined HP", f"{da.get('total_hp', 0):,}")
                    m4.metric("Combined DPS", f"{da.get('total_dps', 0):,}")

                    deck_cols = st.columns(4)
                    for i, card in enumerate(deck_result["deck"]):
                        with deck_cols[i % 4]:
                            st.markdown(f"**{card}**")
                            st.caption(f"Lvl {deck_result['levels'][card]} · {ELIXIR_COSTS.get(card, '?')} elixir")

                    st.dataframe(
                        deck_result["picks"][["Card", "Deck Role", "Level", "Elixir", "HP", "DPS", "Counter Score"]],
                        use_container_width=True, hide_index=True
                    )
                    for w in da.get("warnings", []):
                        st.warning(w)
                else:
                    st.info("Not enough counter data to assemble a full deck yet.")
            else:
                st.info("None of your recent battles had enough matchable opponent cards to suggest counters.")
        else:
            st.info("Could not fetch battle log.")
