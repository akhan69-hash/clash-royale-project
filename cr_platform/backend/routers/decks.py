import itertools
from pathlib import Path
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, Query
from pydantic import BaseModel
from services.card_service import get_max_level, get_rarity_map, get_card_image_url, SLOT_THRESHOLDS
from utils.data_loader import api_level_to_csv_level as api_to_absolute, get_elixir_costs
from utils.deck_analysis import analyze_deck as _analyze_deck
from utils.counter_suggester import (
    get_counter_cards, generate_counter_deck, detect_weaknesses, archetype_label,
    wilson_lower_bound, explain_deck_vs_opponent,
)
from routers.meta import _load_card_stats_df, _clean, _strategy_fields
from routers.synergy import get_synergy_score
from routers.ml import predict_win_probability

REPO_ROOT = Path(__file__).parent.parent.parent.parent

router = APIRouter()

LIVE_DECK_MATCHUPS_PATH = REPO_ROOT / "data" / "deck_matchups_live.csv"
LIVE_DECK_MATCHUP_SCORELINES_PATH = REPO_ROOT / "data" / "deck_matchup_scorelines_live.csv"
LIVE_STRATEGY_MATCHUPS_PATH = REPO_ROOT / "data" / "strategy_matchups_live.csv"
MIN_MATCHUP_FREQUENCY = 8  # below this, even a Wilson-corrected win rate is too thin an evidence base to trust
# Strategy-vs-strategy rows pool many exact decks together, so real sample
# sizes here run far larger than any single exact-deck matchup -- can afford
# a much higher floor than MIN_MATCHUP_FREQUENCY and still return plenty.
MIN_STRATEGY_MATCHUP_FREQUENCY = 25
# Safety cap only -- purely to bound iterrows() cost for an unexpectedly huge
# single-archetype bucket. NOT a pre-filter by win rate: the whole point of
# the Wilson-score fix below is to stop pre-selecting on raw win rate before
# correcting for sample size, so every row that clears MIN_MATCHUP_FREQUENCY
# gets considered, not just whichever happened to sort highest by raw %.
CANDIDATE_POOL_CAP = 500
MIN_USES_FOR_CARD_STAT = 10  # same noise floor meta.py's top_cards() uses


@lru_cache(maxsize=1)
def _load_deck_matchups_df():
    return pd.read_csv(LIVE_DECK_MATCHUPS_PATH) if LIVE_DECK_MATCHUPS_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_scorelines_df():
    return pd.read_csv(LIVE_DECK_MATCHUP_SCORELINES_PATH) if LIVE_DECK_MATCHUP_SCORELINES_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_strategy_matchups_df():
    return pd.read_csv(LIVE_STRATEGY_MATCHUPS_PATH) if LIVE_STRATEGY_MATCHUPS_PATH.exists() else None


MIN_SCORELINE_SAMPLE = 5  # below this, even the most common real scoreline is too thin to call "predicted"


def _predicted_scoreline(vs_archetype: str, deck: list[str]) -> dict | None:
    """Real observed crown-score distribution for this exact (deck, opponent
    archetype) matchup (see scripts/retrain_from_collected.py's
    build_deck_matchup_scorelines) -- e.g. 'this deck beats Hog Cycle 2-1 38%
    of the time, 3-0 22% of the time...'. Returns the most common real
    scoreline plus the top breakdown, or None if there isn't enough sample."""
    df = _load_scorelines_df()
    if df is None:
        return None
    deck_key = ";".join(sorted(deck))
    rows = df[(df["vs_archetype"] == vs_archetype) & (df["deck"] == deck_key)]
    if rows.empty or int(rows["total"].iloc[0]) < MIN_SCORELINE_SAMPLE:
        return None
    rows = rows.sort_values("pct", ascending=False)
    return {
        "total_games": int(rows["total"].iloc[0]),
        "most_likely": rows.iloc[0]["scoreline"],
        "most_likely_pct": float(rows.iloc[0]["pct"]),
        "breakdown": [
            {"score": r["scoreline"], "pct": float(r["pct"]), "count": int(r["count"])}
            for _, r in rows.head(5).iterrows()
        ],
    }


@router.get("/slot-thresholds")
def slot_thresholds():
    """Trophy thresholds for the 3 special deck slots (Evolution/Hero/Wild),
    for showing lock/unlock state when no player is connected yet."""
    return SLOT_THRESHOLDS


