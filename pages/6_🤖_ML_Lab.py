import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_card_reference, get_card_list, get_card_at_level, get_card_types, SUB_UNITS

st.set_page_config(page_title="ML Lab", page_icon="🤖", layout="wide")

DATA_DIR = Path(__file__).parent.parent / "data"
MODELS_DIR = DATA_DIR / "models"


@st.cache_resource
def load_win_predictor():
    path = MODELS_DIR / "win_predictor.joblib"
    if not path.exists():
        return None
    import joblib
    return joblib.load(path)


@st.cache_data
def load_win_predictor_meta():
    path = MODELS_DIR / "win_predictor_meta.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_card_stats():
    path = DATA_DIR / "card_stats.csv"
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def load_elo_metrics():
    path = MODELS_DIR / "elo_eval_metrics.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_elo_sample():
    path = MODELS_DIR / "elo_sample.csv"
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def load_reference():
    return load_card_reference()


card_list = [c for c in get_card_list() if c not in SUB_UNITS]
card_types = get_card_types()
reference = load_reference()

st.title("🤖 ML Lab")
st.caption("Win prediction, card value, and Elo rating — trained on the same 2023 match sample as Meta Analytics.")

tab1, tab2, tab3 = st.tabs(["🔮 Win Predictor", "💎 Card Value", "📊 Elo Ratings"])

