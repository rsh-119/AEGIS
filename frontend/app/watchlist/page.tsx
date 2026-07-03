"use client";

import useSWR, { mutate } from "swr";
import { fetcher, inr, pct, signCls, del } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { Trash2 } from "lucide-react";

export default function WatchlistPage() {
  const { data } = useSWR("/api/watchlist", fetcher, { revalidateOnFocus: false });
  const items = data?.items || [];

  async function remove(id: number) {
    if (!confirm("Remove from watchlist?")) return;
    await del(`/api/watchlist/${id}`);
    mutate("/api/watchlist");
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-display text-3xl font-semibold">Watchlist</h1>
        <div className="w-full max-w-xs">
          <SearchBox placeholder="Add a stock…" />
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-muted">
            <tr className="[&>th]:px-5 [&>th]:py-3 [&>th]:text-left [&>th]:label">
              <th>Asset</th>
              <th className="!text-right">LTP</th>
              <th className="!text-right">Change</th>
              <th className="!text-right">Target</th>
              <th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.length === 0 ? (
              <tr><td colSpan={5} className="px-5 py-10 text-center text-muted">
                Watchlist is empty. Use search above to add NSE/BSE stocks.
              </td></tr>
            ) : items.map((it: any) => (
              <tr key={it.id} className="[&>td]:px-5 [&>td]:py-3 hover:bg-raised/40">
                <td>
                  <a href={`/stock/${it.ticker}`} className="font-medium hover:text-saffron">{it.ticker.replace(".NS", "")}</a>
                  <div className="text-xs text-muted truncate max-w-[180px]">{it.company_name}</div>
                </td>
                <td className="nums text-right">{inr(it.current_price)}</td>
                <td className={`nums text-right ${signCls(it.pct_change)}`}>{pct(it.pct_change)}</td>
                <td className="nums text-right text-muted">{it.target_price ? inr(it.target_price) : "—"}</td>
                <td className="text-right">
                  <button onClick={() => remove(it.id)} className="text-muted hover:text-down">
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
