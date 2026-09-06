"""
Keeps the Postgres `battles` table bounded to a rolling recent window, since
Supabase's real disk quota turned out to be much tighter than the table's
actual growth (real incident, 2026-09-05/06: "No space left on device" during
a routine query -- confirmed the underlying disk was still fully saturated
even after dropping 115MB of confirmed-unused indexes, which means the real
provisioned quota is very close to the table's own current size, not just an
index-bloat problem).

Real, already-existing safety net this relies on: services/battle_collector.py's
save_battles() ALREADY writes every accepted battle to BOTH Postgres and a
local CSV (data/collected_battles.csv, via _append_csv()) unconditionally --
confirmed live (2026-09-06): the CSV has 5.66M rows spanning the full crawl
history vs. Postgres's 1.56M, so the CSV is already a complete, currently-
growing archive of everything ever collected, independent of whatever Postgres
retains. Pruning Postgres rows older than HOT_RETENTION_DAYS is therefore
NOT a data-loss operation -- those rows already live safely on the VM's own
(large, cheap) local disk; Postgres only needs to hold what its OWN real-time
serving functions (dedup checks, recent per-player history, live collection-
stats) actually need fast/indexed access to.

"Still use those numbers, but priority to recent" (real feedback, 2026-09-05):
- scripts/retrain_from_collected.py ALREADY reads from the local CSV (not
  Postgres) with its own RETENTION_WINDOW_DAYS=120 for the "live" analytics
  the app actually displays (card win rates, deck archetypes, etc.) -- this
  is the existing recency-priority mechanism, untouched by this script.
- get_collection_stats()'s "total_battles"/"earliest"/"latest" now come from
  a small incrementally-maintained data/lifetime_totals.json (see
  battle_collector.py's _update_lifetime_totals(), called from _append_csv())
  instead of Postgres's own row count -- so pruning Postgres doesn't make the
  app's own displayed "how many battles have we ever collected" figure
  silently shrink. unique_players/unique_opponents/unique_decks_seen stay
  Postgres-derived (now honestly scoped to "within the retained recent
  window" -- exact all-time set-cardinality tracking would need holding
  millions of tags/decks in memory forever, the exact OOM pattern this
  project has hit four separate times already; not worth reintroducing for
  numbers that were never the headline figure).

Deletes in small batches (bounded by battle_time, not one giant DELETE) so a
single transaction never needs much WAL/temp space -- deliberately gentle
given the disk is already tight. Safe to run repeatedly; a batch that finds
nothing older than the cutoff is a no-op.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg2

# Lowered from an initial 14 (2026-09-06): real measured growth showed ~80%
# of all retained rows were within the last 14 days already -- crawl volume
# has clearly accelerated since this table's early days, so 14 days' worth
# is no longer the small/safe window it was meant to be. 5 days, run daily,
# keeps the steady-state table small enough that regular VACUUM (non-FULL,
# see below) can actually reuse the space DELETE frees for new inserts
# before the file needs to grow -- real Postgres disk quota headroom is
# still very tight (see the 2026-09-06 incident writeup), so err small.
HOT_RETENTION_DAYS = int(os.getenv("HOT_RETENTION_DAYS", "5"))
BATCH_SIZE = 20_000


def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL not set -- nothing to prune (legacy CSV-only mode).")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=HOT_RETENTION_DAYS)).isoformat()
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    total_deleted = 0
    try:
        with conn.cursor() as cur:
            while True:
                # Batch by primary key via a subquery -- avoids one huge
                # DELETE...WHERE battle_time<cutoff needing to sort/hold every
                # matching row's ctids at once.
                cur.execute(
                    "DELETE FROM battles WHERE id IN "
                    "(SELECT id FROM battles WHERE battle_time < %s ORDER BY id LIMIT %s)",
                    (cutoff, BATCH_SIZE),
                )
                deleted = cur.rowcount
                total_deleted += deleted
                if deleted == 0:
                    break
                print(f"  deleted {deleted} rows older than {cutoff} (running total: {total_deleted:,})")
        if total_deleted:
            try:
                with conn.cursor() as cur:
                    cur.execute("VACUUM battles")  # reclaims space DELETE alone leaves as reusable-but-not-freed
            except psycopg2.Error as e:
                # Non-fatal -- the DELETEs above are the real fix; VACUUM is a
                # bonus cleanup that can succeed on a later run once there's
                # more headroom (e.g. if the disk was too full for even this).
                print(f"VACUUM failed (non-fatal, deletes already committed): {e}")
                conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
                print("DB size after prune:", cur.fetchone()[0])
        print(f"Pruned {total_deleted:,} battles older than {HOT_RETENTION_DAYS} days from Postgres "
              f"(already preserved in data/collected_battles.csv).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
