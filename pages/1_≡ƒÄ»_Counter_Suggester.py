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

st.set_page_config(page_title="Counter Suggester", page_icon="🎯", layout="wide")

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = load_playable_cards()
    card_list = get_card_list()
    card_types = get_card_types()
    return df, card_list, card_types

df, card_list, card_types = load_data()

# ── Counter logic ─────────────────────────────────────────────────────────────

# Hard counters: card_name -> list of cards it counters well
HARD_COUNTERS = {
    "Zap":          ["Skeleton", "Goblin", "Bat", "Fire Spirit", "Electro Spirit", "Sparky", "Inferno Dragon", "Inferno Tower"],
    "The Log":      ["Skeleton", "Goblin", "Bat", "Princess", "Dart Goblin", "Rascal Girl"],
    "Arrows":       ["Minion", "Bat", "Skeleton", "Goblin", "Witch", "Night Witch"],
    "Fireball":     ["Musketeer", "Three Musketeers", "Barbarian", "Wizard", "Witch", "Goblin Gang"],
    "Poison":       ["Graveyard", "Goblin Barrel", "Three Musketeers", "Musketeer"],
    "Lightning":    ["Inferno Tower", "Electro Giant", "Sparky", "Three Musketeers", "X-Bow"],
    "Rocket":       ["X-Bow", "Mortar", "Elixir Collector", "Three Musketeers"],
    "Tornado":      ["Hog Rider", "Battle Ram", "Goblin Giant", "Golem"],
    "Inferno Tower":["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Lava Hound", "Balloon"],
    "Inferno Dragon":["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Lava Hound"],
    "Tesla":        ["Hog Rider", "Royal Hogs", "Balloon"],
    "Cannon":       ["Hog Rider", "Royal Hogs", "Giant", "Goblin Drill"],
    "Mini P.E.K.K.A":["Balloon", "Hog Rider", "Giant", "Golem"],
    "Valkyrie":     ["Skeleton", "Goblin", "Bat", "Barbarian", "Witch", "Night Witch"],
    "Bowler":       ["Skeleton Army", "Barbarian", "Goblin Gang", "Royal Recruits"],
    "Executioner":  ["Skeleton Army", "Minion Horde", "Barbarian", "Night Witch"],
    "Musketeer":    ["Balloon", "Lava Hound", "Baby Dragon", "Minion Horde"],
    "Mega Minion":  ["Balloon", "Baby Dragon", "Giant", "P.E.K.K.A"],
    "Electro Wizard":["Sparky", "Inferno Dragon", "Inferno Tower", "Lava Hound"],
    "Electro Dragon":["Sparky", "Skeleton Army", "Goblin Gang", "Minion Horde"],
    "Baby Dragon":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Minion Horde"],
    "Hunter":       ["Giant", "Golem", "Mega Knight", "P.E.K.K.A", "Balloon"],
    "Knight":       ["Miner", "Goblin Barrel", "Princess", "Dart Goblin"],
    "Dark Prince":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Royal Recruits"],
    "Ice Wizard":   ["Hog Rider", "Battle Ram", "Royal Hogs", "Giant"],
    "Fisherman":    ["Giant", "Golem", "Balloon", "Lava Hound"],
    "Mega Knight":  ["Skeleton Army", "Goblin Gang", "Barbarian", "Minion Horde"],
}

# Weaknesses: type of deck -> list of exploiting cards
WEAKNESS_COUNTERS = {
    "no_air_defense": ["Balloon", "Lava Hound", "Inferno Dragon", "Baby Dragon", "Minion Horde", "Flying Machine"],
    "no_spell":       ["Goblin Barrel", "Skeleton Army", "Minion Horde", "Goblin Gang", "Graveyard"],
    "high_elixir":    ["Hog Rider", "Battle Ram", "Royal Hogs", "Goblin Barrel", "Miner", "X-Bow", "Mortar"],
    "no_tank_killer": ["Giant", "Golem", "P.E.K.K.A", "Mega Knight", "Goblin Giant"],
    "no_swarm_clear": ["Valkyrie", "Executioner", "Bowler", "Dark Prince", "Baby Dragon"],
    "building_heavy": ["Rocket", "Lightning", "Earthquake", "Goblin Drill", "Wall Breakers"],
    "low_hp_cards":   ["Fireball", "Rocket", "Lightning", "Poison"],
}

