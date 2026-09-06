import sys
from pathlib import Path
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from services.card_service import (
    get_all_cards, get_card_stats, get_card_at_relative_level, get_card_rankings, get_evolution_stat_bonus
)

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.data_loader import load_card_reference, get_card_types  # noqa: E402
from utils.counter_suggester import HARD_COUNTERS, WEAKNESS_COUNTERS  # noqa: E402
from routers.synergy import top_synergies  # noqa: E402
from routers.meta import get_card_arena_eligibility, _load_evolution_hero_usage_df  # noqa: E402

router = APIRouter()

LIVE_CARD_STATS_PATH = REPO_ROOT / "data" / "card_stats_live.csv"


@lru_cache(maxsize=1)
def _live_card_stats() -> dict:
    if not LIVE_CARD_STATS_PATH.exists():
        return {}
    df = pd.read_csv(LIVE_CARD_STATS_PATH)
    return {row["card_name"]: row for _, row in df.iterrows()}


def _who_counters(card_name: str) -> list[str]:
    """Reverse of HARD_COUNTERS -- cards whose curated counter-list includes this one."""
    return [counter for counter, beats in HARD_COUNTERS.items() if card_name in beats]


def _exploited_weaknesses(card_name: str) -> list[str]:
    """Weakness categories this card is a curated exploiter of (e.g. Balloon
    exploits 'no_air_defense')."""
    return [w for w, exploiters in WEAKNESS_COUNTERS.items() if card_name in exploiters]


def _real_evolution_hero_usage(card_name: str) -> dict | None:
    """Real Regular/Evolved/Hero'd usage split for this card (see
    scripts/retrain_from_collected.py's build_card_variant_usage and
    GET /meta/evolution-usage) -- "Knight" is really up to 3 separately
    tracked real cards (Regular/Evolved/Hero), each with its own real win
    rate. None if the card isn't Evolution/Hero capable, or if not enough
    post-tracking battles have been collected yet."""
    df = _load_evolution_hero_usage_df()
    if df is None:
        return None
    rows = df[df["card_name"] == card_name]
    if rows.empty:
        return None
    total_seen = int(rows["total_seen"].iloc[0])
    variants = {
        row["kind"]: {
            "times_used": int(row["times_used"]),
            "active_rate_pct": round(int(row["times_used"]) / total_seen * 100, 1) if total_seen else 0.0,
            "win_rate_pct": round(float(row["win_rate_pct"]), 1),
        }
        for _, row in rows.iterrows()
    }
    return {"total_seen": total_seen, "variants": variants}

@router.get("")  # not "/" -- avoids a 307 redirect_slashes round-trip for
                 # GET /api/cards (no trailing slash, what the frontend
                 # actually calls); harmless in dev but silently swallowed
                 # into a 404 by main.py's SPA catch-all route in production,
                 # since a matching catch-all route short-circuits Starlette's
                 # slash-redirect fallback before it ever gets considered.
def list_cards(
    type: str = Query(None),
    rarity: str = Query(None),
    min_elixir: int = Query(0),
    max_elixir: int = Query(10),
):
    cards = get_all_cards()
    if type:
        cards = [c for c in cards if c['type'].lower() == type.lower()]
    if rarity:
        cards = [c for c in cards if c['rarity'].lower() == rarity.lower()]
    cards = [c for c in cards
             if c['elixir_cost'] is None or min_elixir <= c['elixir_cost'] <= max_elixir]
    return {"items": cards, "count": len(cards)}

@router.get("/rankings")
def card_rankings(
    stat: str = Query("DPS", description="Stat to rank by: DPS, Hitpoints, Damage"),
    per_elixir: bool = Query(False, description="Normalize by elixir cost"),
):
    return get_card_rankings(stat=stat, normalize_by_elixir=per_elixir)

@router.get("/{name}")
def card_detail(name: str, evolved: bool = Query(False, description="Apply the confirmed evolved-form stat bonus, if any")):
    stats = get_card_stats(name, evolved=evolved)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Card '{name}' not found")
    cards = get_all_cards()
    meta = next((c for c in cards if c['name'] == name), {})
    # Exposes the actual bonus fraction (not just whether one exists) so the
    # frontend can show "+25% HP" explicitly rather than a bare number that
    # silently differs from base with no indication why.
    meta["evolution_hp_bonus"] = get_evolution_stat_bonus().get(name, 0.0)
    return {"card": meta, "stats": stats}

@router.get("/{name}/at-level")
def card_at_level(name: str, relative_level: int = Query(11, ge=1, le=16)):
    row = get_card_at_relative_level(name, relative_level)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No data for {name} at level {relative_level}")
    return row


def _build_profile(name: str) -> dict | None:
    """'Why this card is used' synthesis: role tags (researched, see
    data/card_reference.csv's role_confidence column), real synergy partners
    and win rate/presence (all from live-collected battles), and curated
    counters -- composing what already exists elsewhere in the app rather
    than computing anything new. Elixir efficiency is troop-only: applying
    the HP+DPS-based formula to spells/buildings produces a misleading
    number (no sustained HP/DPS for a one-shot spell), so those get an
    explicit 'not applicable' instead of a fabricated figure."""
    ref = load_card_reference()
    row = ref[ref["card_name"] == name]
    if row.empty:
        return None
    row = row.iloc[0]

    card_type = get_card_types().get(name, "Troop")
    live = _live_card_stats().get(name)

    efficiency = None
    if card_type == "Troop":
        level_row = get_card_at_relative_level(name, 11)
        if level_row:
            hp = level_row.get("hitpoints") or 0
            dps = level_row.get("dps") or 0
            elixir = row["elixir"] if pd.notna(row["elixir"]) else None
            if elixir:
                efficiency = round((hp + dps * 4) / elixir, 1)

    return {
        "name": name,
        "type": card_type,
        "roles": [r for r in row["roles"].split(";") if r] if row["roles"] else [],
        "role_confidence": row.get("role_confidence") or None,
        "role_note": row.get("notes") or None,
        "live_stats": {
            "win_rate": round(float(live["win_rate"]) * 100, 2) if live is not None and pd.notna(live["win_rate"]) else None,
            "presence_rate": round(float(live["presence_rate"]) * 100, 2) if live is not None and pd.notna(live["presence_rate"]) else None,
            "times_used": int(live["times_used"]) if live is not None else None,
        } if live is not None else None,
        "efficiency": efficiency,
        "efficiency_note": None if card_type == "Troop" else "Not applicable -- HP/DPS-based efficiency doesn't meaningfully describe a spell or building.",
        "top_synergies": top_synergies(name, top_n=8)["partners"],
        "countered_by": _who_counters(name),
        "exploits_weaknesses": _exploited_weaknesses(name),
        "arena_usage": get_card_arena_eligibility(name),
        "real_evolution_hero_usage": _real_evolution_hero_usage(name),
    }


@router.get("/{name}/profile")
def card_profile(name: str):
    profile = _build_profile(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Card '{name}' not found")
    return profile


@router.post("/profiles")
def card_profiles_bulk(names: list[str]):
    """Same as /{name}/profile but for many cards in one request -- e.g. the
    Coaching page's Card Level Priorities section used to make 8 separate
    round trips for one deck; this collapses that into one. Silently skips
    any name that doesn't resolve rather than failing the whole batch."""
    return {"profiles": [p for p in (_build_profile(n) for n in names) if p is not None]}
