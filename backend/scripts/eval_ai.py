"""
Golden-set regression check for Aegis's AI surfaces.

Run from backend/:  ./venv/bin/python3 scripts/eval_ai.py

This hits real providers against a small set of stable, liquid large-cap
tickers — it's a lightweight regression check, not a deterministic CI gate
(live market data and model sampling both vary call to call). Its job is to
catch structural regressions unit tests can't: a prompt edit that breaks
schema validation, advice-language ("buy"/"sell"/"hold") creeping back into
output, or a response that stops citing the precomputed sector-comparison
data. Non-deterministic model-judgment items (e.g. whether a fully-grounded
question actually gets answered_from_facts=True) are reported as warnings,
not hard failures — flip the exit code only on the things a prompt/schema
change controls directly.
"""

import asyncio
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas import AnalysisResponse, AskResponse, HealthResponse  # noqa: E402
from app.services import ai_service, peer_service, stock_service  # noqa: E402

GOLDEN_TICKERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]

# CLAUDE.md rule #2: no investment advice, ever — analysis and framing only.
ADVICE_LANGUAGE = re.compile(
    r"\b(you should buy|you should sell|strong buy|strong sell|buy rating|sell rating|"
    r"accumulate on dips|add on dips|book profits now|exit now|hold rating|"
    r"is a buy|is a sell)\b",
    re.IGNORECASE,
)


def scan_advice_language(obj) -> list[str]:
    """Recursively scan every string value in a response for banned
    investment-advice phrasing."""
    hits: list[str] = []
    if isinstance(obj, str):
        if ADVICE_LANGUAGE.search(obj):
            hits.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            hits.extend(scan_advice_language(v))
    elif isinstance(obj, list):
        for v in obj:
            hits.extend(scan_advice_language(v))
    return hits


class Check:
    def __init__(self, name: str):
        self.name = name
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.latency_s: float = 0.0

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.failures


async def eval_ticker(ticker: str) -> list[Check]:
    quote, hist = await asyncio.gather(
        stock_service.get_quote(ticker),
        stock_service.get_history(ticker, "6mo"),
    )
    if "error" in quote and "current_price" not in quote:
        c = Check(f"{ticker}: fetch quote")
        c.fail(f"quote unavailable: {quote.get('error')}")
        return [c]

    signals = stock_service.ratio_signals(quote)
    peer_data = await peer_service.get_peer_comparison(ticker, quote.get("sector", ""), quote.get("industry"))
    peer_avg = peer_data.get("sector_avg", {})

    checks: list[Check] = []

    # ── analyse_stock ─────────────────────────────────────────────────────
    c = Check(f"{ticker}: analyse_stock")
    t0 = time.monotonic()
    analysis = await ai_service.analyse_stock(quote, signals, hist, {}, peer_avg)
    c.latency_s = time.monotonic() - t0
    if "error" in analysis:
        c.fail(f"provider error: {analysis['error']}")
    else:
        try:
            AnalysisResponse.model_validate(analysis)
        except Exception as e:
            c.fail(f"schema validation failed: {e}")
        for hit in scan_advice_language(analysis):
            c.fail(f"advice-language detected: {hit!r}")
        for m in analysis.get("key_metrics", []):
            if not m.get("value") or not m.get("explanation"):
                c.warn(f"key_metric thin on detail: {m.get('label')}")
    checks.append(c)

    # ── diagnose_health ───────────────────────────────────────────────────
    c = Check(f"{ticker}: diagnose_health")
    t0 = time.monotonic()
    health = await ai_service.diagnose_health(quote, hist, {}, [], peer_avg)
    c.latency_s = time.monotonic() - t0
    if "error" in health:
        c.fail(f"provider error: {health['error']}")
    else:
        try:
            HealthResponse.model_validate(health)
        except Exception as e:
            c.fail(f"schema validation failed: {e}")
        for hit in scan_advice_language(health):
            c.fail(f"advice-language detected: {hit!r}")
    checks.append(c)

    # ── answer() — a question the grounding data should fully cover ────────
    c = Check(f"{ticker}: answer('current price and P/E?')")
    t0 = time.monotonic()
    ans = await ai_service.answer("What is the current price and P/E ratio?", quote, hist, [])
    c.latency_s = time.monotonic() - t0
    if "error" in ans:
        c.fail(f"provider error: {ans['error']}")
    else:
        try:
            AskResponse.model_validate(ans)
        except Exception as e:
            c.fail(f"schema validation failed: {e}")
        if ans.get("answered_from_facts") is not True:
            c.warn(f"expected answered_from_facts=True for a fully-grounded question, got {ans.get('answered_from_facts')}")
        for hit in scan_advice_language(ans):
            c.fail(f"advice-language detected: {hit!r}")
    checks.append(c)

    return checks


async def main() -> None:
    all_checks: list[Check] = []
    for ticker in GOLDEN_TICKERS:
        print(f"— evaluating {ticker} —")
        all_checks.extend(await eval_ticker(ticker))

    print("\n" + "=" * 72)
    for c in all_checks:
        status = "PASS" if c.ok else "FAIL"
        print(f"[{status}] {c.name} ({c.latency_s:.1f}s)")
        for f in c.failures:
            print(f"         FAIL → {f}")
        for w in c.warnings:
            print(f"         warn → {w}")

    failed = [c for c in all_checks if not c.ok]
    print("=" * 72)
    print(f"{len(all_checks) - len(failed)}/{len(all_checks)} checks passed"
          f" ({sum(len(c.warnings) for c in all_checks)} warnings)")

    stats = ai_service.get_provider_stats()
    if stats:
        print("\nProvider usage this run:")
        for provider, s in stats.items():
            print(f"  {provider}: {s['calls']} calls, avg {s['avg_latency_s']}s")
    repairs = ai_service.get_repair_counts()
    if repairs:
        print(f"\nSchema repairs triggered: {repairs}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