class DeckCard(BaseModel):
    name: str
    relative_level: int = 11


class DeckAnalyzeRequest(BaseModel):
    cards: list[DeckCard]


class DeckAnalyzeAbsoluteRequest(BaseModel):
    """For callers that already track absolute (1-18) levels directly, e.g. the
    Collection Builder page -- skips the relative-level conversion entirely."""
    cards: dict[str, int]  # name -> absolute level (0/unowned allowed, treated as 1)


class DeckCounterRequest(BaseModel):
    cards: list[str]   # ["Hog Rider", "Zap", ...]
    card_levels: dict[str, int] | None = None  # name -> relative_level, as shown in-game


def _relative_to_absolute_levels(card_names: list[str], relative_by_name: dict[str, int]) -> dict[str, int]:
    """Convert in-game relative levels to our stats CSV's absolute 1-18 scale,
    per card (since each card's real maxLevel, not just its rarity, determines
    the offset -- see utils/data_loader.py's api_level_to_csv_level)."""
    rarity_map = get_rarity_map()
    abs_levels = {}
    for name in card_names:
        relative = relative_by_name.get(name, 11)
        max_level = get_max_level(name, rarity_map.get(name, "Common"))
        abs_levels[name] = api_to_absolute(relative, max_level)
    return abs_levels


@router.post("/analyze")
def analyze_deck(req: DeckAnalyzeRequest):
    card_names = [c.name for c in req.cards]
    relative_by_name = {c.name: c.relative_level for c in req.cards}
    abs_levels = _relative_to_absolute_levels(card_names, relative_by_name)
    return _analyze_deck(card_names, abs_levels)


@router.post("/analyze-absolute")
def analyze_deck_absolute(req: DeckAnalyzeAbsoluteRequest):
    card_names = list(req.cards.keys())
    abs_levels = {name: max(1, level) for name, level in req.cards.items()}
    return _analyze_deck(card_names, abs_levels)


