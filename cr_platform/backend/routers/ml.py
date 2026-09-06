import json
from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from utils.data_loader import get_card_at_level, load_card_reference
from services.battle_collector import get_collection_stats

router = APIRouter()

REPO_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
MODELS_DIR = DATA_DIR / "models"


@lru_cache(maxsize=1)
def _load_model():
    """Live-trained model only -- the 2023-dataset model has been retired."""
    path = MODELS_DIR / "win_predictor_live.joblib"
    if not path.exists():
        return None
    import joblib
    return joblib.load(path)


@lru_cache(maxsize=1)
def _load_model_meta() -> dict | None:
    path = MODELS_DIR / "win_predictor_live_meta.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class PredictRequest(BaseModel):
    deck_a: list[str]
    deck_b: list[str]


def predict_win_probability(deck_a: list[str], deck_b: list[str]) -> float | None:
    """Shared core of /ml/predict's model inference -- deck_a's real
    ML-predicted win probability against deck_b, from the live-trained
    win predictor (see scripts/retrain_from_collected.py's model training
    step). None if the model isn't trained yet or either deck isn't 8 cards.
    Pulled out so other endpoints (e.g. decks.py's counter-deck response)
    can attach a real model-based win probability without duplicating the
    feature-vector construction."""
    model = _load_model()
    meta = _load_model_meta()
    if model is None or meta is None or len(deck_a) != 8 or len(deck_b) != 8:
        return None
    card_order = meta["card_order"]
    card_index = {c: i for i, c in enumerate(card_order)}
    x = np.zeros(len(card_order), dtype=np.int8)
    for c in deck_a:
        if c in card_index:
            x[card_index[c]] += 1
    for c in deck_b:
        if c in card_index:
            x[card_index[c]] -= 1
    return float(model.predict_proba(x.reshape(1, -1))[0, 1])


@router.post("/predict")
def predict(req: PredictRequest):
    model = _load_model()
    meta = _load_model_meta()
    if model is None or meta is None:
        raise HTTPException(status_code=503, detail="No live-trained model yet -- needs 5,000+ collected battles, run scripts/retrain_from_collected.py")
    if len(req.deck_a) != 8 or len(req.deck_b) != 8:
        raise HTTPException(status_code=400, detail="Both decks must have exactly 8 cards")

    card_order = meta["card_order"]
    card_index = {c: i for i, c in enumerate(card_order)}
    unknown = sorted({c for c in req.deck_a + req.deck_b if c not in card_index})

    proba_a = predict_win_probability(req.deck_a, req.deck_b)

    importances = dict(zip(card_order, model.feature_importances_.tolist()))
    present = [
        {"card": c, "importance": importances.get(c, 0), "side": "A" if c in req.deck_a else "B"}
        for c in set(req.deck_a + req.deck_b) if c in importances
    ]
    present.sort(key=lambda x: -x["importance"])

    return {
        "deck_a_win_probability": proba_a,
        "deck_b_win_probability": 1 - proba_a,
        "unknown_cards": unknown,
        "top_influential_cards": present[:8],
        "model_accuracy": meta["accuracy"],
        "model_auc": meta.get("auc"),
        "caveat": meta.get("caveat"),
    }


@lru_cache(maxsize=1)
def _load_card_stats() -> pd.DataFrame | None:
    path = DATA_DIR / "card_stats_live.csv"
    return pd.read_csv(path) if path.exists() else None


@router.get("/card-value")
def card_value(ref_level: int = Query(11, ge=1, le=18)):
    reference = load_card_reference()
    card_stats = _load_card_stats()

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
        rows.append({
            "card_name": card, "elixir": row["elixir"], "rarity": row["rarity"],
            "efficiency": round(float(efficiency), 1),
        })

    value_df = pd.DataFrame(rows)
    if card_stats is not None:
        value_df = value_df.merge(card_stats[["card_name", "win_rate", "times_used"]], on="card_name", how="left")
    else:
        value_df["win_rate"] = None
        value_df["times_used"] = None

    value_df = value_df.sort_values("efficiency", ascending=False)
    value_df = value_df.astype(object).where(pd.notna(value_df), None)
    return {"reference_level": ref_level, "cards": value_df.to_dict(orient="records")}


@router.get("/collection-stats")
def collection_stats():
    """How much real, live battle data has been collected so far via Player
    Lookup page usage -- each lookup contributes its ~25 most recent battles,
    so this grows slowly compared to the 18.3M-match historical base, but it's
    real and current rather than a 2023 snapshot."""
    return get_collection_stats()
