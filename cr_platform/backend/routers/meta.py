import sys
import itertools
from pathlib import Path
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, Query, HTTPException

from services.card_service import get_card_image_url, get_all_cards
from services.battle_collector import get_collection_stats
from utils.data_loader import get_elixir_costs

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.arena_data import get_arena_options  # noqa: E402
from utils.counter_suggester import archetype_label  # noqa: E402
from routers.synergy import get_synergy_score  # noqa: E402


def _clean(v):
    """pandas round-trips a missing value as NaN, not None or absent --
    normalize back to None for JSON responses."""
    return None if pd.isna(v) else v

router = APIRouter()

LIVE_CARD_STATS_PATH = REPO_ROOT / "data" / "card_stats_live.csv"
LIVE_ARENA_USAGE_PATH = REPO_ROOT / "data" / "card_usage_by_arena_live.csv"
LIVE_ARCHETYPES_PATH = REPO_ROOT / "data" / "deck_archetypes_live.csv"
LIVE_ARCHETYPES_BY_ARENA_PATH = REPO_ROOT / "data" / "deck_archetypes_by_arena_live.csv"
LIVE_EVOLUTION_HERO_USAGE_PATH = REPO_ROOT / "data" / "card_variant_usage_live.csv"
LIVE_TOWER_TROOP_USAGE_PATH = REPO_ROOT / "data" / "tower_troop_usage_live.csv"
LIVE_ELIXIR_LEAK_PATH = REPO_ROOT / "data" / "elixir_leak_stats_live.csv"
LIVE_DECK_STRATEGY_SUMMARY_PATH = REPO_ROOT / "data" / "deck_strategy_summary_live.csv"


@lru_cache(maxsize=1)
def _card_meta_lookup() -> dict:
    """name -> {rarity, type, has_evolution, has_hero} for the 'more stats' columns."""
    return {c["name"]: c for c in get_all_cards()}


# These CSVs are only ever rewritten by scripts/retrain_from_collected.py
# (an offline, manually-triggered step), never while the server is serving
# requests -- caching them avoids re-parsing the same file on every request
# to a hot endpoint (found to matter once card_usage_by_arena_live.csv grew
# past a couple thousand rows and was being re-read on every single card
# profile lookup, 8x per Coaching page load).
@lru_cache(maxsize=1)
def _load_card_stats_df():
    return pd.read_csv(LIVE_CARD_STATS_PATH) if LIVE_CARD_STATS_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_arena_usage_df():
    return pd.read_csv(LIVE_ARENA_USAGE_PATH) if LIVE_ARENA_USAGE_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_archetypes_df():
    return pd.read_csv(LIVE_ARCHETYPES_PATH) if LIVE_ARCHETYPES_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_deck_estimate_lookup() -> dict:
    """Exact 8-card deck (sorted, ';'-joined -- same key shape used
    throughout the live CSVs) -> the Deck Quality Model's estimated_win_rate
    for it, from deck_archetypes_live.csv. Shared with players.py's own
    '/{tag}/decks' so a player's personal decks get the same reliability
    treatment as Top Decks/Counter, by exact card-set match."""
    df = _load_archetypes_df()
    if df is None or "estimated_win_rate" not in df.columns:
        return {}
    return dict(zip(df["deck"], df["estimated_win_rate"]))


@lru_cache(maxsize=1)
def _load_archetypes_by_arena_df():
    return pd.read_csv(LIVE_ARCHETYPES_BY_ARENA_PATH) if LIVE_ARCHETYPES_BY_ARENA_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_evolution_hero_usage_df():
    return pd.read_csv(LIVE_EVOLUTION_HERO_USAGE_PATH) if LIVE_EVOLUTION_HERO_USAGE_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_tower_troop_usage_df():
    return pd.read_csv(LIVE_TOWER_TROOP_USAGE_PATH) if LIVE_TOWER_TROOP_USAGE_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_elixir_leak_df():
    return pd.read_csv(LIVE_ELIXIR_LEAK_PATH) if LIVE_ELIXIR_LEAK_PATH.exists() else None


