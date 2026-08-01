"""Pydantic request/response schemas."""

from datetime import date
from typing import Literal
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
