"""
One-time migration: data/collected_battles.csv -> a Supabase (Postgres)
`battles` table (see supabase/schema.sql). Run this ONCE the schema has been
applied to a real Supabase project, with SUPABASE_DB_URL set to that
project's connection string (Supabase dashboard -> Project Settings ->
Database -> Connection string -- use the "Session pooler" URI for a
long-running batch import like this one, not the pgbouncer transaction
pooler, which caps statement size in ways that don't play well with batched
COPY/execute_values).

Usage:
    export SUPABASE_DB_URL="postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"
    python3 scripts/migrate_to_supabase.py --batch-size 5000

Idempotent/safe to re-run: relies on the same (battle_time, team_tag,
opponent_tag) unique constraint the CSV era's in-memory dedup used --
`ON CONFLICT DO NOTHING` means running this twice (e.g. after it's
interrupted partway through a 4M+ row file) never double-inserts.

Deliberately NOT wired into the app yet -- this only moves the data. Once
verified (row counts match, spot-check a few real player tags), a SEPARATE
follow-up rewrites battle_collector.py's read/write path to query Postgres
instead of parsing the CSV -- that's the part that actually removes the
in-memory-full-file-load risk this migration exists to fix, and is
deliberately scoped as its own change so a mistake in the data copy doesn't
get compounded with a mistake in the app's query logic at the same time.
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
COLLECTED_PATH = REPO_ROOT / "data" / "collected_battles.csv"

# Same column list as battle_collector.py's FIELDNAMES -- kept in sync
# manually (not imported) since that module has its own sys.path/import
# setup this standalone script doesn't need to pull in.
CSV_COLUMNS = [
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

INSERT_SQL = f"""
    INSERT INTO battles ({", ".join(CSV_COLUMNS)})
    VALUES %s
    ON CONFLICT ON CONSTRAINT battles_dedup_key DO NOTHING
"""


def _to_array(value: str) -> list[str]:
    return [c for c in value.split(";") if c] if value else []


def _to_int(value: str):
    return int(value) if value not in (None, "") else None


def _to_float(value: str):
    return float(value) if value not in (None, "") else None


def _row_to_tuple(row: dict) -> tuple:
    out = []
    for col in CSV_COLUMNS:
        v = row.get(col, "")
        if col in ARRAY_COLUMNS:
            out.append(_to_array(v))
        elif col in INT_COLUMNS:
            out.append(_to_int(v))
        elif col in FLOAT_COLUMNS:
            out.append(_to_float(v))
        else:
            out.append(v or None)
    return tuple(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--limit", type=int, default=None, help="Stop after N rows (for a quick test run first).")
    ap.add_argument("--since-days", type=int, default=None,
                     help="Only migrate rows with collected_at within the last N days -- real "
                          "production incident (2026-08-28): the free Supabase tier caps a "
                          "database at 500MB, and the full 4.3M+-row history alone is well over "
                          "that once indexed. Skipping older rows client-side (before they're "
                          "even sent) keeps this within budget instead of failing partway "
                          "through with a read-only-transaction error.")
    args = ap.parse_args()
    since_cutoff = (
        (datetime.now(timezone.utc) - timedelta(days=args.since_days)).isoformat()
        if args.since_days else None
    )

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("Set SUPABASE_DB_URL to your Supabase project's Postgres connection string first.")
        sys.exit(1)

    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        print("Missing dependency: pip install psycopg2-binary")
        sys.exit(1)

    if not COLLECTED_PATH.exists():
        print(f"No file at {COLLECTED_PATH}")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    total = 0
    inserted = 0
    start = time.monotonic()

    try:
        with conn.cursor() as cur, open(COLLECTED_PATH, encoding="utf-8", newline="") as f:
            batch = []
            skipped_old = 0
            for row in csv.DictReader(f):
                if since_cutoff and row.get("collected_at", "") < since_cutoff:
                    skipped_old += 1
                    continue
                batch.append(_row_to_tuple(row))
                total += 1
                if len(batch) >= args.batch_size:
                    execute_values(cur, INSERT_SQL, batch)
                    inserted += cur.rowcount
                    conn.commit()
                    batch = []
                    elapsed = time.monotonic() - start
                    print(f"  {total:,} read, {inserted:,} inserted so far ({elapsed:.0f}s elapsed)")
                if args.limit and total >= args.limit:
                    break
            if batch:
                execute_values(cur, INSERT_SQL, batch)
                inserted += cur.rowcount
                conn.commit()
    finally:
        conn.close()

    skip_note = f" ({skipped_old:,} older rows skipped via --since-days {args.since_days})" if since_cutoff else ""
    print(f"\nDone. {total:,} rows read from CSV{skip_note}, {inserted:,} new rows inserted "
          f"(the rest were already-migrated duplicates, safe on a re-run) in {time.monotonic() - start:.0f}s.")


if __name__ == "__main__":
    main()