@lru_cache(maxsize=1)
def _load_deck_strategy_summary() -> dict:
    """strategy label (archetype_label output, e.g. 'Hog Rider (cycle)') ->
    its row from deck_strategy_summary_live.csv -- the real games-played/win-rate
    POOLED ACROSS EVERY EXACT-DECK VARIANT of that strategy (see
    scripts/retrain_from_collected.py's build_deck_strategy_summary), used
    alongside (never instead of) a single deck's own real frequency/win_rate
    so a thin exact-build isn't the only reliability signal shown."""
    if not LIVE_DECK_STRATEGY_SUMMARY_PATH.exists():
        return {}
    df = pd.read_csv(LIVE_DECK_STRATEGY_SUMMARY_PATH)
    return {row["strategy"]: row for _, row in df.iterrows()}


def _strategy_fields(cards: list[str]) -> dict:
    """Shared by /decks (top_decks) and decks.py's /counter so both surface
    the exact same strategy label + pooled-strategy reliability numbers for
    the same deck, regardless of which endpoint returned it."""
    strategy = archetype_label(cards)
    summary_row = _load_deck_strategy_summary().get(strategy)
    return {
        "strategy": strategy,
        "strategy_games_played": int(summary_row["total_frequency"]) if summary_row is not None else None,
        "strategy_win_rate": round(float(summary_row["win_rate"]) * 100, 2) if summary_row is not None else None,
        "strategy_deck_count": int(summary_row["deck_count"]) if summary_row is not None else None,
    }


@router.get("/deck-strategies")
def deck_strategies():
    """Distinct real deck strategies (primary win condition + flavor tags,
    see utils/counter_suggester.archetype_label) with how many real decks and
    real games back each one -- powers the frontend's strategy filter."""
    summary = _load_deck_strategy_summary()
    if not summary:
        return {"strategies": [], "note": "Not enough live battles yet for deck strategy data."}
    rows = sorted(summary.values(), key=lambda r: r["total_frequency"], reverse=True)
    return {"strategies": [
        {
            "strategy": row["strategy"],
            "deck_count": int(row["deck_count"]),
            "total_frequency": int(row["total_frequency"]),
            "win_rate": round(float(row["win_rate"]) * 100, 2),
        }
        for row in rows
    ]}


@router.get("/cards")
def top_cards(sort_by: str = Query("win_rate", description="win_rate or presence_rate"), limit: int = 200):
    """Card usage/win rates from data/card_stats_live.csv -- entirely real,
    current battles collected via Player Lookup + the background crawler.
    The old 2023 Kaggle-snapshot baseline has been retired; this is the only
    card meta view now, and it grows as the live dataset grows."""
    collection = get_collection_stats()
    df = _load_card_stats_df()
    if df is None:
        return {"collection": collection, "cards": [], "note": "Not enough collected battles yet for a meta view."}

    if sort_by == "win_rate":
        # At this dataset's current size, a card used once or twice can show a
        # meaningless "100%" win rate -- require a minimum sample before ranking
        # on win rate (times_used has no such noise problem, so left unfiltered).
        df = df[df["times_used"] >= 10]
    meta = _card_meta_lookup()
    sorted_df = df.sort_values(sort_by, ascending=False).head(limit)
    cards = []
    for _, row in sorted_df.iterrows():
        m = meta.get(row["card_name"], {})
        cards.append({
            "name": row["card_name"],
            "times_used": int(row["times_used"]),
            "win_rate": round(float(row["win_rate"]) * 100, 2) if pd.notna(row["win_rate"]) else None,
            "presence_rate": round(float(row["presence_rate"]) * 100, 2) if pd.notna(row["presence_rate"]) else None,
            "elixir": row["elixir"] if pd.notna(row["elixir"]) else None,
            "rarity": m.get("rarity"),
            "type": m.get("type"),
            "has_evolution": m.get("has_evolution", False),
            "has_hero": m.get("has_hero", False),
            "image_url": get_card_image_url(row["card_name"]),
        })
    return {"collection": collection, "total_cards_with_data": len(df), "cards": cards}


