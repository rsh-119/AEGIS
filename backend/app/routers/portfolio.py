"""/api/portfolio/* — holdings CRUD with live P&L + analysis (auth required)."""

import asyncio
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.models import Holding
from app.schemas import HoldingCreate
from app.services import ai_service, news_service, stock_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
async def list_holdings(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Holding).where(Holding.user_id == user_id)
        )
    ).scalars().all()
    if not rows:
        return {"holdings": [], "summary": _empty_summary()}

    quotes = await asyncio.gather(*[stock_service.get_quote(h.ticker) for h in rows])

    holdings, invested_total, value_total = [], 0.0, 0.0
    for h, q in zip(rows, quotes):
        price = q.get("current_price") or h.avg_price if "error" not in q else h.avg_price
        invested = h.shares * h.avg_price
        value = h.shares * price
        invested_total += invested
        value_total += value
        holdings.append({
            **h.to_dict(),
            "current_price": round(price, 2),
            "invested":       round(invested, 2),
            "current_value":  round(value, 2),
            "pnl":            round(value - invested, 2),
            "pnl_pct":        round((value - invested) / invested * 100 if invested else 0, 2),
            "sector":         q.get("sector") or h.sector or "Unknown",
            "company_name":   q.get("company_name") or h.company_name or h.ticker,
        })

    return {
        "holdings": holdings,
        "summary": {
            "invested": round(invested_total, 2),
            "value":    round(value_total, 2),
            "pnl":      round(value_total - invested_total, 2),
            "pnl_pct":  round((value_total - invested_total) / invested_total * 100 if invested_total else 0, 2),
            "count":    len(holdings),
        },
    }


