"""Authentication endpoints: register, login, logout, refresh, 2FA, password reset, and guest-data sync."""

import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import token_store, totp
from app.core.avatar import MAX_UPLOAD_BYTES, process_avatar_image
from app.core.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    create_access_token,
    create_pre_auth_token,
    create_refresh_token,
    decode_token,
    decode_token_full,
    get_current_user_id,
    hash_password,
    set_auth_cookies,
    verify_password,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.entitlements import is_pro_user
from app.core.oauth import verify_google_id_token
from app.middleware.rate_limiter import (
    AUTH_LIMIT,
    AVATAR_UPLOAD_LIMIT,
    PASSWORD_RESET_LIMIT,
    TWO_FA_LIMIT,
    TWO_FA_VERIFY_LIMIT,
    limiter,
    user_or_ip_key,
)
from app.models import Holding, User, WatchItem
from app.schemas import (
    ForgotPasswordRequest,
    GoogleLogin,
    GuestDataSync,
    GuestDataSyncResponse,
    PasswordChange,
    PreAuthVerify,
    RefreshRequest,
    ResetPasswordRequest,
    SyncResult,
    TwoFactorDisable,
    TwoFactorEnable,
    UserLogin,
    UserRegister,
    UserUpdate,
)
from app.services.email_service import send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


async def _serialize_user(user: User, db: AsyncSession) -> dict:
    """user.to_dict() alone still carries the stale, no-longer-written
    users.is_pro column — overlay the live value from `subscriptions` (see
    entitlements.py), same source of truth every gating check uses."""
    return {**user.to_dict(), "is_pro": await is_pro_user(user.id, db)}


def _issue_session(response: Response, user_id: int) -> None:
    """Mint a new access token and refresh token, store the session in Redis, and set the cookies on the response. Called by login, register, and 2FA verification."""
    session_id = str(uuid.uuid4())
    access_token = create_access_token(user_id, session_id)
    refresh_token, refresh_jti = create_refresh_token(user_id, session_id)
    token_store.start_session(session_id, refresh_jti)
    token_store.track_session(user_id, session_id)
    set_auth_cookies(response, access_token, refresh_token)


async def _unique_username_from_email(email: str, db: AsyncSession) -> str:
    """New Google accounts have no chosen username — derive one from the
    email local-part, falling back to a random numeric suffix on collision.
    Only used by google_login; local registration always takes an explicit
    username from UserRegister."""
    base = "".join(c for c in email.split("@")[0].lower() if c.isalnum() or c == "_")[:24] or "user"
    candidate = base
    for _ in range(20):
        clash = (await db.execute(select(User).where(User.username == candidate))).scalar_one_or_none()
        if not clash:
            return candidate
        candidate = f"{base}{secrets.randbelow(10000)}"
    # Astronomically unlikely with 20 attempts at 4-digit suffixes over a
    # 24-char base, but never loop forever on user input.
    raise HTTPException(status_code=500, detail="Could not generate a unique username — please register manually")


