"""
Data health and quality endpoints -- transparent info about dataset freshness,
size, and completeness for the user-facing UI (no technical jargon).
"""
import sys
from pathlib import Path
from datetime import datetime
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from services.battle_collector import get_collection_stats  # noqa: E402

router = APIRouter()


@lru_cache(maxsize=1)
def _get_data_quality_snapshot():
    """Summarize dataset freshness and completeness."""
    try:
        # Get collection stats
        stats = get_collection_stats()
        total_battles = stats.get("total_battles", 0)
        unique_players = stats.get("unique_players", 0)
        unique_decks = stats.get("unique_decks_seen", 0)
        date_range_start = stats.get("earliest", "unknown")
        date_range_end = stats.get("latest", "unknown")

        # Check live CSV freshness
        live_csvs = {
            "card_stats": REPO_ROOT / "data" / "card_stats_live.csv",
            "deck_archetypes": REPO_ROOT / "data" / "deck_archetypes_live.csv",
            "card_synergy": REPO_ROOT / "data" / "card_synergy_live.csv",
            "deck_strategy": REPO_ROOT / "data" / "deck_strategy_summary_live.csv",
        }

        csv_status = {}
        for name, path in live_csvs.items():
            if path.exists():
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                age_seconds = (datetime.now() - mtime).total_seconds()
                try:
                    row_count = len(pd.read_csv(path))
                except Exception:
                    row_count = 0
                csv_status[name] = {
                    "exists": True,
                    "updated_at": mtime.isoformat(),
                    "age_seconds": int(age_seconds),
                    "rows": row_count,
                }
            else:
                csv_status[name] = {"exists": False}

        return {
            "total_collected_battles": total_battles,
            "unique_players_seen": unique_players,
            "unique_decks_seen": unique_decks,
            "date_range_start": date_range_start,
            "date_range_end": date_range_end,
            "csv_freshness": csv_status,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@router.get("/data-health")
def data_health():
    """
    Data quality snapshot: how fresh is the analytics data, how much coverage,
    when was it last regenerated. For UI dashboards, transparency with the user.
    """
    snapshot = _get_data_quality_snapshot()

    # Human-readable summary
    if "error" not in snapshot:
        battles = snapshot["total_collected_battles"]
        players = snapshot["unique_players_seen"]
        decks = snapshot["unique_decks_seen"]

        if battles > 1_000_000:
            scale = f"{battles / 1_000_000:.1f}M battles"
        elif battles > 1_000:
            scale = f"{battles / 1_000:.0f}K battles"
        else:
            scale = f"{battles} battles"

        # Real bug fixed (2026-09-09): players/decks can now honestly be
        # None (get_collection_stats' new graceful fallback when Postgres
        # itself is unreachable/degraded, rather than raising) -- f"{None:,}"
        # is a real TypeError, which is exactly what took this whole
        # endpoint down right after that fallback started actually firing.
        players_str = f"{players:,}" if players is not None else "an unknown number of"
        decks_str = f"{decks:,}" if decks is not None else "an unknown number of"
        summary = (
            f"Analyzed {scale} from {players_str} players, "
            f"{decks_str} unique decks. "
        )

        # Check freshness
        card_stats = snapshot["csv_freshness"].get("card_stats", {})
        if card_stats.get("exists"):
            age_hours = card_stats.get("age_seconds", 0) / 3600
            if age_hours < 1:
                freshness = "Updated within the last hour"
            elif age_hours < 24:
                freshness = f"Updated {age_hours:.1f} hours ago"
            else:
                freshness = f"Updated {age_hours / 24:.1f} days ago"
        else:
            freshness = "Data not yet available"

        summary += freshness + "."
    else:
        summary = "Unable to compute data health"

    return {
        "summary": summary,
        "data": snapshot,
    }


def clear_cache():
    """Clear the cached snapshot (called after retraining)."""
    _get_data_quality_snapshot.cache_clear()


@router.post("/clear-cache")
def clear_cache_endpoint():
    """Real bug found 2026-08-23: `clear_cache()` above existed specifically
    "to be called after retraining" but nothing ever actually called it --
    `_get_data_quality_snapshot` is `@lru_cache(maxsize=1)` with no TTL, so
    it would happily keep serving a snapshot from BEFORE a retrain forever,
    until the server process itself happened to restart. That meant the new
    nightly retrain cron (deploy/retrain.sh) wouldn't actually make
    /api/health/data-health's "Updated X ago" reflect the fresh data at all
    -- exactly the "9.1 days ago" staleness this whole investigation started
    from. This endpoint is the missing link retrain.sh now calls right after
    the script finishes, so the displayed freshness catches up same-night
    instead of waiting for the next deploy."""
    clear_cache()
    return {"status": "cleared"}
