"use client";

import { useEffect, useState } from "react";
// NOTE: the bare `mutate` exported from "swr" targets the DEFAULT cache — this
// app runs on a custom IDB-backed provider (lib/swr-config), so that mutate
// silently no-ops and new holdings only appeared after a full reload.
// useSWRConfig().mutate is bound to the active provider.
import useSWR, { useSWRConfig } from "swr";
import { fetcher, inr, pct, signCls, post, deleteTolerant404 } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { useAuth } from "@/lib/auth";
import { getGuestHoldings, addGuestHolding, removeGuestHolding, type GuestHolding } from "@/lib/guestData";
import { Trash2, Plus, Briefcase, Info } from "lucide-react";
import Link from "next/link";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { AnalysisPanel } from "./AnalysisPanel";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { SortIcon } from "@/components/ui/sort-icon";

type SortKey = "ticker" | "shares" | "avg_price" | "current_price" | "current_value" | "pnl_pct";
type SortDir = "asc" | "desc";

export default function PortfolioPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { mutate } = useSWRConfig();
  const { data } = useSWR(user ? "/api/portfolio" : null, fetcher, { revalidateOnFocus: false });
  const [form, setForm] = useState({ ticker: "", shares: "", avg_price: "", buy_date: "" });
  const [busy, setBusy] = useState(false);

  const [sortKey, setSortKey] = useState<SortKey>("ticker");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [view, setView] = useState<"holdings" | "analysis">("holdings");

  // Guest (logged-out) portfolio: read from this device's localStorage
  // (lib/guestData.ts) instead of the DB-backed /api/portfolio, which
  // requires a session. P&L is computed client-side from live quotes —
  // there's no guest equivalent of /api/portfolio/analysis's XIRR/sector
  // breakdown, so the Analysis tab is hidden for guests (see the view
  // toggle below).
  const [guestHoldings, setGuestHoldings] = useState<GuestHolding[]>([]);
  useEffect(() => {
    if (!user) setGuestHoldings(getGuestHoldings());
  }, [user]);
  const guestTickers = guestHoldings.map((h) => h.ticker).join(",");
  const { data: guestQuotes } = useSWR(
    !user && guestTickers ? `/api/stocks/batch-quotes?tickers=${encodeURIComponent(guestTickers)}` : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "ticker" ? "asc" : "desc"); }
  }

  let summary = data?.summary;
  let holdings = data?.holdings || [];
  if (!user) {
    let invested = 0, value = 0;
    holdings = guestHoldings.map((h) => {
      const q = guestQuotes?.[h.ticker] || {};
      const price = q.current_price ?? h.avg_price;
      const hInvested = h.shares * h.avg_price;
      const hValue = h.shares * price;
      invested += hInvested;
      value += hValue;
      return {
        id: h.id,
        ticker: h.ticker,
        company_name: q.company_name || h.company_name || h.ticker,
        shares: h.shares,
        avg_price: h.avg_price,
        current_price: Math.round(price * 100) / 100,
        invested: Math.round(hInvested * 100) / 100,
        current_value: Math.round(hValue * 100) / 100,
        pnl: Math.round((hValue - hInvested) * 100) / 100,
        pnl_pct: hInvested ? Math.round(((hValue - hInvested) / hInvested) * 10000) / 100 : 0,
      };
    });
    summary = {
      invested: Math.round(invested * 100) / 100,
      value: Math.round(value * 100) / 100,
      pnl: Math.round((value - invested) * 100) / 100,
      pnl_pct: invested ? Math.round(((value - invested) / invested) * 10000) / 100 : 0,
      count: holdings.length,
    };
  }
  const sortedHoldings = [...holdings].sort((a: any, b: any) => {
    if (sortKey === "ticker") {
      return sortDir === "asc" ? a.ticker.localeCompare(b.ticker) : b.ticker.localeCompare(a.ticker);
    }
    const av = a[sortKey] ?? -Infinity;
    const bv = b[sortKey] ?? -Infinity;
    return sortDir === "asc" ? av - bv : bv - av;
  });

  async function add() {
    if (!form.ticker || !form.shares || !form.avg_price || !form.buy_date) return;
    setBusy(true);
    try {
      if (!user) {
        // Guest: saved on-device (lib/guestData.ts), synced to the account
        // automatically the first time this browser logs in or registers.
        addGuestHolding({
          ticker: form.ticker,
          shares: parseFloat(form.shares),
          avg_price: parseFloat(form.avg_price),
          buy_date: form.buy_date,
        });
        setGuestHoldings(getGuestHoldings());
      } else {
        await post("/api/portfolio", {
          ticker: form.ticker,
          shares: parseFloat(form.shares),
          avg_price: parseFloat(form.avg_price),
          buy_date: form.buy_date,
        });
        mutate("/api/portfolio");
      }
      setForm({ ticker: "", shares: "", avg_price: "", buy_date: "" });
      toast({ variant: "success", title: "Added to portfolio", description: form.ticker });
    } catch (e) {
      toast({ variant: "error", title: "Couldn't add holding", description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number | string) {
    const ok = await confirm({
      title: "Remove this holding?",
      description: "This will remove it from your portfolio permanently.",
      confirmLabel: "Remove",
      destructive: true,
    });
    if (!ok) return;
    if (!user) {
      removeGuestHolding(String(id));
      setGuestHoldings(getGuestHoldings());
      toast({ variant: "success", title: "Holding removed" });
      return;
    }
    const result = await deleteTolerant404(`/api/portfolio/${id}`);
    if (!result.ok) {
      toast({ variant: "error", title: "Couldn't remove holding", description: result.message });
      return;
    }
    mutate("/api/portfolio");
    toast({ variant: "success", title: "Holding removed" });
  }

  if (authLoading) return null;

  const isEmpty = holdings.length === 0;
  // Analysis (XIRR vs Nifty, sector/cap buckets, AI review) is computed
  // server-side against a session's stored holdings — no guest equivalent,
  // so the tab is hidden until sign-in rather than showing a broken/empty view.
  const showAnalysisTab = !!user;

  return (
    <div className={clsx(isEmpty && "mx-auto max-w-3xl", "space-y-6 animate-fade-up")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader />
        {showAnalysisTab && (
          <div className="flex gap-2">
            {([["holdings", "Holdings"], ["analysis", "Analysis"]] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setView(key)}
                className={view === key ? "seg seg-on" : "seg seg-off"}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      {!user && <GuestBanner />}

      {showAnalysisTab && view === "analysis" ? (
        <AnalysisPanel />
      ) : (
      <>
      {/* Summary — skipped while empty, four ₹0 tiles isn't worth showing */}
      {!isEmpty && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Invested" value={inr(summary?.invested)} />
          <Stat label="Current value" value={inr(summary?.value)} />
          <Stat label="P&L" value={inr(summary?.pnl)} cls={signCls(summary?.pnl)} />
          <Stat label="Return" value={pct(summary?.pnl_pct)} cls={signCls(summary?.pnl_pct)} />
        </div>
      )}

      {/* Add form */}
      <Card className="p-6">
        <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
          <Plus className="h-3.5 w-3.5 text-saffron" /> Add holding
        </h2>
        <div className="grid gap-3 sm:grid-cols-4">
          <div>
            <Label className="mb-1.5 block">Stock</Label>
            <SearchBox
              placeholder="Search ticker (TCS, INFY…)"
              onSelect={(symbol) => setForm({ ...form, ticker: symbol })}
            />
          </div>
          <div>
            <Label className="mb-1.5 block">Shares</Label>
            <Input className="nums" type="number" placeholder="0" value={form.shares}
              onChange={(e) => setForm({ ...form, shares: e.target.value })} />
          </div>
          <div>
            <Label className="mb-1.5 block">Avg price</Label>
            <Input className="nums" type="number" placeholder="₹0.00" value={form.avg_price}
              onChange={(e) => setForm({ ...form, avg_price: e.target.value })} />
          </div>
          <div>
            <Label className="mb-1.5 block">Buy date</Label>
            <Input type="date" value={form.buy_date}
              onChange={(e) => setForm({ ...form, buy_date: e.target.value })} />
          </div>
        </div>
        {form.ticker && (
          <p className="mt-3 text-xs text-muted">Selected: <span className="font-semibold text-saffron">{form.ticker}</span></p>
        )}
        <Button onClick={add} disabled={busy || !form.ticker} className="mt-4">
          {busy ? "Adding…" : "Add to portfolio"}
        </Button>
      </Card>

      {/* Holdings */}
      {isEmpty ? (
        <Card className="p-12 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-raised ring-1 ring-border">
            <Briefcase className="h-5 w-5 text-muted" />
          </div>
          <p className="text-sm text-muted">No holdings yet — add your first one above.</p>
        </Card>
      ) : (
      <Card className="overflow-hidden">
        {/* Portfolio table runs 7 columns wide — never fits a phone screen,
            so it scrolls horizontally inside the card rather than clipping
            (previously: Card's own overflow-hidden cut off P&L + delete). */}
        <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-muted">
            <tr className="[&>th]:px-5 [&>th]:py-3 [&>th]:text-left [&>th]:text-micro-cap [&>th]:font-normal [&>th]:uppercase [&>th]:tracking-[0.1px]">
              <th>
                <button onClick={() => handleSort("ticker")} className={clsx("flex items-center gap-1 hover:text-fg", sortKey === "ticker" && "text-saffron")}>
                  Asset <SortIcon active={sortKey === "ticker"} dir={sortDir} />
                </button>
              </th>
              <th className="!text-right">
                <button onClick={() => handleSort("shares")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "shares" && "text-saffron")}>
                  Shares <SortIcon active={sortKey === "shares"} dir={sortDir} />
                </button>
              </th>
              <th className="!text-right">
                <button onClick={() => handleSort("avg_price")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "avg_price" && "text-saffron")}>
                  Avg <SortIcon active={sortKey === "avg_price"} dir={sortDir} />
                </button>
              </th>
              <th className="!text-right">
                <button onClick={() => handleSort("current_price")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "current_price" && "text-saffron")}>
                  LTP <SortIcon active={sortKey === "current_price"} dir={sortDir} />
                </button>
              </th>
              <th className="!text-right">
                <button onClick={() => handleSort("current_value")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "current_value" && "text-saffron")}>
                  Value <SortIcon active={sortKey === "current_value"} dir={sortDir} />
                </button>
              </th>
              <th className="!text-right">
                <button onClick={() => handleSort("pnl_pct")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "pnl_pct" && "text-saffron")}>
                  P&L <SortIcon active={sortKey === "pnl_pct"} dir={sortDir} />
                </button>
              </th>
              <th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sortedHoldings.map((h: any) => (
              <tr key={h.id} className="[&>td]:px-5 [&>td]:py-3 hover:bg-raised/40">
                <td>
                  <a href={`/stock/${h.ticker}`} className="font-medium hover:text-saffron">{h.ticker.replace(".NS", "")}</a>
                  <div className="text-xs text-muted truncate max-w-[160px]">{h.company_name}</div>
                </td>
                <td className="nums text-right">{h.shares}</td>
                <td className="nums text-right text-muted">{inr(h.avg_price)}</td>
                <td className="nums text-right">{inr(h.current_price)}</td>
                <td className="nums text-right">{inr(h.current_value)}</td>
                <td className={`nums text-right font-medium ${signCls(h.pnl)}`}>{pct(h.pnl_pct)}</td>
                <td className="text-right">
                  <button onClick={() => remove(h.id)} className="text-muted hover:text-down">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </Card>
      )}
      </>
      )}
    </div>
  );
}

function Stat({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <Card className="p-4">
      <Label>{label}</Label>
      <p className={`nums mt-1 text-lg font-semibold ${cls || ""}`}>{value}</p>
    </Card>
  );
}

function PageHeader() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-saffron/10 ring-1 ring-saffron/20">
        <Briefcase className="h-4 w-4 text-saffron" />
      </div>
      <h1 className="font-display text-2xl font-semibold tracking-tight">Portfolio</h1>
    </div>
  );
}

/** Shown only when logged out — this portfolio is on-device only
 * (lib/guestData.ts) until the user signs in, at which point it's imported
 * into their account via POST /api/auth/sync-guest-data (see lib/auth.tsx). */
function GuestBanner() {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border bg-raised/40 px-4 py-2.5 text-xs text-muted">
      <Info className="h-3.5 w-3.5 shrink-0 text-saffron" />
      <span>
        Saved on this device only — P&amp;L only, no XIRR/analysis yet.{" "}
        <Link href="/login" className="font-medium text-saffron hover:underline">Sign in</Link>{" "}
        to sync it to your account and unlock full analysis.
      </span>
    </div>
  );
}
