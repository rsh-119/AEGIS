"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { fetcher, inr, pct, signCls } from "@/lib/api";
import {
  Rocket, ExternalLink, Search, TrendingUp, CalendarDays, Layers,
} from "lucide-react";
import clsx from "clsx";
import { Badge } from "@/components/ui/badge";
import { Reveal } from "@/components/motion";

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
  { value: "open", label: "Open now" },
  { value: "upcoming", label: "Upcoming" },
  { value: "listed", label: "Listed" },
];

/* Monogram tile — IPOs are mostly unlisted, so no logos exist yet.
   Deterministic categorical palette, same precedent as StockLogo. */
const MONO_COLORS = [
  "bg-blue-500/15 text-blue-500", "bg-violet-500/15 text-violet-500",
  "bg-teal-500/15 text-teal-600", "bg-amber-500/15 text-amber-600",
  "bg-rose-500/15 text-rose-500", "bg-emerald-500/15 text-emerald-600",
];
function Monogram({ name }: { name: string }) {
  const words = name.trim().split(/\s+/);
  const initials = (words[0]?.[0] ?? "") + (words[1]?.[0] ?? words[0]?.[1] ?? "");
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff;
  return (
    <span className={clsx(
      "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-display text-sm font-semibold uppercase",
      MONO_COLORS[hash % MONO_COLORS.length],
    )}>
      {initials}
    </span>
  );
}

function StatusBadge({ status }: { status: IpoStatus }) {
  if (status === "open")
    return (
      <Badge className="bg-up/10 text-up text-[10px]">
        <span className="relative mr-0.5 flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-up" />
        </span>
        Open now
      </Badge>
    );
  if (status === "upcoming") return <Badge className="bg-saffron/10 text-saffron text-[10px]">Upcoming</Badge>;
  return <Badge className="bg-raised text-muted text-[10px]">Listed</Badge>;
}