@router.post("/register", status_code=201)
@limiter.limit(AUTH_LIMIT)
async def register(request: Request, response: Response, body: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(
            select(User).where(
                (User.email == body.email) | (User.username == body.username)
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already registered",
        )
    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()   # get auto-generated id before commit
    _issue_session(response, user.id)
    return await _serialize_user(user, db)


@router.post("/login")
@limiter.limit(AUTH_LIMIT)
async def login(request: Request, response: Response, body: UserLogin, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    if user.is_2fa_enabled:
        # Password was correct but that's only the first factor — do not
        # issue cookies yet. The frontend must call /2fa/verify-login with
        # this token + a TOTP/backup code before a real session exists.
        return {"requires_2fa": True, "pre_auth_token": create_pre_auth_token(user.id)}
    _issue_session(response, user.id)
    return await _serialize_user(user, db)


@router.post("/google")
@limiter.limit(AUTH_LIMIT)
async def google_login(request: Request, response: Response, body: GoogleLogin, db: AsyncSession = Depends(get_db)):
    claims = await verify_google_id_token(body.credential)
    google_id = claims["sub"]
    email = claims.get("email")
    email_verified = claims.get("email_verified") in (True, "true")

    user = (await db.execute(select(User).where(User.google_id == google_id))).scalar_one_or_none()
    if not user and email:
        # Auto-link to an existing local account only if Google itself
        # verified the email — an unverified email can't be trusted to prove
        # "this is the same person," so it must go through a fresh signup.
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing and email_verified:
            existing.google_id = google_id
            user = existing

    if not user:
        if not email or not email_verified:
            raise HTTPException(status_code=401, detail="Google account has no verified email")
        username = await _unique_username_from_email(email, db)
        user = User(email=email, username=username, hashed_password=None, auth_provider="google", google_id=google_id)
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    if user.is_2fa_enabled:
        return {"requires_2fa": True, "pre_auth_token": create_pre_auth_token(user.id)}
    _issue_session(response, user.id)
    return await _serialize_user(user, db)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,   # script/API clients with no cookie jar
    db: AsyncSession = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME) or (body.refresh_token if body else None)
    if not raw_token:
        raise HTTPException(status_code=401, detail="No refresh token presented")

    decoded = decode_token_full(raw_token, expected_type="refresh")
    if not decoded.sid:
        # A refresh token with no session id cannot be rotated (no chain to
        # check reuse against) and cannot be revoked (logout and password
        # reset both revoke by sid). Accepting it would be a permanent
        # downgrade for the life of the token, so it is rejected outright and
        # the client re-authenticates. See the module docstring.
        raise HTTPException(
            status_code=401,
            detail="This refresh token predates session tracking — please log in again",
        )

    user = await db.get(User, decoded.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    new_access = create_access_token(decoded.user_id, decoded.sid)
    new_refresh, new_refresh_jti = create_refresh_token(decoded.user_id, decoded.sid)

    try:
        token_store.check_and_rotate_refresh(decoded.sid, decoded.jti, new_refresh_jti)
    except token_store.RefreshReuseDetected:
        raise HTTPException(
            status_code=401,
            detail="This refresh token was already used — session revoked as a precaution. Please log in again.",
        )
    except token_store.RefreshSessionRevoked:
        raise HTTPException(status_code=401, detail="Session has been revoked — please log in again")
    except ConnectionError:
        # Fail-closed by design — see token_store.py's module docstring.
        raise HTTPException(status_code=503, detail="Session verification temporarily unavailable — please retry")

    set_auth_cookies(response, new_access, new_refresh)
    return {"detail": "Refreshed"}


@router.get("/me")
async def me(user_id: int = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await _serialize_user(user, db)


@router.patch("/me")
async def update_me(
    body: UserUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.username is not None and body.username != user.username:
        clash = (
            await db.execute(select(User).where(User.username == body.username, User.id != user_id))
        ).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="Username already taken")
        user.username = body.username

    if body.email is not None and body.email != user.email:
        # Email is the account-recovery channel — require the current
        # password so a stolen/leaked access token alone can't redirect it
        # and then use "forgot password" to take over the account.
        if not body.current_password or not verify_password(body.current_password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Current password is required to change your email")
        clash = (
            await db.execute(select(User).where(User.email == body.email, User.id != user_id))
        ).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = body.email

    await db.flush()
    return await _serialize_user(user, db)


@router.post("/me/password")
async def change_password(
    body: PasswordChange,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    await db.flush()
    return {"detail": "Password updated"}


# ── Profile photo ────────────────────────────────────────────────────────────

@router.post("/me/avatar")
@limiter.limit(AVATAR_UPLOAD_LIMIT, key_func=user_or_ip_key)
async def upload_avatar(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Resized/re-encoded server-side (see core/avatar.py) regardless of what
    the client sends — storage size and aspect ratio stay predictable no
    matter the source image, and the client never has to be trusted to have
    actually done any resizing itself."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Bounded read: a bare file.read() materialises the whole upload before
    # process_avatar_image's MAX_UPLOAD_BYTES guard can reject it, so a body
    # of any size ended up resident in memory first. Reading one byte past
    # the cap is enough for that guard to still see an over-limit value and
    # return 413.
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    user.avatar_url = process_avatar_image(raw, file.content_type)
    await db.flush()
    return await _serialize_user(user, db)


@router.delete("/me/avatar")
async def remove_avatar(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.avatar_url = None
    await db.flush()
    return await _serialize_user(user, db)


# ── 2FA ──────────────────────────────────────────────────────────────────────

@router.post("/2fa/setup")
@limiter.limit(TWO_FA_LIMIT, key_func=user_or_ip_key)
async def setup_2fa(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Generates (or regenerates) a TOTP secret and returns it plus its
    otpauth:// URI — shown once, same obligation as a password. Idempotent:
    calling this again before /2fa/enable just overwrites the unconfirmed
    secret; nothing takes effect until /2fa/enable verifies a real code, so
    there's no separate "pending" state to track."""
    if not settings.totp_encryption_key:
        raise HTTPException(status_code=501, detail="2FA is not configured on this server")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    secret = totp.generate_secret()
    user.totp_secret = totp.encrypt_secret(secret)
    await db.flush()
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, user.email)}


@router.post("/2fa/enable")
@limiter.limit(TWO_FA_LIMIT, key_func=user_or_ip_key)
async def enable_2fa(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    body: TwoFactorEnable,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user or not user.totp_secret:
        raise HTTPException(status_code=400, detail="Call /2fa/setup first")
    secret = totp.decrypt_secret(user.totp_secret)
    if not totp.verify_totp_code(secret, body.code):
        raise HTTPException(status_code=401, detail="Invalid code")
    codes = totp.generate_backup_codes()
    user.backup_codes = [hash_password(c) for c in codes]
    user.is_2fa_enabled = True
    await db.flush()
    return {"backup_codes": codes}


@router.post("/2fa/disable")
@limiter.limit(TWO_FA_LIMIT, key_func=user_or_ip_key)
async def disable_2fa(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    body: TwoFactorDisable,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Password reproof, same pattern PATCH /me already uses for the
    email-change guard — turning off a second factor is exactly as
    security-sensitive as changing the recovery email."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.hashed_password or not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user.is_2fa_enabled = False
    user.totp_secret = None
    user.backup_codes = []
    await db.flush()
    return {"detail": "2FA disabled"}


@router.post("/2fa/verify-login")
@limiter.limit(TWO_FA_VERIFY_LIMIT)
async def verify_2fa_login(request: Request, response: Response, body: PreAuthVerify, db: AsyncSession = Depends(get_db)):
    """Completes a login that /login (or /google) diverted into the 2FA
    challenge. Unauthenticated by design — the pre_auth_token itself is the
    only credential available at this point, same status as a password
    already having been checked once."""
    user_id = decode_token(body.pre_auth_token, expected_type="pre_auth")
    user = await db.get(User, user_id)
    if not user or not user.is_active or not user.is_2fa_enabled or not user.totp_secret:
        raise HTTPException(status_code=401, detail="Invalid or expired verification request")

    secret = totp.decrypt_secret(user.totp_secret)
    if totp.verify_totp_code(secret, body.code):
        _issue_session(response, user.id)
        return await _serialize_user(user, db)

    # Fall back to a backup code — single-use, so the matched hash is
    # removed from the list on success rather than just checked.
    for i, code_hash in enumerate(user.backup_codes):
        if verify_password(body.code, code_hash):
            user.backup_codes = user.backup_codes[:i] + user.backup_codes[i + 1:]
            await db.flush()
            _issue_session(response, user.id)
            return await _serialize_user(user, db)

    raise HTTPException(status_code=401, detail="Invalid code")


# ── Password reset ───────────────────────────────────────────────────────────

@router.post("/forgot-password")
@limiter.limit(PASSWORD_RESET_LIMIT)
async def forgot_password(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Always returns the same generic 200 regardless of whether the email
    is registered — enumeration-safe. The DB write (and thus the only
    branch that takes measurably longer) happens before the response is
    built either way, and the email send itself runs as a background task
    after the response is already returned, so a non-existent email can't
    be distinguished by response latency."""
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token_hash = hashlib.sha256(token.encode()).hexdigest()
        user.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=15)
        await db.flush()
        background_tasks.add_task(send_password_reset_email, user.email, token)
    return {"detail": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
@limiter.limit(AUTH_LIMIT)
async def reset_password(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    user = (await db.execute(select(User).where(User.reset_token_hash == token_hash))).scalar_one_or_none()
    if not user or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = hash_password(body.new_password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    user.password_changed_at = datetime.utcnow()
    await db.flush()
    token_store.revoke_all_sessions(user.id)
    return {"detail": "Password has been reset. Please log in again."}


@router.post("/sync-guest-data", response_model=GuestDataSyncResponse)
async def sync_guest_data(
    body: GuestDataSync,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Imports localStorage-only holdings/watchlist data (lib/guestData.ts)
    into the account, called by the frontend right after login/register
    resolves — separate from those endpoints since login has no "new data"
    concept and this keeps auth and data-import as distinct concerns.

    Watchlist: reuses the exact idempotent-insert pattern already
    established in app/db/seed.py's _seed_watchlist — ON CONFLICT DO NOTHING
    against the real uq_watchlist_user_ticker constraint, not a
    select-then-insert race.

    Holdings: no unique constraint exists to hang ON CONFLICT off (multiple
    legitimate buys of the same ticker on different dates are valid), so
    this dedupes on exact match of (ticker, buy_date, shares, avg_price) —
    only skips a re-import if it's byte-identical to an existing row, e.g. a
    retry after a failed sync (frontend only clears localStorage on a
    confirmed 2xx, so a failed sync's guest data gets resubmitted next login).
    """
    watchlist_imported = watchlist_skipped = 0
    if body.watchlist:
        stmt = pg_insert(WatchItem).values([
            {"user_id": user_id, **item.model_dump()} for item in body.watchlist
        ])
        stmt = stmt.on_conflict_do_nothing(constraint="uq_watchlist_user_ticker")
        result = await db.execute(stmt)
        watchlist_imported = result.rowcount
        watchlist_skipped = len(body.watchlist) - watchlist_imported

    holdings_imported = holdings_skipped = 0
    if body.holdings:
        existing = await db.execute(
            select(Holding.ticker, Holding.buy_date, Holding.shares, Holding.avg_price)
            .where(Holding.user_id == user_id)
        )
        existing_set = {tuple(row) for row in existing}
        new_holdings = [
            Holding(user_id=user_id, **h.model_dump())
            for h in body.holdings
            if (h.ticker, h.buy_date, h.shares, h.avg_price) not in existing_set
        ]
        db.add_all(new_holdings)
        holdings_imported = len(new_holdings)
        holdings_skipped = len(body.holdings) - holdings_imported

    await db.flush()
    return GuestDataSyncResponse(
        holdings=SyncResult(imported=holdings_imported, skipped=holdings_skipped),
        watchlist=SyncResult(imported=watchlist_imported, skipped=watchlist_skipped),
    )


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Stateful logout: blocklists the current access token's jti AND revokes
    its whole session (fail-open on Redis errors — see token_store.py), so
    neither the access token nor the refresh token minted alongside it keeps
    working. Cookies are always cleared regardless of whether either write
    succeeded — logout must never appear to fail to the client.

    Revoking the session matters as much as blocklisting the jti: blocklisting
    alone leaves the refresh token from the same login fully valid, so anyone
    holding a copy of it can mint a fresh access token immediately after the
    user logs out, for the remainder of the refresh lifetime (30 days).

    The token is read from the access cookie *or* the Authorization header:
    script/API clients authenticate by header (see core/auth.py's
    _extract_token), and a cookie-only lookup left them with no way to revoke
    anything — logout silently succeeded while their token stayed live.
    """
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if token is None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if token:
        try:
            decoded = decode_token_full(token, expected_type="access")
            ttl = decoded.exp - int(time.time())
            token_store.revoke_access_jti(decoded.jti, ttl)
            if decoded.sid:
                token_store.revoke_session(decoded.sid)
        except HTTPException:
            pass  # already-invalid/expired token — nothing to revoke
    clear_auth_cookies(response)
    return {"detail": "Logged out"}
