"""
Emergency disk-space recovery (2026-09-06): plain DELETE + VACUUM (see
prune_old_battles.py) turned out NOT to be enough -- Postgres's non-FULL
VACUUM only marks space reusable for future inserts into the SAME table, it
never shrinks the file on disk or returns space to the OS. Confirmed live:
after deleting 309K rows the reported DB size didn't move (1333->1335MB) and
the crawler was still hitting the exact same DiskFull error. VACUUM FULL
would actually shrink the table, but needs temp space to write the
compacted copy -- exactly what a disk already at zero free bytes doesn't
have.

TRUNCATE is different: it deallocates the entire table's storage instantly,
no temp space needed (that's what makes it safe here). This script:
  1. Reads only the most recent MAX_ROWS lines of data/collected_battles.csv
     (bounded-deque tail read, same memory-safe pattern
     scripts/retrain_from_collected.py's load_collected() already uses --
     never holds the whole 5.66M-row/2GB file in memory).
  2. TRUNCATEs the battles table (instant, frees 100% of its disk space).
  3. Re-inserts just that recent slice back in, in small batches.

Real growth-rate finding that changed the approach from a date cutoff to a
row-count cap: prune_old_battles.py's first run found ~80% of ALL rows in
Postgres were within the last 14 days (recent crawl volume has clearly
accelerated) -- a "keep N days" cutoff is unpredictable when growth itself
is accelerating, but "keep exactly N rows" is a firm, known size budget
regardless of how fast new battles arrive. MAX_ROWS below is sized to stay
comfortably inside whatever the real (apparently very tight) disk quota is.

Every row this drops from Postgres already lives safely in the local CSV
(confirmed complete and current, 2026-09-06) -- this is a real capacity
fix, not a data-loss operation.
"""
import csv
import io
import os
import sys
from collections import deque
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

REPO_ROOT = Path(__file__).parent.parent
COLLECTED_PATH = REPO_ROOT / "data" / "collected_battles.csv"

MAX_ROWS = int(os.getenv("REBUILD_MAX_ROWS", "150000"))
INSERT_BATCH = 5_000

FIELDNAMES = [
    "battle_time", "game_mode", "team_tag", "team_name", "team_cards",
    "team_crowns", "team_trophies", "team_avg_level", "opponent_tag", "opponent_name", "opponent_cards",
    "opponent_crowns", "opponent_trophies", "opponent_avg_level", "result", "collected_at",
    "team_evolved_cards", "team_hero_cards", "opponent_evolved_cards", "opponent_hero_cards",
    "team_tower_troop", "opponent_tower_troop", "team_elixir_leaked", "opponent_elixir_leaked",
    "team_ambiguous_cards", "opponent_ambiguous_cards",
]
ARRAY_COLUMNS = {
    "team_cards", "opponent_cards", "team_evolved_cards", "team_hero_cards",
    "opponent_evolved_cards", "opponent_hero_cards", "team_ambiguous_cards", "opponent_ambiguous_cards",
}
INT_COLUMNS = {"team_crowns", "team_trophies", "opponent_crowns", "opponent_trophies"}
FLOAT_COLUMNS = {"team_avg_level", "opponent_avg_level", "team_elixir_leaked", "opponent_elixir_leaked"}


def _row_for_pg(row: dict) -> tuple:
    """Copied verbatim from battle_collector.py's _row_for_pg (not imported,
    since this is a standalone one-off recovery script outside the running
    app's request path) -- same CSV-string -> Postgres-typed conversion,
    kept byte-for-byte identical so a real INT/FLOAT column type never
    mismatches what the live app itself would have written."""
    out = []
    for col in FIELDNAMES:
        v = row.get(col, "")
        if col in ARRAY_COLUMNS:
            out.append([c for c in v.split(";") if c] if v else [])
        elif col in INT_COLUMNS:
            out.append(int(v) if v not in (None, "") else None)
        elif col in FLOAT_COLUMNS:
            out.append(float(v) if v not in (None, "") else None)
        else:
            out.append(v or None)
    return tuple(out)


def read_tail(max_rows: int) -> list[dict]:
    print(f"Reading the most recent {max_rows:,} rows of {COLLECTED_PATH} (streaming, bounded memory)...")
    with open(COLLECTED_PATH, "r", encoding="utf-8", newline="") as f:
        header = f.readline()
        tail = deque(f, maxlen=max_rows)
    reader = csv.DictReader(io.StringIO(header + "".join(tail)), fieldnames=None)
    rows = list(reader)
    print(f"Read {len(rows):,} rows.")
    return rows


def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL not set -- nothing to rebuild.")
        return

    rows = read_tail(MAX_ROWS)
    if not rows:
        print("No rows read from the local CSV -- aborting, NOT truncating (nothing safe to reload).")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            print("Truncating battles table (instant, frees all its disk space)...")
            cur.execute("TRUNCATE TABLE battles")
            conn.commit()
            print("Truncated. Reloading recent rows in batches...")

            insert_sql = f"""
                INSERT INTO battles ({", ".join(FIELDNAMES)})
                VALUES %s
                ON CONFLICT ON CONSTRAINT battles_dedup_key DO NOTHING
            """
            total = 0
            for i in range(0, len(rows), INSERT_BATCH):
                batch = rows[i:i + INSERT_BATCH]
                execute_values(cur, insert_sql, [_row_for_pg(r) for r in batch])
                conn.commit()
                total += len(batch)
                print(f"  reloaded {total:,} / {len(rows):,}")

            cur.execute("SELECT count(*) FROM battles")
            real_count = cur.fetchone()[0]
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            size = cur.fetchone()[0]
            print(f"Done. battles now has {real_count:,} real rows. DB size: {size}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
