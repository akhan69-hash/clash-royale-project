#!/usr/bin/env bash
# Runs scripts/check_new_cards.py inside the running app container and
# restarts it only when a new card was actually found and written -- both
# data/card_reference.csv and data/clash_royale_master_stats.csv feed
# @lru_cache-decorated readers (utils/data_loader.py, card_service.py) that
# won't notice an on-disk change until the process restarts, but restarting
# nightly for no reason (most nights: no new card) is unnecessary churn.
#
# Scheduled right after retrain.sh (see deploy/'s crontab) -- same
# low-traffic-hour reasoning, and cheap either way (one API call + a CSV
# diff, nothing like retrain's multi-GB pandas load).
set -uo pipefail
cd "$(dirname "$0")/.."

echo "[$(date -u +%FT%TZ)] Checking for new cards..."
docker compose exec -T app python /app/scripts/check_new_cards.py
status=$?

if [ "$status" -eq 2 ]; then
    echo "[$(date -u +%FT%TZ)] New card(s) written -- restarting app to pick them up."
    docker compose restart app
elif [ "$status" -ne 0 ]; then
    echo "[$(date -u +%FT%TZ)] check_new_cards.py exited $status (unexpected) -- not restarting."
fi
echo "[$(date -u +%FT%TZ)] New-card check finished."
