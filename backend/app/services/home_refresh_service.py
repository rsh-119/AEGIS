"""
home_refresh_service.py — Background task that keeps homepage data warm.

Instead of fetching from external APIs on every user request, this task
pre-fetches data on a fixed schedule and stores it in the module-level caches.
User-facing endpoints always read from cache → instant response.

Schedule (all intervals are multiples of the base 10 s tick):
  Every  10 s  → indices       (NSE direct API — 5 index levels)
  Every  10 min → market overview  (gainers/losers/active via IndianAPI)
  Every  60 min → MF highlights    (MFApi.in — NAVs published once daily)

  Bulk deals: NOT refreshed here — NSE publishes them once per day so the
  1-hour cache TTL is sufficient. First request after startup/expiry fetches
  them and the same data serves for the rest of the day.

If a refresh fails, the previous cached value stays valid until its TTL expires
so users never see an error mid-cycle.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_BASE           = 10     # base tick in seconds
_INDICES_TICKS  = 1      # every 1 tick  = 10 s
_OVERVIEW_TICKS = 60     # every 60 ticks = 10 min
_MF_TICKS       = 360    # every 360 ticks = 60 min


class HomeRefreshTask:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="home-refresh")
        logger.info(
            "HomeRefreshTask started — indices=%ds overview=%dmin mf=%dmin",
            _BASE * _INDICES_TICKS,
            _BASE * _OVERVIEW_TICKS // 60,
            _BASE * _MF_TICKS // 60,
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
                # Overview: every 10 min (and on tick 0 so first run is full)
                if tick % _OVERVIEW_TICKS == 0:
                    await self._refresh_overview()
                else:
                    await self._refresh_indices()

                # MF highlights: every 60 min
                if tick % _MF_TICKS == 0:
                    await self._refresh_mf_highlights()


            tick += 1
            await asyncio.sleep(_BASE)

    # ── Refresh methods ───────────────────────────────────────────────────────

    async def _refresh_indices(self) -> None:
        try:
            from app.services.market_service import get_indices
            indices = await get_indices(_force=True)
            logger.debug("HomeRefresh: indices (%d)", len(indices))
        except Exception as exc:
            logger.warning("HomeRefresh: indices failed — %s", exc)

    async def _refresh_overview(self) -> None:
        try:
            from app.services.market_service import get_market_overview
            ov = await get_market_overview(_force=True)
            logger.info("HomeRefresh: overview (gainers=%d losers=%d)",
                        len(ov.get("gainers", [])), len(ov.get("losers", [])))
        except Exception as exc:
            logger.warning("HomeRefresh: overview failed — %s", exc)

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
