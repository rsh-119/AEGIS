"""
token_store.py — Redis-backed access-token blocklist + refresh-token
rotation/reuse-detection, keyed off the `jti`/`sid` claims minted in
core/auth.py.

Reuses the existing `cache._redis` client (core/cache.py) directly with
plain setex/get/delete — these are simple existence/pointer values, not
JSON-shaped cache entries, so they bypass cache.py's JSON-wrapping/
category-TTL helpers and are stored as raw strings instead.

── Redis key schema ──────────────────────────────────────────────────────────
  auth:blocklist:jti:{jti}      "1"              TTL = seconds left on that
                                                  access token's own exp
                                                  (set on logout)

  auth:session:{sid}:current_jti  <refresh jti>  TTL = jwt_refresh_expire_days
                                                  (the currently-valid refresh
                                                  token in this session's
                                                  rotation chain; re-set on
                                                  every successful rotation)

  auth:session:{sid}:revoked    "1"              TTL = jwt_refresh_expire_days
                                                  (whole-session kill switch —
                                                  set when a rotated-away
                                                  refresh token is replayed,
                                                  i.e. reuse detected)

── Failure mode (deliberate, asymmetric — see RFC) ───────────────────────────
  Blocklist reads (is_access_revoked, called on every authenticated request)
  FAIL OPEN on a Redis error: matches this codebase's universal soft-Redis
  convention (cache.py, health.py's "degraded" status). Worst case, a
  logged-out token stays valid until its own natural expiry (≤ 60 min) during
  an outage — a regression to pre-this-feature behavior, not a new hole.

  Refresh-rotation reads/writes (check_and_rotate_refresh, called only on
  POST /refresh — low-frequency, retryable, not on the hot path) FAIL CLOSED:
  callers should let a raised exception propagate to a 503 rather than
  silently skip the reuse check, because this *is* the security control the
  feature exists for. Do not "fix" this into fail-open to match the rest of
  the file — it's an intentional exception, not an oversight.
"""

from __future__ import annotations

from app.core.cache import cache
from app.core.config import get_settings

settings = get_settings()

_BLOCKLIST_PREFIX = "auth:blocklist:jti:"
_SESSION_PREFIX   = "auth:session:"

_REFRESH_TTL = settings.jwt_refresh_expire_days * 86400


def _redis():
    """Raw redis-py client, or None if Redis was never connected (cache.py's
    connect() silently no-ops on failure — callers must handle None)."""
    return cache._redis


# ── Access-token blocklist (fail-open) ────────────────────────────────────────

def revoke_access_jti(jti: str, ttl_seconds: int) -> None:
    """Called on logout. Silently best-effort — a failure here just means the
    fail-open read path below won't see it, which is the accepted trade-off."""
    if ttl_seconds <= 0 or not jti:
        return
    r = _redis()
    if r is None:
        return
    try:
        r.setex(f"{_BLOCKLIST_PREFIX}{jti}", ttl_seconds, "1")
    except Exception:
        pass


def is_access_revoked(jti: str | None, sid: str | None) -> bool:
    """Checked on every authenticated request. Fail-open: any Redis error, or
    Redis never having connected, is treated as "not revoked" — see module
    docstring for why this half of the file is fail-open."""
    r = _redis()
    if r is None:
        return False
    try:
        if jti and r.exists(f"{_BLOCKLIST_PREFIX}{jti}"):
            return True
        if sid and r.exists(f"{_SESSION_PREFIX}{sid}:revoked"):
            return True
    except Exception:
        return False
    return False


# ── Refresh-token rotation family + reuse detection (fail-closed) ────────────

class RefreshReuseDetected(Exception):
    """Raised when a refresh token that was already rotated away is replayed
    — the whole session has just been revoked as a result."""


class RefreshSessionRevoked(Exception):
    """Raised when a refresh token belongs to an already-revoked session."""


def start_session(sid: str, refresh_jti: str) -> None:
    """Called on login/register — seeds the rotation-chain pointer for a
    brand-new session. Best-effort/fail-open on purpose: login itself must
    never hard-fail because Redis is down (that would make Redis a hard
    dependency for the core auth flow, contradicting this codebase's
    convention everywhere else). If this silently no-ops, the first
    subsequent /refresh call simply finds no current_jti pointer yet, which
    check_and_rotate_refresh already treats as "first refresh of this
    session" — reuse detection just starts working once Redis is back,
    rather than login being blocked by it now."""
    r = _redis()
    if r is None:
        return
    try:
        r.setex(f"{_SESSION_PREFIX}{sid}:current_jti", _REFRESH_TTL, refresh_jti)
    except Exception:
        pass


def check_and_rotate_refresh(sid: str, presented_jti: str, new_jti: str) -> None:
    """Validates a presented refresh token against its session's rotation
    chain, then advances the chain to new_jti. Raises (does not swallow) on
    Redis failure — see module docstring: this is the fail-closed half.

    Raises:
      RefreshSessionRevoked  — session was already killed (prior reuse event
                                or an explicit revoke).
      RefreshReuseDetected   — presented_jti doesn't match the chain's current
                                pointer, i.e. a replay of an already-rotated-
                                away token. The whole session is revoked as a
                                side effect of raising this.
      ConnectionError        — Redis unreachable; caller should return 503,
                                not silently allow the refresh through.
    """
    r = _redis()
    if r is None:
        raise ConnectionError("Redis unavailable — cannot verify refresh-token reuse")

    if r.exists(f"{_SESSION_PREFIX}{sid}:revoked"):
        raise RefreshSessionRevoked()

    current = r.get(f"{_SESSION_PREFIX}{sid}:current_jti")
    if current is not None and current != presented_jti:
        # Replay of a rotated-away token — kill the whole family.
        r.setex(f"{_SESSION_PREFIX}{sid}:revoked", _REFRESH_TTL, "1")
        raise RefreshReuseDetected()

    r.setex(f"{_SESSION_PREFIX}{sid}:current_jti", _REFRESH_TTL, new_jti)


def revoke_session(sid: str) -> None:
    """Explicit whole-session kill (used nowhere yet — available for a future
    'log out all devices' feature). Fail-open by design: a best-effort revoke
    matches this function's non-critical-path usage."""
    r = _redis()
    if r is None:
        return
    try:
        r.setex(f"{_SESSION_PREFIX}{sid}:revoked", _REFRESH_TTL, "1")
    except Exception:
        pass