@router.post("/counter")
def counter_deck(
    req: DeckCounterRequest,
    page: int = Query(1, ge=1, description="1-indexed page number"),
    # Lowered from 10 -> 4 (2026-08-20): a full deck card (header, 8-card
    # grid, MVP line, collapsible details) is tall -- 10 per page meant far
    # more scrolling than intended before pagination controls even appeared,
    # confirmed as a real complaint from mobile use. 4 keeps desktop's
    # 2-column deck grid at a clean 2 rows too.
    page_size: int = Query(4, ge=1, le=50),
    sort_by: str = Query("reliability", description="reliability (default, Wilson-confidence + relevance blend) | frequency | win_rate | synergy_score"),
    strategy: str | None = Query(None, description="Optional -- filter to counter-decks matching this exact strategy label (see GET /meta/deck-strategies)"),
):
    abs_levels = _relative_to_absolute_levels(req.cards, req.card_levels or {}) if req.card_levels else None

    weaknesses = detect_weaknesses(req.cards)
    top_counters = get_counter_cards(req.cards, top_n=12, card_levels=abs_levels)

    # Real, tested decks first: decks actually played (and how often they won)
    # against the opponent's archetype, from data/deck_matchups_live.csv (see
    # scripts/retrain_from_collected.py's build_deck_matchups). Only the
    # synthetic per-card-score assembly (generate_counter_deck) falls back to
    # invented data -- and only when there's no real matchup evidence yet.
    vs_archetype = archetype_label(req.cards)
    elixir_costs = get_elixir_costs()
    card_stats_df = _load_card_stats_df()
    card_win_rates = {}
    if card_stats_df is not None:
        reliable = card_stats_df[card_stats_df["times_used"] >= MIN_USES_FOR_CARD_STAT]
        card_win_rates = dict(zip(reliable["card_name"], reliable["win_rate"]))

    tested_counter_decks = []
    total = 0
    blended_sorted = []  # reliability-ranked candidates, independent of the caller's chosen sort_by/page -- see below
    matchups_df = _load_deck_matchups_df()
    if matchups_df is not None:
        subset = matchups_df[matchups_df["vs_archetype"] == vs_archetype]
        subset = subset[subset["frequency"] >= MIN_MATCHUP_FREQUENCY]

        # Widen the candidate pool first (instead of locking in the top-5-by-
        # raw-win-rate immediately -- that's exactly why every opponent sharing
        # an archetype used to get the identical answer), then rank by a blend
        # of (a) a confidence-adjusted real win rate (Wilson lower bound, so a
        # lucky 5-0 doesn't always beat a proven 40-10) and (b) how relevant
        # THIS specific candidate deck's cards actually are against THIS
        # specific opponent's actual 8 cards -- two different opponents in the
        # same archetype bucket can now surface different top picks and reasons.
        candidates = []
        for _, row in subset.head(CANDIDATE_POOL_CAP).iterrows():
            cards = row["deck"].split(";")
            frequency = int(row["frequency"])
            win_rate = float(row["win_rate"])
            # Real win count (added to the CSV alongside win_rate) is exact;
            # older pre-retrain rows without the column fall back to the
            # rounded derivation this always used before.
            wins_val = row.get("wins")
            wins = int(wins_val) if pd.notna(wins_val) else round(win_rate * frequency)
            confidence = wilson_lower_bound(wins, frequency)
            reasons, relevance = explain_deck_vs_opponent(cards, req.cards, weaknesses=weaknesses)
            estimated_win_rate = row.get("estimated_win_rate")
            # Real feedback (2026-08-26): "Better counters from ML and more
            # depending on reliable counters win rate + number of times
            # played but also a contribution from the ML." estimated_win_rate
            # (the Deck Quality Model's composition-based prediction) was
            # already being computed and shown on every candidate, but never
            # actually fed into the ranking score below -- it was decorative.
            # Now it's a real 25% share whenever a trained estimate exists
            # (composition-based, so it's especially useful for a real but
            # thin-sample deck the Wilson bound alone would rank too low);
            # falls back to the pre-existing confidence+relevance-only blend
            # when no model is trained yet (small live dataset) so ranking
            # never silently changes shape just because the field is absent.
            if pd.notna(estimated_win_rate):
                blended_score = (
                    0.60 * confidence
                    + 0.15 * min(relevance / 10, 1.0)
                    + 0.25 * float(estimated_win_rate)
                )
            else:
                blended_score = 0.75 * confidence + 0.25 * min(relevance / 10, 1.0)
            candidates.append({
                "cards": cards, "frequency": frequency, "win_rate": win_rate, "wins": wins,
                "confidence": confidence, "reasons": reasons, "blended_score": blended_score,
                "estimated_win_rate": float(estimated_win_rate) if pd.notna(estimated_win_rate) else None,
                "typical_evolution": _clean(row.get("typical_evolution")),
                "evolution_rate_pct": _clean(row.get("evolution_rate_pct")),
                "typical_hero": _clean(row.get("typical_hero")),
                "hero_rate_pct": _clean(row.get("hero_rate_pct")),
                "typical_ambiguous": _clean(row.get("typical_ambiguous")),
                "ambiguous_rate_pct": _clean(row.get("ambiguous_rate_pct")),
                "typical_tower_troop": _clean(row.get("typical_tower_troop")),
                "tower_troop_rate_pct": _clean(row.get("tower_troop_rate_pct")),
                "tower_troop_win_rate_pct": _clean(row.get("tower_troop_win_rate_pct")),
                **_strategy_fields(cards),
            })

        # The single "headline" counter deck (used below for counter_deck_*)
        # always uses the reliability blend regardless of what the paginated
        # list is currently sorted/filtered by -- so switching the list's sort
        # or paging through it never changes what's called out as the top pick.
        blended_sorted = sorted(candidates, key=lambda c: c["blended_score"], reverse=True)

        if strategy:
            candidates = [c for c in candidates if c["strategy"] == strategy]

        if sort_by == "frequency":
            candidates.sort(key=lambda c: c["frequency"], reverse=True)
        elif sort_by == "win_rate":
            candidates.sort(key=lambda c: c["win_rate"], reverse=True)
        elif sort_by == "synergy_score":
            for c in candidates:
                pair_scores = [get_synergy_score(a, b) for a, b in itertools.combinations(c["cards"], 2)]
                c["synergy_score"] = round(sum(pair_scores) / len(pair_scores), 2) if pair_scores else None
            candidates.sort(key=lambda c: c["synergy_score"] if c["synergy_score"] is not None else -1, reverse=True)
        else:
            candidates.sort(key=lambda c: c["blended_score"], reverse=True)

        total = len(candidates)
        start = (page - 1) * page_size
        page_candidates = candidates[start:start + page_size]

        for c in page_candidates:
            cards = c["cards"]
            avg_elixir = round(sum(elixir_costs.get(name, 0) for name in cards) / len(cards), 1) if cards else None
            cards_detail = [
                {"name": name, "win_rate": round(card_win_rates[name] * 100, 1) if name in card_win_rates else None}
                for name in cards
            ]
            mvp = max((cd for cd in cards_detail if cd["win_rate"] is not None),
                      key=lambda cd: cd["win_rate"], default=None)
            # Real observed crown-score distribution for this exact matchup
            # (e.g. "2-1 38% of the time"), plus the trained model's own
            # independent win-probability estimate for this deck vs the
            # opponent's actual 8 cards -- two different real signals shown
            # together: what's actually happened, and what the model thinks.
            predicted_scoreline = _predicted_scoreline(vs_archetype, cards)
            model_win_probability = predict_win_probability(cards, req.cards)
            tested_counter_decks.append({
                "cards": cards,
                "frequency": c["frequency"],
                "wins": c["wins"],
                "win_rate": round(c["win_rate"] * 100, 2),
                "estimated_win_rate": round(c["estimated_win_rate"] * 100, 2) if c["estimated_win_rate"] is not None else None,
                "strategy": c["strategy"],
                "strategy_games_played": c["strategy_games_played"],
                "strategy_win_rate": c["strategy_win_rate"],
                "avg_elixir": avg_elixir,
                "reasons": c["reasons"] or ["Real deck seen beating this archetype -- no single standout counter interaction, just a solid overall matchup."],
                "cards_detail": cards_detail,
                "mvp_card": mvp["name"] if mvp else None,
                "typical_evolution": c["typical_evolution"],
                "evolution_rate_pct": c["evolution_rate_pct"],
                "typical_hero": c["typical_hero"],
                "hero_rate_pct": c["hero_rate_pct"],
                "typical_ambiguous": c["typical_ambiguous"],
                "ambiguous_rate_pct": c["ambiguous_rate_pct"],
                "typical_tower_troop": c["typical_tower_troop"],
                "tower_troop_rate_pct": c["tower_troop_rate_pct"],
                "tower_troop_win_rate_pct": c["tower_troop_win_rate_pct"],
                "tower_troop_image_url": get_card_image_url(c["typical_tower_troop"]) if c["typical_tower_troop"] else None,
                "predicted_scoreline": predicted_scoreline,
                "model_win_probability_pct": round(model_win_probability * 100, 1) if model_win_probability is not None else None,
            })

    if blended_sorted:
        counter_deck_cards = blended_sorted[0]["cards"]
        counter_deck_source = "real"
        counter_deck_analysis = _analyze_deck(counter_deck_cards, {c: abs_levels.get(c, 11) if abs_levels else 11 for c in counter_deck_cards})
    else:
        deck_result = generate_counter_deck(req.cards, card_levels=abs_levels)
        counter_deck_cards = deck_result["deck"]
        counter_deck_source = "synthetic"
        counter_deck_analysis = deck_result["analysis"]

    return {
        "weaknesses": weaknesses,
        "top_counters": top_counters.to_dict(orient="records"),
        "vs_archetype": vs_archetype,
        "tested_counter_decks": tested_counter_decks,
        "total": total,
        "page": page,
        "page_size": page_size,
        "counter_deck": counter_deck_cards,
        "counter_deck_source": counter_deck_source,
        "counter_deck_analysis": counter_deck_analysis,
    }


