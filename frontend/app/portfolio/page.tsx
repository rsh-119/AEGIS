"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { useRouter } from "next/navigation";
import { fetcher, inr, pct, signCls, post, del } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { LoginPrompt } from "@/components/LoginPrompt";
import { useAuth } from "@/lib/auth";
import { Trash2, Plus, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useConfirm } from "@/components/ui/confirm-dialog";

type SortKey = "ticker" | "shares" | "avg_price" | "current_price" | "current_value" | "pnl_pct";
type SortDir = "asc" | "desc";

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 text-muted/40 shrink-0" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 text-saffron shrink-0" />
    : <ArrowDown className="h-3 w-3 text-saffron shrink-0" />;
}

export default function PortfolioPage() {
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { data } = useSWR(user ? "/api/portfolio" : null, fetcher, { revalidateOnFocus: false });
  const [form, setForm] = useState({ ticker: "", shares: "", avg_price: "", buy_date: "" });
  const [busy, setBusy] = useState(false);

  const [sortKey, setSortKey] = useState<SortKey>("ticker");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "ticker" ? "asc" : "desc"); }
  }

  const summary = data?.summary;
  const holdings = data?.holdings || [];
  const sortedHoldings = [...holdings].sort((a: any, b: any) => {
    if (sortKey === "ticker") {
      return sortDir === "asc" ? a.ticker.localeCompare(b.ticker) : b.ticker.localeCompare(a.ticker);
    }
    const av = a[sortKey] ?? -Infinity;
    const bv = b[sortKey] ?? -Infinity;
    return sortDir === "asc" ? av - bv : bv - av;
  });

  async function add() {
    if (!user) {
      router.push("/login");
      return;
    }
    if (!form.ticker || !form.shares || !form.avg_price || !form.buy_date) return;
    setBusy(true);
    try {
      await post("/api/portfolio", {
        ticker: form.ticker,
        shares: parseFloat(form.shares),
        avg_price: parseFloat(form.avg_price),
        buy_date: form.buy_date,
      });
      setForm({ ticker: "", shares: "", avg_price: "", buy_date: "" });
      mutate("/api/portfolio");
      toast({ variant: "success", title: "Added to portfolio", description: form.ticker });
    } catch (e) {
      toast({ variant: "error", title: "Couldn't add holding", description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    const ok = await confirm({
      title: "Remove this holding?",
      description: "This will remove it from your portfolio permanently.",
      confirmLabel: "Remove",
      destructive: true,
    });
    if (!ok) return;
    try {
      await del(`/api/portfolio/${id}`);
    } catch (e) {
      // 404 = already gone (stale list, double-click, etc.) — the desired
      // end state is already true, so just refresh instead of erroring out.
      if (!(e instanceof Error) || !e.message.includes("404")) {
        toast({ variant: "error", title: "Couldn't remove holding", description: (e as Error).message });
        return;
      }
    }
    mutate("/api/portfolio");
    toast({ variant: "success", title: "Holding removed" });
  }

  if (authLoading) return null;
  if (!user) {
    return (
      <div className="space-y-6 animate-fade-up">
        <h1 className="font-display text-3xl font-semibold">Portfolio</h1>
        <LoginPrompt what="your portfolio" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <h1 className="font-display text-3xl font-semibold">Portfolio</h1>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Invested" value={inr(summary?.invested)} />
        <Stat label="Current value" value={inr(summary?.value)} />
        <Stat label="P&L" value={inr(summary?.pnl)} cls={signCls(summary?.pnl)} />
        <Stat label="Return" value={pct(summary?.pnl_pct)} cls={signCls(summary?.pnl_pct)} />
      </div>

      {/* Add form */}
      <Card className="p-5">
        <h2 className="mb-4 flex items-center gap-2 font-medium"><Plus className="h-4 w-4 text-saffron" /> Add holding</h2>
        <div className="grid gap-3 sm:grid-cols-4">
          {/* SearchBox for ticker with onSelect callback */}
          <SearchBox
            placeholder="Search ticker (TCS, INFY…)"
            onSelect={(symbol) => setForm({ ...form, ticker: symbol })}
          />
          <Input className="nums" type="number" placeholder="Shares" value={form.shares}
            onChange={(e) => setForm({ ...form, shares: e.target.value })} />
          <Input className="nums" type="number" placeholder="Avg price ₹" value={form.avg_price}
            onChange={(e) => setForm({ ...form, avg_price: e.target.value })} />
          <Input type="date" value={form.buy_date}
            onChange={(e) => setForm({ ...form, buy_date: e.target.value })} />
        </div>
        {form.ticker && (
          <p className="mt-2 text-xs text-muted">Selected: <span className="font-semibold text-saffron">{form.ticker}</span></p>
        )}
        <Button onClick={add} disabled={busy || !form.ticker} className="mt-3">
          {busy ? "Adding…" : "Add to portfolio"}
        </Button>
      </Card>

      {/* Holdings */}
      <Card className="overflow-hidden">
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
            {sortedHoldings.length === 0 ? (
              <tr><td colSpan={7} className="px-5 py-10 text-center text-muted">No holdings yet.</td></tr>
            ) : sortedHoldings.map((h: any) => (
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
      </Card>
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
