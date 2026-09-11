"""File upload handling: avatars (Pillow) and PDFs (pypdf).

Both endpoints accept an arbitrary body from the network, so the questions
are: is the content actually validated, is the size bounded *before* the
bytes are materialised, and can anything be stored that would later be
served as executable content?
"""

from __future__ import annotations

import io
import zlib

import pytest
from PIL import Image

from app.core.avatar import MAX_UPLOAD_BYTES, process_avatar_image
from app.core.cache import cache
from app.middleware.rate_limiter import AI_LIMIT
from app.services import ai_service

# ── Rate-limit helpers ────────────────────────────────────────────────────────
# Budgets are derived from the limiter's own constants, so retuning a limit
# updates these tests instead of silently making them assert the wrong number.

def _limit_per_minute(limit: str) -> int:
    return int(limit.split("/")[0])


AI_BUDGET = _limit_per_minute(AI_LIMIT)
PDF_UPLOAD_BUDGET = 20   # routers/documents.py's explicit upload bound


def _reset_rate_limit_buckets() -> None:
    """Each test gets a fresh bucket; slowapi counts in the shared Redis db
    the suite also flushes between tests."""
    if cache._redis is not None:
        cache._redis.flushdb()


@pytest.fixture
def stub_ai_provider(monkeypatch):
    """Make provider calls instant and offline so the loop measures the rate
    limiter, not the waterfall's retry/timeout behaviour."""
    async def _ok(system, user, max_tokens, model=None, temperature=None, timeout=None):
        return {
            "answer": "ok", "confidence": "High", "answered_from_facts": True,
            "reply": "ok", "tickers": [], "suggestions": [],
            "executive_summary": "ok", "document_type": "concall",
            "company_name": "TCS", "period": "Q1 FY26",
            "key_themes": ["a"], "financial_highlights": ["b"],
            "margin_analysis": {"gross_margin": "1%", "ebitda_margin": "1%",
                                "pat_margin": "1%", "margin_commentary": "ok"},
            "risks_and_concerns": ["c"], "sentiment": "Positive",
            "sentiment_reason": "ok", "suggested_questions": ["q?"],
        }

    for fn in ("_call_groq", "_call_openrouter", "_call_nvidia", "_call_gemini"):
        if hasattr(ai_service, fn):
            monkeypatch.setattr(ai_service, fn, _ok)
    yield




def _png(size=(64, 64), color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (0, 128, 255)).save(buf, format="JPEG")
    return buf.getvalue()


def _minimal_pdf(text: str = "Hello Aegis") -> bytes:
    """A tiny but genuinely valid single-page PDF with extractable text."""
    content = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n"
            "%%EOF").encode()
    return bytes(out)


# ── Avatar: content validation ────────────────────────────────────────────────

def test_avatar_accepts_a_real_png():
    out = process_avatar_image(_png(), "image/png")
    assert out.startswith("data:image/webp;base64,")


def test_avatar_normalises_every_source_to_a_fixed_square():
    """Output dimensions must not depend on the input, so stored size stays
    predictable no matter what the client sends."""
    import base64
    for size in [(64, 64), (2000, 100), (100, 2000), (1, 1)]:
        out = process_avatar_image(_png(size), "image/png")
        raw = base64.b64decode(out.split(",", 1)[1])
        img = Image.open(io.BytesIO(raw))
        assert img.size == (320, 320), f"{size} produced {img.size}"
        assert img.format == "WEBP"


def test_avatar_rejects_a_non_image_content_type():
    with pytest.raises(Exception) as e:
        process_avatar_image(_png(), "application/pdf")
    assert e.value.status_code == 400


def test_avatar_rejects_a_text_file_renamed_as_an_image():
    with pytest.raises(Exception) as e:
        process_avatar_image(b"#!/bin/sh\nrm -rf /\n", "image/png")
    assert e.value.status_code == 422


def test_avatar_rejects_an_html_payload_declared_as_an_image():
    """Stored HTML would be served back inside the avatar data URL."""
    with pytest.raises(Exception) as e:
        process_avatar_image(b"<html><script>alert(1)</script></html>", "image/png")
    assert e.value.status_code == 422


