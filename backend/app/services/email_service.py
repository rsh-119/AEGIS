"""
email_service.py — transactional email via Resend, over raw httpx (no SDK,
same convention as the rest of this codebase's third-party integrations —
see e.g. ai_service.py's Gemini calls).

Fails closed until configured: with no RESEND_API_KEY set, send_* functions
log the content they would have sent (at INFO) instead of making a network
call — same pattern as admin_api_key/sentry_dsn, gated on whether the key is
set, not on APP_ENV. This means local dev "sends" password-reset emails by
printing the reset link to the backend console.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_RESEND_URL = "https://api.resend.com/emails"


async def _send(to_email: str, subject: str, html: str, *, log_fallback: str) -> None:
    if not settings.resend_api_key:
        logger.info("Email (Resend not configured) — to=%s subject=%r\n%s", to_email, subject, log_fallback)
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from_address,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
            resp.raise_for_status()
    except Exception:
        # Best-effort — a failed send must never break the request that
        # triggered it (forgot-password always returns a generic 200
        # regardless). Logged so it's visible in ops, not silently lost.
        logger.exception("Failed to send email via Resend — to=%s subject=%r", to_email, subject)


async def send_password_reset_email(to_email: str, token: str) -> None:
    """token is the plaintext reset token — only ever passed here and into
    the URL; the DB only ever stores its sha256 hash (see routers/auth.py's
    forgot_password)."""
    link = f"{settings.frontend_url}/reset-password?token={token}"
    html = (
        f"<p>Someone requested a password reset for your Aegis account.</p>"
        f'<p><a href="{link}">Reset your password</a> — this link expires in 15 minutes.</p>'
        f"<p>If you didn't request this, you can safely ignore this email.</p>"
    )
    await _send(to_email, "Reset your Aegis password", html, log_fallback=link)
