import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.data_loader import (
    load_playable_cards, get_card_list, get_card_at_level,
    get_card_types, get_card_meta, SUB_UNITS
)
from utils.deck_analysis import analyze_deck, ELIXIR_COSTS, CARD_ROLES

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Clash Royale Deck Builder",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = load_playable_cards()
    card_list = get_card_list()
    card_types = get_card_types()
    return df, card_list, card_types

df, card_list, card_types = load_data()

# ── Sidebar — filters ─────────────────────────────────────────────────────────
st.sidebar.title("⚔️ Deck Builder")
st.sidebar.markdown("---")

# Filter card list by type
type_filter = st.sidebar.multiselect(
    "Filter by Type",
    options=sorted(df["Type"].unique().tolist()),
    default=sorted(df["Type"].unique().tolist())
)

filtered_cards = [
    c for c in card_list
    if card_types.get(c, "Troop") in type_filter
    and c not in SUB_UNITS
]

st.sidebar.markdown("---")
st.sidebar.markdown("### Your Card Levels")
default_level = st.sidebar.slider("Default Level", 1, 18, 11)

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("⚔️ Clash Royale Deck Builder")
st.caption("Build and analyze your deck using real per-level card stats.")

tab1, tab2, tab3 = st.tabs(["🃏 Build Deck", "📊 Card Stats", "🔍 Card Compare"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — DECK BUILDER
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Select 8 Cards")

    col_left, col_right = st.columns([2, 1])

    with col_left:
        # 8 card slots in a 4x2 grid
        selected_cards = []
        card_levels = {}
        slot_cols = st.columns(4)

        for i in range(8):
            with slot_cols[i % 4]:
                card = st.selectbox(
                    f"Slot {i+1}",
                    options=["— empty —"] + filtered_cards,
                    key=f"card_slot_{i}"
                )
                if card != "— empty —":
                    level = st.number_input(
                        "Level",
                        min_value=1, max_value=18,
                        value=default_level,
                        key=f"level_slot_{i}"
                    )
                    selected_cards.append(card)
                    card_levels[card] = int(level)

    with col_right:
        st.subheader("Deck Summary")
        filled = len(selected_cards)
        unique = len(set(selected_cards))

        if filled == 0:
            st.info("Add cards to your deck to see the analysis.")
        else:
            if unique < filled:
                st.error(f"⚠️ Duplicate cards detected! ({filled - unique} duplicate(s))")

            analysis = analyze_deck(list(set(selected_cards)), card_levels)

            st.metric("Cards", f"{filled}/8")
            st.metric("Avg Elixir", f"{analysis.get('avg_elixir', '—')}")
            st.metric("Cycle Cost (4 cheapest)", f"{analysis.get('cycle_cost', '—')} elixir")
            st.metric("Combined HP", f"{analysis.get('total_hp', 0):,}")
            st.metric("Combined DPS", f"{analysis.get('total_dps', 0):,}")

            # Roles covered
            roles = analysis.get("roles_covered", [])
            if roles:
                st.markdown("**Roles Covered:**")
                role_display = {
                    "tank": "🐘 Tank", "mini_tank": "🛡️ Mini Tank",
                    "win_condition": "🏆 Win Condition", "spell": "✨ Spell",
                    "air_defense": "✈️ Air Defense", "cycle": "🔄 Cycle",
                    "spawner": "🏚️ Spawner"
                }
                for r in roles:
                    st.markdown(f"- {role_display.get(r, r)}")

            # Warnings
            warnings = analysis.get("warnings", [])
            if warnings:
                st.markdown("**Warnings:**")
                for w in warnings:
                    st.warning(w)

    # Elixir cost bar chart
    if selected_cards:
        st.markdown("---")
        st.subheader("Elixir Costs")
        elixir_data = {
            c: ELIXIR_COSTS.get(c, 0)
            for c in set(selected_cards)
            if ELIXIR_COSTS.get(c, 0) > 0
        }
        if elixir_data:
            fig = px.bar(
                x=list(elixir_data.keys()),
                y=list(elixir_data.values()),
                labels={"x": "Card", "y": "Elixir Cost"},
                color=list(elixir_data.values()),
                color_continuous_scale="RdYlGn_r",
                title="Elixir Cost per Card"
            )
            fig.update_layout(showlegend=False, coloraxis_showscale=False, height=300)
            st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — CARD STATS
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("Card Statistics Viewer")

    col1, col2 = st.columns([1, 2])

    with col1:
        selected_card = st.selectbox("Select Card", filtered_cards)
        stat_to_plot = st.selectbox(
            "Stat to Plot",
            ["Hitpoints", "Damage", "DPS", "Crown Tower Damage",
             "Charge Damage", "Death Damage", "Shield Hitpoints"]
        )

    card_df = df[df["Unit"] == selected_card].sort_values("Level")

    with col2:
        if not card_df.empty and stat_to_plot in card_df.columns:
            plot_df = card_df[["Level", stat_to_plot]].dropna()
            if not plot_df.empty:
                fig = px.line(
                    plot_df, x="Level", y=stat_to_plot,
                    markers=True,
                    title=f"{selected_card} — {stat_to_plot} by Level",
                    color_discrete_sequence=["#E07B00"]
                )
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"No {stat_to_plot} data for {selected_card}.")

    # Show full stats table
    if not card_df.empty:
        display_cols = [c for c in card_df.columns if card_df[c].notna().any()]
        display_cols = [c for c in display_cols if c not in ("Unit",)]
        st.dataframe(
            card_df[display_cols].set_index("Level").dropna(axis=1, how="all"),
            use_container_width=True
        )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — CARD COMPARE
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("Compare Two Cards")

    col1, col2 = st.columns(2)
    with col1:
        card_a = st.selectbox("Card A", filtered_cards, key="compare_a")
        level_a = st.slider("Level A", 1, 18, 11, key="level_a")
    with col2:
        card_b = st.selectbox("Card B", filtered_cards, index=1, key="compare_b")
        level_b = st.slider("Level B", 1, 18, 11, key="level_b")

    row_a = get_card_at_level(card_a, level_a)
    row_b = get_card_at_level(card_b, level_b)

    compare_stats = ["Hitpoints", "Damage", "DPS", "Crown Tower Damage",
                     "Death Damage", "Charge Damage", "Shield Hitpoints"]

    if row_a is not None and row_b is not None:
        compare_data = []
        for stat in compare_stats:
            val_a = row_a.get(stat) if row_a is not None else None
            val_b = row_b.get(stat) if row_b is not None else None
            if pd.notna(val_a) or pd.notna(val_b):
                compare_data.append({
                    "Stat": stat,
                    card_a: val_a if pd.notna(val_a) else 0,
                    card_b: val_b if pd.notna(val_b) else 0,
                })

        if compare_data:
            compare_df = pd.DataFrame(compare_data)

            fig = go.Figure()
            fig.add_trace(go.Bar(
                name=f"{card_a} (Lvl {level_a})",
                x=compare_df["Stat"],
                y=compare_df[card_a],
                marker_color="#E07B00"
            ))
            fig.add_trace(go.Bar(
                name=f"{card_b} (Lvl {level_b})",
                x=compare_df["Stat"],
                y=compare_df[card_b],
                marker_color="#0077CC"
            ))
            fig.update_layout(
                barmode="group",
                title=f"{card_a} vs {card_b}",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

            # Numeric comparison table
            compare_df["Winner"] = compare_df.apply(
                lambda row: card_a if row[card_a] > row[card_b]
                else (card_b if row[card_b] > row[card_a] else "Tie"),
                axis=1
            )
            st.dataframe(compare_df.set_index("Stat"), use_container_width=True)
