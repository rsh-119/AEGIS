"""JWT authentication utilities and FastAPI dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

_bearer  = HTTPBearer(auto_error=False)   # auto_error=False → returns None if no header

ALGORITHM = "HS256"


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── Token helpers ─────────────────────────────────────────────────────────────

def _create_token(sub: str, token_type: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": sub, "type": token_type, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(
        str(user_id), "access",
        timedelta(minutes=settings.jwt_access_expire_minutes),
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        str(user_id), "refresh",
        timedelta(days=settings.jwt_refresh_expire_days),
    )


def decode_token(token: str, expected_type: str = "access") -> int:
    """Decode a JWT and return user_id (int). Raises HTTPException on any failure."""
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


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> int:
    """Require a valid Bearer token. Returns user_id (int)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(credentials.credentials)


def get_optional_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[int]:
    """Like get_current_user_id but returns None instead of raising when no token."""
    if credentials is None:
        return None
    try:
        return decode_token(credentials.credentials)
    except HTTPException:
        return None