@router.get("/arenas")
def arena_options():
    """List of arena buckets for the Analytics arena selector. See
    utils/arena_data.py for sourcing/accuracy caveats."""
    return {"arenas": get_arena_options()}


@router.get("/arenas/{arena}/cards")
def arena_card_usage(arena: str, limit: int = 30):
    """Most-used cards for one arena bucket, from real battles that had trophy
    data captured (only battles collected since this feature was added --
    the ~8,000-battle backlog before it doesn't have trophies recorded).

    Important caveat: current trophies are NOT a reliable proxy for which
    cards an account has actually unlocked -- veteran accounts pass through
    low trophy ranges constantly (season resets, deliberate trophy-dropping,
    alts) while keeping their fully-leveled collection, which is why cards
    that unlock much later than Arena 1 can still show up there. As of
    2026-07-31, battles collected since then also capture each side's average
    real card level, and scripts/retrain_from_collected.py now excludes
    battle-sides that look like a veteran account in a low arena (avg level
    >= 11 below the Wild-slot/3000-trophy threshold) -- but this can only
    filter NEW battles, not the existing backlog, so low-arena results will
    keep improving in accuracy as the live dataset grows rather than being
    retroactively fixed. `arena_avg_level` below is the real observed average
    so this can be sanity-checked directly instead of taken on faith."""
    df = _load_arena_usage_df()
    if df is None:
        return {"arena": arena, "cards": [], "note": "No arena-tagged battles collected yet -- check back as the live dataset grows."}

    subset = df[df["arena"] == arena].sort_values("times_used", ascending=False).head(limit)
    if subset.empty:
        return {"arena": arena, "cards": [], "note": "No battles seen yet for this arena bucket."}

    meta = _card_meta_lookup()
    cards = []
    arena_avg_level = None
    for _, row in subset.iterrows():
        m = meta.get(row["card_name"], {})
        if "arena_avg_level" in row and pd.notna(row["arena_avg_level"]):
            arena_avg_level = float(row["arena_avg_level"])
        cards.append({
            "name": row["card_name"],
            "times_used": int(row["times_used"]),
            "win_rate": round(float(row["win_rate"]) * 100, 2),
            "rarity": m.get("rarity"),
            "elixir": m.get("elixir_cost"),
            "image_url": get_card_image_url(row["card_name"]),
        })
    return {"arena": arena, "cards": cards, "arena_avg_level": arena_avg_level}


MIN_ARENA_FREQUENCY = 20  # below this, an arena's win rate for a card is noise, not signal


def get_card_arena_eligibility(name: str) -> list[dict]:
    """Which arenas this card is actually common in, from real battles --
    the inverse of /arenas/{arena}/cards (which answers 'what's common at
    this arena'; this answers 'what trophy range is this card actually
    appropriate for'). Shared by the /cards/{name}/arenas endpoint below and
    cards.py's /cards/{name}/profile so both stay consistent."""
    df = _load_arena_usage_df()
    if df is None:
        return []
    subset = df[df["card_name"] == name]
    if subset.empty:
        return []

    arena_order = {a: i for i, a in enumerate(get_arena_options())}
    rows = [
        {
            "arena": row["arena"],
            "times_used": int(row["times_used"]),
            "win_rate": round(float(row["win_rate"]) * 100, 2),
            "meaningful": bool(row["times_used"] >= MIN_ARENA_FREQUENCY),
        }
        for _, row in subset.iterrows()
    ]
    rows.sort(key=lambda r: arena_order.get(r["arena"], 999))
    return rows


