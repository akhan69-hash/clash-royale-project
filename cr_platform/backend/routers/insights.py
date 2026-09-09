from fastapi import APIRouter
from services.activity_log import summarize

router = APIRouter()


@router.get("/summary")
def insights_summary(days: int = 30):
    """Real usage analytics -- unique visitors/requests per day and which
    real features get used, both derived from data/activity_log.jsonl (the
    activity log every real API request already appends to, see
    services/activity_log.py). No separate tracking pipeline, no new data
    collected beyond what was already being logged -- this just finally
    reads it. Not gated behind auth yet (nothing here is a specific
    person's private data -- session ids are anonymous, random per-browser
    identifiers, never tied to a real name/email); revisit if this grows
    into something that should be admin-only."""
    return summarize(days=min(days, 90))
