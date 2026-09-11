"""Pydantic request/response schemas."""

import re
from datetime import date
from typing import Annotated, Literal
from pydantic import AfterValidator, BaseModel, EmailStr, Field


def _validate_password_complexity(v: str) -> str:
    """Shared by every schema that sets a new password (registration, change,
    reset) so the same policy applies regardless of which flow sets it —
    login intentionally does NOT use this, since it must keep accepting
    passwords that were valid under the old (6-char, no-complexity) rule."""
    if len(v) < 12:
        raise ValueError("Password must be at least 12 characters long")
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", v):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[^A-Za-z0-9]", v):
        raise ValueError("Password must contain at least one symbol")
    return v


NewPassword = Annotated[str, Field(max_length=100), AfterValidator(_validate_password_complexity)]

# Length bounds mirroring the mapped column widths in models.py. Without them
# an over-length value reaches Postgres and raises
# StringDataRightTruncationError, which surfaces to the client as an
# unhandled 500 instead of a 422 (and, on the create routes, only after an
# upstream quote lookup has already been paid for).
Ticker = Annotated[str, Field(min_length=1, max_length=20)]          # models: String(20)
CompanyName = Annotated[str, Field(max_length=120)]                   # models: String(120)
Sector = Annotated[str, Field(max_length=60)]                         # models: String(60)
Notes = Annotated[str, Field(max_length=2000)]                        # models: Text (bounded here)


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: NewPassword


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """PATCH /api/auth/me — both fields optional, only what's sent gets touched.
    current_password is required when email is being changed (email is the
    account-recovery channel — a bare access token shouldn't be enough to
    redirect it), but not for a username-only change."""
    username: str | None = Field(default=None, min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr | None = None
    current_password: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: NewPassword


class RefreshRequest(BaseModel):
    """Temporary rollout-only fallback body for POST /refresh — see
    routers/auth.py's module docstring. Auth is otherwise cookie-based;
    tokens are no longer returned in any response body."""
    refresh_token: str


# ── Auth: Google Sign-In ────────────────────────────────────────────────────

class GoogleLogin(BaseModel):
    credential: str  # Google Identity Services ID token (JWT), verified server-side


# ── Auth: 2FA ────────────────────────────────────────────────────────────────

class TwoFactorEnable(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TwoFactorDisable(BaseModel):
    current_password: str


class PreAuthVerify(BaseModel):
    """Body for POST /2fa/verify-login. `code` accepts either a live 6-digit
    TOTP code or an "XXXX-XXXX" backup code — the router tries TOTP first,
    falls back to backup codes, so this field intentionally isn't
    pattern-constrained to one shape."""
    pre_auth_token: str
    code: str


# ── Auth: password reset ────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: NewPassword


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    ticker: Ticker
    alert_type: str = Field(pattern=r"^(above|below)$")
    target_price: float = Field(gt=0)


class AlertUpdate(BaseModel):
    target_price: float | None = Field(default=None, gt=0)
    is_active: bool | None = None


# ── Holdings ──────────────────────────────────────────────────────────────────

class HoldingCreate(BaseModel):
    ticker: Ticker
    shares: float = Field(gt=0)
    avg_price: float = Field(gt=0)
    buy_date: date
    company_name: CompanyName | None = None
    sector: Sector | None = None
    notes: Notes | None = None


class HoldingUpdate(BaseModel):
    """PATCH /api/portfolio/{holding_id} — optimistic concurrency control.
    `version` is required and must match the holding's current version (as
    last returned by GET/POST/PATCH); a mismatch means someone else changed
    it first, and the endpoint returns 409 rather than silently overwriting
    their edit. All business fields are optional — only what's sent gets
    touched, same convention as UserUpdate."""
    version: int
    shares: float | None = Field(default=None, gt=0)
    avg_price: float | None = Field(default=None, gt=0)
    buy_date: date | None = None
    company_name: CompanyName | None = None
    sector: Sector | None = None
    notes: Notes | None = None


class HoldingOut(BaseModel):
    id: int
    ticker: str
    company_name: str | None
    shares: float
    avg_price: float
    buy_date: str
    sector: str | None
    notes: str | None
    version: int = 1
    current_price: float | None = None
    current_value: float | None = None
    invested: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None


# ── Watchlist ─────────────────────────────────────────────────────────────────

class WatchCreate(BaseModel):
    ticker: Ticker
    target_price: float | None = None
    company_name: CompanyName | None = None


# ── Guest-data sync (localStorage → account, on login/register) ────────────────
# Reuses HoldingCreate/WatchCreate directly rather than near-duplicate classes —
# the guest-side frontend store (lib/guestData.ts) mirrors those shapes exactly.

class GuestDataSync(BaseModel):
    # Caps are abuse/DoS guards on an authenticated-but-unmetered endpoint, not
    # real usage limits — no legitimate guest session accumulates anywhere
    # close to this many rows in localStorage before their first login.
    holdings: list[HoldingCreate] = Field(default_factory=list, max_length=50)
    watchlist: list[WatchCreate] = Field(default_factory=list, max_length=100)


class SyncResult(BaseModel):
    imported: int
    skipped: int


class GuestDataSyncResponse(BaseModel):
    holdings: SyncResult
    watchlist: SyncResult


# ── AI ────────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    """`question` goes straight into the provider prompt on an unauthenticated
    route, so its length is the size of the bill an anonymous caller can run
    up per request — bounded here rather than left to the provider."""
    question: str = Field(min_length=1, max_length=2000)
    ticker: Ticker | None = None


# ── AI response validation ────────────────────────────────────────────────────
# These validate the model's own JSON output (analyse_stock/diagnose_health/
# answer) before it ever reaches the frontend — catching a truncated or
# malformed response as a structural error rather than shipping broken JSON.
# Deliberately loose on list lengths (min_length=1, not the prompt's exact
# counts): the goal is to catch genuinely broken output, not to burn a
# repair round-trip because the model wrote 7 key_metrics instead of 8.

class KeyMetric(BaseModel):
    label: str
    value: str
    context: str
    signal: Literal["good", "warn", "bad", "neutral"]
    explanation: str


class AnalysisResponse(BaseModel):
    verdict: str
    verdict_reason: str
    confidence: str
    valuation_grade: str
    plain_summary: str
    valuation: str
    key_metrics: list[KeyMetric] = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    positives: list[str] = Field(min_length=1)
    bull_case: str
    bear_case: str
    outlook: str
    what_to_watch: list[str] = Field(min_length=1)


class HealthResponse(BaseModel):
    status: str
    status_reason: str
    financial_health_score: int = Field(ge=1, le=10)
    summary: str
    concerns: list[str] = Field(min_length=1)
    positives: list[str] = []
    red_flags: list[str] = []


class AskResponse(BaseModel):
    answer: str
    confidence: Literal["High", "Medium", "Low"]
    # True only if every specific fact/number in `answer` came from the injected
    # grounding data (or document text); False if the model drew on general/
    # training knowledge for any part of it. Required (not defaulted) so a
    # model that omits it trips the Task-4 repair-retry instead of silently
    # passing as "grounded" — lets the frontend flag recalled content instead
    # of presenting it with the same authority as live data.
    answered_from_facts: bool


class PortfolioObservation(BaseModel):
    severity: Literal["risk", "opportunity", "neutral"]
    title: str
    insight: str
    action: str


class HoldingSentiment(BaseModel):
    ticker: str
    sentiment: Literal["positive", "negative", "neutral"]
    headline: str   # the specific news headline (or short synthesis) driving this read
    reason: str      # one line — why this headline matters for the stock


class PortfolioReviewResponse(BaseModel):
    verdict: str
    observations: list[PortfolioObservation] = Field(min_length=1)
    # One entry per holding that had usable news — never fabricated for
    # holdings with no headlines in the injected data (see prompt rules).
    holdings_sentiment: list[HoldingSentiment] = []


class ChatResponse(BaseModel):
    reply: str
    suggestions: list[str] = []
    tickers: list[str] = []
    answered_from_facts: bool


class MarginAnalysis(BaseModel):
    gross_margin: str
    ebitda_margin: str
    pat_margin: str
    margin_commentary: str


class ManagementPromise(BaseModel):
    commitment: str
    timeline: str
    metric: str


class DocumentAnalysisResponse(BaseModel):
    executive_summary: str
    document_type: str
    company_name: str | None = None
    period: str
    key_themes: list[str] = Field(min_length=1)
    financial_highlights: list[str] = Field(min_length=1)
    margin_analysis: MarginAnalysis
    revenue_breakdown: list[str] = []
    key_management_quotes: list[str] = []
    management_promises: list[ManagementPromise] = []
    risks_and_concerns: list[str] = Field(min_length=1)
    strategic_initiatives: list[str] = []
    guidance: str | None = None
    capex_guidance: str | None = None
    sentiment: str
    sentiment_reason: str
    suggested_questions: list[str] = Field(min_length=1)