def detect_weaknesses(opponent_cards: list[str]) -> list[str]:
    """Detect weaknesses in an opponent's deck."""
    weaknesses = []
    opp_types = {c: card_types.get(c, "Troop") for c in opponent_cards}

    # Check roles
    opp_roles = set()
    for card in opponent_cards:
        for role, role_cards in CARD_ROLES.items():
            if card in role_cards:
                opp_roles.add(role)

    if "air_defense" not in opp_roles:
        weaknesses.append("no_air_defense")
    if "spell" not in opp_roles:
        weaknesses.append("no_spell")
    if "tank" not in opp_roles and "mini_tank" not in opp_roles:
        weaknesses.append("no_tank_killer")  # they can't stop your tanks
    if "cycle" not in opp_roles:
        weaknesses.append("no_swarm_clear")

    # Elixir check
    opp_elixir = [ELIXIR_COSTS.get(c, 0) for c in opponent_cards if ELIXIR_COSTS.get(c, 0) > 0]
    if opp_elixir and np.mean(opp_elixir) >= 4.2:
        weaknesses.append("high_elixir")

    # Building heavy
    building_count = sum(1 for c in opponent_cards if card_types.get(c) == "Building")
    if building_count >= 2:
        weaknesses.append("building_heavy")

    return weaknesses


def get_counter_cards(opponent_cards: list[str], top_n: int = 12) -> pd.DataFrame:
    """Score all cards by how well they counter the opponent's deck."""
    scores = {}

    # Score from hard counters
    for counter_card, countered_list in HARD_COUNTERS.items():
        for opp_card in opponent_cards:
            if opp_card in countered_list:
                scores[counter_card] = scores.get(counter_card, 0) + 2

    # Score from weakness exploitation
    weaknesses = detect_weaknesses(opponent_cards)
    for weakness in weaknesses:
        for exploit_card in WEAKNESS_COUNTERS.get(weakness, []):
            scores[exploit_card] = scores.get(exploit_card, 0) + 3

    # Remove opponent's own cards from suggestions
    for c in opponent_cards:
        scores.pop(c, None)

    # Build dataframe
    rows = []
    for card, score in sorted(scores.items(), key=lambda x: -x[1])[:top_n]:
        elixir = ELIXIR_COSTS.get(card, "?")
        card_type = card_types.get(card, "Troop")
        row_data = get_card_at_level(card, 11)
        hp = int(row_data["Hitpoints"]) if row_data is not None and pd.notna(row_data.get("Hitpoints")) else "—"
        dps = round(float(row_data["DPS"]), 1) if row_data is not None and pd.notna(row_data.get("DPS")) else "—"

        # Find which weakness/counter this card addresses
        reasons = []
        for opp_card in opponent_cards:
            if card in HARD_COUNTERS and opp_card in HARD_COUNTERS.get(card, []):
                reasons.append(f"Counters {opp_card}")
        for weakness in weaknesses:
            if card in WEAKNESS_COUNTERS.get(weakness, []):
                label = weakness.replace("_", " ").replace("no ", "Exploits lack of ").title()
                if label not in reasons:
                    reasons.append(label)

        rows.append({
            "Card": card,
            "Type": card_type,
            "Elixir": elixir,
            "HP (Lvl 11)": hp,
            "DPS (Lvl 11)": dps,
            "Counter Score": score,
            "Reasons": ", ".join(reasons[:2]) if reasons else "General value",
        })

    return pd.DataFrame(rows)


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
            counter_df = get_counter_cards(opponent_cards, top_n=12)

            if not counter_df.empty:
                # Color by score
                fig = px.bar(
                    counter_df.head(10),
                    x="Card", y="Counter Score",
                    color="Counter Score",
                    color_continuous_scale="Teal",
                    hover_data=["Type", "Elixir", "Reasons"],
                    title="Best Counter Cards (higher = better counter)"
                )
                fig.update_layout(height=350, showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(
                    counter_df[["Card", "Type", "Elixir", "HP (Lvl 11)", "DPS (Lvl 11)", "Reasons"]],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Not enough opponent cards yet to generate counters — try adding more.")
        else:
            st.info("Add at least 2 opponent cards to see counter suggestions.")