@router.get("/cards/{name}/arenas")
def card_arena_eligibility(name: str):
    rows = get_card_arena_eligibility(name)
    if not rows:
        return {"name": name, "arenas": [], "note": "Not enough arena-tagged data for this card yet."}
    return {"name": name, "arenas": rows}


# Computing synergy_score means 28 pairwise real-synergy lookups per deck --
# cheap per deck, but too slow to do for every deck in a 40k+ row archetype
# table. Widen by real popularity (frequency) first to a bounded pool, THEN
# compute the more expensive per-deck metrics only for that pool -- same
# "widen then rerank" shape as /decks/counter's Wilson-score reranking.
DECK_METRIC_CANDIDATE_POOL = 300


@router.get("/deck-lookup")
def deck_lookup(cards: str = Query(..., description="Comma-separated list of exactly 8 card names")):
    """Real win-rate/usage for ONE exact deck, by card set -- not a ranked
    Top-Decks-style listing. Powers the win-rate/usage display on decks that
    are shown as-is rather than browsed (real feedback, 2026-09-07: "My deck
    and Opponent deck does not have copy and paste option. Plus win rate and
    usage does not show on those decks") -- Current Deck and a battle's
    Opponent Deck both just render whatever the live API/battle log
    returned, with no existing lookup into the real aggregate stats every
    other deck display already draws from (deck_archetypes_live.csv). Same
    real data source and sorted-card-set key as /decks, just a single exact
    match instead of a ranked page."""
    card_list = [c.strip() for c in cards.split(",") if c.strip()]
    if len(card_list) != 8:
        raise HTTPException(status_code=400, detail="Exactly 8 card names required")
    deck_key = ";".join(sorted(card_list))

    df = _load_archetypes_df()
    if df is None:
        return {"found": False}
    row = df[df["deck"] == deck_key]
    if row.empty:
        return {"found": False}
    row = row.iloc[0]

    elixir_costs = get_elixir_costs()
    costs = [elixir_costs.get(c, 0) for c in card_list]
    avg_elixir = round(sum(costs) / len(costs), 1)
    cycle_cost = sum(sorted(costs)[:4])
    wins_val = row.get("wins")
    estimated_win_rate = row.get("estimated_win_rate")

    return {
        "found": True,
        "frequency": int(row["frequency"]),
        "wins": int(wins_val) if pd.notna(wins_val) else None,
        "win_rate": round(float(row["win_rate"]) * 100, 2),
        "estimated_win_rate": round(float(estimated_win_rate) * 100, 2) if pd.notna(estimated_win_rate) else None,
        "avg_elixir": avg_elixir,
        "cycle_cost": cycle_cost,
        "typical_evolution": _clean(row.get("typical_evolution")),
        "evolution_rate_pct": _clean(row.get("evolution_rate_pct")),
        "typical_hero": _clean(row.get("typical_hero")),
        "hero_rate_pct": _clean(row.get("hero_rate_pct")),
        "typical_ambiguous": _clean(row.get("typical_ambiguous")),
        "ambiguous_rate_pct": _clean(row.get("ambiguous_rate_pct")),
        **_strategy_fields(card_list),
    }


