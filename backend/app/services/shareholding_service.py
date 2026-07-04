"""
Shareholding pattern history — via IndianAPI's /historical_stats.

Previously scraped BSE India's undocumented internal API directly, but BSE
changed that endpoint (it now returns an HTML page instead of JSON), which
broke shareholding data entirely. IndianAPI's /historical_stats already
provides the same SEBI-mandated quarterly disclosure data reliably, so it
replaces the BSE scraping outright rather than being a fallback.
"""

import logging

from app.services import indianapi_service

logger = logging.getLogger(__name__)

# IndianAPI category name -> our internal bucket. "Government" is folded into
# "public" (it's typically <0.1% and BSE's own historical grouping did the same).
_CATEGORY_MAP = {
    "Promoters": "promoter",
    "FIIs": "fii",
    "DIIs": "dii",
    "Public": "public",
    "Government": "public",
}


async def get_shareholding_history(ticker: str) -> dict:
    """Returns quarterly shareholding pattern history for a stock."""
    bare = ticker.replace(".NS", "").replace(".BO", "")

    raw = await indianapi_service.get_historical_stats(bare, "shareholding_pattern_quarterly")
    if not raw or not isinstance(raw, dict):
        return {"quarters": [], "error": "No shareholding data available", "source": "IndianAPI"}

    quarters: dict[str, dict] = {}
    for category, by_quarter in raw.items():
        bucket = _CATEGORY_MAP.get(category)
        if not bucket or not isinstance(by_quarter, dict):
            continue
        for quarter_label, pct in by_quarter.items():
            try:
                pct = float(pct)
            except (TypeError, ValueError):
                continue
            q = quarters.setdefault(quarter_label, {
                "raw_date": quarter_label, "quarter": quarter_label,
                "promoter": 0.0, "fii": 0.0, "dii": 0.0, "public": 0.0,
            })
            q[bucket] += pct

    if not quarters:
        return {"quarters": [], "error": "No shareholding data available", "source": "IndianAPI"}

    def _sort_key(label: str):
        from datetime import datetime
        try:
            return datetime.strptime(label.strip(), "%b %Y")
        except ValueError:
            return datetime.min

    ordered = sorted(quarters.values(), key=lambda q: _sort_key(q["quarter"]), reverse=True)

    return {
        "quarters": ordered[:12],   # last 3 years
        "source": "IndianAPI",
    }
