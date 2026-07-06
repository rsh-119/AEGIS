"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Flame, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type Commodity = {
  product: string;
  expiry: string;
  last_traded_price: string;
  open_price: string;
  high_price: string;
  low_price: string;
  close_price: string;
  total_quantity_traded: string;
  open_interest: string;
  open_interest_per_change: number;
  change: number;
  per_change: number;
  oiResult: string;
  product_month: string;
};

const OI_RESULT_STYLE: Record<string, string> = {
  "Long Build Up": "bg-up/10 text-up",
  "Short Covering": "bg-up/10 text-up",
  "Short Build Up": "bg-down/10 text-down",
  "Long Unwinding": "bg-down/10 text-down",
  "Call Unwinding": "bg-muted/10 text-muted",
};

type SortKey = "product" | "last_traded_price" | "per_change" | "open_interest";
type SortDir = "asc" | "desc";

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 text-muted/40 shrink-0" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 text-saffron shrink-0" />
    : <ArrowDown className="h-3 w-3 text-saffron shrink-0" />;
}

export default function CommoditiesPage() {
  const { data, isLoading } = useSWR<Commodity[]>("/api/market/commodities", fetcher, { revalidateOnFocus: false });

  const [sortKey, setSortKey] = useState<SortKey>("product");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "product" ? "asc" : "desc"); }
  }

  const rows = useMemo(() => {
    const byProduct = new Map<string, Commodity>();
    for (const c of data ?? []) {
      const existing = byProduct.get(c.product);
      const vol = parseFloat(c.total_quantity_traded) || 0;
      const existingVol = existing ? parseFloat(existing.total_quantity_traded) || 0 : -1;
      if (!existing || vol > existingVol) byProduct.set(c.product, c);
    }
    return [...byProduct.values()].sort((a, b) => {
      if (sortKey === "product") {
        return sortDir === "asc" ? a.product.localeCompare(b.product) : b.product.localeCompare(a.product);
      }
      const av = sortKey === "per_change" ? a.per_change : parseFloat(a[sortKey]) || 0;
      const bv = sortKey === "per_change" ? b.per_change : parseFloat(b[sortKey]) || 0;
      return sortDir === "asc" ? av - bv : bv - av;
    });
  }, [data, sortKey, sortDir]);

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex items-center gap-2">
        <Flame className="h-5 w-5 text-saffron" />
        <h1 className="font-display text-3xl font-semibold">Commodities</h1>
      </div>
      <p className="text-sm text-muted -mt-4">Live MCX futures — most-active contract shown per product.</p>

      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-muted animate-pulse">Loading commodities…</div>
        ) : rows.length === 0 ? (
          <div className="p-10 text-center text-muted">Commodities data unavailable right now.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border text-muted">
                <tr className="[&>th]:px-5 [&>th]:py-3 [&>th]:text-left [&>th]:text-[10px] [&>th]:font-normal [&>th]:uppercase [&>th]:tracking-[0.1px]">
                  <th>
                    <button onClick={() => handleSort("product")} className={clsx("flex items-center gap-1 hover:text-fg", sortKey === "product" && "text-saffron")}>
                      Product <SortIcon active={sortKey === "product"} dir={sortDir} />
                    </button>
                  </th>
                  <th className="hidden sm:table-cell">Expiry</th>
                  <th className="!text-right">
                    <button onClick={() => handleSort("last_traded_price")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "last_traded_price" && "text-saffron")}>
                      LTP <SortIcon active={sortKey === "last_traded_price"} dir={sortDir} />
                    </button>
                  </th>
                  <th className="!text-right">
                    <button onClick={() => handleSort("per_change")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "per_change" && "text-saffron")}>
                      Change <SortIcon active={sortKey === "per_change"} dir={sortDir} />
                    </button>
                  </th>
                  <th className="hidden sm:table-cell !text-right">
                    <button onClick={() => handleSort("open_interest")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "open_interest" && "text-saffron")}>
                      OI <SortIcon active={sortKey === "open_interest"} dir={sortDir} />
                    </button>
                  </th>
                  <th className="hidden md:table-cell">Signal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((c) => {
                  const up = c.per_change >= 0;
                  return (
                    <tr key={c.product} className="[&>td]:px-5 [&>td]:py-3 hover:bg-raised/40">
                      <td className="font-medium whitespace-nowrap">{c.product}</td>
                      <td className="hidden sm:table-cell text-muted text-xs whitespace-nowrap">{c.expiry}</td>
                      <td className="nums text-right whitespace-nowrap">₹{c.last_traded_price}</td>
                      <td className={clsx("nums text-right font-semibold whitespace-nowrap", up ? "text-up" : "text-down")}>
                        {up ? "+" : ""}{c.per_change?.toFixed(2)}%
                      </td>
                      <td className="hidden sm:table-cell nums text-right text-muted whitespace-nowrap">{c.open_interest}</td>
                      <td className="hidden md:table-cell">
                        {c.oiResult && (
                          <Badge className={clsx("text-[10px]", OI_RESULT_STYLE[c.oiResult] ?? "bg-raised text-muted")}>
                            {c.oiResult}
                          </Badge>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
