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


def simulate_investment(
    closes: list[tuple[date, float]],
    mode: str,               # "sip" | "lumpsum"
    amount: float,
    start_date: str = "",    # YYYY-MM-DD; blank = earliest available price
) -> dict:
    """SIP (one purchase per calendar month) or lumpsum (single purchase)
    simulation from start_date to the latest point in `closes`, plus XIRR.
    `closes` is any sorted-ascending (date, price) series — stock closes via
    closes_map(), or a mutual fund's NAV history — the math doesn't care
    which. Extracted here (next to xirr()/close_at()) so the mutual-fund
    returns calculator (routers/mf.py) can reuse the exact same simulation
    the stock returns calculator (routers/stocks.py) already does inline,
    instead of a second copy of this logic.
    Raises ValueError on bad input — caller maps that to an HTTP 400/404."""
    if mode not in ("sip", "lumpsum"):
        raise ValueError("mode must be 'sip' or 'lumpsum'")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if len(closes) < 2:
        raise ValueError("not enough price history to calculate returns")

    earliest, latest = closes[0][0], closes[-1][0]
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("start_date must be YYYY-MM-DD")
    else:
        start = earliest
    start = max(start, earliest)
    if start >= latest:
        raise ValueError("start_date must be before the latest available price date")

    current_price = closes[-1][1]

    if mode == "lumpsum":
        entry_price = close_at(closes, start)
        units = amount / entry_price if entry_price else 0.0
        invested = amount
        current_value = units * current_price
        flows: list[tuple[date, float]] = [(start, -amount), (latest, current_value)]
    else:  # sip
        flows = []
        units = 0.0
        invested = 0.0
        d = start
        while d <= latest:
            px = close_at(closes, d)
            if px:
                units += amount / px
                invested += amount
                flows.append((d, -amount))
            month = d.month + 1
            year = d.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(d.day, 28)   # sidesteps month-length overflow (e.g. Jan 31 -> Feb 31)
            d = date(year, month, day)
        current_value = units * current_price
        flows.append((latest, current_value))

    xirr_pct = xirr(flows)
    absolute_return_pct = round((current_value - invested) / invested * 100, 2) if invested else None

    return {
        "mode": mode,
        "start_date": start.isoformat(),
        "as_of": latest.isoformat(),
        "invested": round(invested, 2),
        "current_value": round(current_value, 2),
        "units": round(units, 4),
        "current_price": current_price,
        "absolute_return_pct": absolute_return_pct,
        "xirr_pct": xirr_pct,
    }
