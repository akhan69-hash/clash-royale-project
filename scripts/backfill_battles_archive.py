"""
One-time backfill for the new local SQLite personal-data archive (see
battle_collector.py's ARCHIVE_DB_PATH / _archive_connect for why this
exists -- real regression fix, 2026-09-07: My Decks lost most of a player's
real history once Postgres got bounded to a small recent window during the
disk-space emergency).

Streams data/collected_battles.csv in fixed-size batches (never holding more
than BATCH_SIZE rows in memory at once -- the same memory-safety discipline
this project has had to relearn after 4 real OOM incidents) and inserts
everything into the SQLite archive, which then has the FULL real history
with a real index on team_tag.

Safe to interrupt and rerun: uses INSERT OR IGNORE against a unique index on
the same (battle_time, team_tag, opponent_tag) dedup key Postgres already
enforces, so a partial prior run just gets topped up, not duplicated.

Run once: python scripts/backfill_battles_archive.py
"""
import csv
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "cr_platform" / "backend"))

from services.battle_collector import FIELDNAMES, ARCHIVE_DB_PATH, COLLECTED_PATH  # noqa: E402

BATCH_SIZE = 50_000


def main():
    if not COLLECTED_PATH.exists():
        print(f"{COLLECTED_PATH} doesn't exist -- nothing to backfill.")
        return

    conn = sqlite3.connect(ARCHIVE_DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; real write-speed win for a bulk one-time load
    cols = ", ".join(f'"{c}" TEXT' for c in FIELDNAMES)
    conn.execute(f"CREATE TABLE IF NOT EXISTS battles ({cols})")
    # Real dedup guarantee -- INSERT OR IGNORE below relies on this unique
    # index existing, so a rerun (or overlap with battle_collector.py's own
    # ongoing _append_archive calls during a long backfill) never double-counts.
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_archive_dedup ON battles(battle_time, team_tag, opponent_tag)")
    conn.commit()

    placeholders = ", ".join("?" for _ in FIELDNAMES)
    insert_sql = f"INSERT OR IGNORE INTO battles ({', '.join(FIELDNAMES)}) VALUES ({placeholders})"

    start = time.monotonic()
    total = 0
    batch = []
    with open(COLLECTED_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            batch.append(tuple(row.get(c, "") for c in FIELDNAMES))
            if len(batch) >= BATCH_SIZE:
                conn.executemany(insert_sql, batch)
                conn.commit()
                total += len(batch)
                elapsed = time.monotonic() - start
                print(f"  imported {total:,} rows ({elapsed:.0f}s elapsed)")
                batch = []
        if batch:
            conn.executemany(insert_sql, batch)
            conn.commit()
            total += len(batch)

    # The real index used for actual per-player lookups (the whole point of
    # this archive) -- built once at the end, after the bulk load, since
    # building it incrementally during millions of inserts would be far
    # slower than one pass at the end.
    print("Building the real team_tag lookup index...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_team_tag ON battles(team_tag)")
    # Search-support indexes (2026-09-08, "make my search engine stronger and
    # faster") -- must match battle_collector.py's _archive_connect exactly,
    # see its comment for why opponent_tag and the two NOCASE name indexes
    # exist. Built here too, post-bulk-load like the index above, so a fresh
    # backfill run gets full search support immediately instead of paying
    # for it on the app's first live search after deploy.
    print("Building the real search-support indexes...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_opponent_tag ON battles(opponent_tag)")
    # Composite/covering -- see battle_collector.py's _archive_connect for
    # why the tag column is included (avoids a base-table lookup per match).
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_team_name_nocase ON battles(team_name COLLATE NOCASE, team_tag)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_opponent_name_nocase ON battles(opponent_name COLLATE NOCASE, opponent_tag)")
    conn.commit()

    cur = conn.execute("SELECT count(*) FROM battles")
    real_count = cur.fetchone()[0]
    conn.close()
    print(f"Done. Processed {total:,} CSV rows -> {real_count:,} real rows now in {ARCHIVE_DB_PATH} "
          f"(some may have been duplicates, correctly ignored).")


if __name__ == "__main__":
    main()
