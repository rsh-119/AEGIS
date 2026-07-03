"""/api/ai/* — grounded Q&A endpoint."""

import asyncio
from fastapi import APIRouter
from app.schemas import AskRequest
from app.services import stock_service, news_service, ai_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/ask")
async def ask(body: AskRequest):
    quote = hist = articles = None
    if body.ticker:
        quote, hist_result = await asyncio.gather(
            stock_service.get_quote(body.ticker),
            stock_service.get_history(body.ticker, "3mo"),
        )
        if "error" in quote:
            quote = None
            hist = None
        else:
            hist = hist_result
            company = quote.get("company_name")
            news_data = await news_service.get_news_and_sentiment(body.ticker, company)
            articles = news_data.get("articles", [])

    result = await ai_service.answer(body.question, quote, hist, articles)
    return {"question": body.question, **result}
