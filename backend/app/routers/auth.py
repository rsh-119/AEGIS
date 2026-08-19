"""/api/auth/* — register, login, token refresh, profile."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from app.core.database import get_db
from app.models import User
from app.schemas import PasswordChange, RefreshRequest, TokenResponse, UserLogin, UserRegister, UserUpdate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
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
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
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
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    user_id = decode_token(body.refresh_token, expected_type="refresh")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.get("/me")
async def me(user_id: int = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.to_dict()


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
    return user.to_dict()


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


@router.post("/logout")
async def logout():
    """Stateless logout — client discards tokens."""
    return {"detail": "Logged out"}
