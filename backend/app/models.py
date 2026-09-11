"""SQLAlchemy ORM models."""

from datetime import datetime, date

from sqlalchemy import Boolean, ForeignKey, Integer, String, Float, Date, DateTime, JSON, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """App user — email + hashed password, no PII beyond email."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    # Nullable as of Google Sign-In: an OAuth-only account has no password to
    # hash. auth_provider distinguishes "local, password required" from
    # "google, hashed_password is None" — see core/oauth.py.
    hashed_password: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(20), default="local", server_default="local")
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # NOTE: there is deliberately no `is_pro` column. Entitlements live in
    # `subscriptions` (see core/entitlements.py); the old boolean was dropped
    # in migration 8c1d4a7f9e20 once nothing read it, so it can no longer
    # drift out of sync with the row that actually grants access.

    # Profile photo — a `data:image/webp;base64,...` URL, not a storage-bucket
    # reference: this codebase has no S3/Cloudinary/Supabase-Storage
    # integration, and core/avatar.py always resizes to a fixed 320x320
    # WEBP thumbnail before this is ever written, so the stored string stays
    # small (a few tens of KB) — a plain TEXT column is the simplest correct
    # choice here, same reasoning as PortfolioReview's JSON blobs.
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 2FA (core/totp.py) ───────────────────────────────────────────────────
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    totp_secret: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Fernet-encrypted, never plaintext
    backup_codes: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # bcrypt hashes, single-use

    # ── Password reset (routers/auth.py's forgot-password/reset-password) ───
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # sha256 hex
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # audit only, not read by any auth check

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        """Note: no "is_pro" key. Pro status is not a property of this row —
        it is derived from `subscriptions` and is overlaid by the callers that
        need it (routers/auth.py::_serialize_user, routers/admin.py), so that
        there is exactly one source of truth. See core/entitlements.py."""
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "auth_provider": self.auth_provider,
            "has_password": self.hashed_password is not None,
            "is_2fa_enabled": self.is_2fa_enabled,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Subscription(Base):
    """Replaced the bare users.is_pro boolean with plan/status/expiry and
    room for a billing-provider link. Zero rows here = free tier, by
    construction. The users.is_pro column it replaced was carried unread for
    one release and has since been dropped (migration 8c1d4a7f9e20), so this
    table is now the only place Pro status exists. No relationship() to User, same
    plain-FK-column convention every other user-owned table here uses
    (Holding, WatchItem, PriceAlert, PortfolioReview)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")          # "free" | "pro"
    status: Mapped[str] = mapped_column(String(20), default="active")      # "active" | "canceled" | "past_due"
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    razorpay_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        """Note: no "is_pro" key. Pro status is not a property of this row —
        it is derived from `subscriptions` and is overlaid by the callers that
        need it (routers/auth.py::_serialize_user, routers/admin.py), so that
        there is exactly one source of truth. See core/entitlements.py."""
        return {
            "plan": self.plan,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shares: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)          # in INR
    buy_date: Mapped[date] = mapped_column(Date)
    sector: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # Must come after `version` is defined — SQLAlchemy's declarative
    # processing needs the actual mapped_column object here, not a string
    # name. This is what makes the unit-of-work include `version` in every
    # UPDATE's WHERE clause and auto-increment it — a lost-update race (two
    # writers reading the same version, both trying to write) raises
    # StaleDataError instead of silently applying a lost update.
    __mapper_args__ = {"version_id_col": version}

    def to_dict(self) -> dict:
        """Note: no "is_pro" key. Pro status is not a property of this row —
        it is derived from `subscriptions` and is overlaid by the callers that
        need it (routers/auth.py::_serialize_user, routers/admin.py), so that
        there is exactly one source of truth. See core/entitlements.py."""
        return {
            "id": self.id,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "shares": self.shares,
            "avg_price": self.avg_price,
            "buy_date": self.buy_date.isoformat(),
            "sector": self.sector,
            "notes": self.notes,
            "version": self.version,
        }


class WatchItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        """Note: no "is_pro" key. Pro status is not a property of this row —
        it is derived from `subscriptions` and is overlaid by the callers that
        need it (routers/auth.py::_serialize_user, routers/admin.py), so that
        there is exactly one source of truth. See core/entitlements.py."""
        return {
            "id": self.id,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "target_price": self.target_price,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PriceAlert(Base):
    """User-defined price alert — fires when ticker crosses target."""

    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    alert_type: Mapped[str] = mapped_column(String(10))   # "above" | "below"
    target_price: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        """Note: no "is_pro" key. Pro status is not a property of this row —
        it is derived from `subscriptions` and is overlaid by the callers that
        need it (routers/auth.py::_serialize_user, routers/admin.py), so that
        there is exactly one source of truth. See core/entitlements.py."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "alert_type": self.alert_type,
            "target_price": self.target_price,
            "is_active": self.is_active,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PortfolioReview(Base):
    """One row per generated AI portfolio review — full history, not just
    latest, so a future "past reviews"/trend feature needs no schema change."""

    __tablename__ = "portfolio_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    observations: Mapped[list] = mapped_column(JSON)
    holdings_sentiment: Mapped[list] = mapped_column(JSON, default=list)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    shown_holdings: Mapped[int] = mapped_column(Integer)
    total_holdings: Mapped[int] = mapped_column(Integer)
    incomplete_holdings: Mapped[list] = mapped_column(JSON, default=list)
    fingerprint: Mapped[str] = mapped_column(String(24), index=True)   # matches the Redis cache-key hash
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        """Note: no "is_pro" key. Pro status is not a property of this row —
        it is derived from `subscriptions` and is overlaid by the callers that
        need it (routers/auth.py::_serialize_user, routers/admin.py), so that
        there is exactly one source of truth. See core/entitlements.py."""
        return {
            "verdict": self.verdict,
            "observations": self.observations,
            "holdings_sentiment": self.holdings_sentiment,
            "truncated": self.truncated,
            "shown_holdings": self.shown_holdings,
            "total_holdings": self.total_holdings,
            "incomplete_holdings": self.incomplete_holdings,
            "generated_at": self.created_at.isoformat() if self.created_at else None,
        }


class AICache(Base):
    """Caches AI-generated analysis (NVIDIA/Groq/OpenRouter) to avoid repeat API calls."""

    __tablename__ = "ai_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(120), index=True)  # e.g. "analysis:TCS.NS:6mo"
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
