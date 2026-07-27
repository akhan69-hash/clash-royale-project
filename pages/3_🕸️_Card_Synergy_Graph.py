import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_playable_cards, get_card_list, get_card_types, SUB_UNITS
from utils.deck_analysis import ELIXIR_COSTS, CARD_ROLES

st.set_page_config(page_title="Card Synergy Graph", page_icon="🕸️", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"
MIN_CO_OCCURRENCE = 20  # ignore real pairs seen fewer times than this (too noisy)


@st.cache_data
def load_data():
    df = load_playable_cards()
    card_list = get_card_list()
    card_types = get_card_types()
    return df, card_list, card_types


@st.cache_data
def load_real_synergy():
    """Real co-occurrence/win-rate data from scripts/build_analytics_data.py, if it's
    been run. Returns None if not -- callers fall back to the rule-based SYNERGY_PAIRS."""
    path = DATA_DIR / "card_synergy.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    lookup = {}
    for _, row in df.iterrows():
        key = tuple(sorted((row["card_a"], row["card_b"])))
        lookup[key] = {
            "co_occurrence": int(row["co_occurrence"]),
            "win_rate_together": row["win_rate_together"],
        }
    return lookup


@st.cache_data
def load_analytics_meta():
    path = DATA_DIR / "analytics_meta.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


df, card_list, card_types = load_data()
REAL_SYNERGY = load_real_synergy()
ANALYTICS_META = load_analytics_meta()

st.title("🕸️ Card Synergy Graph")
st.caption("Explore which cards work best together based on real match co-occurrence where available, falling back to curated role-based pairs otherwise.")

if REAL_SYNERGY is not None and ANALYTICS_META:
    st.info(
        f"📊 Synergy scores marked **Data** are computed from "
        f"{ANALYTICS_META['total_matches_sampled']:,} real matches "
        f"({ANALYTICS_META['date_range_start'][:10]} to {ANALYTICS_META['date_range_end'][:10]}). "
        f"Pairs marked **Rule** (including any card without match data, e.g. evolutions or "
        f"cards added since this sample) use the curated fallback list instead."
    )
else:
    st.warning(
        "⚠️ No real match data found yet -- showing curated rule-based synergy pairs only. "
        "Run `scripts/fetch_match_sample.py` then `scripts/build_analytics_data.py` to unlock real data."
    )

st.markdown("---")

# ── Synergy Matrix (rule-based until match data is loaded) ───────────────────

# Explicit synergy pairs (score 1-10)
SYNERGY_PAIRS = {
    ("Giant", "Musketeer"): 9,
    ("Giant", "Witch"): 8,
    ("Giant", "Wizard"): 8,
    ("Giant", "Electro Wizard"): 7,
    ("Giant", "Mega Minion"): 7,
    ("Golem", "Night Witch"): 10,
    ("Golem", "Baby Dragon"): 9,
    ("Golem", "Lumberjack"): 9,
    ("Golem", "Electro Wizard"): 8,
    ("Hog Rider", "Zap"): 10,
    ("Hog Rider", "The Log"): 9,
    ("Hog Rider", "Ice Golem"): 8,
    ("Hog Rider", "Musketeer"): 7,
    ("Balloon", "Lumberjack"): 10,
    ("Balloon", "Freeze"): 9,
    ("Balloon", "Inferno Dragon"): 8,
    ("Balloon", "Bat"): 7,
    ("X-Bow", "Tesla"): 9,
    ("X-Bow", "Ice Spirit"): 8,
    ("X-Bow", "The Log"): 8,
    ("X-Bow", "Archers"): 7,
    ("Mortar", "Giant Snowball"): 8,
    ("Mortar", "Goblin"): 7,
    ("Lava Hound", "Balloon"): 10,
    ("Lava Hound", "Inferno Dragon"): 9,
    ("Lava Hound", "Bat"): 8,
    ("Miner", "Goblin Barrel"): 9,
    ("Miner", "Poison"): 8,
    ("Miner", "Princess"): 7,
    ("Goblin Barrel", "Princess"): 9,
    ("Goblin Barrel", "Dart Goblin"): 7,
    ("Goblin Barrel", "Zap"): 8,
    ("Graveyard", "Freeze"): 10,
    ("Graveyard", "Poison"): 9,
    ("Graveyard", "Ice Golem"): 8,
    ("P.E.K.K.A", "Battle Ram"): 9,
    ("P.E.K.K.A", "Electro Wizard"): 8,
    ("Sparky", "Goblin Gang"): 8,
    ("Sparky", "Ice Spirit"): 8,
    ("Sparky", "Zap"): 7,
    ("Three Musketeers", "Elixir Collector"): 10,
    ("Three Musketeers", "Battle Ram"): 8,
    ("Battle Ram", "Zap"): 8,
    ("Battle Ram", "Goblin Gang"): 7,
    ("Mega Knight", "Goblin Barrel"): 9,
    ("Mega Knight", "Skeleton"): 8,
    ("Mega Knight", "Zap"): 7,
    ("Electro Giant", "Zap"): 9,
    ("Electro Giant", "Electro Spirit"): 8,
    ("Royal Giant", "Furnace"): 8,
    ("Royal Giant", "Musketeer"): 7,
    ("Knight", "Fireball"): 7,
    ("Knight", "Musketeer"): 8,
    ("Valkyrie", "Hog Rider"): 8,
    ("Valkyrie", "Miner"): 7,
    ("Ice Wizard", "Tornado"): 10,
    ("Ice Wizard", "Graveyard"): 9,
    ("Bowler", "Graveyard"): 9,
    ("Bowler", "Goblin Barrel"): 7,
    ("Night Witch", "Golem"): 10,
    ("Night Witch", "Giant"): 8,
    ("Witch", "Giant"): 8,
    ("Witch", "Golem"): 7,
    ("Executioner", "Tornado"): 10,
    ("Executioner", "Goblin Barrel"): 7,
    ("Lumberjack", "Balloon"): 10,
    ("Lumberjack", "Golem"): 8,
    ("Fisherman", "Inferno Tower"): 8,
    ("Fisherman", "Inferno Dragon"): 7,
    ("Ram Rider", "Zap"): 8,
    ("Ram Rider", "Goblin Barrel"): 7,
    ("Golden Knight", "Goblin Barrel"): 8,
    ("Skeleton King", "Skeleton"): 8,
    ("Archer Queen", "Giant"): 8,
    ("Monk", "Giant"): 7,
}

def _real_synergy_entry(card_a: str, card_b: str):
    """Real (co_occurrence, win_rate_together) for a pair if data exists and passes
    the minimum sample size, else None."""
    if REAL_SYNERGY is None:
        return None
    entry = REAL_SYNERGY.get(tuple(sorted((card_a, card_b))))
    if entry and entry["co_occurrence"] >= MIN_CO_OCCURRENCE:
        return entry
    return None


def get_synergy_score(card_a: str, card_b: str) -> float:
    """Get synergy score between two cards: real win-rate-together (scaled to 0-10)
    when we have enough match data for the pair, else the curated rule-based score."""
    real = _real_synergy_entry(card_a, card_b)
    if real:
        return round(real["win_rate_together"] * 10, 1)
    pair1 = (card_a, card_b)
    pair2 = (card_b, card_a)
    return SYNERGY_PAIRS.get(pair1, SYNERGY_PAIRS.get(pair2, 0))


def get_synergy_source(card_a: str, card_b: str) -> str:
    return "Data" if _real_synergy_entry(card_a, card_b) else "Rule"


def get_top_synergies(card: str, top_n: int = 10) -> pd.DataFrame:
    """Get top synergy partners for a given card."""
    results = []
    for other_card in card_list:
        if other_card == card:
            continue
        score = get_synergy_score(card, other_card)
        if score > 0:
            real = _real_synergy_entry(card, other_card)
            results.append({
                "Partner Card": other_card,
                "Synergy Score": score,
                "Source": "Data" if real else "Rule",
                "Co-occurrences": real["co_occurrence"] if real else None,
                "Type": card_types.get(other_card, "Troop"),
                "Elixir": ELIXIR_COSTS.get(other_card, "?")
            })
    return pd.DataFrame(sorted(results, key=lambda x: -x["Synergy Score"])[:top_n])

def build_synergy_network(selected_cards: list[str]) -> go.Figure:
    """Build a network graph of synergies between selected cards."""
    if len(selected_cards) < 2:
        return None

    # Nodes
    n = len(selected_cards)
    angles = [2 * np.pi * i / n for i in range(n)]
    x_pos = {card: np.cos(a) for card, a in zip(selected_cards, angles)}
    y_pos = {card: np.sin(a) for card, a in zip(selected_cards, angles)}

    edge_traces = []
    max_score = 10

    for i, card_a in enumerate(selected_cards):
        for card_b in selected_cards[i+1:]:
            score = get_synergy_score(card_a, card_b)
            if score > 0:
                width = 1 + (score / max_score) * 5
                opacity = 0.3 + (score / max_score) * 0.7
                edge_traces.append(go.Scatter(
                    x=[x_pos[card_a], x_pos[card_b], None],
                    y=[y_pos[card_a], y_pos[card_b], None],
                    mode="lines",
                    line=dict(width=width, color=f"rgba(255,165,0,{opacity:.2f})"),
                    hoverinfo="skip",
                    showlegend=False
                ))

    # Node colors by type
    type_colors = {
        "Troop": "#4A90D9", "Spell": "#E07B00",
        "Building": "#7B68EE", "Champion": "#FFD700",
        "Tower Troop": "#90EE90"
    }
    node_colors = [type_colors.get(card_types.get(c, "Troop"), "#888") for c in selected_cards]

    # Synergy score per node (sum of all connected edges)
    node_scores = []
    for card in selected_cards:
        total = sum(get_synergy_score(card, other) for other in selected_cards if other != card)
        node_scores.append(total)

    node_trace = go.Scatter(
        x=[x_pos[c] for c in selected_cards],
        y=[y_pos[c] for c in selected_cards],
        mode="markers+text",
        marker=dict(
            size=[20 + s * 2 for s in node_scores],
            color=node_colors,
            line=dict(width=2, color="white")
        ),
        text=selected_cards,
        textposition="top center",
        hovertext=[
            f"{c}<br>Type: {card_types.get(c,'Troop')}<br>Total Synergy: {s}"
            for c, s in zip(selected_cards, node_scores)
        ],
        hoverinfo="text",
        showlegend=False
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        title="Deck Synergy Network",
        showlegend=False,
        hovermode="closest",
        height=500,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig


# ── UI ────────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["🔍 Card Synergy Lookup", "🕸️ Deck Synergy Network"])

# ── Tab 1: Single card synergy lookup ─────────────────────────────────────────
with tab1:
    st.subheader("Find Best Partners for a Card")

    selected_card = st.selectbox("Select a Card", card_list)
    top_n = st.slider("Show top N partners", 5, 20, 10)

    synergy_df = get_top_synergies(selected_card, top_n)

    if not synergy_df.empty:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.dataframe(synergy_df, use_container_width=True, hide_index=True)

        with col2:
            fig = px.bar(
                synergy_df,
                x="Partner Card", y="Synergy Score",
                color="Synergy Score",
                color_continuous_scale="Oranges",
                hover_data=["Type", "Elixir", "Source", "Co-occurrences"],
                title=f"Top Synergy Partners for {selected_card}"
            )
            fig.update_layout(height=400, showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No explicit synergy data for {selected_card} yet. This will improve when match data is integrated.")

# ── Tab 2: Deck network ────────────────────────────────────────────────────────
with tab2:
    st.subheader("Visualize Synergies in Your Deck")
    st.caption("Select up to 8 cards to see how they connect.")

    net_cols = st.columns(4)
    net_cards = []
    for i in range(8):
        with net_cols[i % 4]:
            card = st.selectbox(
                f"Card {i+1}",
                options=["— empty —"] + card_list,
                key=f"net_card_{i}"
            )
            if card != "— empty —":
                net_cards.append(card)

    if len(net_cards) >= 2:
        fig = build_synergy_network(net_cards)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

        # Synergy matrix
        st.subheader("Synergy Matrix")
        matrix_data = pd.DataFrame(
            index=net_cards, columns=net_cards, dtype=float
        )
        for ca in net_cards:
            for cb in net_cards:
                matrix_data.loc[ca, cb] = get_synergy_score(ca, cb) if ca != cb else 0

        fig2 = px.imshow(
            matrix_data.astype(float),
            color_continuous_scale="Oranges",
            title="Card-to-Card Synergy Scores",
            labels=dict(color="Synergy")
        )
        fig2.update_layout(height=450)
        st.plotly_chart(fig2, use_container_width=True)

        # Total synergy score for each card in the deck
        totals = {card: int(matrix_data.loc[card].sum()) for card in net_cards}
        st.subheader("Most Synergistic Cards in This Deck")
        total_df = pd.DataFrame(
            sorted(totals.items(), key=lambda x: -x[1]),
            columns=["Card", "Total Synergy Score"]
        )
        st.dataframe(total_df, use_container_width=True, hide_index=True)
    else:
        st.info("Select at least 2 cards to see the synergy network.")
