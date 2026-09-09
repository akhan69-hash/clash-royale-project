"""
Lightweight, append-only log of what's happening in the app per browser
session -- deliberately kept in its OWN file (data/activity_log.jsonl),
separate from data/collected_battles.csv (real Clash Royale match data from
the crawler/Player Lookup) and from data/crawl_state.json (the crawler's own
frontier state). This is product/usage data about the app itself, not game
data.

Built as foundation only for a planned AI-assisted navigation feature, with
"no dashboard... on top, on purpose... a real design decision for whenever
[that] is built" -- real feedback (2026-09-08), "collect user data and
where they are going and what features they are using," is that decision:
read_recent_events/summarize below turn this same raw log (unchanged --
still just log_activity() appending, still one line per real request) into
the first real usage-analytics view, without needing a second parallel
tracking pipeline. Each request already carries a path that maps
reasonably well to a real feature (see FEATURE_MAP) -- "where they are
going" per exact page isn't 100% precise (a few SPA pages, notably Home,
don't have a distinctive API call of their own), but sessions-per-day,
per-feature usage, and overall traffic trend are all real, honestly
derived from real requests.

One JSON object per line (JSONL), grouped by the frontend's stable
per-browser `X-Session-Id` header (see frontend/src/utils/session.ts) so a
visitor's requests can be reconstructed as one session later, without ever
tearing the file open for a read-modify-write cycle (the exact non-atomic
pattern that caused a real data-loss incident in crawl_state.json earlier in
this project -- append-only sidesteps that class of bug entirely).
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock

REPO_ROOT = Path(__file__).parent.parent.parent.parent
LOG_PATH = REPO_ROOT / "data" / "activity_log.jsonl"

_write_lock = Lock()

# Ordered (first match wins) path-pattern -> human feature label, covering
# every real router prefix registered in main.py. Regexes rather than plain
# prefixes so e.g. /api/players/search and /api/players/{tag} (both real,
# distinct features) don't collide under the same "Player Lookup" bucket.
FEATURE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^/api/players/search"), "Player Search"),
    (re.compile(r"^/api/players/[^/]+/battles"), "Player Lookup - Battle History"),
    (re.compile(r"^/api/players/[^/]+/decks"), "My Decks"),
    (re.compile(r"^/api/players/[^/]+$"), "Player Lookup"),
    (re.compile(r"^/api/coaching"), "Coach"),
    (re.compile(r"^/api/decks/counter"), "Counter Suggester"),
    (re.compile(r"^/api/decks"), "Deck Lab"),
    (re.compile(r"^/api/synergy"), "Synergy"),
    (re.compile(r"^/api/ml"), "Win Predictor"),
    (re.compile(r"^/api/rankings"), "Rankings"),
    (re.compile(r"^/api/meta/deck-lookup"), "Deck Stats Lookup"),
    (re.compile(r"^/api/meta"), "Analytics"),
    (re.compile(r"^/api/cards"), "Browse Cards"),
    (re.compile(r"^/api/whats-next"), "News"),
]


def _feature_for_path(path: str) -> str:
    for pattern, label in FEATURE_MAP:
        if pattern.match(path):
            return label
    return path  # unmapped -- shown as-is rather than silently dropped


def read_recent_events(days: int = 30, max_lines: int = 500_000) -> list[dict]:
    """Bounded read of the tail of the log -- real lesson from this
    project's own repeated OOM incidents (see battle_collector.py's
    _load_cache comments): never assume a real production log file stays
    small just because it's small today. Reads at most the last
    `max_lines` raw lines (cheap, fixed-size), THEN filters to `days` --
    bounding memory first regardless of how far back `days` would
    otherwise reach. Malformed lines (a partial write caught mid-append,
    vanishingly rare given the write lock, but not impossible) are skipped
    rather than raising."""
    if not LOG_PATH.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with open(LOG_PATH, encoding="utf-8") as f:
        lines = f.readlines()[-max_lines:]
    events = []
    for line in lines:
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["ts"])
            if ts >= cutoff:
                events.append(entry)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return events


def summarize(days: int = 30) -> dict:
    """Real usage summary -- unique sessions/requests per day, and which
    real features got used how much, both by request count and by how many
    distinct sessions touched them (a feature hit by 1 session 500 times
    should not look "bigger" than one touched by 100 different sessions
    once each -- both numbers are shown so that distinction stays visible
    rather than collapsed into one count)."""
    events = read_recent_events(days=days)

    daily: dict[str, dict] = {}
    feature_requests: dict[str, int] = defaultdict(int)
    feature_sessions: dict[str, set] = defaultdict(set)
    all_sessions: set = set()

    for e in events:
        date = e["ts"][:10]
        sid = e.get("session_id")
        if date not in daily:
            daily[date] = {"date": date, "requests": 0, "sessions": set()}
        daily[date]["requests"] += 1
        if sid:
            daily[date]["sessions"].add(sid)
            all_sessions.add(sid)
        feature = _feature_for_path(e.get("path", ""))
        feature_requests[feature] += 1
        if sid:
            feature_sessions[feature].add(sid)

    daily_list = [
        {"date": d["date"], "requests": d["requests"], "unique_sessions": len(d["sessions"])}
        for d in sorted(daily.values(), key=lambda d: d["date"])
    ]
    top_features = sorted(
        (
            {"feature": f, "requests": n, "unique_sessions": len(feature_sessions[f])}
            for f, n in feature_requests.items()
        ),
        key=lambda x: x["requests"], reverse=True,
    )

    return {
        "days": days,
        "total_requests": len(events),
        "unique_sessions": len(all_sessions),
        "daily": daily_list,
        "top_features": top_features,
    }


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
