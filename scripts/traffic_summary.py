"""
Summarizes data/activity_log.jsonl (see cr_platform/backend/services/
activity_log.py) into plain, human-readable traffic/usage stats -- real
feedback (2026-08-21): "how do i monitor traffic and user interaction with
the product." There's no in-app dashboard for this yet (the log was built
as a foundation for a future AI-nav feature, nothing reads it besides this
script), so this is the fastest real way to see what's actually happening:
SSH into the server and run it.

Usage (SSH into the server, from ~/royaleiq -- run directly on the host,
not inside the container: data/ is bind-mounted from here, but scripts/
is baked into the image at build time, so a script added after the last
deploy won't exist inside the running container until the next deploy):
    python3 scripts/traffic_summary.py
    python3 scripts/traffic_summary.py --days 1
    python3 scripts/traffic_summary.py --days 7 --top 20

Or locally against a copy of the log for testing.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LOG_PATH = REPO_ROOT / "data" / "activity_log.jsonl"

# Collapses dynamic path segments (a player tag, a card name) so
# /api/players/ABC123/battles and /api/players/XYZ789/battles count as the
# SAME route instead of 100k different ones -- otherwise "top paths" is
# useless noise.
_TAG_RE = re.compile(r"/api/players/[^/]+")


def _normalize_path(path: str) -> str:
    return _TAG_RE.sub("/api/players/{tag}", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, help="Only count activity from the last N days (default 7).")
    ap.add_argument("--top", type=int, default=15, help="How many top paths/tags to show (default 15).")
    args = ap.parse_args()

    if not LOG_PATH.exists():
        print(f"No activity log found at {LOG_PATH} -- nothing collected yet.")
        sys.exit(0)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    sessions: set[str] = set()
    player_tags: Counter[str] = Counter()
    paths: Counter[str] = Counter()
    statuses: Counter[int] = Counter()
    by_day: Counter[str] = Counter()
    total = 0
    skipped_older = 0
    bad_lines = 0

    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            try:
                ts = datetime.fromisoformat(row["ts"])
            except (KeyError, ValueError):
                bad_lines += 1
                continue
            if ts < cutoff:
                skipped_older += 1
                continue
            total += 1
            sessions.add(row.get("session_id", ""))
            if row.get("player_tag"):
                player_tags[row["player_tag"]] += 1
            paths[_normalize_path(row.get("path", ""))] += 1
            statuses[row.get("status_code", 0)] += 1
            by_day[ts.date().isoformat()] += 1

    print(f"=== Royale IQ traffic summary (last {args.days} day{'s' if args.days != 1 else ''}) ===\n")
    print(f"Requests:        {total:,}")
    print(f"Unique sessions: {len(sessions):,}")
    print(f"Unique player tags looked up: {len(player_tags):,}")
    if bad_lines:
        print(f"(skipped {bad_lines} malformed lines)")
    print(f"(+{skipped_older:,} older requests outside this window -- widen with --days)\n")

    if by_day:
        print("Requests per day:")
        for day in sorted(by_day):
            print(f"  {day}  {by_day[day]:>6,}")
        print()

    if paths:
        print(f"Top {args.top} paths:")
        for path, count in paths.most_common(args.top):
            print(f"  {count:>6,}  {path}")
        print()

    if player_tags:
        print(f"Top {args.top} most-looked-up player tags:")
        for tag, count in player_tags.most_common(args.top):
            print(f"  {count:>4,}x  {tag}")
        print()

    if statuses:
        print("Status codes:")
        for code, count in sorted(statuses.items()):
            print(f"  {code}: {count:,}")


if __name__ == "__main__":
    main()
