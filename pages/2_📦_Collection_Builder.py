import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_playable_cards, get_card_list, get_card_types, SUB_UNITS
from utils.deck_analysis import ELIXIR_COSTS, CARD_ROLES, analyze_deck

st.set_page_config(page_title="Collection Builder", page_icon="📦", layout="wide")

@st.cache_data
def load_data():
    df = load_playable_cards()
    card_list = get_card_list()
    card_types = get_card_types()
    return df, card_list, card_types

df, card_list, card_types = load_data()

st.title("📦 Collection Builder")
st.caption("Set your card levels to see what decks you can build and how your collection stacks up.")

st.markdown("---")

# ── Collection Input ──────────────────────────────────────────────────────────
st.subheader("Your Card Levels")
st.info("Set each card to your actual in-game level. Cards at level 0 means you don't own them yet.")

connected = st.session_state.get("connected_collection")
if connected:
    st.success(
        f"🌐 Connected collection available for **{st.session_state.get('connected_player_name', 'your account')}** "
        f"({len(connected)} cards matched). Click below to load your real levels."
    )

# Group cards by type for cleaner display
type_order = ["Troop", "Spell", "Building", "Champion"]
type_groups = {}
for card in card_list:
    t = card_types.get(card, "Troop")
    if t not in type_groups:
        type_groups[t] = []
    type_groups[t].append(card)

# Store collection in session state
if "collection" not in st.session_state:
    st.session_state.collection = {card: 11 for card in card_list}

def _set_levels(levels: dict[str, int]):
    """Update the collection AND clear each card's number_input widget state,
    since Streamlit widgets ignore `value=` once they've been instantiated once
    -- without this, quick-set buttons silently no-op on subsequent clicks."""
    for card, level in levels.items():
        st.session_state.collection[card] = level
        st.session_state.pop(f"collection_{card}", None)

# Quick set buttons
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    if st.button("Set All to Level 11"):
        _set_levels({card: 11 for card in card_list})
with col2:
    if st.button("Set All to Level 14"):
        _set_levels({card: 14 for card in card_list})
with col3:
    if st.button("Set All to Max (18)"):
        _set_levels({card: 18 for card in card_list})
with col4:
    if st.button("Reset All to 0 (Unowned)"):
        _set_levels({card: 0 for card in card_list})
with col5:
    if connected and st.button("🌐 Load My Connected Collection", type="primary"):
        _set_levels({card: level for card, level in connected.items() if card in card_list})

st.markdown("---")

# Card level inputs by type
for card_type in type_order:
    cards_in_type = type_groups.get(card_type, [])
    if not cards_in_type:
        continue

    with st.expander(f"{card_type}s ({len(cards_in_type)} cards)", expanded=(card_type == "Troop")):
        cols = st.columns(5)
        for i, card in enumerate(cards_in_type):
            with cols[i % 5]:
                level = st.number_input(
                    card,
                    min_value=0,
                    max_value=18,
                    value=st.session_state.collection.get(card, 11),
                    key=f"collection_{card}",
                    help="0 = unowned"
                )
                st.session_state.collection[card] = level

st.markdown("---")

# ── Collection Stats ──────────────────────────────────────────────────────────
st.subheader("Collection Overview")

collection = st.session_state.collection
owned_cards = {c: l for c, l in collection.items() if l > 0}
unowned = [c for c, l in collection.items() if l == 0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Cards Owned", len(owned_cards))
col2.metric("Cards Unowned", len(unowned))
avg_level = round(np.mean(list(owned_cards.values())), 1) if owned_cards else 0
col3.metric("Average Level", avg_level)
max_level_cards = sum(1 for l in owned_cards.values() if l >= 18)
col4.metric("Max Level Cards", max_level_cards)

# Level distribution chart
if owned_cards:
    level_counts = pd.Series(list(owned_cards.values())).value_counts().sort_index()
    fig = px.bar(
        x=level_counts.index,
        y=level_counts.values,
        labels={"x": "Level", "y": "Number of Cards"},
        title="Your Card Level Distribution",
        color=level_counts.values,
        color_continuous_scale="Blues"
    )
    fig.update_layout(height=300, showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ── Deck Viability Checker ────────────────────────────────────────────────────
st.subheader("Buildable Deck Checker")
st.caption("Enter a deck to check if you own all the cards and what level they'd be at.")

deck_check_cols = st.columns(4)
deck_to_check = []
for i in range(8):
    with deck_check_cols[i % 4]:
        card = st.selectbox(
            f"Slot {i+1}",
            options=["— empty —"] + card_list,
            key=f"deck_check_{i}"
        )
        if card != "— empty —":
            deck_to_check.append(card)

if len(deck_to_check) > 0:
    st.markdown("**Deck Check Results:**")
    result_rows = []
    all_owned = True
    for card in deck_to_check:
        lvl = collection.get(card, 0)
        owned = lvl > 0
        if not owned:
            all_owned = False
        result_rows.append({
            "Card": card,
            "Your Level": lvl if owned else "❌ Unowned",
            "Status": "✅ Ready" if lvl >= 11 else ("⚠️ Underleveled" if owned else "❌ Not owned"),
            "Elixir Cost": ELIXIR_COSTS.get(card, "?")
        })

    result_df = pd.DataFrame(result_rows)
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    if all_owned:
        owned_levels = {card: collection[card] for card in deck_to_check}
        analysis = analyze_deck(deck_to_check, owned_levels)
        st.success(f"✅ You own all cards! Avg elixir: {analysis.get('avg_elixir')} | Avg level: {round(np.mean(list(owned_levels.values())), 1)}")
    else:
        missing = [r["Card"] for r in result_rows if r["Status"] == "❌ Not owned"]
        st.error(f"❌ Missing cards: {', '.join(missing)}")

st.markdown("---")

# ── Upgrade Priority ──────────────────────────────────────────────────────────
st.subheader("Upgrade Priority")
st.caption("Cards you own but haven't maxed yet, sorted by how far they are from level 14 (tournament standard).")

tournament_level = st.slider("Target Level", 1, 18, 14)

upgradeable = [
    {"Card": c, "Current Level": l, "Levels to Target": max(0, tournament_level - l)}
    for c, l in owned_cards.items()
    if l < tournament_level
]
upgradeable.sort(key=lambda x: x["Levels to Target"])

if upgradeable:
    upgrade_df = pd.DataFrame(upgradeable)
    fig = px.bar(
        upgrade_df.head(20),
        x="Card", y="Levels to Target",
        color="Levels to Target",
        color_continuous_scale="RdYlGn_r",
        title=f"Cards Furthest from Level {tournament_level} (top 20)"
    )
    fig.update_layout(height=350, showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(upgrade_df, use_container_width=True, hide_index=True)
else:
    st.success(f"🎉 All owned cards are at level {tournament_level} or above!")
