"""
home_refresh_service.py — Background task that keeps homepage data warm.

Market data (indices, gainers/losers) is otherwise purely demand-driven:
during NSE trading hours (Mon-Fri 9:15am-3:30pm IST, minus a couple of fixed
national holidays — see market_service.is_market_hours), the first user
request after the 30-min cache expires triggers a live fetch; outside those
hours prices can't change, so requests are served straight from a long-lived
snapshot with NO live fetch attempted at all.

This task's only job is to capture that snapshot once, right after market
close each trading day, so it reflects the actual end-of-day closing prices
rather than whatever the last intraday cache-miss happened to catch. It
checks every 10 minutes (cheap — no API calls unless it's actually time to
snapshot) and fires at most once per trading day.

MF highlights: refreshed hourly — mfapi.in isn't quota-metered like IndianAPI,
and NAVs only publish once a day anyway.

Bulk deals: no longer fetched (removed 2026-07-04 — NSE's bulk-deals API and
its CSV fallback both fail unreliably from cloud IPs; IndianAPI has no
equivalent endpoint).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 600    # 10 min — just a clock check, negligible cost
_MF_TICKS       = 6      # every 6 checks of _CHECK_INTERVAL = 60 min


class HomeRefreshTask:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._last_snapshot_date: date | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="home-refresh")
        logger.info(
            "HomeRefreshTask started — end-of-day snapshot once/trading-day, mf=%dmin",
            _MF_TICKS * _CHECK_INTERVAL // 60,
        )

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("HomeRefreshTask stopped")

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        tick = 0
        while self._running:
            async with self._lock:
                await self._maybe_snapshot_close()

                if tick % _MF_TICKS == 0:
                    await self._refresh_mf_highlights()

            tick += 1
            await asyncio.sleep(_CHECK_INTERVAL)

    # ── Refresh methods ───────────────────────────────────────────────────────

    async def _maybe_snapshot_close(self) -> None:
        from app.services.market_service import _IST, _MARKET_CLOSE, is_market_hours

        now = datetime.now(_IST)
        today = now.date()
        if self._last_snapshot_date == today:
            return
        # Fire once, shortly after close on a trading day (not itself "market
        # hours" anymore, so this won't retrigger on every check afterward).
        if now.weekday() >= 5 or now.time() < _MARKET_CLOSE or is_market_hours(now):
            return
        try:
            from app.services.market_service import get_indices, get_market_overview
            indices, overview = await asyncio.gather(
                get_indices(_force=True), get_market_overview(_force=True),
            )
            self._last_snapshot_date = today
            logger.info(
                "HomeRefresh: end-of-day snapshot captured (indices=%d gainers=%d losers=%d)",
                len(indices), len(overview.get("gainers", [])), len(overview.get("losers", [])),
            )
        except Exception as exc:
            logger.warning("HomeRefresh: end-of-day snapshot failed — %s", exc)

    async def _refresh_mf_highlights(self) -> None:
        try:
            from app.services.mf_service import get_mf_highlights
            result = await get_mf_highlights("1y")
            n = len(result.get("popular") or result.get("top_gainers") or [])
            logger.info("HomeRefresh: MF highlights (%d funds)", n)
        except Exception as exc:
            logger.warning("HomeRefresh: MF highlights failed — %s", exc)

# Module-level singleton started by main.py
home_refresh = HomeRefreshTask()
