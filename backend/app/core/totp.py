"""
totp.py — TOTP secret generation/encryption and backup-code generation.

Pure crypto helpers, no DB access and no FastAPI Depends — same rationale
core/auth.py itself follows (see entitlements.py's docstring on why that
module stays separate): routes in routers/auth.py orchestrate these helpers
plus User mutation plus _issue_session, because that orchestration is
router-local, not because it belongs in this module.

totp_secret is stored Fernet-encrypted on User.totp_secret (see models.py) —
not plaintext (a DB dump would hand out every user's 2FA seed) and not
hashed (unlike a password, it must be decrypted to generate a comparison
code, so a one-way hash can't work here). Backup codes are the opposite: a
one-way bcrypt hash is exactly right (compare-only, via core.auth's existing
hash_password/verify_password — no new hashing code needed).
"""

from __future__ import annotations

import secrets

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()

_ISSUER = "Aegis"


def _fernet() -> Fernet:
    """Raises if TOTP_ENCRYPTION_KEY isn't configured — callers (routers/auth.py's
    /2fa/setup) must catch this and return 501, not let it 500."""
    if not settings.totp_encryption_key:
        raise RuntimeError("TOTP_ENCRYPTION_KEY is not configured")
    return Fernet(settings.totp_encryption_key.encode())


def generate_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        # Wrong/rotated encryption key, or corrupted data — treat as a
        # configuration error, not a user-facing 401, since it means every
        # 2FA-enabled user is locked out until the key is fixed.
        raise RuntimeError("Could not decrypt totp_secret — TOTP_ENCRYPTION_KEY may have changed")


def provisioning_uri(secret: str, email: str) -> str:
    """otpauth:// URI for the frontend to render as a QR code (see
    routers/auth.py's /2fa/setup — the backend never renders an image)."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER)


def verify_totp_code(secret: str, code: str) -> bool:
    """valid_window=1 tolerates one 30s step of clock drift either side —
    standard TOTP leniency, not a security weakening (still ~90s of total
    validity per code, well within normal expectations)."""
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def generate_backup_codes(count: int = 8) -> list[str]:
    """Plaintext codes, shown to the user exactly once by the /2fa/enable
    response — caller is responsible for hashing before storing (via
    core.auth.hash_password) and never persisting the plaintext."""
    return [f"{secrets.token_hex(4)[:4]}-{secrets.token_hex(4)[4:]}".upper() for _ in range(count)]
