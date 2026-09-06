from pathlib import Path
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, Query

from services.card_service import get_card_image_url
from utils.data_loader import get_card_list, get_card_types, get_elixir_costs

router = APIRouter()

REPO_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
MIN_LIVE_CO_OCCURRENCE = 10  # ignore real pairs seen fewer times than this (too noisy)

MIN_USES_FOR_SUGGEST_WIN_RATE = 10  # same noise floor decks.py's counter endpoint uses
# Not imported from routers.meta -- meta.py already imports get_synergy_score
# FROM this module, so importing meta.py back here would be a circular
# import. Self-contained loader instead, same shape as meta.py's.
_LIVE_CARD_STATS_PATH = REPO_ROOT / "data" / "card_stats_live.csv"


@lru_cache(maxsize=1)
def _load_card_win_rates() -> dict[str, float]:
    if not _LIVE_CARD_STATS_PATH.exists():
        return {}
    df = pd.read_csv(_LIVE_CARD_STATS_PATH)
    reliable = df[df["times_used"] >= MIN_USES_FOR_SUGGEST_WIN_RATE]
    return dict(zip(reliable["card_name"], reliable["win_rate"]))

# Curated fallback pairs for cards/combos with no (or too little) real match data --
# ported as-is from pages/3_Card_Synergy_Graph.py so both apps agree.
SYNERGY_PAIRS = {
    ("Giant", "Musketeer"): 9, ("Giant", "Witch"): 8, ("Giant", "Wizard"): 8,
    ("Giant", "Electro Wizard"): 7, ("Giant", "Mega Minion"): 7,
    ("Golem", "Night Witch"): 10, ("Golem", "Baby Dragon"): 9, ("Golem", "Lumberjack"): 9,
    ("Golem", "Electro Wizard"): 8,
    ("Hog Rider", "Zap"): 10, ("Hog Rider", "The Log"): 9, ("Hog Rider", "Ice Golem"): 8,
    ("Hog Rider", "Musketeer"): 7,
    ("Balloon", "Lumberjack"): 10, ("Balloon", "Freeze"): 9, ("Balloon", "Inferno Dragon"): 8,
    ("Balloon", "Bat"): 7,
    ("X-Bow", "Tesla"): 9, ("X-Bow", "Ice Spirit"): 8, ("X-Bow", "The Log"): 8,
    ("X-Bow", "Archers"): 7,
    ("Mortar", "Giant Snowball"): 8, ("Mortar", "Goblin"): 7,
    ("Lava Hound", "Balloon"): 10, ("Lava Hound", "Inferno Dragon"): 9, ("Lava Hound", "Bat"): 8,
    ("Miner", "Goblin Barrel"): 9, ("Miner", "Poison"): 8, ("Miner", "Princess"): 7,
    ("Goblin Barrel", "Princess"): 9, ("Goblin Barrel", "Dart Goblin"): 7, ("Goblin Barrel", "Zap"): 8,
    ("Graveyard", "Freeze"): 10, ("Graveyard", "Poison"): 9, ("Graveyard", "Ice Golem"): 8,
    ("P.E.K.K.A", "Battle Ram"): 9, ("P.E.K.K.A", "Electro Wizard"): 8,
    ("Sparky", "Goblin Gang"): 8, ("Sparky", "Ice Spirit"): 8, ("Sparky", "Zap"): 7,
    ("Three Musketeers", "Elixir Collector"): 10, ("Three Musketeers", "Battle Ram"): 8,
    ("Battle Ram", "Zap"): 8, ("Battle Ram", "Goblin Gang"): 7,
    ("Mega Knight", "Goblin Barrel"): 9, ("Mega Knight", "Skeleton"): 8, ("Mega Knight", "Zap"): 7,
    ("Electro Giant", "Zap"): 9, ("Electro Giant", "Electro Spirit"): 8,
    ("Royal Giant", "Furnace"): 8, ("Royal Giant", "Musketeer"): 7,
    ("Knight", "Fireball"): 7, ("Knight", "Musketeer"): 8,
    ("Valkyrie", "Hog Rider"): 8, ("Valkyrie", "Miner"): 7,
    ("Ice Wizard", "Tornado"): 10, ("Ice Wizard", "Graveyard"): 9,
    ("Bowler", "Graveyard"): 9, ("Bowler", "Goblin Barrel"): 7,
    ("Night Witch", "Golem"): 10, ("Night Witch", "Giant"): 8,
    ("Witch", "Giant"): 8, ("Witch", "Golem"): 7,
    ("Executioner", "Tornado"): 10, ("Executioner", "Goblin Barrel"): 7,
    ("Lumberjack", "Balloon"): 10, ("Lumberjack", "Golem"): 8,
    ("Fisherman", "Inferno Tower"): 8, ("Fisherman", "Inferno Dragon"): 7,
    ("Ram Rider", "Zap"): 8, ("Ram Rider", "Goblin Barrel"): 7,
    ("Golden Knight", "Goblin Barrel"): 8, ("Skeleton King", "Skeleton"): 8,
    ("Archer Queen", "Giant"): 8, ("Monk", "Giant"): 7,
}