function fmtDate(d?: string | null) {
  if (!d) return null;
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/* Bid-open → bid-close → listing mini-timeline */
function Timeline({ ipo }: { ipo: Ipo }) {
  const steps = [
    { label: "Bids open", date: fmtDate(ipo.bidding_start_date) },
    { label: "Bids close", date: fmtDate(ipo.bidding_end_date) },
    { label: "Listing", date: fmtDate(ipo.listing_date) },
  ];
  if (steps.every((s) => !s.date)) return null;
  return (
    <div className="mt-4 flex items-center">
      {steps.map((s, i) => (
        <div key={s.label} className={clsx("flex items-center", i > 0 && "flex-1")}>
          {i > 0 && <span className="mx-1.5 h-px flex-1 bg-border" aria-hidden />}
          <div className="text-center">
            <span className={clsx(
              "mx-auto block h-1.5 w-1.5 rounded-full",
              s.date ? "bg-saffron" : "bg-border",
            )} aria-hidden />
            <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.08em] text-muted">{s.label}</p>
            <p className="nums text-[11px] font-semibold text-fg">{s.date ?? "TBA"}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function IpoCard({ ipo }: { ipo: Ipo }) {
  const router = useRouter();
  const priceBand =
    ipo.min_price != null && ipo.max_price != null
      ? `₹${ipo.min_price.toLocaleString("en-IN")} – ₹${ipo.max_price.toLocaleString("en-IN")}`
      : ipo.issue_price != null ? inr(ipo.issue_price) : "TBA";

  // Listed issues now trade — the card opens their stock page. Everything
  // else opens the SEBI filing when one exists.
  const openTarget = () => {
    if (ipo.status === "listed") router.push(`/stock/${encodeURIComponent(ipo.symbol)}.NS`);
    else if (ipo.document_url) window.open(ipo.document_url, "_blank", "noopener");
  };
  const clickable = ipo.status === "listed" || !!ipo.document_url;

  return (
    <div
      onClick={clickable ? openTarget : undefined}
      onKeyDown={(e) => { if (clickable && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openTarget(); } }}
      role={clickable ? "link" : undefined}
      tabIndex={clickable ? 0 : undefined}
      className={clsx(
        "group flex h-full flex-col rounded-2xl border border-border bg-surface p-5 shadow-sm transition-all duration-300",
        clickable && "cursor-pointer hover:-translate-y-1 hover:border-saffron/40 hover:shadow-lg hover:shadow-black/5 active:scale-[0.99]",
      )}
    >
      <div className="flex items-start gap-3">
        <Monogram name={ipo.name} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold leading-snug text-fg group-hover:text-saffron transition-colors">
            {ipo.name.trim()}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[10px] text-muted">{ipo.symbol}</span>
            <StatusBadge status={ipo.status} />
            {ipo.is_sme && <Badge className="bg-blue-500/10 text-blue-500 text-[10px]">SME</Badge>}
          </div>
        </div>
        {ipo.status === "listed" && ipo.listing_gains != null && (
          <span className={clsx(
            "nums shrink-0 rounded-lg px-2 py-1 text-sm font-bold",
            ipo.listing_gains >= 0 ? "bg-up/10 text-up" : "bg-down/10 text-down",
          )}>
            {pct(ipo.listing_gains)}
          </span>
        )}
      </div>

      {/* Numbers row */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-raised/50 px-3 py-2">
          <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted">
            {ipo.status === "listed" ? "Issue price" : "Price band"}
          </p>
          <p className="nums mt-0.5 text-sm font-semibold text-fg">
            {ipo.status === "listed" && ipo.issue_price != null ? inr(ipo.issue_price) : priceBand}
          </p>
        </div>
        <div className="rounded-xl bg-raised/50 px-3 py-2">
          <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted">
            {ipo.status === "listed" ? "Listed at" : "Lot size"}
          </p>
          <p className="nums mt-0.5 text-sm font-semibold text-fg">
            {ipo.status === "listed"
              ? (ipo.listing_price != null ? inr(ipo.listing_price) : "—")
              : (ipo.lot_size != null ? `${ipo.lot_size} shares` : "TBA")}
          </p>
        </div>
      </div>

      <Timeline ipo={ipo} />

      {ipo.additional_text && (
        <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-muted">{ipo.additional_text}</p>
      )}

      {/* Footer actions */}
      <div className="mt-auto flex items-center justify-between gap-2 pt-4">
        <span className="text-xs font-semibold text-saffron opacity-0 transition-opacity duration-200 group-hover:opacity-100 max-sm:opacity-100">
          {ipo.status === "listed" ? "View stock →" : ipo.document_url ? "View filing →" : ""}
        </span>
        {ipo.document_url && ipo.status === "listed" && (
          <a
            href={ipo.document_url}
            target="_blank"
            rel="noopener"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[10px] text-muted transition-colors hover:border-saffron/50 hover:text-saffron"
          >
            <ExternalLink className="h-3 w-3" /> Filing
          </a>
        )}
      </div>
    </div>
  );
}

export default function IpoPage() {
  const { data, isLoading } = useSWR<Ipo[]>("/api/market/ipo", fetcher, { revalidateOnFocus: false });
  const [tab, setTab] = useState<IpoStatus | null>(null);
  const [query, setQuery] = useState("");

  const ipos = data ?? [];
  const grouped = useMemo(() => {
    const g: Record<IpoStatus, Ipo[]> = { upcoming: [], open: [], listed: [] };
    for (const ipo of ipos) if (ipo.status in g) g[ipo.status].push(ipo);
    // Upcoming: soonest bidding first (TBA last); Listed: freshest listing first
    g.upcoming.sort((a, b) => (a.bidding_start_date ?? "9999") < (b.bidding_start_date ?? "9999") ? -1 : 1);
    g.listed.sort((a, b) => ((b.listing_date ?? "") < (a.listing_date ?? "") ? -1 : 1));
    return g;
  }, [ipos]);

  // Default to whichever tab actually has something happening
  const activeTab: IpoStatus = tab ?? (grouped.open.length ? "open" : "upcoming");
  const q = query.trim().toLowerCase();
  const active = grouped[activeTab].filter(
    (i) => !q || i.name.toLowerCase().includes(q) || i.symbol.toLowerCase().includes(q),
  );

  const listedWithGains = grouped.listed.filter((i) => i.listing_gains != null);
  const avgGain = listedWithGains.length
    ? listedWithGains.reduce((s, i) => s + (i.listing_gains ?? 0), 0) / listedWithGains.length
    : null;

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div>
        <p className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.18em] text-saffron">
          <Rocket className="h-3.5 w-3.5" /> Primary market
        </p>
        <h1 className="mt-2 font-display text-[clamp(1.9rem,4vw,2.75rem)] font-medium leading-tight tracking-[-0.015em]">
          IPO Watch
        </h1>
        <p className="mt-1.5 text-sm text-muted">
          Every mainboard and SME issue — price bands, bidding windows, and how they listed.
        </p>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { icon: <TrendingUp className="h-4 w-4" />, label: "Open for bidding", value: String(grouped.open.length) },
          { icon: <CalendarDays className="h-4 w-4" />, label: "Upcoming issues", value: String(grouped.upcoming.length) },
          { icon: <Layers className="h-4 w-4" />, label: "Recently listed", value: String(grouped.listed.length) },
          {
            icon: <Rocket className="h-4 w-4" />, label: "Avg listing pop",
            value: avgGain != null ? `${avgGain >= 0 ? "+" : ""}${avgGain.toFixed(1)}%` : "—",
            cls: avgGain != null ? signCls(avgGain) : undefined,
          },
        ].map((s) => (
          <div key={s.label} className="rounded-2xl border border-border bg-surface p-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-saffron/10 text-saffron">
              {s.icon}
            </span>
            <p className={clsx("nums mt-2.5 text-2xl font-semibold text-fg", s.cls)}>{s.value}</p>
            <p className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Tabs + search */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={clsx(activeTab === t.value ? "seg seg-on" : "seg seg-off", "flex items-center gap-1.5")}
            >
              {t.label}
              <span className={clsx(
                "nums rounded-full px-1.5 text-[10px]",
                activeTab === t.value ? "bg-white/20" : "bg-raised",
              )}>
                {grouped[t.value].length}
              </span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-2">
          <Search className="h-3.5 w-3.5 text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search issues…"
            className="w-36 bg-transparent text-xs text-fg outline-none placeholder:text-muted/70 sm:w-48"
          />
        </div>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-52 rounded-2xl" />
          ))}
        </div>
      ) : active.length === 0 ? (
        <div className="rounded-2xl border border-border bg-surface p-12 text-center text-sm text-muted">
          {q ? `Nothing matches “${query}” in this tab.` : `No ${activeTab === "open" ? "open" : activeTab} issues right now — check the other tabs.`}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {active.map((ipo, i) => (
            <Reveal key={`${ipo.symbol}-${ipo.status}`} delay={Math.min(i, 8) * 60} className="h-full">
              <IpoCard ipo={ipo} />
            </Reveal>
          ))}
        </div>
      )}

      <p className="text-right font-mono text-[10px] uppercase tracking-[0.14em] text-muted/60">
        Source: SEBI filings via IndianAPI · refreshed hourly
      </p>
    </div>
  );
}
