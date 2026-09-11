"""One-time backfill for seen_players/seen_decks (see battle_collector.py's
_archive_connect/_append_archive) -- these two tables only get maintained
INCREMENTALLY for battles collected from 2026-09-11 onward; this populates
them from the full real history that already existed before that.

Deliberately does NOT use SQL COUNT(DISTINCT ...) at any point -- directly
measured that against this project's real row count (6.8M+), on both
Postgres and local SQLite. A single streaming pass over the CSV with
Python's own `set()` for dedup is a real, bounded, one-time memory cost
(a few hundred MB for a script that runs once and exits) rather than a
per-request risk, and avoids the slow-DISTINCT problem entirely.
"""
import csv
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
COLLECTED_PATH = REPO_ROOT / "data" / "collected_battles.csv"
ARCHIVE_DB_PATH = REPO_ROOT / "data" / "battles_archive.db"

BATCH_SIZE = 200_000  # flush to disk periodically so memory for the BATCH stays bounded (the running sets below still grow with real cardinality -- see the docstring)


def main():
    if not COLLECTED_PATH.exists():
        print(f"{COLLECTED_PATH} doesn't exist -- nothing to backfill.")
        return

    conn = sqlite3.connect(ARCHIVE_DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("CREATE TABLE IF NOT EXISTS seen_players (tag TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS seen_decks (deck_key TEXT PRIMARY KEY)")
    conn.commit()

    all_players: set[str] = set()
    all_decks: set[str] = set()
    pending_players: set[str] = set()
    pending_decks: set[str] = set()

    def flush():
        if pending_players:
            conn.executemany("INSERT OR IGNORE INTO seen_players (tag) VALUES (?)", [(p,) for p in pending_players])
            pending_players.clear()
        if pending_decks:
            conn.executemany("INSERT OR IGNORE INTO seen_decks (deck_key) VALUES (?)", [(d,) for d in pending_decks])
            pending_decks.clear()
        conn.commit()

    start = time.monotonic()
    total = 0
    with open(COLLECTED_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            for tag_field in ("team_tag", "opponent_tag"):
                tag = row.get(tag_field, "")
                if tag and tag not in all_players:
                    all_players.add(tag)
                    pending_players.add(tag)
            for cards_field in ("team_cards", "opponent_cards"):
                parts = (row.get(cards_field) or "").split(";")
                if len(parts) == 8 and all(parts):
                    key = ";".join(sorted(parts))
                    if key not in all_decks:
                        all_decks.add(key)
                        pending_decks.add(key)
            if len(pending_players) + len(pending_decks) >= BATCH_SIZE:
                flush()
                elapsed = time.monotonic() - start
                print(f"  processed {total:,} rows ({elapsed:.0f}s) -- "
                      f"{len(all_players):,} unique players, {len(all_decks):,} unique decks so far")
    flush()

    real_players = conn.execute("SELECT COUNT(*) FROM seen_players").fetchone()[0]
    real_decks = conn.execute("SELECT COUNT(*) FROM seen_decks").fetchone()[0]
    conn.close()
    print(f"Done in {time.monotonic() - start:.0f}s. Processed {total:,} CSV rows -> "
          f"{real_players:,} real unique players, {real_decks:,} real unique decks now in {ARCHIVE_DB_PATH}.")


if __name__ == "__main__":
    sys.exit(main())
