"use client";

import { useState } from "react";
import { Calculator } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inr, pct, signCls } from "@/lib/api";
import { ProjectionCalculator } from "@/components/ProjectionCalculator";

type CalcResult = {
  mode: "sip" | "lumpsum";
  start_date: string;
  as_of: string;
  invested: number;
  current_value: number;
  units: number;
  current_price: number;
  absolute_return_pct: number | null;
  xirr_pct: number | null;
};

/** What-if returns calculator for a single stock — monthly SIP or a one-time
 * lumpsum, from a chosen start date to the latest available price. */
export function ReturnsCalculator({ ticker }: { ticker: string }) {
  const [view, setView] = useState<"historical" | "forward">("historical");
  const [mode, setMode] = useState<"sip" | "lumpsum">("sip");
  const [amount, setAmount] = useState("5000");
  const [startDate, setStartDate] = useState("");
  const [result, setResult] = useState<CalcResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function switchMode(m: "sip" | "lumpsum") {
    if (m === mode) return;
    setMode(m);
    setAmount(m === "sip" ? "5000" : "100000");
    setResult(null);
    setError(null);
  }

  async function calculate(e: React.FormEvent) {
    e.preventDefault();
    const amt = Number(amount);
    if (!amt || amt <= 0) return;
    setBusy(true);
    setError(null);
    try {
      const params = new URLSearchParams({ mode, amount: String(amt) });
      if (startDate) params.set("start_date", startDate);
      const res = await fetch(`/api/stocks/${encodeURIComponent(ticker)}/calculator?${params}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || `Request failed (${res.status})`);
      setResult(body as CalcResult);
    } catch (err) {
      setError((err as Error).message || "Couldn't calculate returns");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border bg-raised/40 px-4 py-3">
        <Calculator className="h-4 w-4 text-saffron" />
        <h3 className="text-sm font-semibold">Returns Calculator</h3>
      </div>

      <div className="p-5">
        {/* Historical (real price data) vs forward projection (assumed rate) */}
        <div className="mb-4 flex w-fit gap-1 rounded-lg bg-raised p-1">
          {(["historical", "forward"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={clsx("seg", view === v ? "seg-on" : "seg-off")}
            >
              {v === "historical" ? "Since a date" : "Project forward"}
            </button>
          ))}
        </div>

        {view === "forward" ? (
          <ProjectionCalculator />
        ) : (
          <>
            <div className="mb-4 flex w-fit gap-1 rounded-lg bg-raised p-1">
              {(["sip", "lumpsum"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => switchMode(m)}
                  className={clsx("seg", mode === m ? "seg-on" : "seg-off")}
                >
                  {m === "sip" ? "Monthly SIP" : "One-time"}
                </button>
              ))}
            </div>

            <form onSubmit={calculate} className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <div>
                <Label className="mb-1.5 block">{mode === "sip" ? "Monthly amount (₹)" : "Amount (₹)"}</Label>
                <Input
                  type="number" min={1} step="any" value={amount}
                  onChange={(e) => setAmount(e.target.value)} required
                />
              </div>
              <div>
                <Label className="mb-1.5 block">Since (blank = earliest available)</Label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? "Calculating…" : "Calculate"}
              </Button>
            </form>

            {error && <p className="mt-4 text-sm text-down">{error}</p>}

            {result && (
              <div className="mt-5 border-t border-border pt-5">
                <div className="grid gap-4 sm:grid-cols-4">
                  <div>
                    <p className="text-xs text-muted">Invested</p>
                    <p className="nums mt-1 text-lg font-semibold text-fg">{inr(result.invested)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted">Current value</p>
                    <p className="nums mt-1 text-lg font-semibold text-fg">{inr(result.current_value)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted">Absolute return</p>
                    <p className={clsx("nums mt-1 text-lg font-semibold", signCls(result.absolute_return_pct))}>
                      {pct(result.absolute_return_pct)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted">Annualised (XIRR)</p>
                    <p className={clsx("nums mt-1 text-lg font-semibold", signCls(result.xirr_pct))}>
                      {pct(result.xirr_pct)}
                    </p>
                  </div>
                </div>
                <p className="mt-4 text-[11px] leading-relaxed text-muted/70">
                  {result.mode === "sip" ? "Monthly" : "One-time"} investment from {result.start_date} to{" "}
                  {result.as_of}, buying at each period&apos;s close price — {result.units.toLocaleString("en-IN")}{" "}
                  units at {inr(result.current_price)} today. Past performance is not indicative of future returns.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
