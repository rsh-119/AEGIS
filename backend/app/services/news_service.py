"""
news_service.py — fetches up to 1 year of headlines for an Indian stock
and scores sentiment locally with VADER (no API key needed).

Sources:
  1. yfinance .news  (fast, often India-relevant, includes publish timestamps)
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
import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

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


def _fetch_sync(ticker: str, company: str | None) -> list[dict]:
    t = normalise_ticker(ticker)
    name = company or t.replace(".NS", "").replace(".BO", "")
    now = _now_ts()
    cutoff = now - _ONE_YEAR
    items: list[dict] = []
    seen: set[str] = set()

    # ── 1. yfinance news ────────────────────────────────────────────────────
    try:
        for n in (yf.Ticker(t).news or [])[:30]:
            content = n.get("content", n)
            if isinstance(content, dict):
                title = content.get("title")
                publisher = (content.get("provider") or {}).get("displayName", "")
                link = (content.get("canonicalUrl") or {}).get("url", "")
                # New yfinance schema has pubDate inside content
                raw_ts = content.get("pubDate")
            else:
                title = n.get("title")
                publisher = n.get("publisher", "")
                link = n.get("link", "")
                raw_ts = n.get("providerPublishTime")

            if not title:
                continue

            # Parse timestamp
            ts: float | None = None
            if raw_ts:
                try:
                    ts = float(raw_ts)
                    # If it looks like milliseconds (>1e11), convert
                    if ts > 1e11:
                        ts /= 1000
                except Exception:
                    pass

            # Skip if older than 1 year
            if ts and ts < cutoff:
                continue

            key = title[:60]
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "title": title,
                "publisher": publisher,
                "link": link,
                "date": _fmt_date(ts),
                "ts": ts or 0,
            })
    except Exception as e:
        logger.debug("yfinance news failed: %s", e)

    # ── 2. Google News RSS — multiple queries for wider coverage ────────────
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

    # Sort by recency (most recent first, unknown dates last)
    items.sort(key=lambda x: x.get("ts", 0), reverse=True)

    return items[:60]  # cap at 60 articles


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
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(_pool, _fetch_sync, ticker, company)
    sentiment = _score(items)
    return {"articles": items, "sentiment": sentiment}
