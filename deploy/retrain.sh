#!/usr/bin/env bash
# Refreshes the "live" analytics CSVs (card_stats_live.csv, deck_archetypes_
# live.csv, etc.) from the latest data/collected_battles.csv -- real
# feedback (2026-08-23): the app's own /api/health/data-health reported
# "Updated 9.1 days ago," which is a real gap, not a display bug: nothing on
# this server was ever actually scheduled to re-run
# scripts/retrain_from_collected.py, so it only ever refreshed on whichever
# session happened to run it manually last (2026-08-14).
#
# Scheduled at a deliberately low-traffic hour (see crontab -- right after
# the nightly backup) rather than run on-demand during a normal session:
# the collected-battles file is now 1.2GB+, and a pandas load of that size
# is a real, if transient, multi-GB memory spike on a VM that has already
# hit two real OOM-driven outages in one day (2026-08-21, 2026-08-23) --
# see the OOM-incident memory notes. Running this at 4:30am US-Pacific-ish
# server-local low-traffic time keeps that spike away from real user load.
set -uo pipefail
cd "$(dirname "$0")/.."

echo "[$(date -u +%FT%TZ)] Starting live-analytics retrain..."
docker compose exec -T app python /app/scripts/retrain_from_collected.py
echo "[$(date -u +%FT%TZ)] Retrain finished."

# Real bug found the same day this script was written: the data-health
# snapshot /api/health/data-health serves is cached in-process with no TTL
# (see routers/health.py's own docstring) -- without this, tonight's fresh
# CSVs would sit on disk correctly updated while the running server kept
# reporting the OLD "Updated N days ago" until its next full restart, making
# this whole retrain job invisible to users until some unrelated future deploy.
curl -sf -X POST http://localhost/api/health/clear-cache > /dev/null \
  && echo "[$(date -u +%FT%TZ)] Data-health cache cleared." \
  || echo "[$(date -u +%FT%TZ)] Warning: failed to clear data-health cache."