@router.get("/analysis")
async def portfolio_analysis(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Groww-style analysis: XIRR vs a Nifty-50 benchmark (same cashflows,
    same dates, invested into the index instead), plus market-cap and sector
    allocation buckets. Everything derives from live quotes + buy dates —
    no stored history needed."""
    rows = (
        await db.execute(select(Holding).where(Holding.user_id == user_id))
    ).scalars().all()
    if not rows:
        return {"empty": True, "summary": _empty_summary()}

    quotes = await asyncio.gather(*[stock_service.get_quote(h.ticker) for h in rows])

    today = date.today()
    holdings, invested_total, value_total = [], 0.0, 0.0
    flows: list[tuple[date, float]] = []
    for h, q in zip(rows, quotes):
        price = q.get("current_price") or h.avg_price if "error" not in q else h.avg_price
        invested = h.shares * h.avg_price
        value = h.shares * price
        invested_total += invested
        value_total += value
        flows.append((h.buy_date or today, -invested))
        holdings.append({
            "ticker":     h.ticker,
            "name":       q.get("company_name") or h.company_name or h.ticker,
            "invested":   invested,
            "value":      value,
            "sector":     q.get("sector") or h.sector or "Others",
            "market_cap": q.get("market_cap"),
            "cap_type":   q.get("cap_type"),
        })
    flows.append((today, value_total))

    xirr = _xirr(flows)
    nifty_xirr = await _nifty_benchmark_xirr(flows)
    growth = await _growth_series(rows)

    return {
        "empty": False,
        "growth": growth,
        "summary": {
            "invested": round(invested_total, 2),
            "value":    round(value_total, 2),
            "pnl":      round(value_total - invested_total, 2),
            "pnl_pct":  round((value_total - invested_total) / invested_total * 100 if invested_total else 0, 2),
            "count":    len(holdings),
        },
        "xirr_pct":       xirr,
        "nifty_xirr_pct": nifty_xirr,
        "outperformance_pct": (
            round(xirr - nifty_xirr, 2) if xirr is not None and nifty_xirr is not None else None
        ),
        "cap_buckets":    _bucketise(holdings, _cap_label, value_total),
        "sector_buckets": _bucketise(holdings, lambda x: x["sector"], value_total, top=6),
        "as_of": today.isoformat(),
    }


@router.get("/news")
async def portfolio_news(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Latest news across the user's holdings — Groww-style feed. Per-ticker
    news is cached by news_service, so this is one warm pass per session."""
    rows = (
        await db.execute(select(Holding).where(Holding.user_id == user_id))
    ).scalars().all()
    if not rows:
        return {"items": []}

    # One entry per distinct ticker, largest positions first, capped at 8
    seen: dict[str, Holding] = {}
    for h in rows:
        seen.setdefault(h.ticker, h)
    tickers = list(seen.values())[:8]

    quotes, news = await asyncio.gather(
        asyncio.gather(*[stock_service.get_quote(h.ticker) for h in tickers]),
        asyncio.gather(*[
            news_service.get_news_and_sentiment(h.ticker, h.company_name)
            for h in tickers
        ], return_exceptions=True),
    )

    items = []
    for h, q, nd in zip(tickers, quotes, news):
        if isinstance(nd, Exception):
            continue
        price = q.get("current_price") if "error" not in q else None
        change = q.get("change_pct") if "error" not in q else None
        for a in (nd.get("articles") or [])[:3]:
            items.append({
                "ticker":     h.ticker,
                "company":    q.get("company_name") or h.company_name or h.ticker,
                "price":      price,
                "change_pct": change,
                "title":      a.get("title"),
                "url":        a.get("link") or "",
                "source":     a.get("publisher") or "",
                "date":       a.get("date"),
                "ts":         a.get("ts") or 0,
            })

    items.sort(key=lambda x: -x["ts"])
    return {"items": items[:12]}


@router.get("/insights")
async def portfolio_insights(
    ai: bool = False,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Decision support: deterministic health signals computed from the
    portfolio (always), plus an optional LLM review (?ai=1 — on demand so a
    tab visit never spends model tokens)."""
    analysis = await portfolio_analysis(user_id, db)
    if analysis.get("empty"):
        return {"empty": True, "signals": [], "ai": None}

    summary = analysis["summary"]
    caps = analysis["cap_buckets"]
    sectors = analysis["sector_buckets"]
    xirr = analysis["xirr_pct"]
    nifty = analysis["nifty_xirr_pct"]

    signals: list[dict] = []

    top_sector = sectors[0] if sectors else None
    if top_sector and top_sector["alloc_pct"] > 40:
        signals.append({
            "kind": "warning",
            "title": f"{top_sector['label']} is {top_sector['alloc_pct']:.0f}% of your portfolio",
            "detail": "A single sector above 40% means one bad quarter for the industry hits most of your capital. Consider spreading new buys elsewhere.",
        })

    all_holdings = [i for b in sectors for i in b["holdings"]]
    if all_holdings and summary["value"]:
        biggest = max(all_holdings, key=lambda x: x["value"])
        weight = biggest["value"] / summary["value"] * 100
        if weight > 30:
            signals.append({
                "kind": "warning",
                "title": f"{biggest['name']} alone is {weight:.0f}% of your portfolio",
                "detail": "Single-stock concentration cuts both ways — it works until it doesn't. Most frameworks cap one position at 10–15%.",
            })

    small = next((c for c in caps if c["label"] == "Small cap"), None)
    if small and small["alloc_pct"] > 50:
        signals.append({
            "kind": "warning",
            "title": f"Small caps are {small['alloc_pct']:.0f}% of your book",
            "detail": "Small caps swing hardest in drawdowns and dry up in liquidity crunches. Make sure the sizing matches your risk appetite.",
        })

    if summary["count"] < 5:
        signals.append({
            "kind": "info",
            "title": f"Only {summary['count']} holding{'s' if summary['count'] > 1 else ''}",
            "detail": "Under five stocks, one company's news dominates your returns. 8–15 names across sectors smooths the ride without diluting conviction.",
        })

    for h in all_holdings:
        if h["pnl_pct"] <= -20:
            signals.append({
                "kind": "warning",
                "title": f"{h['name']} is down {abs(h['pnl_pct']):.0f}%",
                "detail": "Re-check the original thesis. If it's broken, averaging down turns a mistake into a bigger one; if intact, volatility is the price of entry.",
            })
        elif h["pnl_pct"] >= 40:
            signals.append({
                "kind": "positive",
                "title": f"{h['name']} is up {h['pnl_pct']:.0f}%",
                "detail": "Winners drift into oversized positions. Consider a partial booking or a trailing stop to protect the gain without exiting the story.",
            })

    if xirr is not None and nifty is not None:
        diff = xirr - nifty
        signals.append({
            "kind": "positive" if diff >= 0 else "info",
            "title": f"You're {'beating' if diff >= 0 else 'trailing'} the Nifty by {abs(diff):.1f}% annualised",
            "detail": (
                "Your stock picks are adding value over simply buying the index — keep doing what's working."
                if diff >= 0 else
                "An index fund with the same cashflows would be ahead. Worth asking which holdings earn their place."
            ),
        })

    ai_review = None
    if ai:
        table = "\n".join(
            f"- {h['name']} ({h['ticker']}): {h['value'] / summary['value'] * 100:.1f}% weight, P&L {h['pnl_pct']:+.1f}%"
            for h in sorted(all_holdings, key=lambda x: -x["value"])
        )
        sector_line = ", ".join(f"{s['label']} {s['alloc_pct']:.0f}%" for s in sectors)
        context = (
            f"Holdings:\n{table}\n\nSector mix: {sector_line}\n"
            f"Portfolio XIRR: {xirr}% vs Nifty 50 {nifty}% (same cashflows).\n"
            f"Total P&L: {summary['pnl_pct']}%."
        )
        try:
            result = await ai_service.review_portfolio(context)
            ai_review = result.get("observations") or None
        except Exception:
            ai_review = None

    return {"empty": False, "signals": signals[:6], "ai": ai_review}


@router.post("/ask")
async def ask_portfolio(
    body: dict,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Free-form Q&A grounded in the user's live portfolio snapshot."""
    question = str(body.get("question") or "").strip()
    if not question or len(question) > 500:
        raise HTTPException(400, "Question must be 1-500 characters")

    analysis = await portfolio_analysis(user_id, db)
    if analysis.get("empty"):
        return {"answer": "Your portfolio is empty — add a holding first and I'll have something to talk about.", "followups": []}

    summary = analysis["summary"]
    sectors = analysis["sector_buckets"]
    all_holdings = [i for b in sectors for i in b["holdings"]]
    table = "\n".join(
        f"- {h['name']} ({h['ticker']}): value ₹{h['value']:,.0f}, "
        f"{h['value'] / summary['value'] * 100:.1f}% weight, P&L {h['pnl_pct']:+.1f}%"
        for h in sorted(all_holdings, key=lambda x: -x["value"])[:10]
    )
    sector_line = ", ".join(f"{s['label']} {s['alloc_pct']:.0f}%" for s in sectors)
    context = (
        f"{table}\n"
        f"Sector mix: {sector_line}\n"
        f"Totals: invested ₹{summary['invested']:,.0f}, current ₹{summary['value']:,.0f}, "
        f"P&L {summary['pnl_pct']:+.1f}%\n"
        f"Portfolio XIRR: {analysis['xirr_pct']}% | Nifty 50 (same cashflows): {analysis['nifty_xirr_pct']}%\n"
        f"As of: {analysis['as_of']}"
    )
    result = await ai_service.ask_portfolio(question, context)
    if not result.get("answer"):
        return {"answer": "I couldn't work that one out just now — try rephrasing or ask again in a moment.", "followups": []}
    return result


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _cap_label(h: dict) -> str:
    cap = (h.get("cap_type") or "").lower()
    if cap in {"large", "mid", "small"}:
        return f"{cap.capitalize()} cap"
    # Fallback thresholds (₹): SEBI-ish proxy — 100th company ≈ ₹67k Cr,
    # 250th ≈ ₹22k Cr.
    mcap = h.get("market_cap")
    if not mcap:
        return "Uncategorised"
    if mcap >= 6.7e11:
        return "Large cap"
    if mcap >= 2.2e11:
        return "Mid cap"
    return "Small cap"


def _bucketise(holdings: list[dict], key, value_total: float, top: int | None = None) -> list[dict]:
    groups: dict[str, dict] = {}
    for h in holdings:
        label = key(h) or "Others"
        g = groups.setdefault(label, {"label": label, "value": 0.0, "invested": 0.0, "count": 0, "items": []})
        g["value"] += h["value"]
        g["invested"] += h["invested"]
        g["count"] += 1
        g["items"].append(h)

    buckets = sorted(groups.values(), key=lambda g: -g["value"])
    if top and len(buckets) > top:
        rest = buckets[top:]
        folded = {
            "label": "Others",
            "value": sum(b["value"] for b in rest),
            "invested": sum(b["invested"] for b in rest),
            "count": sum(b["count"] for b in rest),
            "items": [i for b in rest for i in b["items"]],
        }
        buckets = buckets[:top] + [folded]

    out = []
    for b in buckets:
        pnl = b["value"] - b["invested"]
        out.append({
            "label":     b["label"],
            "count":     b["count"],
            "value":     round(b["value"], 2),
            "invested":  round(b["invested"], 2),
            "pnl":       round(pnl, 2),
            "pnl_pct":   round(pnl / b["invested"] * 100 if b["invested"] else 0, 2),
            "alloc_pct": round(b["value"] / value_total * 100 if value_total else 0, 2),
            # clickable drill-down: which holdings make up this bucket
            "holdings": [
                {
                    "ticker":  i["ticker"],
                    "name":    i["name"],
                    "value":   round(i["value"], 2),
                    "pnl_pct": round((i["value"] - i["invested"]) / i["invested"] * 100 if i["invested"] else 0, 2),
                }
                for i in sorted(b["items"], key=lambda x: -x["value"])[:8]
            ],
        })
    return out


def _xirr(flows: list[tuple[date, float]]) -> float | None:
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


def _closes_map(hist: dict | None) -> list[tuple[date, float]]:
    out: list[tuple[date, float]] = []
    for c in (hist or {}).get("candles") or []:
        try:
            out.append((datetime.strptime(str(c["date"])[:10], "%Y-%m-%d").date(), float(c["close"])))
        except Exception:
            continue
    out.sort()
    return out


def _close_at(closes: list[tuple[date, float]], d: date) -> float | None:
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


async def _growth_series(rows) -> list[dict]:
    """Portfolio value vs 'same cashflows into the Nifty' over time — the
    Groww-style growth chart. Reconstructed from per-holding price history
    (shares x close, each holding entering on its buy date), sampled weekly.
    Returns [] when history is unavailable."""
    try:
        today = date.today()
        nifty_hist, *stock_hists = await asyncio.gather(
            stock_service._history_from_indianapi("NIFTY", "5y"),
            *[stock_service.get_history(h.ticker, "5y") for h in rows],
        )
        nifty_closes = _closes_map(nifty_hist)
        if len(nifty_closes) < 5:
            return []
        stock_closes = [_closes_map(sh if isinstance(sh, dict) else None) for sh in stock_hists]

        start = min((h.buy_date or today) for h in rows)
        timeline = [d for d, _ in nifty_closes if d >= start]
        if not timeline:
            return []
        # Weekly sampling, but always keep the final point
        sampled = timeline[::5]
        if sampled[-1] != timeline[-1]:
            sampled.append(timeline[-1])

        series = []
        for d in sampled:
            invested = value = nifty_units = 0.0
            for h, closes in zip(rows, stock_closes):
                bd = h.buy_date or today
                if bd > d:
                    continue
                invested += h.shares * h.avg_price
                px = _close_at(closes, d)
                # No history for this stock — carry it at cost so the line
                # stays honest instead of dropping the position entirely.
                value += h.shares * (px if px is not None else h.avg_price)
                buy_nifty = _close_at(nifty_closes, bd) or nifty_closes[0][1]
                nifty_units += (h.shares * h.avg_price) / buy_nifty
            nifty_px = _close_at(nifty_closes, d) or nifty_closes[-1][1]
            series.append({
                "date":     d.isoformat(),
                "invested": round(invested, 2),
                "value":    round(value, 2),
                "nifty":    round(nifty_units * nifty_px, 2),
            })
        return series
    except Exception:
        return []


async def _nifty_benchmark_xirr(flows: list[tuple[date, float]]) -> float | None:
    """What the same rupees on the same dates would have earned in the
    Nifty 50: buy index units at each cashflow date's close, value them at the
    latest close, then run the identical XIRR."""
    try:
        hist = await stock_service._history_from_indianapi("NIFTY", "5y")
        candles = (hist or {}).get("candles") or []
        closes: list[tuple[date, float]] = []
        for c in candles:
            try:
                closes.append((datetime.strptime(str(c["date"])[:10], "%Y-%m-%d").date(), float(c["close"])))
            except Exception:
                continue
        if len(closes) < 5:
            return None
        closes.sort()

        def close_on(d: date) -> float:
            # nearest candle at or before d; clamp to first candle for older buys
            best = closes[0][1]
            for cd, cv in closes:
                if cd <= d:
                    best = cv
                else:
                    break
            return best

        last_date, last_close = closes[-1]
        units = 0.0
        bench_flows: list[tuple[date, float]] = []
        for d, amt in flows[:-1]:              # buys only (negative amounts)
            units += -amt / close_on(d)
            bench_flows.append((d, amt))
        bench_flows.append((last_date, units * last_close))
        return _xirr(bench_flows)
    except Exception:
        return None


@router.post("", status_code=201)
async def add_holding(
    body: HoldingCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ticker = stock_service.normalise_ticker(body.ticker)
    q = await stock_service.get_quote(ticker)
    holding = Holding(
        user_id=user_id,
        ticker=ticker,
        company_name=body.company_name or (q.get("company_name") if "error" not in q else ticker),
        shares=body.shares,
        avg_price=body.avg_price,
        buy_date=body.buy_date,
        sector=body.sector or (q.get("sector") if "error" not in q else None),
        notes=body.notes,
    )
    db.add(holding)
    await db.flush()
    return holding.to_dict()


@router.delete("/{holding_id}")
async def delete_holding(
    holding_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Holding, holding_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "Holding not found")
    await db.delete(row)
    return {"deleted": holding_id}


def _empty_summary():
    return {"invested": 0, "value": 0, "pnl": 0, "pnl_pct": 0, "count": 0}