@router.get("/decks")
def top_decks(
    limit: int = Query(14, description="Page size -- kept as `limit` for backward compatibility with existing small fixed-preview callers"),
    page: int = Query(1, ge=1, description="1-indexed page number, for paging through the full candidate pool"),
    arena: str | None = Query(None, description="Optional arena bucket -- omit for all-time"),
    sort_by: str = Query("frequency", description="frequency | win_rate | cycle_cost | synergy_score"),
    card: str | None = Query(None, description="Optional -- only decks containing this exact card name"),
    variant: str | None = Query(None, description="Optional, requires `card` -- regular | evolution | hero | evolved_or_hero. Filters to decks where `card` is real-typically played as that specific variant."),
    strategy: str | None = Query(None, description="Optional -- exact strategy label from GET /meta/deck-strategies, e.g. 'Hog Rider (cycle)'"),
):
    """Real, exact decks seen in live-collected battles (see
    scripts/retrain_from_collected.py's build_deck_archetypes[_by_arena]) --
    replaces the old 2023-dataset KMeans-clustered archetypes entirely.
    Exact-deck grouping rather than clustering, since live volume doesn't yet
    need it. Pass `arena` to filter to one arena bucket instead of all-time.
    `sort_by=cycle_cost` surfaces the cheapest real decks (smallest sum of
    the 4 cheapest cards); `sort_by=synergy_score` surfaces decks whose cards
    have the best real average synergy together (see routers/synergy.py's
    get_synergy_score) -- both real, not invented rankings. Each deck also
    carries its real 'typical' Evolution/Hero card (if any), so the frontend
    can show the actual evolved/hero art instead of always the base card.

    `card`+`variant` power "show me decks using Hero Knight specifically" --
    filtered on the FULL table before the popularity-based candidate-pool cap
    below, so a real but less-frequent card/variant combo isn't silently cut
    before the filter even runs. `strategy` filters to one real strategy label
    (primary win condition + flavor, see archetype_label) the same way.

    Reliability: most decks only have a handful of real games (see
    scripts/retrain_from_collected.py's docstrings) -- rather than hiding
    those, each deck also carries `strategy_games_played`/`strategy_win_rate`
    (this deck's real win rate pooled with every other real variant of the
    same strategy) and `estimated_win_rate` (the Deck Quality Model's
    composition-based estimate, see train_deck_quality_model), so a thin
    exact-build is never the only number shown."""
    elixir_costs = get_elixir_costs()

    if arena:
        df = _load_archetypes_by_arena_df()
        if df is None:
            return {"note": "Not enough arena-tagged live battles yet for by-arena deck archetypes.", "decks": []}
        df = df[df["arena"] == arena]
        if df.empty:
            return {"note": f"No decks seen 2+ times yet for {arena}.", "decks": []}
    else:
        df = _load_archetypes_df()
        if df is None:
            return {"note": "Not enough live battles yet for deck archetypes (500+ needed).", "decks": []}

    if card:
        df = df[df["deck"].apply(lambda d: card in str(d).split(";"))]
        if variant == "evolution":
            df = df[df["typical_evolution"] == card]
        elif variant == "hero":
            df = df[df["typical_hero"] == card]
        elif variant == "evolved_or_hero":
            df = df[df["typical_ambiguous"] == card]
        elif variant == "regular":
            df = df[(df["typical_evolution"] != card) & (df["typical_hero"] != card) & (df["typical_ambiguous"] != card)]
        if df.empty:
            return {"note": f"No real decks seen yet with {card}" + (f" as {variant}" if variant else "") + ".", "decks": [], "total": 0, "page": page, "page_size": limit}

    if strategy:
        df = df[df["deck"].apply(lambda d: archetype_label(str(d).split(";")) == strategy)]
        if df.empty:
            return {"note": f"No real decks seen yet for strategy '{strategy}'.", "decks": [], "total": 0, "page": page, "page_size": limit}

    # Real perf bug fixed 2026-08-06: this used to only cap the candidate pool
    # for cycle_cost/synergy_score, so a plain frequency/win_rate request
    # (the DEFAULT, most common request) iterated and recomputed elixir/cycle
    # cost for the ENTIRE archetypes table (69k+ rows all-time) on every call
    # -- 6-10+ real seconds, which is what "Top Decks won't load" actually
    # was. Every sort mode now widens by real popularity first, same as the
    # existing cycle_cost/synergy_score path, since none of them need more
    # than a few hundred candidates to produce a correct top-`limit` result.
    candidate_df = df.sort_values("frequency", ascending=False).head(DECK_METRIC_CANDIDATE_POOL)

    decks = []
    for _, row in candidate_df.iterrows():
        cards = row["deck"].split(";")
        if len(cards) != 8:
            continue
        costs = [elixir_costs.get(c, 0) for c in cards]
        avg_elixir = round(sum(costs) / len(costs), 1)
        cycle_cost = sum(sorted(costs)[:4])
        synergy_score = None
        if sort_by == "synergy_score":
            pair_scores = [get_synergy_score(a, b) for a, b in itertools.combinations(cards, 2)]
            synergy_score = round(sum(pair_scores) / len(pair_scores), 2) if pair_scores else None
        wins_val = row.get("wins")
        estimated_win_rate = row.get("estimated_win_rate")
        decks.append({
            "cards": cards,
            "frequency": int(row["frequency"]),
            "wins": int(wins_val) if pd.notna(wins_val) else None,
            "win_rate": round(float(row["win_rate"]) * 100, 2),
            "estimated_win_rate": round(float(estimated_win_rate) * 100, 2) if pd.notna(estimated_win_rate) else None,
            "avg_elixir": avg_elixir,
            "cycle_cost": cycle_cost,
            "synergy_score": synergy_score,
            "typical_evolution": _clean(row.get("typical_evolution")),
            "evolution_rate_pct": _clean(row.get("evolution_rate_pct")),
            "typical_hero": _clean(row.get("typical_hero")),
            "hero_rate_pct": _clean(row.get("hero_rate_pct")),
            # Dual-capable card (Knight/Musketeer/Wizard/Valkyrie) confirmed
            # real-active but Evolution-vs-Hero undeterminable -- see
            # card_service.split_evolution_hero_cards's docstring.
            "typical_ambiguous": _clean(row.get("typical_ambiguous")),
            "ambiguous_rate_pct": _clean(row.get("ambiguous_rate_pct")),
            # Real King Tower Troop most-often played with this exact deck
            # (see scripts/retrain_from_collected.py's _typical_tower_troop) --
            # None until 5+ tracked sightings exist for this deck.
            "typical_tower_troop": _clean(row.get("typical_tower_troop")),
            "tower_troop_rate_pct": _clean(row.get("tower_troop_rate_pct")),
            "tower_troop_win_rate_pct": _clean(row.get("tower_troop_win_rate_pct")),
            "tower_troop_image_url": get_card_image_url(row["typical_tower_troop"]) if _clean(row.get("typical_tower_troop")) else None,
            **_strategy_fields(cards),
        })

    if sort_by == "cycle_cost":
        decks.sort(key=lambda d: d["cycle_cost"])
    elif sort_by == "synergy_score":
        decks.sort(key=lambda d: d["synergy_score"] if d["synergy_score"] is not None else -1, reverse=True)
    elif sort_by == "win_rate":
        decks.sort(key=lambda d: d["win_rate"], reverse=True)
    else:
        decks.sort(key=lambda d: d["frequency"], reverse=True)

    total = len(decks)
    start = (page - 1) * limit
    return {"decks": decks[start:start + limit], "total": total, "page": page, "page_size": limit}


