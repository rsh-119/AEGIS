"""finance_math.py — shared money-weighted-return math.

Originally lived only in routers/portfolio.py (XIRR vs Nifty benchmark);
extracted here so the stock-page returns calculator (routers/stocks.py) can
reuse the exact same bisection/close-lookup logic instead of duplicating it.
"""

from __future__ import annotations

from datetime import date, datetime


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Annualised money-weighted return via bisection. Returns % or None when
    the cashflows can't produce a root (e.g. everything bought today)."""
    if len(flows) < 2:
        return None
    t0 = min(d for d, _ in flows)
    yrs = [(d - t0).days / 365.25 for d, _ in flows]
    amts = [a for _, a in flows]
    if not (any(a < 0 for a in amts) and any(a > 0 for a in amts)):
        return None
    if max(yrs) < 1 / 365:          # all cashflows on one day — undefined
        return None

    def npv(r: float) -> float:
        return sum(a / (1 + r) ** y for a, y in zip(amts, yrs))

    lo, hi = -0.9999, 10.0
    f_lo = npv(lo)
    if f_lo * npv(hi) > 0:
        return None
    mid = 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        f = npv(mid)
        if abs(f) < 1e-7:
            break
        if f_lo * f > 0:
            lo, f_lo = mid, f
        else:
            hi = mid
    return round(mid * 100, 2)


def closes_map(hist: dict | None) -> list[tuple[date, float]]:
    """Extract sorted (date, close) pairs from a stock_service.get_history()
    result's "candles" list."""
    out: list[tuple[date, float]] = []
    for c in (hist or {}).get("candles") or []:
        try:
            out.append((datetime.strptime(str(c["date"])[:10], "%Y-%m-%d").date(), float(c["close"])))
        except Exception:
            continue
    out.sort()
    return out


def close_at(closes: list[tuple[date, float]], d: date) -> float | None:
    """Last close at or before d; clamps to the first candle for older dates."""
    if not closes:
        return None
    best = closes[0][1]
    for cd, cv in closes:
        if cd <= d:
            best = cv
        else:
            break
    return best