REPRESENTATIVE_DECKS_PER_STRATEGY = 3


@router.get("/counter-strategy")
def counter_strategy(
    vs_strategy: str = Query(..., description="A real strategy label from GET /meta/deck-strategies, e.g. 'Hog Rider (cycle)'"),
    page: int = Query(1, ge=1),
    # Lowered from 10 -> 4 (2026-08-20): a full deck card (header, 8-card
    # grid, MVP line, collapsible details) is tall -- 10 per page meant far
    # more scrolling than intended before pagination controls even appeared,
    # confirmed as a real complaint from mobile use. 4 keeps desktop's
    # 2-column deck grid at a clean 2 rows too.
    page_size: int = Query(4, ge=1, le=50),
    sort_by: str = Query("frequency", description="frequency (default, most real games) | win_rate"),
):
    """Real counters for a whole STRATEGY, not one exact opponent deck --
    complements /counter (which needs a specific 8-card opponent deck built
    first) by letting a player just pick the archetype they're facing (say,
    'Hog Rider (cycle)') from a dropdown and immediately see which real
    COUNTER STRATEGIES have beaten it, backed by real games POOLED across
    every real exact-deck variant of that counter strategy (see
    scripts/retrain_from_collected.py's build_strategy_matchups) -- a far
    larger, more reliable sample than any single exact-deck matchup (which
    can be as thin as MIN_MATCHUP_COUNT=5). Each counter strategy also comes
    with a few real representative decks so the recommendation is concrete,
    not just a label."""
    df = _load_strategy_matchups_df()
    if df is None:
        return {"vs_strategy": vs_strategy, "counters": [], "total": 0, "page": page, "page_size": page_size,
                "note": "Not enough live battles yet for strategy-level matchup data."}

    subset = df[(df["vs_strategy"] == vs_strategy) & (df["frequency"] >= MIN_STRATEGY_MATCHUP_FREQUENCY)]
    if subset.empty:
        return {"vs_strategy": vs_strategy, "counters": [], "total": 0, "page": page, "page_size": page_size,
                "note": f"No real strategy-level counters with {MIN_STRATEGY_MATCHUP_FREQUENCY}+ real games yet for '{vs_strategy}'."}

    subset = subset.sort_values("win_rate" if sort_by == "win_rate" else "frequency", ascending=False)
    total = len(subset)
    start = (page - 1) * page_size
    page_rows = subset.iloc[start:start + page_size]

    # Representative real decks for each counter strategy, drawn from the
    # SAME exact-deck matchup table /counter uses -- computed once for this
    # vs_strategy, not re-filtered from scratch per counter-strategy row.
    elixir_costs = get_elixir_costs()
    matchups_df = _load_deck_matchups_df()
    vs_subset = None
    if matchups_df is not None:
        vs_subset = matchups_df[matchups_df["vs_archetype"] == vs_strategy].copy()
        vs_subset["my_strategy"] = vs_subset["deck"].apply(lambda d: archetype_label(str(d).split(";")))

    counters = []
    for _, row in page_rows.iterrows():
        my_strategy = row["my_strategy"]
        representative_decks = []
        if vs_subset is not None:
            candidates = vs_subset[vs_subset["my_strategy"] == my_strategy] \
                .sort_values("frequency", ascending=False).head(REPRESENTATIVE_DECKS_PER_STRATEGY)
            for _, drow in candidates.iterrows():
                cards = drow["deck"].split(";")
                avg_elixir = round(sum(elixir_costs.get(c, 0) for c in cards) / len(cards), 1) if cards else None
                estimated = drow.get("estimated_win_rate")
                representative_decks.append({
                    "cards": cards,
                    "frequency": int(drow["frequency"]),
                    "wins": int(drow["wins"]) if pd.notna(drow.get("wins")) else None,
                    "win_rate": round(float(drow["win_rate"]) * 100, 2),
                    "estimated_win_rate": round(float(estimated) * 100, 2) if pd.notna(estimated) else None,
                    "avg_elixir": avg_elixir,
                    "typical_evolution": _clean(drow.get("typical_evolution")),
                    "evolution_rate_pct": _clean(drow.get("evolution_rate_pct")),
                    "typical_hero": _clean(drow.get("typical_hero")),
                    "hero_rate_pct": _clean(drow.get("hero_rate_pct")),
                    "typical_ambiguous": _clean(drow.get("typical_ambiguous")),
                    "ambiguous_rate_pct": _clean(drow.get("ambiguous_rate_pct")),
                    "typical_tower_troop": _clean(drow.get("typical_tower_troop")),
                    "tower_troop_rate_pct": _clean(drow.get("tower_troop_rate_pct")),
                    "tower_troop_win_rate_pct": _clean(drow.get("tower_troop_win_rate_pct")),
                    "tower_troop_image_url": get_card_image_url(drow["typical_tower_troop"]) if _clean(drow.get("typical_tower_troop")) else None,
                })
        counters.append({
            "strategy": my_strategy,
            "frequency": int(row["frequency"]),
            "wins": int(row["wins"]),
            "win_rate": round(float(row["win_rate"]) * 100, 2),
            "deck_count": int(row["deck_count"]),
            "representative_decks": representative_decks,
        })

    return {"vs_strategy": vs_strategy, "counters": counters, "total": total, "page": page, "page_size": page_size}
