"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { fetcher, inr, pct, signCls, post, del } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { Trash2, Plus } from "lucide-react";

export default function PortfolioPage() {
  const { data } = useSWR("/api/portfolio", fetcher, { revalidateOnFocus: false });
  const [form, setForm] = useState({ ticker: "", shares: "", avg_price: "", buy_date: "" });
  const [busy, setBusy] = useState(false);

  const summary = data?.summary;
  const holdings = data?.holdings || [];

  async function add() {
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
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("Remove this holding?")) return;
    await del(`/api/portfolio/${id}`);
    mutate("/api/portfolio");
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
      <div className="card p-5">
        <h2 className="mb-4 flex items-center gap-2 font-medium"><Plus className="h-4 w-4 text-saffron" /> Add holding</h2>
        <div className="grid gap-3 sm:grid-cols-4">
          {/* SearchBox for ticker with onSelect callback */}
          <SearchBox
            placeholder="Search ticker (TCS, INFY…)"
            onSelect={(symbol) => setForm({ ...form, ticker: symbol })}
          />
          <input className="input nums" type="number" placeholder="Shares" value={form.shares}
            onChange={(e) => setForm({ ...form, shares: e.target.value })} />
          <input className="input nums" type="number" placeholder="Avg price ₹" value={form.avg_price}
            onChange={(e) => setForm({ ...form, avg_price: e.target.value })} />
          <input className="input" type="date" value={form.buy_date}
            onChange={(e) => setForm({ ...form, buy_date: e.target.value })} />
        </div>
        {form.ticker && (
          <p className="mt-2 text-xs text-muted">Selected: <span className="font-semibold text-saffron">{form.ticker}</span></p>
        )}
        <button onClick={add} disabled={busy || !form.ticker} className="btn-primary mt-3">
          {busy ? "Adding…" : "Add to portfolio"}
        </button>
      </div>

      {/* Holdings */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-muted">
            <tr className="[&>th]:px-5 [&>th]:py-3 [&>th]:text-left [&>th]:label">
              <th>Asset</th>
              <th className="!text-right">Shares</th>
              <th className="!text-right">Avg</th>
              <th className="!text-right">LTP</th>
              <th className="!text-right">Value</th>
              <th className="!text-right">P&L</th>
              <th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {holdings.length === 0 ? (
              <tr><td colSpan={7} className="px-5 py-10 text-center text-muted">No holdings yet.</td></tr>
            ) : holdings.map((h: any) => (
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
    </div>
  );
}

function Stat({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="card p-4">
      <p className="label">{label}</p>
      <p className={`nums mt-1 text-lg font-semibold ${cls || ""}`}>{value}</p>
    </div>
  );
}
