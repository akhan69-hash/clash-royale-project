#!/usr/bin/env bash
# Keeps the Postgres `battles` table bounded to a rolling 5-day recent
# window (see scripts/prune_old_battles.py) -- real incident, 2026-09-06:
# Supabase's actual disk quota turned out much tighter than the table's
# unbounded growth, stalling the crawler for two days with a real
# "No space left on device" error. Every pruned row already lives safely in
# data/collected_battles.csv (save_battles() always dual-writes both), so
# this is routine housekeeping, not a destructive operation.
#
# Scheduled daily, after the existing backup/retrain/check_new_cards jobs
# (same low-traffic-hour reasoning) -- cheap (small batched DELETEs + a
# non-FULL VACUUM on an intentionally small table now, not the huge backlog
# this incident had to recover from with a one-off truncate+reload).
set -uo pipefail
cd "$(dirname "$0")/.."

echo "[$(date -u +%FT%TZ)] Pruning old battles from Postgres..."
docker compose exec -T app python3 /app/scripts/prune_old_battles.py
echo "[$(date -u +%FT%TZ)] Prune finished."
