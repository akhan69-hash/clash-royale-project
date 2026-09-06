"""
Official Supercell leaderboards -- top players, top clans, and tournament
search. Distinct from everything else in this app: those are all built from
OUR OWN collected battle data, while this is a direct, real-time proxy onto
Supercell's own rankings, refreshed on their side roughly every 10-15 minutes.

Reuses CR_API_KEY from the environment (the same key the background crawler
and Player Lookup already use) so the frontend doesn't need to re-enter a key
just to browse public leaderboards.

Important API quirk found while building this (2026-07-29): the classic
`/locations/{id}/rankings/players` endpoint is effectively dead post-Ranked-
mode-rework -- it returns empty results for real locations. The actual,
working endpoint for player rankings is `/locations/{id}/pathoflegend/players`
(confirmed against the live API). Clan rankings still use the classic
`/locations/{id}/rankings/clans` path, unaffected.

Tournaments have no "browse all" endpoint at all -- Supercell only supports
searching by (partial) name or looking up a specific tag, since tournaments
are player-created and transient, not a fixed leaderboard.
"""
import os
import time

import httpx
from fastapi import APIRouter, HTTPException, Header, Query

router = APIRouter()
CR_API_BASE = "https://api.clashroyale.com/v1"


def get_api_key(authorization: str = Header(None)) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    key = os.getenv("CR_API_KEY", "")
    if not key:
        raise HTTPException(status_code=401, detail="CR API key required. Set CR_API_KEY env or pass Authorization header.")
    return key


async def _cr_get(path: str, api_key: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{CR_API_BASE}{path}", headers={"Authorization": f"Bearer {api_key}"}, params=params)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Not found")
    if resp.status_code == 403:
        raise HTTPException(status_code=403, detail="Invalid API key or IP not whitelisted")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Clash Royale API error: {resp.text[:200]}")
    return resp.json()


_locations_cache: dict = {"items": None, "fetched_at": 0.0}
LOCATIONS_TTL = 3600  # locations barely ever change -- cache for an hour


@router.get("/locations")
async def locations(authorization: str = Header(None)):
    api_key = get_api_key(authorization)
    now = time.time()
    if _locations_cache["items"] is None or now - _locations_cache["fetched_at"] > LOCATIONS_TTL:
        data = await _cr_get("/locations", api_key, {"limit": 250})
        _locations_cache["items"] = data.get("items", [])
        _locations_cache["fetched_at"] = now
    items = _locations_cache["items"]
    return {
        "regions": [l for l in items if not l.get("isCountry")],
        "countries": sorted([l for l in items if l.get("isCountry")], key=lambda l: l["name"]),
    }


@router.get("/players")
async def top_players(location_id: int = Query(57000249), limit: int = Query(50, ge=1, le=200),
                       authorization: str = Header(None)):
    """Top players by Path of Legends rating. Confirmed via direct testing:
    this endpoint ONLY works for actual country-level locations -- the
    broader region groupings (Europe, International, etc, all with
    isCountry=false) 404 with 'Rankings not found for location', even though
    those same broad regions work fine for clan rankings below. There's no
    single "worldwide top players" list in the official API anymore; 57000249
    (United States) is just a real, populous default, not a global ranking."""
    api_key = get_api_key(authorization)
    data = await _cr_get(f"/locations/{location_id}/pathoflegend/players", api_key, {"limit": limit})
    return {"players": data.get("items", [])}


@router.get("/clans")
async def top_clans(location_id: int = Query(57000006), limit: int = Query(50, ge=1, le=200),
                     authorization: str = Header(None)):
    api_key = get_api_key(authorization)
    data = await _cr_get(f"/locations/{location_id}/rankings/clans", api_key, {"limit": limit})
    return {"clans": data.get("items", [])}


# Real feedback (2026-09-02): "clan search only in 'clan' tab with top clan
# leaderboard and other stuff but all clan stuff" -- everything clan-related
# (leaderboard above, search/detail/members/war countdown below) lives in
# this one router so the frontend's whole "Clan" tab has one backend home.
# Registered BEFORE the /clans/{tag} routes below -- FastAPI matches path
# routes in registration order, and "search" would otherwise be swallowed as
# a literal {tag} value by the more general route.
@router.get("/clans/search")
async def search_clans(name: str = Query(..., min_length=3), authorization: str = Header(None)):
    """Real clan search by (partial) name -- same /clans?name= endpoint the
    game's own in-app clan search uses. Like tournament search, there's no
    'browse all clans' endpoint; name search is the only real lookup path."""
    api_key = get_api_key(authorization)
    data = await _cr_get("/clans", api_key, {"name": name, "limit": 20})
    return {"clans": data.get("items", [])}


@router.get("/clans/{tag}")
async def get_clan(tag: str, authorization: str = Header(None)):
    """Full real clan detail -- includes memberList directly (no separate
    /members call needed), each with real tag/name/role/trophies/donations."""
    api_key = get_api_key(authorization)
    tag = tag.lstrip("#").upper()
    return await _cr_get(f"/clans/%23{tag}", api_key)


@router.get("/clans/{tag}/war")
async def get_clan_war(tag: str, authorization: str = Header(None)):
    """Real live River Race state -- state/periodType/periodIndex plus real
    warEndTime/collectionEndTime timestamps, which is what actually answers
    "clan battle close in this many days" (real feedback, 2026-09-02): the
    frontend computes a countdown from warEndTime rather than this endpoint
    guessing at one, since Supercell's own period boundaries can shift."""
    api_key = get_api_key(authorization)
    tag = tag.lstrip("#").upper()
    return await _cr_get(f"/clans/%23{tag}/currentriverrace", api_key)


@router.get("/tournaments")
async def search_tournaments(name: str = Query(..., min_length=3), authorization: str = Header(None)):
    """Supercell only supports searching tournaments by (partial) name --
    there's no 'list all open tournaments' endpoint, since they're
    player-created and constantly cycling."""
    api_key = get_api_key(authorization)
    data = await _cr_get("/tournaments", api_key, {"name": name})
    return {"tournaments": data.get("items", [])}


@router.get("/tournaments/{tag}")
async def get_tournament(tag: str, authorization: str = Header(None)):
    api_key = get_api_key(authorization)
    tag = tag.lstrip("#").upper()
    data = await _cr_get(f"/tournaments/%23{tag}", api_key)
    return data