def _load_synergy_csv(filename: str) -> dict | None:
    path = DATA_DIR / filename
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


@lru_cache(maxsize=1)
def _load_live_synergy() -> dict | None:
    return _load_synergy_csv("card_synergy_live.csv")


def _best_entry(card_a: str, card_b: str) -> tuple[dict | None, str]:
    """Real, current, growing battle data takes priority; the curated rule
    list is the last resort for pairs with no real co-occurrence data yet.
    Returns (entry, source) where source is 'live' or 'rule'. The 2023
    historical-dataset fallback tier has been retired entirely."""
    key = tuple(sorted((card_a, card_b)))

    live = _load_live_synergy()
    if live is not None:
        entry = live.get(key)
        if entry and entry["co_occurrence"] >= MIN_LIVE_CO_OCCURRENCE:
            return entry, "live"

    return None, "rule"


def get_synergy_score(card_a: str, card_b: str) -> float:
    """Context-free pairwise score for the deck-network view (a handful of
    user-picked cards, not "all partners of X" -- no percentile context to
    rank against). Real data still wins on win-rate-together; curated rule
    pairs are the fallback when there's no real co-occurrence at all."""
    entry, _ = _best_entry(card_a, card_b)
    if entry:
        return round(entry["win_rate_together"] * 10, 1)
    return SYNERGY_PAIRS.get((card_a, card_b), SYNERGY_PAIRS.get((card_b, card_a), 0))


def _rank_score(co_percentile: float, win_rate: float) -> float:
    """Blends 'how often real players actually pair these' (percentile rank
    of co_occurrence among this card's OTHER real partners -- comparable
    across cards regardless of how generically popular either card is) with
    a smaller bonus for outperforming the ~50% ladder-matchmaking baseline.
    Weighted toward frequency since that's the literal "commonly used
    together" signal a real player recognizes -- win rate on its own is
    noisy this close to 50/50 and shouldn't be the only thing that decides
    whether an obviously-common real combo shows up in the list."""
    freq_component = co_percentile * 7  # 0-7
    quality_component = max(0.0, min(win_rate - 0.45, 0.10)) / 0.10 * 3  # 0-3
    return round(freq_component + quality_component, 2)


