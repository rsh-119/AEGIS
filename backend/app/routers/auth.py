"""/api/auth/* — register, login, token refresh, profile.

Auth is cookie-based (httpOnly access + refresh cookies — see
core/auth.py's set_auth_cookies/clear_auth_cookies) with an
Authorization: Bearer fallback for non-browser clients, handled transparently
by get_current_user_id. /login, /register, /refresh no longer return tokens
in the JSON body.

/refresh keeps a temporary fallback that also accepts a JSON
{"refresh_token": "..."} body for one deploy cycle, so an already-open
browser tab running the previous (localStorage-based) frontend build doesn't
hard-break mid-session while Vercel/Render finish redeploying — see the RFC's
rollout section. Remove that fallback once no such clients remain.
"""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import token_store
from app.core.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_token_full,
    get_current_user_id,
    hash_password,
    set_auth_cookies,
    verify_password,
)
from app.core.database import get_db
from app.core.entitlements import is_pro_user
from app.middleware.rate_limiter import AUTH_LIMIT, limiter
from app.models import Holding, User, WatchItem
from app.schemas import (
    GuestDataSync,
    GuestDataSyncResponse,
    PasswordChange,
    RefreshRequest,
    SyncResult,
    UserLogin,
    UserRegister,
    UserUpdate,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _serialize_user(user: User, db: AsyncSession) -> dict:
    """user.to_dict() alone still carries the stale, no-longer-written
    users.is_pro column — overlay the live value from `subscriptions` (see
    entitlements.py), same source of truth every gating check uses."""
    return {**user.to_dict(), "is_pro": await is_pro_user(user.id, db)}


def _issue_session(response: Response, user_id: int) -> None:
    """Mint a fresh login session: one session_id shared by the access token
    and the first refresh token in its rotation chain, cookies set on the
    response, and the chain's starting pointer recorded in Redis."""
    session_id = str(uuid.uuid4())
    access_token = create_access_token(user_id, session_id)
    refresh_token, refresh_jti = create_refresh_token(user_id, session_id)
    token_store.start_session(session_id, refresh_jti)
    set_auth_cookies(response, access_token, refresh_token)


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
    _issue_session(response, user.id)
    return await _serialize_user(user, db)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,   # temporary rollout fallback — see module docstring
    db: AsyncSession = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME) or (body.refresh_token if body else None)
    if not raw_token:
        raise HTTPException(status_code=401, detail="No refresh token presented")

    decoded = decode_token_full(raw_token, expected_type="refresh")
    if not decoded.sid:
        # Pre-migration token minted before sid/jti existed — no rotation
        # chain to verify against. Accept once so an in-flight session isn't
        # hard-broken by the deploy, but it gets a fresh sid from here on.
        user = await db.get(User, decoded.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")
        _issue_session(response, decoded.user_id)
        return {"detail": "Refreshed"}

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
    """Stateful logout: blocklists the current access token's jti (fail-open
    on Redis errors — see token_store.py) so a stolen-but-not-yet-expired
    token stops working immediately, not just after its natural exp. Cookies
    are always cleared regardless of whether the blocklist write succeeded —
    logout must never appear to fail to the client."""
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if token:
        try:
            decoded = decode_token_full(token, expected_type="access")
            ttl = decoded.exp - int(time.time())
            token_store.revoke_access_jti(decoded.jti, ttl)
        except HTTPException:
            pass  # already-invalid/expired token — nothing to revoke
    clear_auth_cookies(response)
    return {"detail": "Logged out"}
