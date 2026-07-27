"""
Trains an XGBoost classifier to predict the winner of a match from the two
decks alone (no player skill/trophy info) -- the "Win Prediction" ML/AI
roadmap item.

Data: data/raw_matches/*.csv (same 30-day sample used for the Analytics
phase; see scripts/fetch_match_sample.py / build_analytics_data.py).

Method:
- Each match becomes one training row: a signed difference vector over the
  known cards (+1 = p1 has it and p2 doesn't, -1 = reverse, 0 = both/neither),
  label = did p1 win. This is half the width of concatenating two one-hot
  vectors and is symmetric by construction (swap p1/p2 -> vector negates,
  label flips), so the model can't pick up a spurious "team 1 always wins"
  signal.
- Time-based train/test split (first 25 days train, last 5 days test) rather
  than a random split -- a random split would let the exact same deck-vs-deck
  matchup appear in both train and test (common at this data volume), which
  inflates accuracy in a way that wouldn't hold up on genuinely new matches.
- Matches where any of the 16 card slots doesn't map through
  data/card_reference.csv's match_id column are dropped (same simplification
  as the Analytics phase pipeline).

Realistic expectation: Clash Royale ladder matchmaking targets close-to-50/50
outcomes, so accuracy in the 52-60% range is a legitimate result here, not a
sign of a broken pipeline -- deck composition alone only explains part of
who wins.

Usage: python scripts/train_win_predictor.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import joblib
import numpy as np
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.data_loader import get_card_match_id_map

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw_matches"
MODELS_DIR = ROOT / "data" / "models"
OUT_MODEL = MODELS_DIR / "win_predictor.joblib"
OUT_META = MODELS_DIR / "win_predictor_meta.json"

KEPT_GAMEMODES = (72000323, 72000006)  # same as build_analytics_data.py: Ranked1v1, Ladder

TEST_DAYS = {"20231102", "20231103", "20231104", "20231105", "20231106"}

RAW_COLUMNS = [
    "datetime", "gamemode",
    "p1_tag", "p1_trophies", "p1_crowns",
    *[f"p1_c{i}" for i in range(1, 9)],
    "p2_tag", "p2_trophies", "p2_crowns",
    *[f"p2_c{i}" for i in range(1, 9)],
]


def main():
    name_to_id, id_to_name = get_card_match_id_map()
    card_names = sorted(name_to_id.keys())
    card_index = {name_to_id[name]: i for i, name in enumerate(card_names)}
    n_cards = len(card_names)
    print(f"{n_cards} known cards -> {n_cards}-dim feature vector")

    min_id, max_id = min(id_to_name), max(id_to_name)
    id_lookup = np.full(max_id - min_id + 1, -1, dtype=np.int32)
    for cid, idx in card_index.items():
        id_lookup[cid - min_id] = idx

    con = duckdb.connect()
    raw = con.read_csv(str(RAW_DIR / "*.csv"), header=False, names=RAW_COLUMNS, ignore_errors=True)
    con.register("raw", raw)

    known_ids = "(" + ",".join(str(i) for i in id_to_name) + ")"
    gamemode_list = ",".join(str(g) for g in KEPT_GAMEMODES)

    print("Querying matches (this scans all 30 raw files)...")
    df = con.execute(f"""
        SELECT
            substr(datetime, 1, 8) AS day,
            p1_c1, p1_c2, p1_c3, p1_c4, p1_c5, p1_c6, p1_c7, p1_c8,
            p2_c1, p2_c2, p2_c3, p2_c4, p2_c5, p2_c6, p2_c7, p2_c8,
            CASE WHEN p1_crowns > p2_crowns THEN 1 ELSE 0 END AS p1_won
        FROM raw
        WHERE gamemode IN ({gamemode_list}) AND p1_crowns <> p2_crowns
          AND p1_c1 IN {known_ids} AND p1_c2 IN {known_ids} AND p1_c3 IN {known_ids} AND p1_c4 IN {known_ids}
          AND p1_c5 IN {known_ids} AND p1_c6 IN {known_ids} AND p1_c7 IN {known_ids} AND p1_c8 IN {known_ids}
          AND p2_c1 IN {known_ids} AND p2_c2 IN {known_ids} AND p2_c3 IN {known_ids} AND p2_c4 IN {known_ids}
          AND p2_c5 IN {known_ids} AND p2_c6 IN {known_ids} AND p2_c7 IN {known_ids} AND p2_c8 IN {known_ids}
    """).fetchdf()
    print(f"{len(df):,} matches with fully-known decks on both sides")

    p1_cols = [f"p1_c{i}" for i in range(1, 9)]
    p2_cols = [f"p2_c{i}" for i in range(1, 9)]

    def build_matrix(sub_df):
        n = len(sub_df)
        X = np.zeros((n, n_cards), dtype=np.int8)
        rows = np.repeat(np.arange(n), 8)

        p1_ids = sub_df[p1_cols].to_numpy()
        cols_p1 = id_lookup[p1_ids.flatten() - min_id]
        np.add.at(X, (rows, cols_p1), 1)

        p2_ids = sub_df[p2_cols].to_numpy()
        cols_p2 = id_lookup[p2_ids.flatten() - min_id]
        np.add.at(X, (rows, cols_p2), -1)

        return X

    is_test = df["day"].isin(TEST_DAYS)
    train_df = df[~is_test]
    test_df = df[is_test]
    print(f"Train: {len(train_df):,} matches ({train_df['day'].min()}-{train_df['day'].max()})")
    print(f"Test:  {len(test_df):,} matches ({test_df['day'].min()}-{test_df['day'].max()})")

    print("Building feature matrices...")
    X_train = build_matrix(train_df)
    y_train = train_df["p1_won"].to_numpy()
    X_test = build_matrix(test_df)
    y_test = test_df["p1_won"].to_numpy()

    print("Training XGBoost...")
    model = XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)
    ll = log_loss(y_test, y_proba)
    print(f"Test accuracy: {acc:.4f} | AUC: {auc:.4f} | log loss: {ll:.4f} | baseline (coin flip): 0.5000")

    importances = model.feature_importances_
    top_features = sorted(zip(card_names, importances), key=lambda x: -x[1])[:20]

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, OUT_MODEL)

    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "card_order": card_names,
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        "train_days": [train_df["day"].min(), train_df["day"].max()],
        "test_days": [test_df["day"].min(), test_df["day"].max()],
        "accuracy": round(float(acc), 4),
        "auc": round(float(auc), 4),
        "log_loss": round(float(ll), 4),
        "baseline_accuracy": 0.5,
        "top_features": [{"card": c, "importance": round(float(v), 5)} for c, v in top_features],
        "source": "s1m0n38/clash-royale-games (Kaggle)",
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Saved model to {OUT_MODEL}")
    print(f"Saved meta to {OUT_META}")


if __name__ == "__main__":
    main()
