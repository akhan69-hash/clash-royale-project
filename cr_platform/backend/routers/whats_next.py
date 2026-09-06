"""
"What's Next" -- upcoming/recent Clash Royale content (season info, balance
changes, new cards), hand-researched via WebSearch/WebFetch against real
sources (RoyaleAPI's news blog, community trackers) and cited per entry.

This is inherently time-sensitive editorial content, not derived from our
own data pipeline -- there's no automated refresh here. `data/whats_next.json`
carries its own `research_date` so staleness is visible rather than hidden.
Keeping it current requires periodically re-running the research pass (a
scheduled agent could automate that later; not built this pass).
"""
import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

REPO_ROOT = Path(__file__).parent.parent.parent.parent
WHATS_NEXT_PATH = REPO_ROOT / "data" / "whats_next.json"


@router.get("")
def whats_next():
    if not WHATS_NEXT_PATH.exists():
        return {"research_date": None, "entries": []}
    with open(WHATS_NEXT_PATH, encoding="utf-8") as f:
        return json.load(f)
