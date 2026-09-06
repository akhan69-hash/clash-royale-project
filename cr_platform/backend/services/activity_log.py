"""
Lightweight, append-only log of what's happening in the app per browser
session -- deliberately kept in its OWN file (data/activity_log.jsonl),
separate from data/collected_battles.csv (real Clash Royale match data from
the crawler/Player Lookup) and from data/crawl_state.json (the crawler's own
frontier state). This is product/usage data about the app itself, not game
data.

Foundation only, built for a specific stated future use: a planned
AI-assisted navigation feature that will need to understand what a visitor
has actually been doing across their whole visit. Nothing reads this file
yet beyond appending to it -- no dashboard, no analytics queries built on
top, on purpose (that's a real design decision for whenever the AI feature
is actually built, not to be guessed at now).

One JSON object per line (JSONL), grouped by the frontend's stable
per-browser `X-Session-Id` header (see frontend/src/utils/session.ts) so a
visitor's requests can be reconstructed as one session later, without ever
tearing the file open for a read-modify-write cycle (the exact non-atomic
pattern that caused a real data-loss incident in crawl_state.json earlier in
this project -- append-only sidesteps that class of bug entirely).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

REPO_ROOT = Path(__file__).parent.parent.parent.parent
LOG_PATH = REPO_ROOT / "data" / "activity_log.jsonl"

_write_lock = Lock()


def log_activity(session_id: str | None, player_tag: str | None, method: str, path: str, status_code: int) -> None:
    if not session_id:
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "player_tag": player_tag,
        "method": method,
        "path": path,
        "status_code": status_code,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    # A plain lock (not a full atomic-temp-file swap) is the right amount of
    # care here -- this is a pure append, never a read-modify-write, so the
    # only real race is two threads' writes interleaving mid-line; the lock
    # prevents that without needing crawl_state.json's heavier machinery
    # (which exists because THAT file is fully rewritten on every save).
    with _write_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
