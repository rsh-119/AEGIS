"""
avatar.py — profile photo validation, crop/resize, re-encode.

Pure image-processing helper, no DB access — same rationale as core/oauth.py
and core/totp.py (routers/auth.py's /me/avatar orchestrates this plus the
User mutation, because that orchestration is router-local).

Stored directly on users.avatar_url as a `data:image/webp;base64,...` URL,
not a reference into any object-storage bucket — this codebase has no S3/
Cloudinary/Supabase-Storage integration, and every upload is forced down to
a fixed 320x320 WEBP thumbnail before it's ever written, so the stored
string stays small (a few tens of KB). A plain Postgres TEXT column is the
simplest correct choice at that size, same reasoning as PortfolioReview's
JSON blobs — reach for real object storage only if avatars ever need to be
originals/full-size, which a profile photo never does.
"""

from __future__ import annotations

import base64
import io

from fastapi import HTTPException
from PIL import Image, ImageOps

MAX_UPLOAD_BYTES = 8 * 1024 * 1024   # 8 MB raw upload guard, before any processing
TARGET_SIZE = 320                     # square thumbnail, px per side
WEBP_QUALITY = 82
MAX_ENCODED_BYTES = 400 * 1024        # sanity cap on the final data URL's payload


def process_avatar_image(raw: bytes, content_type: str | None) -> str:
    """Validates, center-crops to a TARGET_SIZE square, re-encodes as WEBP,
    and returns a `data:image/webp;base64,...` URL ready to store on
    User.avatar_url. Raises HTTPException (400/413/422) on anything
    invalid — routers/auth.py's upload_avatar lets these propagate as-is."""
    if not content_type or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image too large — max 8 MB")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()   # force a full decode now, not lazily on first use — a
                      # truncated/corrupt file must fail here, not later
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read that file as an image")

    # EXIF-aware rotation first (phone photos often carry a rotation tag the
    # raw pixel data ignores), then normalise to RGB — drops alpha/CMYK/
    # palette quirks that would otherwise break the WEBP re-encode below.
    img = ImageOps.exif_transpose(img).convert("RGB")

    # Center-crop to a square before resizing, so every avatar renders at
    # the same aspect ratio regardless of the source photo's shape.
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize(
        (TARGET_SIZE, TARGET_SIZE), Image.LANCZOS
    )

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY)
    encoded = buf.getvalue()
    if len(encoded) > MAX_ENCODED_BYTES:
        # Practically unreachable at 320x320/quality 82 for a real photo —
        # guarded anyway rather than trusting that combination never changes.
        raise HTTPException(status_code=413, detail="Image couldn't be compressed small enough — try a different photo")

    b64 = base64.b64encode(encoded).decode()
    return f"data:image/webp;base64,{b64}"
