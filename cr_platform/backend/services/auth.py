"""
Real user accounts (2026-09-02) -- verification-only. Sign-up/login/logout/
password-reset all happen CLIENT-SIDE via @supabase/supabase-js talking
directly to Supabase's own Auth API (see cr_platform/frontend/src/utils/
supabaseClient.ts and contexts/AuthContext.tsx) -- this backend never
handles a password or issues a token itself, which is the whole point of
using Supabase Auth instead of hand-rolling one (no password-hashing or JWT
library existed in this codebase before this).

get_current_user() below is forward-looking infrastructure: nothing in the
app gates a real feature behind login yet (per the agreed scope for this
first pass -- favorites/collection stay in localStorage), so this dependency
isn't registered on any route today. It exists so a future protected
endpoint is `Depends(get_current_user)` away, not a fresh investigation.

Real open question, deliberately not guessed: Supabase projects sign JWTs
one of two ways depending on when the project was created / its dashboard
settings --
  - Newer/default: asymmetric (ES256/RS256), verifiable via a public JWKS
    endpoint at {SUPABASE_URL}/auth/v1/.well-known/jwks.json -- no secret
    needed on our side at all.
  - Legacy: a single static HS256 shared secret (Project Settings -> API ->
    JWT Settings -> "JWT Secret" in the Supabase dashboard).
This picks whichever the real project is actually configured for at
runtime (SUPABASE_JWT_SECRET set -> HS256; otherwise -> JWKS) instead of
assuming one, since getting this wrong silently rejects every real logged-in
user.
"""
import os
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


@lru_cache(maxsize=1)
def _jwks_client() -> "jwt.PyJWKClient | None":
    if not SUPABASE_URL:
        return None
    return jwt.PyJWKClient(f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json")


def _decode(token: str) -> dict:
    if SUPABASE_JWT_SECRET:
        return jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
    client = _jwks_client()
    if client is None:
        raise HTTPException(status_code=500, detail="Auth not configured (SUPABASE_URL/SUPABASE_JWT_SECRET missing)")
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated")


def get_current_user(authorization: str = Header(None)) -> dict:
    """FastAPI dependency -- raises 401 if the bearer token is missing/
    invalid/expired, otherwise returns the decoded Supabase JWT claims
    (includes real `sub` = the user's UUID, `email`, etc.). Not used by any
    route yet -- see this module's docstring."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    try:
        return _decode(token)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid session: {e}")
