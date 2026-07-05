"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetcher, inr, pct, signCls } from "@/lib/api";
import { Rocket, ExternalLink, Calendar } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type IpoStatus = "upcoming" | "open" | "listed";

type Ipo = {
  symbol: string;
  name: string;
  status: IpoStatus;
  is_sme: boolean;
  additional_text?: string | null;
  min_price?: number | null;
  max_price?: number | null;
  issue_price?: number | null;
  listing_gains?: number | null;
  listing_price?: number | null;
  bidding_start_date?: string | null;
  bidding_end_date?: string | null;
  listing_date?: string | null;
  lot_size?: number | null;
  document_url?: string | null;
};

const TABS: { value: IpoStatus; label: string }[] = [
  { value: "upcoming", label: "Upcoming" },
  { value: "open", label: "Open" },
  { value: "listed", label: "Listed" },
];

export default function IpoPage() {
  const { data, isLoading } = useSWR<Ipo[]>("/api/market/ipo", fetcher, { revalidateOnFocus: false });
  const [tab, setTab] = useState<IpoStatus>("upcoming");

  const ipos = data ?? [];
  const grouped = useMemo(() => {
    const g: Record<IpoStatus, Ipo[]> = { upcoming: [], open: [], listed: [] };
    for (const ipo of ipos) {
      if (ipo.status in g) g[ipo.status].push(ipo);
    }
    return g;
  }, [ipos]);

  const active = grouped[tab];

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex items-center gap-2">
        <Rocket className="h-5 w-5 text-saffron" />
        <h1 className="font-display text-3xl font-semibold">IPO Watch</h1>
      </div>

      <Card className="overflow-hidden">
        {/* Tab header */}
        <div className="flex items-center overflow-x-auto border-b border-border px-2">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={clsx(
                "flex items-center gap-1.5 border-b-2 px-4 py-3 text-sm font-medium transition-all duration-200",
                tab === t.value
                  ? "border-saffron text-saffron"
                  : "border-transparent text-muted hover:text-fg"
              )}
            >
              {t.label}
              <Badge className="bg-raised text-muted text-[10px]">{grouped[t.value].length}</Badge>
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-muted animate-pulse">Loading IPOs…</div>
        ) : active.length === 0 ? (
          <div className="p-10 text-center text-muted">No {tab} IPOs right now.</div>
        ) : (
          <div className="divide-y divide-border">
            {active.map((ipo) => (
              <IpoRow key={ipo.symbol} ipo={ipo} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function IpoRow({ ipo }: { ipo: Ipo }) {
  const priceLabel = ipo.min_price != null && ipo.max_price != null
    ? `${inr(ipo.min_price)} – ${inr(ipo.max_price)}`
    : ipo.issue_price != null ? inr(ipo.issue_price) : "—";

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 hover:bg-raised/40">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="font-semibold text-fg truncate">{ipo.name.trim()}</p>
          {ipo.is_sme && <Badge className="bg-blue-500/10 text-blue-500 text-[10px]">SME</Badge>}
        </div>
        {ipo.additional_text && (
          <p className="mt-0.5 text-xs text-muted">{ipo.additional_text}</p>
        )}
        {(ipo.bidding_start_date || ipo.listing_date) && (
          <div className="mt-1 flex items-center gap-1 text-[10px] text-muted">
            <Calendar className="h-3 w-3" />
            {ipo.bidding_start_date && <span>Bids from {ipo.bidding_start_date}</span>}
            {ipo.listing_date && <span>· Listing {ipo.listing_date}</span>}
          </div>
        )}
      </div>

      <div className="shrink-0 text-right">
        <p className="nums text-sm font-bold text-fg">{priceLabel}</p>
        {ipo.listing_gains != null && (
          <p className={clsx("nums text-xs font-semibold", signCls(ipo.listing_gains))}>
            {pct(ipo.listing_gains)} listing gain
          </p>
        )}
      </div>

      {ipo.document_url && (
        <a
          href={ipo.document_url}
          target="_blank"
          rel="noopener"
          className="flex shrink-0 items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-saffron hover:border-saffron/50 transition-colors"
        >
          <ExternalLink className="h-3 w-3" /> Filing
        </a>
      )}
    </div>
  );
}
