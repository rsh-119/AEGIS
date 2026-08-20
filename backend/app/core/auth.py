"""JWT authentication utilities and FastAPI dependencies.

Tokens carry three identity claims beyond the standard `sub`/`exp`:
  - `jti` (JWT ID)    — unique per token, used to blocklist a single access
                        token on logout (see token_store.py).
  - `sid` (session id) — shared by every access+refresh token minted from one
                        login, and by every refresh token in its rotation
                        chain. Used to detect refresh-token reuse (a stolen
                        token replayed after the legitimate client already
                        rotated past it) and to revoke a whole login session
                        at once, not just a single token.

Auth is carried via httpOnly cookies for browser clients (see
_set_auth_cookies/ACCESS_COOKIE_NAME/REFRESH_COOKIE_NAME) with an
Authorization: Bearer fallback for script/API/CI clients that don't hold a
cookie jar. The Bearer header, when present, always takes priority.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

_bearer  = HTTPBearer(auto_error=False)   # auto_error=False → returns None if no header

ALGORITHM = "HS256"

# ── Cookie names ────────────────────────────────────────────────────────────
# No explicit `domain=` is ever set when writing these — that keeps them
# host-only so they bind to whatever origin the browser actually saw. In
# production that's the Vercel frontend domain (Next.js's rewrite proxies
# /api/* to the Render backend and passes Set-Cookie through untouched), not
# the backend's own domain — which is what makes SameSite=Strict work with
# zero cross-site cookie issues and no separate CSRF token.
ACCESS_COOKIE_NAME  = "aegis_access"
REFRESH_COOKIE_NAME = "aegis_refresh"


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── Token helpers ─────────────────────────────────────────────────────────────

def _create_token(
    sub: str,
    token_type: str,
    expires_delta: timedelta,
    jti: str | None = None,
    session_id: str | None = None,
) -> tuple[str, str]:
    """Returns (encoded_jwt, jti) — jti is generated here when not supplied,
    and always returned so callers (e.g. the refresh-family Redis pointer)
    can record it without decoding the token they just minted."""
    jti = jti or str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + expires_delta
    payload: dict = {"sub": sub, "type": token_type, "jti": jti, "exp": expire}
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM), jti


def create_access_token(user_id: int, session_id: str) -> str:
    """Every access token belongs to a login session (`sid`) — required so a
    revoked session can reject its still-unexpired access tokens, not just
    block future refreshes."""
    token, _ = _create_token(
        str(user_id), "access",
        timedelta(minutes=settings.jwt_access_expire_minutes),
        session_id=session_id,
    )
    return token


def create_refresh_token(user_id: int, session_id: str) -> tuple[str, str]:
    """Returns (token, jti). The jti is the refresh-rotation-chain pointer
    value the caller must persist in Redis (see token_store.set_refresh_jti)."""
    return _create_token(
        str(user_id), "refresh",
        timedelta(days=settings.jwt_refresh_expire_days),
        session_id=session_id,
    )


@dataclass
class DecodedToken:
    user_id: int
    jti: str | None
    sid: str | None
    exp: int  # unix timestamp


def decode_token(token: str, expected_type: str = "access") -> int:
    """Decode a JWT and return user_id (int). Raises HTTPException on any failure.

    Kept returning a bare int (not the full claim set) so the ~6 existing
    call sites that only need the user id are untouched — see
    decode_token_full for jti/sid access."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate token")


def decode_token_full(token: str, expected_type: str = "access") -> DecodedToken:
    """Like decode_token but also returns jti/sid/exp — needed anywhere that
    has to identify *this specific token* or *this login session* (logout,
    refresh-rotation, reuse detection, revocation checks)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return DecodedToken(
            user_id=int(user_id),
            jti=payload.get("jti"),
            sid=payload.get("sid"),
            exp=int(payload["exp"]),
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate token")
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Cookie helpers ─────────────────────────────────────────────────────────────

def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set both auth cookies on a response. httpOnly so an XSS payload can't
    read either one; Secure only in production (a local http:// dev server
    can't set an HTTPS-only cookie); SameSite=Strict is safe here because the
    app is same-origin-with-the-API in every environment that matters (see
    module docstring) — there's no cross-site scenario where the cookie would
    need to be attached, so no CSRF token is needed either."""
    is_prod = settings.app_env == "production"
    response.set_cookie(
        ACCESS_COOKIE_NAME, access_token,
        httponly=True, secure=is_prod, samesite="strict",
        max_age=settings.jwt_access_expire_minutes * 60, path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME, refresh_token,
        httponly=True, secure=is_prod, samesite="strict",
        max_age=settings.jwt_refresh_expire_days * 86400,
        path="/api/auth",  # only ever needs to reach /refresh and /logout
    )


def clear_auth_cookies(response: Response) -> None:
    """Path must match what set_auth_cookies used, or delete_cookie silently no-ops."""
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Authorization header takes priority (keeps script/API/CI clients that
    don't hold a cookie jar working unchanged); falls back to the access
    cookie for browser clients."""
    if credentials is not None:
        return credentials.credentials
    return request.cookies.get(ACCESS_COOKIE_NAME)


def get_current_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> int:
    """Require a valid, non-revoked access token. Returns user_id (int)."""
    token = _extract_token(request, credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    decoded = decode_token_full(token)
    from app.core import token_store  # local import avoids a cache.py import cycle at module load
    if token_store.is_access_revoked(decoded.jti, decoded.sid):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decoded.user_id


def get_optional_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[int]:
    """Like get_current_user_id but returns None instead of raising when no
    token / an invalid or revoked token is present."""
    token = _extract_token(request, credentials)
    if token is None:
        return None
    try:
        decoded = decode_token_full(token)
        from app.core import token_store
        if token_store.is_access_revoked(decoded.jti, decoded.sid):
            return None
        return decoded.user_id
    except HTTPException:
        return None