def test_avatar_rejects_svg():
    """SVG is script-capable; it must not survive as SVG."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(Exception) as e:
        process_avatar_image(svg, "image/svg+xml")
    assert e.value.status_code == 422


def test_avatar_rejects_empty_content():
    with pytest.raises(Exception) as e:
        process_avatar_image(b"", "image/png")
    assert e.value.status_code == 422


def test_avatar_rejects_a_truncated_image():
    truncated = _png()[: len(_png()) // 2]
    with pytest.raises(Exception) as e:
        process_avatar_image(truncated, "image/png")
    assert e.value.status_code == 422


def test_avatar_rejects_oversize_content():
    with pytest.raises(Exception) as e:
        process_avatar_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_UPLOAD_BYTES + 1), "image/png")
    assert e.value.status_code == 413


def test_avatar_output_never_contains_raw_script_text():
    out = process_avatar_image(_jpeg(), "image/jpeg")
    assert "<script" not in out and "javascript:" not in out


def test_avatar_strips_metadata_by_re_encoding():
    """Re-encoding means EXIF/GPS from the source never reaches storage."""
    import base64
    buf = io.BytesIO()
    img = Image.new("RGB", (400, 400), (10, 20, 30))
    img.save(buf, format="JPEG", exif=Image.Exif().tobytes())
    out = process_avatar_image(buf.getvalue(), "image/jpeg")
    raw = base64.b64decode(out.split(",", 1)[1])
    assert Image.open(io.BytesIO(raw)).getexif().items() == {}.items()


# ── Avatar: the HTTP boundary ─────────────────────────────────────────────────

async def test_avatar_upload_requires_auth(client):
    r = await client.post("/api/auth/me/avatar",
                          files={"file": ("a.png", _png(), "image/png")})
    assert r.status_code == 401


async def test_avatar_upload_stores_a_webp_data_url(client, user_a, bearer):
    r = await client.post("/api/auth/me/avatar",
                          files={"file": ("a.png", _png(), "image/png")},
                          headers=bearer(user_a.id))
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"].startswith("data:image/webp;base64,")


async def test_avatar_upload_rejects_a_renamed_executable(client, user_a, bearer):
    r = await client.post("/api/auth/me/avatar",
                          files={"file": ("evil.png", b"MZ\x90\x00" + b"\x00" * 500, "image/png")},
                          headers=bearer(user_a.id))
    assert r.status_code == 422


@pytest.mark.parametrize("filename", [
    "../../../etc/passwd.png", "..\\..\\windows\\system32.png",
    "a\x00.png", "𝕏𝕏𝕏.png", "a" * 300 + ".png",
])
async def test_avatar_filename_is_never_used_for_storage(client, user_a, bearer, filename):
    """Content is stored inline as a data URL, so a hostile filename must be
    irrelevant — never echoed, never used as a path."""
    r = await client.post("/api/auth/me/avatar",
                          files={"file": (filename, _png(), "image/png")},
                          headers=bearer(user_a.id))
    assert r.status_code == 200, r.text
    assert filename not in r.text


async def test_avatar_delete_clears_the_stored_image(client, user_a, bearer):
    await client.post("/api/auth/me/avatar",
                      files={"file": ("a.png", _png(), "image/png")},
                      headers=bearer(user_a.id))
    r = await client.delete("/api/auth/me/avatar", headers=bearer(user_a.id))
    assert r.status_code == 200 and r.json()["avatar_url"] is None


async def test_avatar_upload_rejects_oversize_with_413(client, user_a, bearer):
    """The cap is enforced (413, not 500 or silent acceptance). Note this
    only proves the outcome: the guard lives inside process_avatar_image, so
    the bytes are already resident by the time it runs — see
    test_avatar_read_is_bounded_before_processing for that half."""
    oversize = b"\x89PNG\r\n\x1a\n" + b"\x00" * (12 * 1024 * 1024)
    r = await client.post("/api/auth/me/avatar",
                          files={"file": ("big.png", oversize, "image/png")},
                          headers=bearer(user_a.id))
    assert r.status_code == 413


async def test_avatar_read_is_bounded_before_processing(client, user_a, bearer, monkeypatch):
    """`raw = await file.read()` with no argument materialises the entire
    upload before any size check. Assert the handler never asks for the whole
    body unbounded — an oversize request must be refused on the declared
    length, or read in a bounded way."""
    import app.routers.auth as auth_router

    unbounded_reads: list[int | None] = []
    real_process = auth_router.process_avatar_image

    from starlette.datastructures import UploadFile as StarletteUploadFile
    original_read = StarletteUploadFile.read

    async def _tracking_read(self, size: int = -1):
        unbounded_reads.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(StarletteUploadFile, "read", _tracking_read)

    oversize = b"\x89PNG\r\n\x1a\n" + b"\x00" * (12 * 1024 * 1024)
    await client.post("/api/auth/me/avatar",
                      files={"file": ("big.png", oversize, "image/png")},
                      headers=bearer(user_a.id))

    assert unbounded_reads and all(s != -1 for s in unbounded_reads), (
        "upload_avatar calls file.read() with no size limit, so a body of any "
        f"size is fully buffered before the 8 MB guard runs (reads: {unbounded_reads})"
    )


# ── PDF upload ────────────────────────────────────────────────────────────────

async def test_pdf_upload_extracts_text(client):
    r = await client.post("/api/documents/upload-pdf",
                          files={"file": ("doc.pdf", _minimal_pdf("Revenue grew 12%"), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Revenue grew" in body["text"]
    assert body["pages"] == 1


async def test_pdf_upload_rejects_a_non_pdf(client):
    r = await client.post("/api/documents/upload-pdf",
                          files={"file": ("doc.pdf", b"this is plain text", "application/pdf")})
    assert r.status_code == 422


async def test_pdf_upload_rejects_an_image_renamed_as_pdf(client):
    r = await client.post("/api/documents/upload-pdf",
                          files={"file": ("doc.pdf", _png(), "application/pdf")})
    assert r.status_code == 422


async def test_pdf_upload_rejects_empty_content(client):
    r = await client.post("/api/documents/upload-pdf",
                          files={"file": ("doc.pdf", b"", "application/pdf")})
    assert r.status_code == 422


async def test_pdf_extraction_error_does_not_leak_internals(client):
    r = await client.post("/api/documents/upload-pdf",
                          files={"file": ("doc.pdf", b"%PDF-1.4\ngarbage", "application/pdf")})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "Traceback" not in detail
    assert "/home/" not in detail and "site-packages" not in detail, (
        f"PDF error leaked internal paths: {detail}"
    )


async def test_pdf_upload_is_rate_limited(client):
    """Anonymous access is intentional (the free Ask AI PDF chat uses it), so
    the control that matters is a bound: without one, a CPU-bound pypdf parse
    over arbitrary bytes is reachable at the global 120/min ceiling.

    Asserted by actually exhausting the bucket. The previous version of this
    test checked that the endpoint function carried a `__wrapped__` attribute
    — an implementation detail of slowapi's decorator, which proves a decorator
    was applied but never that a request is refused, and which silently stopped
    finding the route at all when FastAPI changed how include_router nests
    routes.
    """
    _reset_rate_limit_buckets()
    codes = []
    for _ in range(PDF_UPLOAD_BUDGET + 4):
        r = await client.post(
            "/api/documents/upload-pdf",
            files={"file": ("doc.pdf", _minimal_pdf(), "application/pdf")},
        )
        codes.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codes, (
        f"POST /api/documents/upload-pdf never refused a request in "
        f"{len(codes)} attempts — a CPU-bound pypdf parse is reachable at the "
        f"global ceiling. Codes: {codes}"
    )


async def test_pdf_upload_enforces_its_size_cap_before_reading_the_body(client):
    """30 MB is checked after `await file.read()`, so the bytes are already
    resident before the guard runs."""
    big = _minimal_pdf() + b"\n%" + b"A" * (40 * 1024 * 1024)
    r = await client.post("/api/documents/upload-pdf",
                          files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 413


@pytest.mark.parametrize("path,body,needs_pro", [
    ("/api/documents/ask",     {"text": "Revenue grew. " * 30, "question": "How?"}, False),
    # Pro-gated: entitlement is checked before the limiter, so without
    # credentials this route 401s and never reaches its quota at all.
    ("/api/documents/analyze", {"text": "Revenue grew. " * 30, "company": "TCS"}, True),
    ("/api/ai/ask",            {"question": "What is the outlook?"}, False),
    ("/api/ai/ask-stream",     {"question": "What is the outlook?"}, False),
    ("/api/chat",              {"message": "hello", "history": []}, False),
])
async def test_llm_endpoints_carry_an_ai_rate_limit(
    client, path, body, needs_pro, pro_user, bearer, stub_ai_provider
):
    """Every route that can reach the provider waterfall needs its own AI
    quota; the global 120/min ceiling is not a spend control.

    Driven through the real HTTP path and asserted on a real 429, rather than
    on slowapi's `__wrapped__` marker. A decorator being present is not the
    property that matters — a request being refused is — and the marker check
    broke silently (StopIteration, no route found) the moment FastAPI changed
    its router internals, which is exactly the failure mode an
    implementation-detail assertion has.
    """
    _reset_rate_limit_buckets()
    headers = bearer(pro_user.id) if needs_pro else {}
    codes = []
    for _ in range(AI_BUDGET + 4):
        r = await client.post(path, json=body, headers=headers)
        codes.append(r.status_code)
        if r.status_code == 429:
            break
    assert 401 not in codes and 403 not in codes, (
        f"POST {path} rejected before the quota could be exercised — this test "
        f"would then prove nothing about rate limiting. Codes: {codes}"
    )
    assert 429 in codes, (
        f"POST {path} never returned 429 in {len(codes)} attempts — a caller "
        f"can issue LLM requests at the global 120/min ceiling. Codes: {codes}"
    )
    assert codes.index(429) <= AI_BUDGET, (
        f"POST {path} allowed {codes.index(429)} calls before refusing, more "
        f"than AI_LIMIT ({AI_BUDGET}/min) permits: {codes}"
    )
