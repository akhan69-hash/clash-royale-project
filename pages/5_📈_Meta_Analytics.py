import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_card_reference, get_card_types

st.set_page_config(page_title="Meta Analytics", page_icon="📈", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"


@st.cache_data
def load_card_stats():
    path = DATA_DIR / "card_stats.csv"
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def load_archetypes():
    path = DATA_DIR / "deck_archetypes.csv"
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def load_meta():
    path = DATA_DIR / "analytics_meta.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_reference():
    return load_card_reference()


card_stats = load_card_stats()
archetypes = load_archetypes()
meta = load_meta()
reference = load_reference()
card_types = get_card_types()

st.title("📈 Meta Analytics")
st.caption("Real win rates and deck archetypes derived from actual match data.")

if meta:
    st.info(
        f"📊 Based on {meta['total_matches_sampled']:,} matches from "
        f"{meta['date_range_start'][:10]} to {meta['date_range_end'][:10]} "
        f"(source: {meta['source']}). Cards released after this date have no data here yet."
    )
else:
    st.error(
        "No analytics data found. Run `scripts/fetch_match_sample.py` then "
        "`scripts/build_analytics_data.py` to generate it."
    )
    st.stop()

st.markdown("---")

tab1, tab2 = st.tabs(["🏆 Win Rates", "🗂️ Deck Archetypes"])

# ── Tab 1: Win Rates ────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Card Usage & Win Rates")

    merged = card_stats.merge(
        reference[["card_name", "rarity", "is_champion", "has_evolution"]],
        on="card_name", how="left"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        rarity_options = sorted(merged["rarity"].dropna().unique().tolist())
        rarity_filter = st.multiselect("Rarity", rarity_options, default=rarity_options)
    with col2:
        min_presence = st.slider("Min presence rate (%)", 0.0, 5.0, 0.1, step=0.05)
    with col3:
        sort_by = st.selectbox("Sort by", ["win_rate", "times_used", "presence_rate"], index=0)

    filtered = merged[
        merged["rarity"].isin(rarity_filter)
        & (merged["presence_rate"] * 100 >= min_presence)
    ].sort_values(sort_by, ascending=False)

    if filtered.empty:
        st.info("No cards match these filters. Try lowering the minimum presence rate.")
    else:
        fig = px.bar(
            filtered.head(30),
            x="card_name", y="win_rate",
            color="win_rate",
            color_continuous_scale="RdYlGn",
            range_color=[0.4, 0.6],
            hover_data=["times_used", "presence_rate", "rarity"],
            title="Win Rate by Card (top 30 shown, filtered)",
            labels={"card_name": "Card", "win_rate": "Win Rate"}
        )
        fig.update_layout(height=450, showlegend=False, coloraxis_showscale=True)
        fig.add_hline(y=0.5, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)

        display_df = filtered[["card_name", "rarity", "times_used", "win_rate", "presence_rate", "elixir"]].copy()
        display_df["win_rate"] = (display_df["win_rate"] * 100).round(2)
        display_df["presence_rate"] = (display_df["presence_rate"] * 100).round(3)
        display_df.columns = ["Card", "Rarity", "Times Used", "Win Rate (%)", "Presence Rate (%)", "Elixir"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    no_data_cards = reference[~reference["card_name"].isin(card_stats["card_name"])]
    if not no_data_cards.empty:
        with st.expander(f"⏳ {len(no_data_cards)} cards with no match data yet"):
            st.caption(
                "These cards were added after the match data sample, or are evolutions "
                "(this dataset can't distinguish evolution usage from base-card usage) -- "
                "stats-only until newer match data is collected."
            )
            st.dataframe(
                no_data_cards[["card_name", "rarity", "has_evolution", "notes"]],
                use_container_width=True, hide_index=True
            )

# ── Tab 2: Deck Archetypes ───────────────────────────────────────────────────────
with tab2:
    st.subheader("Deck Archetypes (K-Means Clusters)")

    if archetypes is None or archetypes.empty:
        st.info("No archetype data found. Run the analytics pipeline to generate it.")
    else:
        st.caption(
            f"{len(archetypes)} archetypes found by clustering the most frequently "
            "played decks in the sample by card composition."
        )

        fig = px.scatter(
            archetypes,
            x="avg_elixir", y="win_rate",
            size="total_frequency",
            color="win_rate",
            color_continuous_scale="RdYlGn",
            range_color=[0.4, 0.6],
            hover_data=["cluster", "deck_count", "representative_cards"],
            title="Archetype Win Rate vs Average Elixir (bubble size = frequency)",
            labels={"avg_elixir": "Average Elixir", "win_rate": "Win Rate"}
        )
        fig.add_hline(y=0.5, line_dash="dash", line_color="gray")
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        for _, row in archetypes.sort_values("total_frequency", ascending=False).iterrows():
            rep_cards = row["representative_cards"].split(";")
            example = row["example_deck"].split(";")
            with st.expander(
                f"Archetype {row['cluster']} — {rep_cards[0]} / {rep_cards[1]} "
                f"(win rate {row['win_rate']*100:.1f}%, {row['deck_count']} unique decks)"
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("Win Rate", f"{row['win_rate']*100:.1f}%")
                c2.metric("Avg Elixir", row["avg_elixir"])
                c3.metric("Sample Size", f"{row['total_frequency']:,}")
                st.markdown("**Representative cards:** " + ", ".join(rep_cards))
                st.markdown("**Example deck:** " + ", ".join(example))
