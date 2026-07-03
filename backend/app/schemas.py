"""Pydantic request/response schemas."""

from datetime import date
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    ticker: str
    alert_type: str = Field(pattern=r"^(above|below)$")
    target_price: float = Field(gt=0)


class AlertUpdate(BaseModel):
    target_price: float | None = Field(default=None, gt=0)
    is_active: bool | None = None


# ── Holdings ──────────────────────────────────────────────────────────────────

class HoldingCreate(BaseModel):
    ticker: str
    shares: float = Field(gt=0)
    avg_price: float = Field(gt=0)
    buy_date: date
    company_name: str | None = None
    sector: str | None = None
    notes: str | None = None


class HoldingOut(BaseModel):
    id: int
    ticker: str
    company_name: str | None
    shares: float
    avg_price: float
    buy_date: str
    sector: str | None
    notes: str | None
    current_price: float | None = None
    current_value: float | None = None
    invested: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None


# ── Watchlist ─────────────────────────────────────────────────────────────────

class WatchCreate(BaseModel):
    ticker: str
    target_price: float | None = None
    company_name: str | None = None


# ── AI ────────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    ticker: str | None = None
