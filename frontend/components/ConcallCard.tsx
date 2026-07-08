"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher } from "@/lib/api";
import {
  ChevronDown,
  ChevronUp,
  TrendingUp,
  TrendingDown,
  Mic2,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Newspaper,
  MessageSquare,
  Eye,
  BarChart3,
  Wallet,
  Target,
  FileText,
  Sparkles,
} from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

type Quarter = {
  label: string;
  period_end: string;
  revenue: string | null;
  gross_profit: string | null;
  operating_income: string | null;
  net_income: string | null;
  net_income_raw: number | null;
  ebitda: string | null;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
  net_margin_pct: number | null;
  revenue_yoy_pct: number | null;
  net_income_yoy_pct: number | null;
  op_income_yoy_pct: number | null;
  operating_cashflow: string | null;
  free_cashflow: string | null;
  total_debt: string | null;
  interest_expense: string | null;
  prev_revenue: string | null;
  prev_net_income: string | null;
  headline: string | null;
  summary: string | null;
  key_numbers: Record<string, string> | null;
  highlights: string[];
  concerns: string[];
  management_commentary: string | null;
  management_promises: string[];
  guidance_note: string | null;
  analyst_view: string | null;
  news_headlines: string[];
};

function YoY({ pct, label }: { pct: number | null; label?: string }) {
  if (pct == null) return null;
  const up = pct >= 0;
  return (
    <span className={clsx("nums inline-flex items-center gap-0.5 text-[11px] font-semibold", up ? "text-up" : "text-down")}>
      {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
      {up ? "+" : ""}{pct.toFixed(1)}%{label ? ` ${label} YoY` : " YoY"}
    </span>
  );
}

function StatBox({ label, value, sub }: { label: string; value: string | number | null; sub?: React.ReactNode }) {
  if (value == null) return null;
  return (
    <Card className="p-4 cursor-default select-none text-center transition-all duration-200 hover:-translate-y-0.5 hover:border-[rgba(21,128,61,0.22)] hover:shadow-[var(--shadow-md),var(--shadow-glow)]">
      <Label className="mb-1 block">{label}</Label>
      <p className="nums text-sm font-bold text-fg">{value}</p>
      {sub && <div className="mt-1">{sub}</div>}
    </Card>
  );
}

function MarginBar({ label, value, color }: { label: string; value: number | null; color: string }) {
  if (value == null) return null;
  const w = Math.min(Math.max(value, 0), 100);
  return (
    <div>
      <div className="flex justify-between text-[11px] mb-0.5">
        <span className="text-muted">{label}</span>
        <span className={clsx("nums font-semibold", color)}>{value}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-raised overflow-hidden">
        <div className={clsx("h-full rounded-full transition-all duration-500", color === "text-up" ? "bg-up" : color === "text-down" ? "bg-down" : "bg-saffron")} style={{ width: `${w}%` }} />
      </div>
    </div>
  );
}

function QuarterPanel({ q, defaultOpen, idx }: { q: Quarter; defaultOpen: boolean; idx: number }) {
  const [open, setOpen] = useState(defaultOpen);
  const [newsExpanded, setNewsExpanded] = useState(false);

  const isProfit = (q.net_income_raw ?? 0) >= 0;

  return (
    <div className={clsx(
      "overflow-hidden rounded-xl border transition-all duration-200",
      open ? "border-saffron/30 shadow-md" : "border-border hover:border-saffron/20"
    )}>
      {/* ── Header ── */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition hover:bg-raised/40"
      >
        <div className="flex items-center gap-3 min-w-0">
          <Badge className={clsx(
            "shrink-0 ring-1 font-bold text-xs",
            idx === 0 ? "bg-saffron text-white ring-saffron/40" : "bg-saffron/10 text-saffron ring-saffron/20"
          )}>
            {q.label}
          </Badge>
          {idx === 0 && (
            <Badge className="bg-up/10 text-up ring-1 ring-up/20 text-[10px] font-bold shrink-0">LATEST</Badge>
          )}
          <div className="min-w-0">
            {q.headline ? (
              <p className="truncate text-sm font-semibold text-fg">{q.headline}</p>
            ) : (
              <p className="text-sm text-muted italic">Summary unavailable</p>
            )}
            <p className="text-[10px] text-muted mt-0.5">{q.period_end}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-4">
          {q.revenue && (
            <div className="hidden sm:block text-right">
              <Label className="block">Revenue</Label>
              <p className="nums text-xs font-bold text-fg">{q.revenue}</p>
              {q.revenue_yoy_pct != null && <YoY pct={q.revenue_yoy_pct} />}
            </div>
          )}
          {q.net_income && (
            <div className="hidden md:block text-right">
              <Label className="block">Net P&amp;L</Label>
              <p className={clsx("nums text-xs font-bold", isProfit ? "text-up" : "text-down")}>
                {q.net_income}
              </p>
              {q.net_income_yoy_pct != null && <YoY pct={q.net_income_yoy_pct} />}
            </div>
          )}
          {q.total_debt && (
            <div className="hidden lg:block text-right">
              <Label className="block">Total Debt</Label>
              <p className="nums text-xs font-bold text-saffron">{q.total_debt}</p>
            </div>
          )}
          {open ? (
            <ChevronUp className="h-4 w-4 shrink-0 text-saffron" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted" />
          )}
        </div>
      </button>

      {open && (
        <div className="border-t border-border space-y-6 px-5 py-5 animate-fade-up">

          {/* ── Key Financials ── */}
          <div>
            <Label className="mb-3 flex items-center gap-1.5">
              <BarChart3 className="h-3 w-3" /> Key Financials
            </Label>

            {/* Top 3 highlighted cards */}
            <div className="grid grid-cols-1 gap-2 mb-3 sm:grid-cols-3">
              <div className="rounded-xl border border-up/20 bg-up/5 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-up mb-1">Revenue</p>
                <p className="nums text-sm font-bold text-fg">{q.revenue ?? "—"}</p>
                {q.revenue_yoy_pct != null && <div className="mt-1"><YoY pct={q.revenue_yoy_pct} label="YoY" /></div>}
                {q.prev_revenue && <p className="text-[10px] text-muted mt-0.5">Prev: {q.prev_revenue}</p>}
              </div>

              <div className={clsx("rounded-xl border p-3", isProfit ? "border-emerald-500/20 bg-emerald-500/5" : "border-down/20 bg-down/5")}>
                <p className={clsx("text-[10px] font-semibold uppercase tracking-wider mb-1", isProfit ? "text-emerald-400" : "text-down")}>Net Profit</p>
                <p className="nums text-sm font-bold text-fg">{q.net_income ?? "—"}</p>
                {q.net_income_yoy_pct != null && <div className="mt-1"><YoY pct={q.net_income_yoy_pct} label="YoY" /></div>}
                {q.net_margin_pct != null && <p className="text-[10px] text-muted mt-0.5">Margin: {q.net_margin_pct.toFixed(1)}%</p>}
                {q.prev_net_income && <p className="text-[10px] text-muted">Prev: {q.prev_net_income}</p>}
              </div>

              <div className="rounded-xl border border-saffron/20 bg-saffron/5 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-saffron mb-1">Total Debt</p>
                <p className="nums text-sm font-bold text-fg">{q.total_debt ?? "—"}</p>
                {q.interest_expense && <p className="text-[10px] text-muted mt-0.5">Interest exp: {q.interest_expense}</p>}
              </div>
            </div>

            {/* Secondary metrics grid — only shows rows with actual data */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatBox label="EBITDA"       value={q.ebitda} />
              <StatBox label="Gross Profit" value={q.gross_profit} />
              <StatBox label="Operating CF" value={q.operating_cashflow} />
              <StatBox label="Free CF"      value={q.free_cashflow} />
            </div>
          </div>

          {/* ── Margin bars ── */}
          {(q.gross_margin_pct != null || q.operating_margin_pct != null || q.net_margin_pct != null) && (
            <div>
              <Label className="mb-3 flex items-center gap-1.5">
                <Wallet className="h-3 w-3" /> Margins
              </Label>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <MarginBar label="Gross Margin" value={q.gross_margin_pct} color="text-up" />
                <MarginBar label="EBIT Margin" value={q.operating_margin_pct} color="text-saffron" />
                <MarginBar label="PAT Margin" value={q.net_margin_pct} color={isProfit ? "text-up" : "text-down"} />
              </div>
            </div>
          )}

          {/* ── YoY summary row ── */}
          {(q.revenue_yoy_pct != null || q.net_income_yoy_pct != null || q.op_income_yoy_pct != null) && (
            <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-lg bg-raised/50 border border-border px-4 py-3 text-sm text-muted">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted shrink-0 self-center">YoY Change</span>
              {q.revenue_yoy_pct != null && (
                <span className="flex items-center gap-1.5">Revenue <YoY pct={q.revenue_yoy_pct} /></span>
              )}
              {q.op_income_yoy_pct != null && (
                <span className="flex items-center gap-1.5">EBIT <YoY pct={q.op_income_yoy_pct} /></span>
              )}
              {q.net_income_yoy_pct != null && (
                <span className="flex items-center gap-1.5">PAT <YoY pct={q.net_income_yoy_pct} /></span>
              )}
            </div>
          )}

          {/* ── AI Narrative Summary ── */}
          {q.summary && (
            <div className="rounded-xl bg-raised/60 border border-border p-4 space-y-2">
              <Label className="flex items-center gap-1.5">
                <Mic2 className="h-3.5 w-3.5 text-saffron" /> AI Concall Summary
              </Label>
              <p className="text-sm leading-relaxed text-fg/90">{q.summary}</p>
            </div>
          )}

          {/* ── Management Commentary ── */}
          {q.management_commentary && (
            <div className="rounded-xl bg-raised/40 border border-border p-4">
              <Label className="mb-2 flex items-center gap-1.5">
                <MessageSquare className="h-3.5 w-3.5 text-saffron" /> Management Commentary
              </Label>
              <p className="text-sm leading-relaxed text-fg/80 italic">&ldquo;{q.management_commentary}&rdquo;</p>
            </div>
          )}

          {/* ── Management Promises ── */}
          {q.management_promises?.length > 0 && (
            <div className="rounded-xl border border-amber-400/25 bg-amber-400/5 p-4">
              <Label className="mb-3 flex items-center gap-1.5 text-saffron">
                <Target className="h-3.5 w-3.5" /> Management Commitments &amp; Promises
              </Label>
              <ul className="space-y-2">
                {q.management_promises.map((promise, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-saffron/70" />
                    <p className="text-sm text-fg/85">{promise}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ── Highlights & Concerns ── */}
          <div className="grid gap-4 sm:grid-cols-2">
            {q.highlights?.length > 0 && (
              <div>
                <Label className="mb-3 flex items-center gap-1.5 text-up">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Highlights
                </Label>
                <ul className="space-y-2">
                  {q.highlights.map((h, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-sm text-fg/85">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-up/70" />
                      {h}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {q.concerns?.length > 0 && (
              <div>
                <Label className="mb-3 flex items-center gap-1.5 text-down">
                  <AlertCircle className="h-3.5 w-3.5" /> Concerns
                </Label>
                <ul className="space-y-2">
                  {q.concerns.map((c, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-sm text-fg/85">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-down/70" />
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* ── Analyst View ── */}
          {q.analyst_view && (
            <div className="flex items-start gap-2 rounded-lg bg-raised/50 border border-border px-4 py-3">
              <Eye className="h-4 w-4 shrink-0 mt-0.5 text-muted" />
              <p className="text-sm text-fg/80">
                <span className="font-semibold text-muted">Analyst view: </span>{q.analyst_view}
              </p>
            </div>
          )}

          {/* ── Guidance ── */}
          {q.guidance_note && (
            <div className="flex items-start gap-2.5 rounded-xl bg-saffron/5 border border-saffron/25 px-4 py-3.5">
              <ArrowRight className="h-4 w-4 shrink-0 mt-0.5 text-saffron" />
              <p className="text-sm text-fg/85">{q.guidance_note}</p>
            </div>
          )}

          {/* ── Real news headlines ── */}
          {q.news_headlines?.length > 0 && (
            <div>
              <button
                onClick={() => setNewsExpanded((e) => !e)}
                className="text-[10px] font-normal uppercase tracking-[0.1px] text-muted mb-2 flex items-center gap-1.5 hover:text-fg transition-colors"
              >
                <Newspaper className="h-3.5 w-3.5" />
                Source news ({q.news_headlines.length})
                {newsExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>
              {newsExpanded && (
                <ul className="space-y-1.5 border border-border rounded-lg p-3 bg-raised/30 animate-fade-in">
                  {q.news_headlines.map((h, i) => (
                    <li key={i} className="text-xs text-muted flex items-start gap-2">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-border" />
                      {h}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-3">
      <div className="skeleton h-5 w-48 rounded mb-4" />
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="skeleton h-16 w-full rounded-xl" style={{ opacity: 1 - i * 0.15 }} />
      ))}
    </div>
  );
}

export function ConcallCard({ ticker }: { ticker: string }) {
  const { data, error, isLoading } = useSWR(
    `/api/stocks/${ticker}/concall-summary`,
    fetcher,
    { revalidateOnFocus: false }
  );

  return (
    <section className="space-y-4">
      {/* ── Section header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-saffron/10 ring-1 ring-saffron/20">
            <Mic2 className="h-4 w-4 text-saffron" />
          </div>
          <div>
            <h2 className="section-title">Quarterly Concall Analysis</h2>
            <p className="text-[11px] text-muted">AI-generated summaries of last 4 earnings calls with real news context</p>
          </div>
        </div>
        {data?.company && (
          <span className="hidden sm:block text-sm font-semibold text-fg/60">{data.company}</span>
        )}
      </div>

      <Card className="p-5">
        {isLoading && <Skeleton />}

        {error && (
          <div className="rounded-xl border border-border bg-raised/40 px-5 py-6 text-center">
            <Mic2 className="mx-auto mb-3 h-8 w-8 text-muted/40" />
            <p className="text-sm font-medium text-muted">Quarterly data unavailable</p>
            <p className="mt-1 text-xs text-muted/60">Yahoo Finance may not carry financials for this stock.</p>
          </div>
        )}

        {data?.quarters?.length > 0 && (
          <div className="space-y-3">
            {/* Sector tag */}
            {data.sector && (
              <div className="flex items-center gap-2 mb-2">
                <Badge className="bg-raised text-muted ring-1 ring-border text-[10px]">{data.sector}</Badge>
                <span className="text-[10px] text-muted">· AI context: financial data + earnings news headlines</span>
              </div>
            )}

            {(data.quarters as Quarter[]).map((q, i) => (
              <QuarterPanel key={q.label} q={q} defaultOpen={i === 0} idx={i} />
            ))}

            <p className="pt-1 text-[10px] text-muted">
              Financials via Yahoo Finance · AI synthesis by AEGIS (Groq/Llama-3.3) · News via Google News RSS · Not investment advice
            </p>

            {/* ── Document Analyzer CTA ── */}
            <div className="mt-2 flex flex-col items-stretch gap-4 rounded-2xl border border-saffron/20 bg-gradient-to-r from-saffron/8 via-saffron/5 to-transparent px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-saffron/15 ring-1 ring-saffron/25">
                  <FileText className="h-5 w-5 text-saffron" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-fg">Have the actual concall transcript or annual report?</p>
                  <p className="text-xs text-muted">Upload a PDF or paste text — get deep AI analysis, management promises &amp; Q&amp;A</p>
                </div>
              </div>
              <Link
                href="/concall/document"
                className="flex w-full shrink-0 grow-0 items-center justify-center gap-1.5 rounded-xl bg-saffron px-4 py-2 text-sm font-semibold text-white shadow-md shadow-saffron/20 transition-all hover:bg-amber-400 hover:shadow-saffron/30 sm:w-auto"
              >
                <Sparkles className="h-4 w-4" /> Analyze Document
              </Link>
            </div>
          </div>
        )}
      </Card>
    </section>
  );
}
