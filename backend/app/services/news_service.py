"""
news_service.py — fetches up to 1 year of headlines for an Indian stock
and scores sentiment locally with VADER (no API key needed).

Sources:
  1. IndianAPI /company_news  (fast, India-specific)
  2. Google News RSS — multiple search queries to maximise coverage
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.services import indianapi_service
from app.services.stock_service import normalise_ticker

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=4)
_vader = SentimentIntensityAnalyzer()

# How far back to include (seconds). 1 year = 365 * 86400
_ONE_YEAR = 365 * 86_400


def _now_ts() -> float:
    return time.time()


def _rss_ts(entry) -> float | None:
    """Parse feedparser entry published time → Unix timestamp."""
    pt = getattr(entry, "published_parsed", None)
    if pt:
        try:
            return float(calendar.timegm(pt))
        except Exception:
            pass
    return None


def _fmt_date(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y")
    except Exception:
        return None


async def _fetch_indianapi_news(ticker: str, company: str | None, cutoff: float) -> tuple[list[dict], set[str]]:
    """IndianAPI /company_news — India-specific, no yfinance involved."""
    t = normalise_ticker(ticker)
    name = company or t.replace(".NS", "").replace(".BO", "")
    items: list[dict] = []
    seen: set[str] = set()
    try:
        for n in await indianapi_service.get_company_news(name):
            title = (n.get("title") or "").strip()
            if not title:
                continue
            ts: float | None = None
            raw_published = n.get("published")
            if raw_published:
                try:
                    # e.g. "Sat, 04 Jul 2026 10:49:42 IST" — drop tz abbreviation, treat as naive
                    naive = raw_published.rsplit(" ", 1)[0]
                    ts = datetime.strptime(naive, "%a, %d %b %Y %H:%M:%S").timestamp()
                except Exception:
                    ts = None
            if ts and ts < cutoff:
                continue
            key = title[:60]
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "title": title,
                "publisher": n.get("source", ""),
                "link": n.get("article_link", ""),
                "date": _fmt_date(ts),
                "ts": ts or 0,
            })
    except Exception as e:
        logger.debug("IndianAPI company_news failed: %s", e)
    return items, seen


def _fetch_rss_sync(ticker: str, company: str | None, cutoff: float, seen: set[str]) -> list[dict]:
    t = normalise_ticker(ticker)
    name = company or t.replace(".NS", "").replace(".BO", "")
    items: list[dict] = []

    # ── Google News RSS — multiple queries for wider coverage ────────────
    rss_queries = [
        f"{name} NSE stock",
        f"{name} earnings results quarterly",
        f"{name} share price",
        f"{name} company news India",
    ]

    for q in rss_queries:
        try:
            url = (
                f"https://news.google.com/rss/search?q={quote_plus(q)}"
                f"&hl=en-IN&gl=IN&ceid=IN:en"
            )
            feed = feedparser.parse(url)
            for entry in (feed.entries or [])[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                ts = _rss_ts(entry)
                if ts and ts < cutoff:
                    continue  # older than 1 year

                key = title[:60]
                if key in seen:
                    continue
                seen.add(key)

                try:
                    publisher = entry.source.title if hasattr(entry, "source") else "Google News"
                except Exception:
                    publisher = "Google News"

                items.append({
                    "title": title,
                    "publisher": publisher,
                    "link": entry.get("link", ""),
                    "date": _fmt_date(ts),
                    "ts": ts or 0,
                })
        except Exception as e:
            logger.debug("google rss failed for query '%s': %s", q, e)

    return items


def _score(items: list[dict]) -> dict:
    if not items:
        return {"label": "Neutral", "score": 0.0, "positive": 0, "negative": 0, "neutral": 0}
    pos = neg = neu = 0
    total = 0.0
    for it in items:
        c = _vader.polarity_scores(it["title"])["compound"]
        it["sentiment"] = round(c, 3)
        total += c
        if c >= 0.05:
            pos += 1
        elif c <= -0.05:
            neg += 1
        else:
            neu += 1
    avg = total / len(items)
    label = "Positive" if avg >= 0.05 else "Negative" if avg <= -0.05 else "Neutral"
    return {
        "label": label,
        "score": round(avg, 3),
        "positive": pos,
        "negative": neg,
        "neutral": neu,
    }


async def get_news_and_sentiment(ticker: str, company: str | None = None) -> dict:
    cutoff = _now_ts() - _ONE_YEAR

    india_items, seen = await _fetch_indianapi_news(ticker, company, cutoff)

    loop = asyncio.get_event_loop()
    rss_items = await loop.run_in_executor(_pool, _fetch_rss_sync, ticker, company, cutoff, seen)

    items = india_items + rss_items
    items.sort(key=lambda x: x.get("ts", 0), reverse=True)
    items = items[:60]

    sentiment = _score(items)
    return {"articles": items, "sentiment": sentiment}
