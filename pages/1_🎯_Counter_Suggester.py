import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_playable_cards, get_card_list, get_card_at_level, get_card_types, SUB_UNITS
from utils.deck_analysis import ELIXIR_COSTS, CARD_ROLES, analyze_deck
from utils.counter_suggester import (
    HARD_COUNTERS, WEAKNESS_COUNTERS, detect_weaknesses, get_counter_cards, generate_counter_deck,
)

st.set_page_config(page_title="Counter Suggester", page_icon="🎯", layout="wide")

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = load_playable_cards()
    card_list = get_card_list()
    card_types = get_card_types()
    return df, card_list, card_types

df, card_list, card_types = load_data()


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("🎯 Counter Suggester")
st.caption("Enter your opponent's deck and get the best cards to counter it.")

st.markdown("---")

# Opponent deck input
st.subheader("Opponent's Deck")
opp_cols = st.columns(4)
opponent_cards = []

for i in range(8):
    with opp_cols[i % 4]:
        card = st.selectbox(
            f"Card {i+1}",
            options=["— empty —"] + card_list,
            key=f"opp_card_{i}"
        )
        if card != "— empty —":
            opponent_cards.append(card)

if len(opponent_cards) == 0:
    st.info("Add your opponent's cards above to see counter suggestions.")
else:
    st.markdown("---")

    # ── Level source: connected API collection, or a manual default ──────────
    connected = st.session_state.get("connected_collection")
    st.subheader("Card Levels for Suggestions")
    if connected:
        use_connected = st.checkbox(
            f"Use my connected collection levels ({st.session_state.get('connected_player_name', 'loaded from Live API')})",
            value=True,
        )
    else:
        use_connected = False
        st.caption("💡 Connect your account on the Live API page to use your real card levels here instead of a flat default.")

    if use_connected:
        card_levels = connected
        default_level = 11
    else:
        card_levels = None
        default_level = st.slider("Assume all suggested cards are at level", 1, 18, 11)

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Deck Analysis")

        # Opponent elixir
        opp_elixir = [ELIXIR_COSTS.get(c, 0) for c in opponent_cards if ELIXIR_COSTS.get(c, 0) > 0]
        avg_elixir = round(np.mean(opp_elixir), 2) if opp_elixir else 0
        st.metric("Avg Elixir", avg_elixir)

        # Roles
        opp_roles = set()
        for card in opponent_cards:
            for role, role_cards in CARD_ROLES.items():
                if card in role_cards:
                    opp_roles.add(role)

        all_roles = set(CARD_ROLES.keys())
        missing_roles = all_roles - opp_roles

        st.markdown("**✅ Has:**")
        role_display = {
            "tank": "🐘 Tank", "mini_tank": "🛡️ Mini Tank",
            "win_condition": "🏆 Win Condition", "spell": "✨ Spell",
            "air_defense": "✈️ Air Defense", "cycle": "🔄 Cycle",
            "spawner": "🏚️ Spawner"
        }
        for r in sorted(opp_roles):
            st.markdown(f"- {role_display.get(r, r)}")

        if missing_roles:
            st.markdown("**❌ Missing:**")
            for r in sorted(missing_roles):
                st.markdown(f"- {role_display.get(r, r)}")

        # Weaknesses
        weaknesses = detect_weaknesses(opponent_cards)
        if weaknesses:
            st.markdown("**⚠️ Exploitable Weaknesses:**")
            weakness_labels = {
                "no_air_defense": "No air defense → play air troops",
                "no_spell": "No spell → swarm them",
                "high_elixir": "High elixir → cycle fast",
                "no_tank_killer": "No tank killer → push with tanks",
                "no_swarm_clear": "No swarm clear → flood with cheap troops",
                "building_heavy": "Building heavy → use spell/drill",
                "low_hp_cards": "Fragile cards → use area spells",
            }
            for w in weaknesses:
                st.warning(weakness_labels.get(w, w))

    with col_right:
        st.subheader("Top Counter Cards")

        if len(opponent_cards) >= 2:
            counter_df = get_counter_cards(opponent_cards, top_n=12, card_levels=card_levels, default_level=default_level)

            if not counter_df.empty:
                # Color by score
                fig = px.bar(
                    counter_df.head(10),
                    x="Card", y="Counter Score",
                    color="Counter Score",
                    color_continuous_scale="Teal",
                    hover_data=["Type", "Elixir", "Level", "Reasons"],
                    title="Best Counter Cards (higher = better counter)"
                )
                fig.update_layout(height=350, showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(
                    counter_df[["Card", "Type", "Elixir", "Level", "HP", "DPS", "Reasons"]],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Not enough opponent cards yet to generate counters — try adding more.")
        else:
            st.info("Add at least 2 opponent cards to see counter suggestions.")

    # ── Full counter deck ──────────────────────────────────────────────────────
    if len(opponent_cards) >= 2:
        st.markdown("---")
        st.subheader("🃏 Generated Counter Deck")
        st.caption("A full 8-card deck built to answer this opponent — covers key roles first, then fills with the highest-scoring remaining counters.")

        result = generate_counter_deck(opponent_cards, card_levels=card_levels, default_level=default_level)

        if result["deck"]:
            deck_analysis = result["analysis"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Avg Elixir", deck_analysis.get("avg_elixir", "—"))
            m2.metric("Cycle Cost", f"{deck_analysis.get('cycle_cost', '—')} elixir")
            m3.metric("Combined HP", f"{deck_analysis.get('total_hp', 0):,}")
            m4.metric("Combined DPS", f"{deck_analysis.get('total_dps', 0):,}")

            deck_cols = st.columns(4)
            for i, card in enumerate(result["deck"]):
                with deck_cols[i % 4]:
                    st.markdown(f"**{card}**")
                    st.caption(f"Lvl {result['levels'][card]} · {ELIXIR_COSTS.get(card, '?')} elixir")

            st.dataframe(
                result["picks"][["Card", "Deck Role", "Level", "Elixir", "HP", "DPS", "Counter Score"]],
                use_container_width=True, hide_index=True
            )

            missing_roles = deck_analysis.get("roles_missing", [])
            if missing_roles:
                st.caption(f"Roles not covered: {', '.join(missing_roles)}")
            for w in deck_analysis.get("warnings", []):
                st.warning(w)
        else:
            st.info("Not enough counter data to assemble a full deck yet.")