@router.get("/evolution-usage")
def evolution_hero_usage():
    """Real Regular/Evolved/Hero'd usage split for every Evolution/Hero-
    capable card (see scripts/retrain_from_collected.py's
    build_card_variant_usage) -- "Knight" is really up to 4 separately
    tracked real cards here (Regular, Evolved, Hero, and -- for the 4
    dual-capable cards only -- an honest "Evolved or Hero" bucket, since
    real match data can't tell those two systems apart for those cards; see
    services/card_service.split_evolution_hero_cards's docstring), each with
    its own real win rate and the correct card art for that specific
    variant. Only counts battles collected since Evolution/Hero tracking was
    added (2026-08-01) -- the historical backlog before that was backfilled
    blank and correctly excluded, not silently treated as 'never evolved.'"""
    df = _load_evolution_hero_usage_df()
    if df is None:
        return {"cards": [], "note": "Not enough battles collected since Evolution/Hero usage tracking was added yet -- check back as fresh battles come in."}
    meta = _card_meta_lookup()

    VARIANT_ORDER = {"regular": 0, "evolution": 1, "hero": 2, "evolved_or_hero": 3}
    cards = []
    for name, group in df.groupby("card_name"):
        m = meta.get(name, {})
        total_seen = int(group["total_seen"].iloc[0])
        variants = []
        for _, row in group.sort_values("kind", key=lambda s: s.map(VARIANT_ORDER)).iterrows():
            kind = row["kind"]
            # "evolved_or_hero" deliberately shows the base card art, not a
            # guessed evolution/hero frame -- we genuinely don't know which
            # of the two real systems was active, so picking either frame
            # would visually assert a specific answer that isn't real.
            image_url = (
                m.get("evolution_image_url") if kind == "evolution"
                else m.get("hero_image_url") if kind == "hero"
                else get_card_image_url(name)
            )
            variants.append({
                "kind": kind,
                "times_used": int(row["times_used"]),
                "active_rate_pct": round(int(row["times_used"]) / total_seen * 100, 1) if total_seen else 0.0,
                "win_rate_pct": round(float(row["win_rate_pct"]), 1),
                "image_url": image_url,
                # Base card art as a fallback -- some very recently-added Hero
                # cards (e.g. Hero Valkyrie/Berserker, Season 86) have a real
                # heroMedium URL in the official catalog, but the actual
                # image file hasn't been published to Supercell's CDN yet
                # (confirmed 404 on the asset itself, 2026-08-05). The
                # frontend falls back to this when the variant art 404s.
                "base_image_url": get_card_image_url(name),
                "evolution_image_url": m.get("evolution_image_url"),
                "hero_image_url": m.get("hero_image_url"),
            })
        cards.append({
            "name": name,
            "rarity": m.get("rarity"),
            "total_seen": total_seen,
            "variants": variants,
        })
    # Rank by how much real signal exists for the evolution/hero split -- cards
    # with a bigger, more-evenly-split real sample first.
    cards.sort(key=lambda c: c["total_seen"], reverse=True)
    return {"cards": cards}


