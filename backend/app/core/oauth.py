"""
oauth.py — Google Sign-In token verification.

Pure verification helper, no DB access — same DB-free-core-module rationale
as core/auth.py and core/totp.py. Verifies via a raw httpx GET to Google's
tokeninfo endpoint rather than the google-auth SDK: this codebase already
prefers a direct API call over a heavy SDK where one call is all that's
needed (see ai_service.py's Gemini integration, which makes the same
trade-off explicitly). Google's tokeninfo endpoint does the signature/expiry/
issuer validation server-side — this function's job is just the call plus
checking the audience claim matches our client id.
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()

_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


async def verify_google_id_token(credential: str) -> dict:
    """Returns Google's decoded claims dict (sub, email, email_verified,
    aud, ...) on success. Raises HTTPException(401) on any failure —
    expired/malformed token, network error, or an audience mismatch (a
    token minted for a different app's client id)."""
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google Sign-In is not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_TOKENINFO_URL, params={"id_token": credential})
    except httpx.HTTPError:
        raise HTTPException(status_code=401, detail="Could not verify Google credential")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired Google credential")

    claims = resp.json()
    if claims.get("aud") != settings.google_client_id:
        raise HTTPException(status_code=401, detail="Google credential was not issued for this app")
    return claims
