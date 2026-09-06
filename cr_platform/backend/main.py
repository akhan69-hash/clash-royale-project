import asyncio
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
import uvicorn

load_dotenv(Path(__file__).parent / ".env")  # CR_API_KEY for the auto-crawler, if present -- gitignored

from routers import cards, players, decks, meta, synergy, ml, rankings, coaching, whats_next, health  # noqa: E402
from services import auto_crawler  # noqa: E402
from services.battle_collector import get_collection_stats  # noqa: E402
from services.activity_log import log_activity  # noqa: E402

# Set on the deployed instance's .env only (never locally) -- hides the
# auto-generated API docs/schema in production. Leaving them on in local dev
# is fine (only reachable from this machine); in production they're a free
# map of the entire API surface handed to anyone who asks, so no reason to
# publish them once this is a real public site.
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

app = FastAPI(
    title="Clash Royale Analytics API",
    description="Real-time CR stats, deck analysis, player profiles",
    version="1.0.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

# Per-IP rate limiting -- the actual practical defense against bulk scraping
# (see the security discussion this same session: hiding endpoints doesn't
# stop scraping, throttling does). get_remote_address reads request.client,
# which correctly resolves to the real visitor IP (not Caddy's container IP)
# because uvicorn is started with --proxy-headers in production -- see the
# repo-root Dockerfile/docker-compose.yml. A generous global default; individual
# endpoints can get tighter limits later if a specific one turns out to need it.
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Browsers reject a wildcard origin combined with allow_credentials=True, so
# this must be an explicit list. Defaults to the local dev origins; a real
# deployment sets CORS_ORIGINS (comma-separated) to its actual domain(s) --
# though when the frontend is served from THIS SAME app (see the static-file
# section below, the normal production setup), requests are same-origin and
# CORS doesn't even come into play for them; this mainly matters for local
# dev (frontend on :5173, backend on :8000) or any separately-hosted frontend.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8501").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    # Real feedback (2026-09-06): "let's Work UI UX using vercel" -- Vercel
    # gives every single deployment (production AND every preview build) its
    # own real, dynamically-generated subdomain (<project>-<hash>.vercel.app),
    # so a fixed allow_origins list can never keep up with new preview URLs
    # as they're created. This regex covers any real *.vercel.app origin in
    # one rule instead of needing CORS_ORIGINS updated (and the backend
    # redeployed) for every new preview.
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PLAYER_TAG_PATH_RE = re.compile(r"^/api/players/([^/]+)")


# Foundation for a planned future AI-assisted navigation feature (see
# services/activity_log.py's module docstring for the full reasoning) --
# appends one JSONL row per real API request to data/activity_log.jsonl,
# grouped by the frontend's stable X-Session-Id header. Only real /api/*
# calls are logged (not the SPA's own static asset requests below), and
# /health + /api/crawler-status are excluded as internal noise, not real
# visitor activity.
_SKIP_LOG_PATHS = {"/health", "/api/crawler-status"}


@app.middleware("http")
async def _log_activity_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") and path not in _SKIP_LOG_PATHS:
        session_id = request.headers.get("x-session-id")
        player_tag = request.headers.get("x-player-tag")
        if not player_tag:
            m = _PLAYER_TAG_PATH_RE.match(path)
            # /api/players/search is a literal route (see players.py), not a
            # /{tag} path -- without this check it gets misread as a lookup
            # for a player tag literally named "search" (found via the new
            # traffic_summary.py script showing "search" as a top tag).
            if m and m.group(1) != "search":
                player_tag = m.group(1)
        log_activity(session_id, player_tag, request.method, path, response.status_code)
    return response


app.include_router(cards.router, prefix="/api/cards", tags=["Cards"])
app.include_router(players.router, prefix="/api/players", tags=["Players"])
app.include_router(decks.router, prefix="/api/decks", tags=["Decks"])
app.include_router(meta.router, prefix="/api/meta", tags=["Meta"])
app.include_router(synergy.router, prefix="/api/synergy", tags=["Synergy"])
app.include_router(ml.router, prefix="/api/ml", tags=["ML"])
app.include_router(rankings.router, prefix="/api/rankings", tags=["Rankings"])
app.include_router(coaching.router, prefix="/api/coaching", tags=["Coaching"])
app.include_router(whats_next.router, prefix="/api/whats-next", tags=["What's Next"])
app.include_router(health.router, prefix="/api/health", tags=["Health"])


@app.on_event("startup")
async def _start_auto_crawler():
    auto_crawler.start()


# Emergency fix (2026-08-23): this used to await the cache warm-up here,
# blocking uvicorn from accepting ANY traffic -- including a trivial
# /health check -- until it finished. That was fine when it took 30-70s
# (2026-08-07). It does not anymore: the dataset has kept growing, this
# server is now also relying on swap (added after a real OOM incident
# earlier this same day -- see memory notes), and swap-backed memory
# access is far slower than RAM for the same work, so this blocking wait
# had grown to 15+ minutes and made the whole site look completely down
# (every request timing out, not just slow) for that entire window.
# Reverted to the pre-2026-08-07 behavior: the cache lazily builds itself
# on whichever real request needs it first (still only ever once, still
# memoized -- see battle_collector._load_cache), instead of blocking
# server startup on it. The tradeoff is the ORIGINAL one this pre-warm was
# built to avoid (one real request eventually pays the full cold-load
# cost) -- a real but far smaller cost than the entire server being
# unreachable for everyone, including for endpoints that don't even touch
# battle data, for the full warm-up duration.
#
# This is a stopgap, not the fix: the underlying problem is _load_cache()
# loading the ENTIRE ever-growing collected_battles.csv into several
# in-memory Python structures with no bound tied to real size. That needs
# a real fix (a real on-disk database instead of full-file in-memory
# loading) before this keeps recurring as the file keeps growing --
# flagged in detail in this session's memory notes.
#
# @app.on_event("startup")
# async def _warm_battle_cache():
#     await asyncio.to_thread(get_collection_stats)


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/crawler-status")
def crawler_status():
    return auto_crawler.get_status()


# Production serves the built React frontend from this SAME process (one
# service, one domain, no cross-origin API calls needed) -- see the
# repo-root Dockerfile, which runs `npm run build` before starting uvicorn.
# In local dev this directory doesn't exist (the frontend runs separately via
# `npm run dev` on :5173, proxying /api to this backend -- see
# frontend/vite.config.ts), so `/` falls back to a plain API status message
# instead, same as before.
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        # Never let this swallow a real API 404 -- only unmatched, non-/api
        # paths fall through to here (every real /api/* route is already
        # registered above and matches first).
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = FRONTEND_DIST / full_path
        # Real gotcha found 2026-08-19: neither index.html nor the hashed
        # asset files carried any Cache-Control header before this (Starlette's
        # FileResponse default), which for index.html specifically means a
        # browser can keep serving an already-open tab's in-memory bundle
        # indefinitely -- no refresh even attempts a re-fetch, so a real
        # shipped bug fix can look "still broken" purely because the tab
        # never reloaded. The hashed asset files (index-<hash>.js/css) get a
        # long cache lifetime since their filename itself changes on every
        # build (safe to cache hard); index.html -- the only thing that ever
        # references the current hash -- must always be revalidated.
        if full_path and candidate.is_file():
            max_age = 31536000 if full_path.startswith("assets/") else 0
            headers = {"Cache-Control": f"public, max-age={max_age}, immutable"} if max_age \
                else {"Cache-Control": "no-cache"}
            return FileResponse(candidate, headers=headers)
        # Anything else (/, /build, /player/123, ...) is a client-side route
        # -- always serve the SPA shell and let React Router take over.
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
else:
    @app.get("/")
    def root():
        return {"status": "ok", "message": "CR Analytics API running (no built frontend found -- run the frontend dev server separately)"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