@router.get("/tower-troop-usage")
def tower_troop_usage():
    """Real 'which King Tower Troop do people actually use, how often, how
    well' data (see scripts/retrain_from_collected.py's
    build_tower_troop_usage) -- from the battlelog's real per-match
    supportCards field. Only counts battles collected since this tracking
    was added (2026-08-01), same reasoning as /evolution-usage."""
    df = _load_tower_troop_usage_df()
    if df is None:
        return {"tower_troops": [], "note": "Not enough battles collected since Tower Troop usage tracking was added yet -- check back as fresh battles come in."}
    troops = []
    for _, row in df.sort_values("times_used", ascending=False).iterrows():
        troops.append({
            "name": row["tower_troop"],
            "times_used": int(row["times_used"]),
            "win_rate": round(float(row["win_rate"]) * 100, 2),
            "image_url": get_card_image_url(row["tower_troop"]),
        })
    return {"tower_troops": troops}


@router.get("/elixir-leak-stats")
def elixir_leak_stats():
    """Real average elixir-leaked (unspent elixir sitting idle mid-match, per
    Supercell's own elixirLeaked battlelog field -- confirmed real via direct
    API inspection 2026-08-01) bucketed by deck archetype, so Coaching can
    compare a player's own real recent average against similar decks instead
    of a made-up benchmark. Only counts battles collected since this tracking
    was added, same reasoning as the other post-cutoff aggregations."""
    df = _load_elixir_leak_df()
    if df is None:
        return {"archetypes": [], "note": "Not enough battles collected since elixir-leak tracking was added yet -- check back as fresh battles come in."}
    archetypes = [
        {"archetype": row["archetype"], "avg_elixir_leaked": round(float(row["avg_elixir_leaked"]), 2), "battles": int(row["battles"])}
        for _, row in df.sort_values("battles", ascending=False).iterrows()
    ]
    return {"archetypes": archetypes}