# ── Tab 1: Win Predictor ─────────────────────────────────────────────────────────
with tab1:
    model = load_win_predictor()
    meta = load_win_predictor_meta()

    if model is None or meta is None:
        st.error("No trained model found. Run `scripts/train_win_predictor.py` to generate one.")
    else:
        st.info(
            f"📊 Model accuracy: **{meta['accuracy']*100:.1f}%** (AUC {meta['auc']:.3f}) on "
            f"{meta['n_test']:,} held-out matches from {meta['test_days'][0][:4]}-{meta['test_days'][0][4:6]}-{meta['test_days'][0][6:]} "
            f"to {meta['test_days'][1][:4]}-{meta['test_days'][1][4:6]}-{meta['test_days'][1][6:]}, trained on "
            f"{meta['n_train']:,} earlier matches. Baseline (coin flip) is 50% — ladder matchmaking is "
            f"designed to produce close games, so deck composition alone only explains part of who wins."
        )

        card_order = meta["card_order"]
        st.subheader("Pick Two Decks")
        col1, col2 = st.columns(2)
        deck_a, deck_b = [], []
        with col1:
            st.markdown("**Deck A**")
            for i in range(8):
                c = st.selectbox(f"A — Card {i+1}", ["— empty —"] + card_list, key=f"ml_a_{i}")
                if c != "— empty —":
                    deck_a.append(c)
        with col2:
            st.markdown("**Deck B**")
            for i in range(8):
                c = st.selectbox(f"B — Card {i+1}", ["— empty —"] + card_list, key=f"ml_b_{i}")
                if c != "— empty —":
                    deck_b.append(c)

        if len(deck_a) == 8 and len(deck_b) == 8:
            unknown_a = [c for c in deck_a if c not in card_order]
            unknown_b = [c for c in deck_b if c not in card_order]
            if unknown_a or unknown_b:
                st.warning(
                    f"These cards have no match data so can't be scored by the model "
                    f"(treated as neutral): {', '.join(sorted(set(unknown_a + unknown_b)))}"
                )

            card_index = {c: i for i, c in enumerate(card_order)}
            x = np.zeros(len(card_order), dtype=np.int8)
            for c in deck_a:
                if c in card_index:
                    x[card_index[c]] += 1
            for c in deck_b:
                if c in card_index:
                    x[card_index[c]] -= 1

            proba_a = model.predict_proba(x.reshape(1, -1))[0, 1]

            st.markdown("---")
            m1, m2 = st.columns(2)
            m1.metric("Deck A Win Probability", f"{proba_a*100:.1f}%")
            m2.metric("Deck B Win Probability", f"{(1-proba_a)*100:.1f}%")

            fig = go.Figure(go.Bar(
                x=[proba_a, 1 - proba_a], y=["Deck A", "Deck B"],
                orientation="h", marker_color=["#4A90D9", "#E07B00"],
            ))
            fig.update_layout(height=200, xaxis=dict(range=[0, 1], title="Win Probability"), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            importances = dict(zip(card_order, model.feature_importances_))
            present = [(c, importances.get(c, 0)) for c in set(deck_a + deck_b) if c in importances]
            present.sort(key=lambda x: -x[1])
            if present:
                st.markdown("**Most influential cards in this matchup** (by overall model importance):")
                imp_df = pd.DataFrame(present[:8], columns=["Card", "Model Importance"])
                imp_df["Side"] = imp_df["Card"].apply(lambda c: "Deck A" if c in deck_a else "Deck B")
                st.dataframe(imp_df, use_container_width=True, hide_index=True)
        else:
            st.info("Fill both 8-card decks to get a prediction.")

# ── Tab 2: Card Value ─────────────────────────────────────────────────────────────
with tab2:
    st.subheader("Elixir Value: Stat Efficiency vs Real Win Rate")
    card_stats = load_card_stats()

    if card_stats is None:
        st.error("No card_stats.csv found. Run the Analytics pipeline first.")
    else:
        ref_level = st.slider("Reference level for stat efficiency", 1, 18, 11)

        rows = []
        for _, row in reference.iterrows():
            card = row["card_name"]
            level_row = get_card_at_level(card, ref_level)
            if level_row is None or pd.isna(row["elixir"]) or row["elixir"] == 0:
                continue
            hp = level_row.get("Hitpoints")
            dps = level_row.get("DPS")
            if pd.isna(hp) and pd.isna(dps):
                continue
            hp = hp if pd.notna(hp) else 0
            dps = dps if pd.notna(dps) else 0
            efficiency = (hp + dps * 4) / row["elixir"]
            rows.append({"card_name": card, "elixir": row["elixir"], "rarity": row["rarity"], "efficiency": round(efficiency, 1)})

        value_df = pd.DataFrame(rows).merge(
            card_stats[["card_name", "win_rate", "times_used"]], on="card_name", how="left"
        )

        col1, col2 = st.columns(2)
        with col1:
            elixir_filter = st.multiselect(
                "Elixir cost", sorted(value_df["elixir"].unique().tolist()),
                default=sorted(value_df["elixir"].unique().tolist())
            )
        with col2:
            rarity_filter = st.multiselect(
                "Rarity", sorted(value_df["rarity"].dropna().unique().tolist()),
                default=sorted(value_df["rarity"].dropna().unique().tolist())
            )

        filtered = value_df[value_df["elixir"].isin(elixir_filter) & value_df["rarity"].isin(rarity_filter)]

        st.caption(
            f"Efficiency = (Hitpoints + DPS×4) / Elixir at level {ref_level} — a rough 'stat output per elixir' "
            "measure. Win Rate (where available) is the real, match-derived signal from Meta Analytics. "
            "These are two independent signals, not blended into one score — a card can be stat-efficient but "
            "still underperform (or vice versa) once real players use it."
        )

        fig = px.scatter(
            filtered, x="efficiency", y="win_rate",
            color="rarity", size="elixir",
            hover_data=["card_name", "elixir", "times_used"],
            labels={"efficiency": "Stat Efficiency (per elixir)", "win_rate": "Real Win Rate"},
            title="Stat Efficiency vs Real Win Rate"
        )
        if filtered["win_rate"].notna().any():
            fig.add_hline(y=0.5, line_dash="dash", line_color="gray")
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        display_df = filtered.sort_values("efficiency", ascending=False)[
            ["card_name", "elixir", "rarity", "efficiency", "win_rate", "times_used"]
        ].copy()
        display_df["win_rate"] = (display_df["win_rate"] * 100).round(2)
        display_df.columns = ["Card", "Elixir", "Rarity", "Efficiency", "Win Rate (%)", "Times Used"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── Tab 3: Elo Ratings ─────────────────────────────────────────────────────────────
with tab3:
    st.subheader("Elo Rating System")
    elo_metrics = load_elo_metrics()
    elo_sample = load_elo_sample()

    if elo_metrics is None or elo_sample is None:
        st.error("No Elo data found. Run `scripts/build_elo_ratings.py` first.")
    else:
        m1, m2 = st.columns(2)
        m1.metric("Elo Predictive Accuracy", f"{elo_metrics['elo_accuracy']*100:.1f}%")
        m2.metric("Baseline (coin flip)", f"{elo_metrics['baseline_accuracy']*100:.0f}%")

        st.caption(
            f"Evaluated on {elo_metrics['n_eval_matches']:,} held-out matches from "
            f"{', '.join(elo_metrics['test_days'])}. Elo computed from scratch over the full 30-day "
            f"sample (K={elo_metrics['k_factor']}, starting at {elo_metrics['initial_elo']}), processed "
            f"in match order — it only reflects in-sample performance during this window, not each "
            f"player's real lifetime skill. In the same range as the deck-only Win Predictor's accuracy, "
            f"which makes sense: both are picking up a real but partial signal on a ladder designed for "
            f"close matches."
        )

        st.warning(
            "⚠️ **The original plan compared Elo against raw trophies — dropped, and here's why:** "
            + elo_metrics.get("trophy_comparison_dropped_reason", "")
        )

        st.markdown("---")
        st.subheader(f"Sample: {elo_metrics['n_players_sampled']:,} players with 20+ matches in the window")
        st.caption(
            "Trophies shown below are the last **post-match** value observed for each player in this "
            "sample (see warning above) — a descriptive look at how Elo relates to it, not a claim "
            "that either one predicts the other."
        )
        fig = px.scatter(
            elo_sample, x="last_observed_trophies", y="final_elo",
            size="matches_played", opacity=0.5,
            labels={"last_observed_trophies": "Last Observed (Post-Match) Trophies", "final_elo": "Elo Rating"},
            title="Elo Rating vs Last Observed Trophies (sample players)"
        )
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            elo_sample.sort_values("matches_played", ascending=False).head(50),
            use_container_width=True, hide_index=True
        )
