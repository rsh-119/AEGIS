"""
documents.py — PDF upload + document AI analysis + Q&A.
"""

import io

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
from pydantic import BaseModel, Field

import pypdf

from app.core.entitlements import get_pro_user_id
from app.middleware.rate_limiter import AI_LIMIT, limiter, user_or_ip_key
from app.services import ai_service

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_PDF_BYTES = 30 * 1024 * 1024   # 30 MB

# Uploading and asking are deliberately open to anonymous callers — the free
# Ask AI PDF chat (components/AskAI.tsx) uses both without an account. What
# they were missing is a bound: /ask reaches the full LLM waterfall, and
# /upload-pdf drives pypdf over arbitrary bytes, with only the global
# 120/min ceiling in between. Keyed per-account where a token is present,
# per-IP otherwise (see user_or_ip_key).
PDF_UPLOAD_LIMIT = "20/minute"


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    company: str | None = Field(default=None, max_length=120)
    model: str = Field(default="deepseek", max_length=20)   # "groq" | "deepseek" | "minimax"


class AskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    question: str = Field(min_length=1, max_length=2000)
    company: str | None = Field(default=None, max_length=120)


@router.post("/upload-pdf")
@limiter.limit(PDF_UPLOAD_LIMIT, key_func=user_or_ip_key)
async def upload_pdf(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    file: UploadFile = File(...),
):
    """Extract text from an uploaded PDF (concall transcript / annual report).

    Read is capped at MAX_PDF_BYTES + 1 rather than unbounded: a bare
    `await file.read()` materialises the whole body before the size check
    below can reject it, so the guard did nothing to stop a multi-gigabyte
    upload from being resident in memory first.
    """
    content = await file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large (max 30 MB).")
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        text = "\n\n".join(pages).strip()
        if not text:
            raise HTTPException(
                status_code=422,
                detail="Could not extract text. This may be a scanned PDF — try copy-pasting the text instead.",
            )
        return {"text": text, "pages": len(reader.pages), "chars": len(text), "filename": file.filename}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF extraction failed: {e}")


@router.post("/analyze")
@limiter.limit(AI_LIMIT, key_func=user_or_ip_key)
async def analyze_document(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    req: AnalyzeRequest,
    _pro: int = Depends(get_pro_user_id),
):
    """Full AI analysis of a concall document or any financial text. Pro-only
    — exclusive to the /concall/document analyzer (unlike upload-pdf/ask,
    which are shared with the free Ask AI PDF-chat feature and stay open)."""
    text = req.text.strip()
    if len(text) < 100:
        raise HTTPException(status_code=422, detail="Document too short — paste at least a paragraph.")
    result = ai_service.public_result(
        await ai_service.analyze_document(text, req.company, model=req.model)
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/ask")
@limiter.limit(AI_LIMIT, key_func=user_or_ip_key)
async def ask_document(
    request: Request,
    response: Response,   # required by slowapi's header-injection wrapper
    req: AskRequest,
):
    """Answer a specific question about the uploaded document."""
    text = req.text.strip()
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Document text too short.")
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    result = ai_service.public_result(
        await ai_service.ask_document(text[:18000], req.question.strip(), req.company)
    )
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result
