"use client";

import { useMemo, useState } from "react";
import clsx from "clsx";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inr } from "@/lib/api";
import { projectSip, projectLumpsum } from "@/lib/calculator";

const YEAR_PRESETS = [4, 5, 7, 10];
const DEFAULT_RATE = "12";

/** Forward-looking "if I start today" SIP/lumpsum projection — assumed
 * constant annual return, no dependency on any stock's real price history.
 * Self-contained: drops into the stock page (inside ReturnsCalculator's
 * "Project forward" mode) and the standalone /calculator page identically. */
export function ProjectionCalculator({ className }: { className?: string }) {
  const [mode, setMode] = useState<"sip" | "lumpsum">("sip");
  const [amount, setAmount] = useState("5000");
  const [years, setYears] = useState("5");
  const [rate, setRate] = useState(DEFAULT_RATE);

  function switchMode(m: "sip" | "lumpsum") {
    if (m === mode) return;
    setMode(m);
    setAmount(m === "sip" ? "5000" : "100000");
  }

  const result = useMemo(() => {
    const amt = Number(amount);
    const yrs = Number(years);
    const r = Number(rate);
    if (!amt || amt <= 0 || !yrs || yrs <= 0 || !isFinite(r)) return null;
    return mode === "sip" ? projectSip(amt, yrs, r) : projectLumpsum(amt, yrs, r);
  }, [mode, amount, years, rate]);

  const multiplier = result && result.invested > 0 ? result.value / result.invested : null;

  return (
    <div className={className}>
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

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <Label className="mb-1.5 block">{mode === "sip" ? "Monthly amount (₹)" : "Amount (₹)"}</Label>
          <Input type="number" min={1} step="any" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </div>
        <div>
          <Label className="mb-1.5 block">Expected annual return (%)</Label>
          <Input type="number" min={0} step="any" value={rate} onChange={(e) => setRate(e.target.value)} />
        </div>
        <div>
          <Label className="mb-1.5 block">Years from today</Label>
          <Input type="number" min={1} max={30} step="any" value={years} onChange={(e) => setYears(e.target.value)} />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {YEAR_PRESETS.map((y) => (
          <button
            key={y}
            type="button"
            onClick={() => setYears(String(y))}
            className={clsx("seg", Number(years) === y ? "seg-on" : "seg-off")}
          >
            {y}y
          </button>
        ))}
      </div>

      {result && (
        <div className="mt-5 border-t border-border pt-5">
          <div className="grid gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-muted">Total invested</p>
              <p className="nums mt-1 text-lg font-semibold text-fg">{inr(result.invested)}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Projected value</p>
              <p className="nums mt-1 text-lg font-semibold text-up">{inr(result.value)}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Estimated gain</p>
              <p className="nums mt-1 text-lg font-semibold text-up">{inr(result.gain)}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Multiplier</p>
              <p className="nums mt-1 text-lg font-semibold text-fg">{multiplier != null ? `${multiplier.toFixed(2)}x` : "—"}</p>
            </div>
          </div>
          <p className="mt-4 text-[11px] leading-relaxed text-muted/70">
            Projection only, assuming a constant {rate}% annual return compounded {mode === "sip" ? "monthly" : "yearly"} over{" "}
            {years} year{Number(years) === 1 ? "" : "s"} — actual returns vary and are never guaranteed. Not investment advice.
          </p>
        </div>
      )}
    </div>
  );
}
