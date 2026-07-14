"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, inr, pct, signCls } from "@/lib/api";
import {
  Rocket, ExternalLink, Search, TrendingUp, CalendarDays, Layers,
  ChevronRight, ChevronDown, CheckCircle2, Circle, X, MousePointerClick,
} from "lucide-react";
import clsx from "clsx";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
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
  { value: "open", label: "Open" },
  { value: "upcoming", label: "Upcoming" },
  { value: "listed", label: "Listed" },
];

type TypeFilter = "all" | "mainboard" | "sme";

/* ── Small pieces ───────────────────────────────────────────── */

const MONO_COLORS = [
  "bg-blue-500/15 text-blue-500", "bg-violet-500/15 text-violet-500",
  "bg-teal-500/15 text-teal-600", "bg-amber-500/15 text-amber-600",
  "bg-rose-500/15 text-rose-500", "bg-emerald-500/15 text-emerald-600",
];
function Monogram({ name, size = "h-10 w-10 text-sm" }: { name: string; size?: string }) {
  const words = name.trim().split(/\s+/);
  const initials = (words[0]?.[0] ?? "") + (words[1]?.[0] ?? words[0]?.[1] ?? "");
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff;
  return (
    <span className={clsx(
      "flex shrink-0 items-center justify-center rounded-xl font-display font-semibold uppercase",
      size, MONO_COLORS[hash % MONO_COLORS.length],
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
        Open
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

function priceBand(ipo: Ipo) {
  if (ipo.min_price != null && ipo.max_price != null)
    return `₹${ipo.min_price.toLocaleString("en-IN")} – ₹${ipo.max_price.toLocaleString("en-IN")}`;
  if (ipo.issue_price != null) return inr(ipo.issue_price);
  return "TBA";
}

function minInvestment(ipo: Ipo): { amount: string; shares: number } | null {
  const px = ipo.max_price ?? ipo.issue_price ?? ipo.min_price;
  if (px == null || ipo.lot_size == null) return null;
  return { amount: inr(px * ipo.lot_size), shares: ipo.lot_size };
}

/* ── Schedule stepper — Groww-style check circles ───────────── */
function Schedule({ ipo }: { ipo: Ipo }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const steps = [
    { label: "Bidding opens", raw: ipo.bidding_start_date },
    { label: "Bidding closes", raw: ipo.bidding_end_date },
    { label: ipo.status === "listed" ? "Listed on" : "Tentative listing", raw: ipo.listing_date },
  ];
  if (steps.every((s) => !s.raw)) return null;

  // done = date passed; the first not-done step with a date is "active"
  let activeAssigned = false;
  const rendered = steps.map((s) => {
    const dt = s.raw ? new Date(s.raw) : null;
    const valid = dt && !isNaN(dt.getTime());
    const done = valid ? dt! < today || ipo.status === "listed" : false;
    let state: "done" | "active" | "pending" = done ? "done" : "pending";
    if (!done && !activeAssigned && valid) { state = "active"; activeAssigned = true; }
    return { ...s, date: fmtDate(s.raw), state };
  });

  return (
    <div>
      <h4 className="text-sm font-semibold text-fg">Schedule</h4>
      <div className="mt-4 flex items-start">
        {rendered.map((s, i) => (
          <div key={s.label} className={clsx("flex items-start", i > 0 && "flex-1")}>
            {i > 0 && <span className="mx-2 mt-2.5 h-px flex-1 bg-border" aria-hidden />}
            <div className="flex w-20 flex-col items-center text-center">
              {s.state === "done" ? (
                <CheckCircle2 className="h-5 w-5 text-up" />
              ) : s.state === "active" ? (
                <span className="flex h-5 w-5 items-center justify-center rounded-full ring-2 ring-saffron">
                  <span className="h-2 w-2 rounded-full bg-saffron" />
                </span>
              ) : (
                <Circle className="h-5 w-5 text-border" />
              )}
              <p className="nums mt-1.5 text-[11px] font-semibold text-fg">{s.date ?? "TBA"}</p>
              <p className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.06em] text-muted">{s.label}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── FAQ accordion — templated from the issue's own data ─────── */
function Faq({ ipo }: { ipo: Ipo }) {
  const [open, setOpen] = useState<number | null>(null);
  const inv = minInvestment(ipo);
  const qs: { q: string; a: string }[] = [];

  if (ipo.min_price != null || ipo.issue_price != null) {
    qs.push({
      q: `What is the price band of ${ipo.name}?`,
      a: ipo.min_price != null && ipo.max_price != null
        ? `The price band is ${priceBand(ipo)} per share.${ipo.issue_price != null ? ` The final issue price was set at ${inr(ipo.issue_price)}.` : ""}`
        : `The issue price is ${inr(ipo.issue_price!)} per share.`,
    });
  }
  if (ipo.lot_size != null) {
    qs.push({
      q: `What is the lot size of ${ipo.name}?`,
      a: `One lot is ${ipo.lot_size.toLocaleString("en-IN")} shares${inv ? `, so the minimum application works out to about ${inv.amount} at the top of the band` : ""}.`,
    });
  }
  if (ipo.bidding_start_date || ipo.bidding_end_date) {
    qs.push({
      q: `What are the open and close dates of ${ipo.name}?`,
      a: `Bidding ${ipo.bidding_start_date ? `opens on ${fmtDate(ipo.bidding_start_date)}` : "dates are yet to be announced"}${ipo.bidding_end_date ? ` and closes on ${fmtDate(ipo.bidding_end_date)}` : ""}.${ipo.listing_date ? ` ${ipo.status === "listed" ? "It listed" : "Tentative listing is"} on ${fmtDate(ipo.listing_date)}.` : ""}`,
    });
  }
  if (ipo.status === "listed" && ipo.listing_gains != null) {
    qs.push({
      q: `How did ${ipo.name} perform on listing day?`,
      a: `It listed at ${ipo.listing_price != null ? inr(ipo.listing_price) : "—"} against an issue price of ${ipo.issue_price != null ? inr(ipo.issue_price) : "—"} — a ${Math.abs(ipo.listing_gains).toFixed(2)}% ${ipo.listing_gains >= 0 ? "gain" : "loss"} for allottees.`,
    });
  }
  qs.push({
    q: `Is ${ipo.name} a mainboard or SME issue?`,
    a: ipo.is_sme
      ? "It's an SME issue — these list on the NSE Emerge / BSE SME platforms, typically with larger lot sizes and lower liquidity than mainboard IPOs."
      : "It's a mainboard issue, listing on the main NSE/BSE exchanges.",
  });

  return (
    <div>
      <h4 className="text-sm font-semibold text-fg">Frequently asked questions</h4>
      <div className="mt-2 divide-y divide-border">
        {qs.map((item, i) => (
          <div key={i}>
            <button
              onClick={() => setOpen(open === i ? null : i)}
              aria-expanded={open === i}
              className="flex w-full items-center justify-between gap-3 py-3 text-left text-[13px] font-medium text-fg transition-colors hover:text-saffron"
            >
              {item.q}
              <ChevronDown className={clsx("h-3.5 w-3.5 shrink-0 text-muted transition-transform duration-200", open === i && "rotate-180")} />
            </button>
            {open === i && (
              <p className="pb-3 text-xs leading-relaxed text-muted">{item.a}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Detail panel ────────────────────────────────────────────── */
function DetailPanel({ ipo, onClose }: { ipo: Ipo; onClose?: () => void }) {
  const inv = minInvestment(ipo);
  const details: { label: string; value: string; cls?: string }[] = [
    { label: ipo.status === "listed" ? "Issue price" : "Price band", value: ipo.status === "listed" && ipo.issue_price != null ? inr(ipo.issue_price) : priceBand(ipo) },
    { label: "Lot size", value: ipo.lot_size != null ? `${ipo.lot_size.toLocaleString("en-IN")} shares` : "TBA" },
  ];
  if (ipo.status === "listed") {
    details.push({ label: "Listed at", value: ipo.listing_price != null ? inr(ipo.listing_price) : "—" });
    if (ipo.listing_gains != null)
      details.push({ label: "Listing gain", value: pct(ipo.listing_gains), cls: signCls(ipo.listing_gains) });
  } else if (inv) {
    details.push({ label: "Min investment", value: inv.amount });
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-start gap-3 border-b border-border p-5">
        <Monogram name={ipo.name} size="h-11 w-11 text-sm" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-lg font-semibold leading-snug text-fg">{ipo.name.trim()}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[10px] text-muted">{ipo.symbol}</span>
            <StatusBadge status={ipo.status} />
            {ipo.is_sme && <Badge className="bg-blue-500/10 text-blue-500 text-[10px]">SME</Badge>}
          </div>
        </div>
        {onClose ? (
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-muted transition-colors hover:bg-raised hover:text-fg">
            <X className="h-4 w-4" />
          </button>
        ) : inv && ipo.status !== "listed" ? (
          <div className="shrink-0 text-right">
            <p className="nums text-lg font-bold text-fg">{inv.amount}</p>
            <p className="text-[10px] text-muted">min · {inv.shares.toLocaleString("en-IN")} shares</p>
          </div>
        ) : null}
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto p-5">
        {/* Details grid */}
        <div>
          <h4 className="text-sm font-semibold text-fg">IPO details</h4>
          <div className="mt-3 grid grid-cols-2 gap-3">
            {details.map((d) => (
              <div key={d.label} className="rounded-xl bg-raised/50 px-3 py-2.5">
                <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted">{d.label}</p>
                <p className={clsx("nums mt-0.5 text-sm font-semibold text-fg", d.cls)}>{d.value}</p>
              </div>
            ))}
          </div>
        </div>

        <Schedule ipo={ipo} />

        {ipo.additional_text && (
          <div>
            <h4 className="text-sm font-semibold text-fg">Notes</h4>
            <p className="mt-1.5 text-xs leading-relaxed text-muted">{ipo.additional_text}</p>
          </div>
        )}

        <Faq ipo={ipo} />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2.5 border-t border-border p-4">
        {ipo.status === "listed" && (
          <Link
            href={`/stock/${encodeURIComponent(ipo.symbol)}.NS`}
            className="btn-sheen flex-1 rounded-full bg-saffron px-5 py-2.5 text-center text-sm font-semibold text-white shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md active:scale-[0.98]"
          >
            View stock →
          </Link>
        )}
        {ipo.document_url && (
          <a
            href={ipo.document_url}
            target="_blank"
            rel="noopener"
            className={clsx(
              "flex items-center justify-center gap-1.5 rounded-full border border-border px-5 py-2.5 text-sm font-medium text-muted transition-colors hover:border-saffron/50 hover:text-saffron",
              ipo.status !== "listed" && "flex-1",
            )}
          >
            <ExternalLink className="h-3.5 w-3.5" /> {ipo.status === "listed" ? "Filing" : "Read the filing (RHP)"}
          </a>
        )}
      </div>
    </div>
  );
}

/* ── Page ────────────────────────────────────────────────────── */
export default function IpoPage() {
  const { data, isLoading } = useSWR<Ipo[]>("/api/market/ipo", fetcher, { revalidateOnFocus: false });
  const [tab, setTab] = useState<IpoStatus | null>(null);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Ipo | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  const ipos = data ?? [];
  const grouped = useMemo(() => {
    const g: Record<IpoStatus, Ipo[]> = { upcoming: [], open: [], listed: [] };
    for (const ipo of ipos) if (ipo.status in g) g[ipo.status].push(ipo);
    g.upcoming.sort((a, b) => ((a.bidding_start_date ?? "9999") < (b.bidding_start_date ?? "9999") ? -1 : 1));
    g.listed.sort((a, b) => ((b.listing_date ?? "") < (a.listing_date ?? "") ? -1 : 1));
    return g;
  }, [ipos]);

  const activeTab: IpoStatus = tab ?? (grouped.open.length ? "open" : "upcoming");
  const q = query.trim().toLowerCase();
  const active = grouped[activeTab].filter((i) => {
    if (typeFilter === "sme" && !i.is_sme) return false;
    if (typeFilter === "mainboard" && i.is_sme) return false;
    return !q || i.name.toLowerCase().includes(q) || i.symbol.toLowerCase().includes(q);
  });

  // Keep the detail panel coherent with the visible list
  useEffect(() => {
    if (selected && !active.some((i) => i.symbol === selected.symbol && i.status === selected.status)) {
      setSelected(null);
      setMobileOpen(false);
    }
  }, [activeTab, typeFilter, q]); // eslint-disable-line react-hooks/exhaustive-deps

  const listedWithGains = grouped.listed.filter((i) => i.listing_gains != null);
  const avgGain = listedWithGains.length
    ? listedWithGains.reduce((s, i) => s + (i.listing_gains ?? 0), 0) / listedWithGains.length
    : null;

  function choose(ipo: Ipo) {
    setSelected(ipo);
    if (typeof window !== "undefined" && window.innerWidth < 1024) setMobileOpen(true);
  }

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div>
        <p className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.18em] text-saffron">
          <Rocket className="h-3.5 w-3.5" /> Primary market
        </p>
        <h1 className="mt-2 font-display text-[clamp(1.9rem,4vw,2.75rem)] font-medium leading-tight tracking-[-0.015em]">
          IPO Dashboard
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
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-saffron/10 text-saffron">{s.icon}</span>
            <p className={clsx("nums mt-2.5 text-2xl font-semibold text-fg", s.cls)}>{s.value}</p>
            <p className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={clsx(activeTab === t.value ? "seg seg-on" : "seg seg-off", "flex items-center gap-1.5")}
            >
              {t.label}
              <span className={clsx("nums rounded-full px-1.5 text-[10px]", activeTab === t.value ? "bg-white/20" : "bg-raised")}>
                {grouped[t.value].length}
              </span>
            </button>
          ))}
          <span className="mx-1 h-5 w-px bg-border" aria-hidden />
          {(["all", "mainboard", "sme"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setTypeFilter(f)}
              className={clsx(
                "rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-[0.08em] transition-colors",
                typeFilter === f ? "bg-raised text-fg ring-1 ring-border" : "text-muted hover:text-fg",
              )}
            >
              {f === "all" ? "All" : f === "sme" ? "SME" : "Mainboard"}
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

      {/* Master–detail */}
      <div className="grid items-start gap-5 lg:grid-cols-[1.4fr_1fr]">
        {/* List */}
        <Card className="overflow-hidden">
          <div className="hidden grid-cols-[1fr_auto_auto] gap-4 border-b border-border bg-raised/40 px-5 py-2.5 font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted sm:grid">
            <span>Company</span>
            <span className="w-20 text-right">{activeTab === "listed" ? "Listed" : "Closes"}</span>
            <span className="w-24 text-right">{activeTab === "listed" ? "Returns" : "Price band"}</span>
          </div>
          {isLoading ? (
            <div className="divide-y divide-border">
              {Array.from({ length: 7 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-4">
                  <div className="skeleton h-10 w-10 rounded-xl" />
                  <div className="flex-1 space-y-1.5">
                    <div className="skeleton h-3.5 w-40 rounded" />
                    <div className="skeleton h-2.5 w-24 rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : active.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted">
              {q || typeFilter !== "all" ? "Nothing matches these filters." : `No ${activeTab} issues right now — check the other tabs.`}
            </div>
          ) : (
            <div className="max-h-[620px] divide-y divide-border overflow-y-auto">
              {active.map((ipo) => {
                const isSel = selected?.symbol === ipo.symbol && selected?.status === ipo.status;
                return (
                  <button
                    key={`${ipo.symbol}-${ipo.status}`}
                    onClick={() => choose(ipo)}
                    aria-current={isSel}
                    className={clsx(
                      "grid w-full grid-cols-[1fr_auto] items-center gap-3 px-4 py-3.5 text-left transition-colors sm:grid-cols-[1fr_auto_auto] sm:gap-4 sm:px-5",
                      isSel ? "bg-saffron/8" : "hover:bg-raised/40",
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <Monogram name={ipo.name} />
                      <div className="min-w-0">
                        <p className={clsx("truncate text-sm font-semibold", isSel ? "text-saffron" : "text-fg")}>
                          {ipo.name.trim()}
                        </p>
                        <div className="mt-0.5 flex items-center gap-1.5">
                          <span className="font-mono text-[10px] text-muted">{ipo.symbol}</span>
                          {ipo.is_sme && <Badge className="bg-blue-500/10 text-blue-500 text-[9px]">SME</Badge>}
                        </div>
                      </div>
                    </div>
                    <span className="nums hidden w-20 text-right text-xs text-muted sm:block">
                      {fmtDate(activeTab === "listed" ? ipo.listing_date : ipo.bidding_end_date) ?? "TBA"}
                    </span>
                    <span className="flex w-auto items-center justify-end gap-1.5 sm:w-24">
                      {activeTab === "listed" && ipo.listing_gains != null ? (
                        <span className={clsx("nums text-xs font-bold", signCls(ipo.listing_gains))}>{pct(ipo.listing_gains)}</span>
                      ) : (
                        <span className="nums text-xs text-fg">{priceBand(ipo)}</span>
                      )}
                      <ChevronRight className={clsx("h-3.5 w-3.5", isSel ? "text-saffron" : "text-muted/50")} />
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </Card>

        {/* Detail — desktop side panel */}
        <div className="sticky top-24 hidden lg:block">
          <Card className="max-h-[calc(100vh-8rem)] overflow-hidden">
            {selected ? (
              <DetailPanel ipo={selected} />
            ) : (
              <div className="flex flex-col items-center justify-center gap-3 p-14 text-center">
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-saffron/10 text-saffron">
                  <MousePointerClick className="h-6 w-6" />
                </span>
                <p className="text-sm font-medium text-fg">Select an issue to see the full story</p>
                <p className="max-w-[220px] text-xs leading-relaxed text-muted">
                  Price band, lot size, bidding schedule, listing performance and filings.
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Detail — mobile sheet */}
      {mobileOpen && selected && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={() => setMobileOpen(false)} aria-hidden />
          <div className="absolute inset-x-0 bottom-0 max-h-[88vh] overflow-hidden rounded-t-3xl border-t border-border bg-surface shadow-2xl">
            <DetailPanel ipo={selected} onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <p className="text-right font-mono text-[10px] uppercase tracking-[0.14em] text-muted/60">
        Source: SEBI filings via IndianAPI · refreshed hourly
      </p>
    </div>
  );
}
