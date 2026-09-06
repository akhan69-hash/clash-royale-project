#!/usr/bin/env bash
# Run this ON THE VM (in ~/royaleiq, after new code has been transferred
# there) to rebuild and restart the app with zero manual Docker commands to
# remember. Local dev's equivalent of "restart the backend" -- deploy on
# purpose, no CI/CD wired up, matching how this whole project has been
# restarted manually all along.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Building and restarting..."
docker compose up -d --build

echo "Waiting for the app to report healthy..."
for i in $(seq 1 40); do
  if curl -sf http://localhost/health > /dev/null 2>&1; then
    echo "Healthy."
    exit 0
  fi
  sleep 3
done
echo "Warning: did not report healthy within the wait window -- check 'docker compose logs app'."
exit 1
