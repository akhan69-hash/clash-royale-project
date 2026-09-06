"""
Runs scripts/crawl_battles.py's crawl loop automatically, in the background,
for as long as the backend process is running -- this is what makes the
dataset "grow by itself" rather than needing someone to remember to re-run
the script. Each cycle crawls a small batch (BATCH_SIZE new players), then
sleeps, then does it again, picking up right where the on-disk crawl state
(data/crawl_state.json) left off -- including across a server restart.

Needs CR_API_KEY available to the server process (env var, or a backend/.env
file loaded via python-dotenv) since this runs with no browser/user attached
to supply it per-request. If it's not set, the loop logs once and stays
idle rather than failing loudly every cycle.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

BATCH_SIZE = 60
INTERVAL_SECONDS = 30

# Real production incident (2026-08-26/28): retrain_from_collected.py runs
# ~10 separate full-dataset df.iterrows() passes over the ENTIRE
# collected_battles.csv (4.3M+ rows and growing daily). At the old
# cycle-count-based cadence (every 10 crawl cycles = ~5 minutes, forever)
# this got more expensive every single day as the file grew, until a single
# retrain's peak memory was enough to exhaust both RAM and swap simultaneously
# and wedge the whole VM (SSH included) for 2 days straight -- worse than any
# prior incident, since every earlier one at least left SSH reachable for a
# restart. Retraining analytics every 5 minutes was never actually necessary
# (nothing reads card_stats_live.csv/etc. at anywhere near that freshness),
# so this is now wall-clock gated instead of cycle-count gated: a fixed
# interval regardless of how fast/slow crawling happens to be running.
RETRAIN_INTERVAL_SECONDS = 4 * 60 * 60  # once every 4 hours (was ~every 5 min)

_task: asyncio.Task | None = None
_status = {
    "running": False,
    "last_result": None,
    "last_error": None,
    "cycles": 0,
    "last_retrain": None,
    "retrain_error": None,
}
_last_retrain_at: float = 0.0


def get_status() -> dict:
    return dict(_status)


async def _loop():
    from crawl_battles import run_crawl

    global _last_retrain_at
    _status["running"] = True
    warned_no_key = False

    while True:
        # EMERGENCY DISABLE (2026-08-28): crawling calls save_battles(), which
        # calls battle_collector.py's _load_cache() -- the ORIGINAL, still-
        # unfixed root cause from days ago (loads the entire 1.5GB+ CSV into
        # memory on first use per process). Every restart tonight cleared
        # that cache, and the very next crawl cycle's save_battles() call was
        # enough to re-trigger a fresh expensive reload, climbing toward the
        # same OOM danger independent of (and even with) the retrain fixes
        # above. Paused here until _load_cache() itself gets a real bounded-
        # read fix (or the Postgres migration is wired in to replace it) --
        # re-enable by removing this block once that's done and verified.
        if os.getenv("CR_CRAWLER_PAUSED", "1") == "1":
            print("[auto-crawl] paused (CR_CRAWLER_PAUSED) -- see 2026-08-28 emergency-disable note above.")
            await asyncio.sleep(INTERVAL_SECONDS * 10)
            continue

        api_key = os.getenv("CR_API_KEY", "")
        if not api_key:
            if not warned_no_key:
                print("[auto-crawl] CR_API_KEY not set -- idle. Set it in cr_platform/backend/.env to enable.")
                warned_no_key = True
            await asyncio.sleep(INTERVAL_SECONDS)
            continue

        try:
            # run_crawl does blocking HTTP calls -- keep it off the event loop
            result = await asyncio.to_thread(run_crawl, api_key, BATCH_SIZE, False)
            _status["last_result"] = result
            _status["last_error"] = None
            _status["cycles"] += 1
            if result["crawled_this_run"] > 0:
                print(f"[auto-crawl] cycle {_status['cycles']}: {result['crawled_this_run']} players "
                      f"({result.get('new_players_this_run', result['crawled_this_run'])} new, "
                      f"{result.get('recrawled_this_run', 0)} re-crawled), "
                      f"+{result['new_battles']} battles, {result['frontier_remaining']} left in frontier "
                      f"(total: {result['collection']['total_battles']} battles)")

            # Periodically retrain analytics from collected battles -- wall-clock
            # gated (see RETRAIN_INTERVAL_SECONDS docstring above), not tied to
            # crawl cycle count.
            # EMERGENCY DISABLE (2026-08-28): retrain_from_collected.py's
            # load_collected() still reads the ENTIRE CSV into memory before
            # any row-count/date cap applies, so even a "capped" run climbed
            # toward the same OOM danger a full run did (caught + aborted
            # twice live on production today). Disabled here until
            # load_collected() itself is fixed to only ever materialize a
            # bounded number of rows -- re-enable by restoring the
            # `now - _last_retrain_at >= RETRAIN_INTERVAL_SECONDS` condition
            # below once that's done and verified safe at production scale.
            now = time.monotonic()
            if False and now - _last_retrain_at >= RETRAIN_INTERVAL_SECONDS:
                _last_retrain_at = now
                print(f"[auto-crawl] Retraining analytics (cycle {_status['cycles']})...")
                try:
                    await asyncio.to_thread(_retrain_analytics)
                    _status["last_retrain"] = "success"
                    _status["retrain_error"] = None
                    print(f"[auto-crawl] Analytics retrained successfully")
                except Exception as e:
                    _status["retrain_error"] = str(e)
                    print(f"[auto-crawl] Analytics retrain failed: {e}")

        except Exception as e:
            _status["last_error"] = str(e)
            print(f"[auto-crawl] error: {e}")

        await asyncio.sleep(INTERVAL_SECONDS)


def _retrain_analytics():
    """Regenerate analytics CSVs from collected battles."""
    from retrain_from_collected import main as retrain_main
    # retrain_from_collected.py's main() handles all the logic
    retrain_main()


def start():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


def stop():
    global _task
    if _task and not _task.done():
        _task.cancel()
