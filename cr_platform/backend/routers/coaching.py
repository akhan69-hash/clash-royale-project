"""
Personal Coaching Hub -- backend surface.

IMPORTANT, verified by direct testing of the official API (2026-07-31, and
corrected 2026-08-01): the Clash Royale battlelog endpoint returns match
summaries (final result, crowns, tower HP, both decks with real levels,
trophies) plus a few real per-match fields discovered later -- `elixirLeaked`
(real per-side elixir left unspent) and `supportCards` (the real King Tower
Troop used) are both genuinely available and captured (see
services/battle_collector.py). What's still NOT exposed anywhere in this API:
card placement coordinates and play-by-play in-match timing/trades -- those
would need screen-capture/computer-vision of the live game client, a
different project belonging to the same future "bot" phase already deferred.

Everything below is composed from real match-summary data and the app's
existing curated tables (role taxonomy, hard counters) -- no invented
numbers standing in for the data that doesn't exist. Deck health, counters,
and card-value endpoints are NOT duplicated here -- the frontend calls the
existing /decks and /cards endpoints directly for those.
"""
import sys
from pathlib import Path
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, Query
from pydantic import BaseModel

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.coaching import classify_losses  # noqa: E402
from utils.arena_data import get_arena_for_trophies, get_arena_options  # noqa: E402
from utils.counter_suggester import archetype_label  # noqa: E402

router = APIRouter()

LIVE_ELIXIR_LEAK_PATH = REPO_ROOT / "data" / "elixir_leak_stats_live.csv"


@lru_cache(maxsize=1)
def _load_elixir_leak_df():
    return pd.read_csv(LIVE_ELIXIR_LEAK_PATH) if LIVE_ELIXIR_LEAK_PATH.exists() else None


class ElixirBenchmarkRequest(BaseModel):
    cards: list[str]  # the player's own 8-card deck


@router.post("/elixir-benchmark")
def elixir_benchmark(req: ElixirBenchmarkRequest):
    """Real average elixir-leaked for decks in the same archetype as the
    player's own deck (see scripts/retrain_from_collected.py's
    build_elixir_leak_stats) -- lets Coaching say 'you leak X, similar real
    decks leak Y' instead of an invented benchmark number."""
    archetype = archetype_label(req.cards)
    df = _load_elixir_leak_df()
    if df is None:
        return {"archetype": archetype, "avg_elixir_leaked": None, "battles": 0}
    row = df[df["archetype"] == archetype]
    if row.empty:
        return {"archetype": archetype, "avg_elixir_leaked": None, "battles": 0}
    r = row.iloc[0]
    return {"archetype": archetype, "avg_elixir_leaked": round(float(r["avg_elixir_leaked"]), 2), "battles": int(r["battles"])}


class LossPatternRequest(BaseModel):
    your_deck: list[str]
    losses: list[list[str]]  # each entry is one real opponent's 8-card deck from a battle the player lost


@router.post("/loss-patterns")
def loss_patterns(req: LossPatternRequest):
    return classify_losses(req.your_deck, req.losses)


@router.get("/arena-for-trophies")
def arena_for_trophies(trophies: int = Query(...)):
    """Given a real trophy count, returns the current arena bucket and the
    next one up, so the frontend can pull real by-arena data for both via
    the existing /meta/arenas/{arena}/cards and /meta/decks?arena= endpoints."""
    arena = get_arena_for_trophies(trophies)
    options = get_arena_options()
    next_arena = None
    if arena in options:
        idx = options.index(arena)
        if idx + 1 < len(options):
            next_arena = options[idx + 1]
    return {"arena": arena, "next_arena": next_arena}
