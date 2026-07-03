"""
documents.py — PDF upload + document AI analysis + Q&A.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

import pypdf

from app.services import ai_service

router = APIRouter(prefix="/api/documents", tags=["documents"])


class AnalyzeRequest(BaseModel):
    text: str
    company: str | None = None
    model: str = "deepseek"   # "groq" | "deepseek" | "minimax"


class AskRequest(BaseModel):
    text: str
    question: str
    company: str | None = None


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF (concall transcript / annual report)."""
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:  # 30 MB guard
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
async def analyze_document(req: AnalyzeRequest):
    """Full AI analysis of a concall document or any financial text."""
    text = req.text.strip()
    if len(text) < 100:
        raise HTTPException(status_code=422, detail="Document too short — paste at least a paragraph.")
    result = await ai_service.analyze_document(text, req.company, model=req.model)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/ask")
async def ask_document(req: AskRequest):
    """Answer a specific question about the uploaded document."""
    text = req.text.strip()
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Document text too short.")
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    result = await ai_service.ask_document(text[:18000], req.question.strip(), req.company)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result