@router.get("/{card}")
def top_synergies(card: str, top_n: int = Query(200, ge=1, le=250)):
    """All real/curated partners for a card, ranked so that real live match
    data always outranks a curated guess -- a guess is only shown for cards
    with no real co-occurrence data at all (the 2023 historical-dataset
    fallback tier this docstring used to also mention has been fully
    retired, see _best_entry). top_n
    defaults to effectively "all" so the frontend can scroll through the
    full list instead of being cut off at an arbitrary top-10."""
    card_list = get_card_list()
    card_types = get_card_types()
    elixir_costs = get_elixir_costs()

    raw = []
    for other in card_list:
        if other == card:
            continue
        entry, source = _best_entry(card, other)
        if entry:
            raw.append({"partner": other, "source": source,
                        "co_occurrence": entry["co_occurrence"],
                        "win_rate_together": entry["win_rate_together"]})
        else:
            rule_score = SYNERGY_PAIRS.get((card, other), SYNERGY_PAIRS.get((other, card), 0))
            if rule_score > 0:
                raw.append({"partner": other, "source": "rule", "co_occurrence": None,
                            "win_rate_together": None, "score": rule_score})

    # Percentile-rank co_occurrence within the live-data tier, so a pair's
    # rank reflects how common it is RELATIVE TO this card's other real
    # partners, not diluted by how generically popular either card is.
    live_rows = [r for r in raw if r["source"] == "live"]
    if live_rows:
        counts = sorted(r["co_occurrence"] for r in live_rows)
        n = len(counts)
        for r in live_rows:
            pct = sum(1 for c in counts if c <= r["co_occurrence"]) / n
            r["score"] = _rank_score(pct, r["win_rate_together"])

    TIER_RANK = {"live": 0, "rule": 1}
    raw.sort(key=lambda r: (TIER_RANK[r["source"]], -r["score"]))

    results = []
    for r in raw[:top_n]:
        results.append({
            "partner": r["partner"],
            "score": r["score"],
            "source": r["source"],
            "co_occurrence": r["co_occurrence"],
            "win_rate_together": round(r["win_rate_together"] * 100, 1) if r["win_rate_together"] is not None else None,
            "type": card_types.get(r["partner"], "Troop"),
            "elixir": elixir_costs.get(r["partner"]),
            "image_url": get_card_image_url(r["partner"]),
        })
    return {"card": card, "total_partners": len(raw), "partners": results}


@router.post("/network")
def synergy_network(cards: list[str]):
    """Pairwise synergy matrix + per-card totals for a set of up to 8 cards."""
    cards = cards[:8]
    matrix = []
    for a in cards:
        row = {"card": a}
        for b in cards:
            row[b] = get_synergy_score(a, b) if a != b else 0
        matrix.append(row)

    totals = {
        a: round(sum(get_synergy_score(a, b) for b in cards if b != a), 1)
        for a in cards
    }
    return {"cards": cards, "matrix": matrix, "totals": totals}


@router.post("/suggest")
def suggest_cards(cards: list[str], top_n: int = Query(12, ge=1, le=30)):
    """Given a partial (or full) deck, real cards to ADD for better synergy --
    every real card not already in `cards`, ranked by its average real
    synergy score (get_synergy_score) against every card already selected,
    with each candidate's own real overall win rate shown alongside (not
    blended into the rank -- shown separately so a user can weigh both, same
    honesty as everywhere else real win rate is surfaced). With an empty
    `cards` list, falls back to ranking by real overall win rate alone
    (there's nothing to be synergistic WITH yet)."""
    cards = cards[:8]
    all_cards = get_card_list()
    card_types = get_card_types()
    elixir_costs = get_elixir_costs()
    win_rates = _load_card_win_rates()

    candidates = [c for c in all_cards if c not in cards and card_types.get(c) != "Tower Troop"]

    results = []
    for cand in candidates:
        if cards:
            avg_synergy = round(sum(get_synergy_score(cand, c) for c in cards) / len(cards), 2)
        else:
            avg_synergy = None
        results.append({
            "name": cand,
            "avg_synergy": avg_synergy,
            "win_rate_pct": round(win_rates[cand] * 100, 1) if cand in win_rates else None,
            "type": card_types.get(cand, "Troop"),
            "elixir": elixir_costs.get(cand),
            "image_url": get_card_image_url(cand),
        })

    if cards:
        results.sort(key=lambda r: r["avg_synergy"] if r["avg_synergy"] is not None else -1, reverse=True)
    else:
        results.sort(key=lambda r: r["win_rate_pct"] if r["win_rate_pct"] is not None else -1, reverse=True)

    return {"suggestions": results[:top_n]}
