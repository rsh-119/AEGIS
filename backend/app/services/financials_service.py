"""
financials_service.py — Screener-style financial statement tables.

Transforms IndianAPI's /historical_stats ("all") into clean tabular data:
quarterly results, annual P&L, balance sheet, cash flow, and key ratios —
plus the compounded growth summary box. Same underlying source (and cache)
as concall_service and shareholding_service, so this costs no extra
IndianAPI quota when those have already been called for a ticker.
"""
from __future__ import annotations

from datetime import datetime

from app.services import indianapi_service
from app.services.stock_service import bare_ticker

_PL_ROWS = [
    ("Sales", "Sales", "cr"),
    ("Expenses", "Expenses", "cr"),
    ("Operating Profit", "Operating Profit", "cr"),
    ("OPM %", "OPM %", "pct"),
    ("Other Income", "Other Income", "cr"),
    ("Interest", "Interest", "cr"),
    ("Depreciation", "Depreciation", "cr"),
    ("Profit before tax", "Profit before Tax", "cr"),
    ("Tax %", "Tax %", "pct"),
    ("Net Profit", "Net Profit", "cr"),
    ("EPS in Rs", "EPS", "num"),
]
_PL_ROWS_ANNUAL = _PL_ROWS + [("Dividend Payout %", "Dividend Payout %", "pct")]

_BS_ROWS = [
    ("Equity Capital", "Equity Capital", "cr"),
    ("Reserves", "Reserves", "cr"),
    ("Borrowings", "Borrowings", "cr"),
    ("Other Liabilities", "Other Liabilities", "cr"),
    ("Total Liabilities", "Total Liabilities", "cr"),
    ("Fixed Assets", "Fixed Assets", "cr"),
    ("CWIP", "CWIP", "cr"),
    ("Investments", "Investments", "cr"),
    ("Other Assets", "Other Assets", "cr"),
    ("Total Assets", "Total Assets", "cr"),
]

_CF_ROWS = [
    ("Cash from Operating Activity", "Cash from Operating Activity", "cr"),
    ("Cash from Investing Activity", "Cash from Investing Activity", "cr"),
    ("Cash from Financing Activity", "Cash from Financing Activity", "cr"),
    ("Net Cash Flow", "Net Cash Flow", "cr"),
    ("Free Cash Flow", "Free Cash Flow", "cr"),
    ("CFO/OP", "CFO / Operating Profit", "pct"),
]

_RATIO_ROWS = [
    ("Debtor Days", "Debtor Days", "num"),
    ("Inventory Days", "Inventory Days", "num"),
    ("Days Payable", "Days Payable", "num"),
    ("Cash Conversion Cycle", "Cash Conversion Cycle", "num"),
    ("Working Capital Days", "Working Capital Days", "num"),
    ("ROCE %", "ROCE %", "pct"),
]


def _sort_periods(labels: list[str]) -> list[str]:
    """'Mar 2024' style labels, oldest -> newest. 'TTM' always sorts last."""
    def key(label: str):
        if label == "TTM":
            return datetime.max
        try:
            return datetime.strptime(label.strip(), "%b %Y")
        except ValueError:
            return datetime.min
    return sorted(labels, key=key)


def _table(raw: dict, periods: list[str], row_defs: list[tuple[str, str, str]]) -> dict:
    rows = [
        {
            "key": key,
            "label": label,
            "unit": unit,
            "values": [(raw.get(key) or {}).get(p) for p in periods],
        }
        for key, label, unit in row_defs
    ]
    return {"periods": periods, "rows": rows}


async def get_financials(ticker: str) -> dict:
    """Quarterly results, annual P&L, balance sheet, cash flow and ratios — last ~10-12 periods each."""
    bare = bare_ticker(ticker)
    stats = await indianapi_service.get_historical_stats(bare, "all")
    if not stats or not stats.get("quarter_results"):
        return {"error": "No financial statement data available for this stock."}

    qr = stats["quarter_results"]
    yr = stats.get("yoy_results") or {}
    bs = stats.get("balancesheet") or {}
    cf = stats.get("cashflow") or {}
    ratios = stats.get("ratios") or {}
    growth = stats.get("profit_loss_stats") or {}

    q_periods = _sort_periods(list(qr.get("Sales", {}).keys()))[-8:]
    y_labels = [p for p in yr.get("Sales", {}).keys() if p != "TTM"]
    y_periods = _sort_periods(y_labels)
    if "TTM" in yr.get("Sales", {}):
        y_periods = y_periods + ["TTM"]
    bs_periods = _sort_periods(list(bs.get("Total Assets", {}).keys()))
    cf_periods = _sort_periods(list(cf.get("Free Cash Flow", {}).keys()))
    ratio_periods = _sort_periods(list(ratios.get("ROCE %", {}).keys()))

    return {
        "quarterly": _table(qr, q_periods, _PL_ROWS),
        "profit_loss": _table(yr, y_periods, _PL_ROWS_ANNUAL),
        "balance_sheet": _table(bs, bs_periods, _BS_ROWS),
        "cash_flow": _table(cf, cf_periods, _CF_ROWS),
        "ratios": _table(ratios, ratio_periods, _RATIO_ROWS),
        "growth": growth,
    }
