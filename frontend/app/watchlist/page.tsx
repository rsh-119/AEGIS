"use client";

import useSWR, { mutate } from "swr";
import { fetcher, inr, pct, signCls, del } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { LoginPrompt } from "@/components/LoginPrompt";
import { useAuth } from "@/lib/auth";
import { Trash2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { useConfirm } from "@/components/ui/confirm-dialog";

export default function WatchlistPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { data } = useSWR(user ? "/api/watchlist" : null, fetcher, { revalidateOnFocus: false });
  const items = data?.items || [];

  async function remove(id: number) {
    const ok = await confirm({
      title: "Remove from watchlist?",
      confirmLabel: "Remove",
      destructive: true,
    });
    if (!ok) return;
    try {
      await del(`/api/watchlist/${id}`);
    } catch (e) {
      // 404 = already gone (stale list, double-click, etc.) — the desired
      // end state is already true, so just refresh instead of erroring out.
      if (!(e instanceof Error) || !e.message.includes("404")) {
        toast({ variant: "error", title: "Couldn't remove item", description: (e as Error).message });
        return;
      }
    }
    mutate("/api/watchlist");
    toast({ variant: "success", title: "Removed from watchlist" });
  }

  if (authLoading) return null;
  if (!user) {
    return (
      <div className="space-y-6 animate-fade-up">
        <h1 className="font-display text-3xl font-semibold">Watchlist</h1>
        <LoginPrompt what="your watchlist" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-display text-3xl font-semibold">Watchlist</h1>
        <div className="w-full max-w-xs">
          <SearchBox placeholder="Add a stock…" />
        </div>
      </div>

      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-muted">
            <tr className="[&>th]:px-5 [&>th]:py-3 [&>th]:text-left [&>th]:text-[10px] [&>th]:font-normal [&>th]:uppercase [&>th]:tracking-[0.1px]">
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
      </Card>
    </div>
  );
}
