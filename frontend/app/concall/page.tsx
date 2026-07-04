"use client";

import { useCallback, useRef, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import {
  Mic2, FileText, ExternalLink, ChevronDown, ChevronUp,
  TrendingUp, TrendingDown, AlertTriangle, CheckCircle2,
  Lightbulb, Users, BarChart3, Calendar, Newspaper,
  Upload, ClipboardPaste, Sparkles, Send, X, RefreshCw,
  Target, Quote, PieChart, DollarSign, MessageSquare,
  Hammer, Search, Building2,
} from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";

// ─── Quarter types ────────────────────────────────────────────────────────────
type Quarter = {
  label: string; revenue?: number; net_income?: number;
  gross_profit?: number; ebit?: number;
  prev_revenue?: number; prev_net_income?: number;
  headline?: string; summary?: string;
  key_numbers?: string[]; highlights?: string[]; concerns?: string[];
  management_commentary?: string; guidance_note?: string;
  analyst_view?: string; news_headlines?: string[];
};

// ─── Document analysis types ──────────────────────────────────────────────────
type Promise_ = { commitment: string; timeline: string; metric: string };
type MarginAnalysis = { gross_margin: string; ebitda_margin: string; pat_margin: string; margin_commentary: string };
type Analysis = {
  executive_summary: string; document_type: string;
  company_name: string | null; period: string | null;
  key_themes: string[]; financial_highlights: string[];
  margin_analysis: MarginAnalysis | null; revenue_breakdown: string[];
  key_management_quotes: string[]; management_promises: Promise_[];
  risks_and_concerns: string[]; strategic_initiatives: string[];
  guidance: string | null; capex_guidance: string | null;
  sentiment: string; sentiment_reason: string; suggested_questions: string[];
};
type ChatMsg = { role: "user" | "ai"; text: string; confidence?: string; source?: string };

// ─── Helpers ──────────────────────────────────────────────────────────────────
function inrCr(v?: number) {
  if (v == null) return "—";
  const cr = v / 1e7;
  return `₹${cr >= 1000 ? `${(cr / 1000).toFixed(1)}K` : cr.toFixed(0)} Cr`;
}
function pctChg(curr?: number, prev?: number) {
  if (!curr || !prev) return null;
  return ((curr - prev) / Math.abs(prev)) * 100;
}
function pctFmt(v: number | null) {
  if (v == null) return null;
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

// ─── Styling maps ─────────────────────────────────────────────────────────────
const SENTIMENT_STYLE: Record<string, string> = {
  "Positive":              "text-emerald-400 bg-emerald-400/10 ring-emerald-400/30",
  "Cautiously optimistic": "text-up bg-up/10 ring-up/30",
  "Neutral":               "text-saffron bg-saffron/10 ring-saffron/30",
  "Cautious":              "text-orange-400 bg-orange-400/10 ring-orange-400/30",
  "Negative":              "text-down bg-down/10 ring-down/30",
};
const CONF_STYLE: Record<string, string> = { High: "text-up", Medium: "text-saffron", Low: "text-muted" };
const THEME_COLORS = [
  "bg-up/8 text-up ring-up/20", "bg-saffron/8 text-saffron ring-saffron/20",
  "bg-accent/8 text-accent ring-accent/20", "bg-down/8 text-down ring-down/20",
  "bg-muted/10 text-fg ring-border",
];

// ─── Section card ─────────────────────────────────────────────────────────────
function Section({ icon: Icon, title, accent, children, collapsible = true }: {
  icon: React.FC<{ className?: string }>; title: string;
  accent: string; children: React.ReactNode; collapsible?: boolean;
}) {
  const [open, setOpen] = useState(true);
  const borderCls = accent.includes("up") ? "border-up/15" : accent.includes("saffron") ? "border-saffron/15" : accent.includes("down") ? "border-down/15" : accent.includes("accent") ? "border-accent/15" : "border-border";
  const iconBg = accent.includes("up") ? "bg-up/10" : accent.includes("saffron") ? "bg-saffron/10" : accent.includes("down") ? "bg-down/10" : accent.includes("accent") ? "bg-accent/10" : "bg-raised";
  return (
    <div className={`rounded-2xl border bg-surface overflow-hidden ${borderCls}`}>
      <button className="flex w-full items-center justify-between px-5 py-4"
        onClick={() => collapsible && setOpen(!open)}
        style={{ cursor: collapsible ? "pointer" : "default" }}
      >
        <div className="flex items-center gap-2.5">
          <div className={`flex h-8 w-8 items-center justify-center rounded-xl ${iconBg}`}>
            <Icon className={`h-4 w-4 ${accent}`} />
          </div>
          <span className={`font-semibold text-sm ${accent}`}>{title}</span>
        </div>
        {collapsible && (open ? <ChevronUp className="h-4 w-4 text-muted" /> : <ChevronDown className="h-4 w-4 text-muted" />)}
      </button>
      {open && <div className="px-5 pb-5 pt-0 border-t border-border/50">{children}</div>}
    </div>
  );
}

// ─── QuarterCard ──────────────────────────────────────────────────────────────
function QuarterCard({ q, company, isFirst, symbol }: { q: Quarter; company: string; isFirst: boolean; symbol: string }) {
  const [open, setOpen] = useState(isFirst);
  const [newsOpen, setNewsOpen] = useState(false);
  const revChg = pctChg(q.revenue, q.prev_revenue);
  const niChg = pctChg(q.net_income, q.prev_net_income);
  const niPositive = (q.net_income ?? 0) >= 0;
  const overallType: "positive" | "negative" | "warning" =
    niPositive && (revChg ?? 0) >= 0 ? "positive"
    : !niPositive || (niChg ?? 0) < -20 ? "negative" : "warning";
  const bare = symbol.replace(/\.(NS|BO)$/, "");

  return (
    <div className={clsx("card overflow-hidden border transition-all duration-200", open ? "border-saffron/30" : "border-border hover:border-saffron/20")}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-saffron/10 ring-1 ring-saffron/20">
            <Mic2 className="h-4 w-4 text-saffron" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-fg">{q.label}</span>
              {isFirst && <span className="rounded-full bg-saffron px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Latest</span>}
              <span className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider",
                overallType === "positive" ? "bg-up/10 text-up" : overallType === "negative" ? "bg-down/10 text-down" : "bg-yellow-500/10 text-yellow-500")}>
                {overallType === "positive" ? <TrendingUp className="h-2.5 w-2.5" /> : overallType === "negative" ? <TrendingDown className="h-2.5 w-2.5" /> : <AlertTriangle className="h-2.5 w-2.5" />}
                {overallType}
              </span>
            </div>
            {q.headline && <p className="mt-0.5 truncate text-xs text-muted">{q.headline}</p>}
          </div>
        </div>
        <div className="hidden sm:flex items-center gap-4 shrink-0">
          <div className="text-right">
            <p className="text-[10px] text-muted">Revenue</p>
            <p className="nums text-sm font-bold">{inrCr(q.revenue)}</p>
            {revChg != null && <p className={clsx("text-[10px] font-semibold", revChg >= 0 ? "text-up" : "text-down")}>{pctFmt(revChg)} YoY</p>}
          </div>
          <div className="text-right">
            <p className="text-[10px] text-muted">Net {niPositive ? "Profit" : "Loss"}</p>
            <p className={clsx("nums text-sm font-bold", niPositive ? "text-up" : "text-down")}>{inrCr(Math.abs(q.net_income ?? 0))}</p>
            {niChg != null && <p className={clsx("text-[10px] font-semibold", niChg >= 0 ? "text-up" : "text-down")}>{pctFmt(niChg)} YoY</p>}
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-muted" /> : <ChevronDown className="h-4 w-4 text-muted" />}
        </div>
        <div className="sm:hidden">{open ? <ChevronUp className="h-4 w-4 text-muted" /> : <ChevronDown className="h-4 w-4 text-muted" />}</div>
      </button>

      {open && (
        <div className="border-t border-border">
          <div className="flex flex-wrap items-center gap-2 bg-saffron/5 px-5 py-3 border-b border-saffron/10">
            <FileText className="h-3.5 w-3.5 text-saffron shrink-0" />
            <span className="text-xs font-medium text-saffron">Official Documents:</span>
            {[
              { href: `https://www.screener.in/company/${bare}/concalls/`, label: "Screener.in" },
              { href: `https://www.google.com/search?q=${encodeURIComponent(`${company} ${q.label} concall transcript site:bseindia.com OR site:nseindia.com`)}`, label: "BSE/NSE Search" },
            ].map(({ href, label }) => (
              <a key={label} href={href} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 rounded-md bg-surface px-2.5 py-1 text-xs font-medium text-fg ring-1 ring-border hover:ring-saffron/40 hover:text-saffron transition-all">
                <ExternalLink className="h-3 w-3" /> {label}
              </a>
            ))}
          </div>
          <div className="space-y-5 p-5">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: "Revenue", value: inrCr(q.revenue), chg: revChg },
                { label: "Net " + (niPositive ? "Profit" : "Loss"), value: inrCr(Math.abs(q.net_income ?? 0)), chg: niChg, flip: !niPositive },
                { label: "Gross Profit", value: inrCr(q.gross_profit) },
                { label: "EBIT", value: inrCr(q.ebit) },
              ].map((m) => (
                <div key={m.label} className="rounded-xl bg-raised/60 p-3 ring-1 ring-border/50">
                  <p className="text-[10px] text-muted mb-1">{m.label}</p>
                  <p className={clsx("nums text-base font-bold", m.flip ? "text-down" : "text-fg")}>{m.value}</p>
                  {m.chg != null && <p className={clsx("text-[10px] font-semibold mt-0.5", m.chg >= 0 ? "text-up" : "text-down")}>{pctFmt(m.chg)} YoY</p>}
                </div>
              ))}
            </div>
            {q.key_numbers?.length ? (
              <div>
                <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted"><BarChart3 className="h-3.5 w-3.5 text-saffron" /> Key Numbers</p>
                <div className="flex flex-wrap gap-2">
                  {q.key_numbers.map((kn, i) => <span key={i} className="rounded-lg bg-raised px-3 py-1.5 text-xs font-medium text-fg ring-1 ring-border">{kn}</span>)}
                </div>
              </div>
            ) : null}
            {q.summary && (
              <div>
                <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted"><Lightbulb className="h-3.5 w-3.5 text-saffron" /> AI Summary</p>
                <p className="text-sm leading-relaxed text-fg/90">{q.summary}</p>
              </div>
            )}
            {((q.highlights?.length ?? 0) > 0 || (q.concerns?.length ?? 0) > 0) && (
              <div className="grid gap-4 sm:grid-cols-2">
                {q.highlights?.length ? (
                  <div>
                    <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-up"><CheckCircle2 className="h-3.5 w-3.5" /> Highlights</p>
                    <ul className="space-y-1.5">{q.highlights.map((h, i) => <li key={i} className="flex items-start gap-2 text-xs text-fg/80"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-up" />{h}</li>)}</ul>
                  </div>
                ) : null}
                {q.concerns?.length ? (
                  <div>
                    <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-down"><AlertTriangle className="h-3.5 w-3.5" /> Concerns</p>
                    <ul className="space-y-1.5">{q.concerns.map((c, i) => <li key={i} className="flex items-start gap-2 text-xs text-fg/80"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-down" />{c}</li>)}</ul>
                  </div>
                ) : null}
              </div>
            )}
            {q.management_commentary && (
              <div className="rounded-xl bg-raised/40 p-4 ring-1 ring-border/50">
                <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted"><Users className="h-3.5 w-3.5 text-saffron" /> Management Commentary</p>
                <p className="text-sm italic leading-relaxed text-fg/80">&ldquo;{q.management_commentary}&rdquo;</p>
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              {q.guidance_note && <div className="rounded-xl bg-saffron/5 p-4 ring-1 ring-saffron/15"><p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-saffron">Guidance</p><p className="text-xs leading-relaxed text-fg/80">{q.guidance_note}</p></div>}
              {q.analyst_view && <div className="rounded-xl bg-raised/40 p-4 ring-1 ring-border/50"><p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-muted">Analyst View</p><p className="text-xs leading-relaxed text-fg/80">{q.analyst_view}</p></div>}
            </div>
            {q.news_headlines?.length ? (
              <div>
                <button onClick={() => setNewsOpen(!newsOpen)} className="flex items-center gap-2 text-xs font-semibold text-muted hover:text-fg transition-colors">
                  <Newspaper className="h-3.5 w-3.5" />{newsOpen ? "Hide" : "Show"} news ({q.news_headlines.length}){newsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </button>
                {newsOpen && <ul className="mt-2 space-y-1.5 border-l-2 border-border pl-4">{q.news_headlines.map((h, i) => <li key={i} className="text-xs text-muted leading-snug">{h}</li>)}</ul>}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Upload zone ──────────────────────────────────────────────────────────────
function UploadZone({ onFile }: { onFile: (f: File) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const handleFile = (f: File) => { if (f.type !== "application/pdf") { alert("Please upload a PDF."); return; } onFile(f); };
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
      onClick={() => fileRef.current?.click()}
      className={clsx("group relative flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed px-8 py-12 cursor-pointer transition-all duration-200",
        dragging ? "border-saffron bg-saffron/8 scale-[1.01]" : "border-border hover:border-saffron/50 hover:bg-saffron/3")}
    >
      <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
      <div className={clsx("flex h-14 w-14 items-center justify-center rounded-2xl ring-2 transition-all", dragging ? "bg-saffron/20 ring-saffron/40" : "bg-raised ring-border group-hover:ring-saffron/30")}>
        <Upload className={clsx("h-6 w-6 transition-colors", dragging ? "text-saffron" : "text-muted group-hover:text-saffron")} />
      </div>
      <div className="text-center">
        <p className="font-semibold text-fg">Drop your PDF here</p>
        <p className="mt-1 text-sm text-muted">Concall transcript, annual report, investor presentation</p>
      </div>
      <span className="rounded-lg bg-saffron/10 px-4 py-1.5 text-sm font-medium text-saffron ring-1 ring-saffron/20">Browse file</span>
    </div>
  );
}

// ─── Analysis panel ───────────────────────────────────────────────────────────
function AnalysisPanel({ analysis, company, chat, chatLoading, chatInput, setChatInput, onSend, onReset, onQuestion }: {
  analysis: Analysis; company: string;
  chat: ChatMsg[]; chatLoading: boolean;
  chatInput: string; setChatInput: (v: string) => void;
  onSend: () => void; onReset: () => void;
  onQuestion: (q: string) => void;
}) {
  const sentStyle = SENTIMENT_STYLE[analysis.sentiment] ?? "text-muted bg-raised ring-border";
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="space-y-4 animate-fade-up">
      {/* Header card */}
      <div className="rounded-2xl border border-border bg-surface overflow-hidden">
        <div className="h-1 w-full bg-gradient-to-r from-saffron via-amber-400 to-up" />
        <div className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-lg bg-raised px-2.5 py-1 text-xs font-medium text-muted ring-1 ring-border">{analysis.document_type}</span>
                {analysis.period && <span className="rounded-lg bg-saffron/10 px-2.5 py-1 text-xs font-semibold text-saffron ring-1 ring-saffron/20">{analysis.period}</span>}
                <span className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold ring-1 ${sentStyle}`}>{analysis.sentiment}</span>
              </div>
              <h2 className="mt-3 text-xl font-bold text-fg">{analysis.company_name || company || "Document Analysis"}</h2>
              <p className="mt-1 text-sm text-muted">{analysis.sentiment_reason}</p>
            </div>
            <button onClick={onReset} className="flex shrink-0 items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs text-muted hover:text-fg hover:border-saffron/30 transition-all">
              <RefreshCw className="h-3.5 w-3.5" /> New
            </button>
          </div>
          {/* Executive summary */}
          <div className="mt-4 rounded-xl bg-raised/60 border border-border p-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-saffron"><Sparkles className="h-3.5 w-3.5" /> Executive Summary</p>
            <p className="text-sm leading-relaxed text-fg/90">{analysis.executive_summary}</p>
          </div>
          {/* Guidance + Capex */}
          {(analysis.guidance || analysis.capex_guidance) && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {analysis.guidance && (
                <div className="flex items-start gap-3 rounded-xl border border-up/20 bg-up/5 px-4 py-3">
                  <TrendingUp className="mt-0.5 h-4 w-4 shrink-0 text-up" />
                  <div><p className="text-xs font-semibold uppercase tracking-wider text-up mb-0.5">Forward Guidance</p><p className="text-sm text-fg/85">{analysis.guidance}</p></div>
                </div>
              )}
              {analysis.capex_guidance && (
                <div className="flex items-start gap-3 rounded-xl border border-accent/20 bg-accent/5 px-4 py-3">
                  <Hammer className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  <div><p className="text-xs font-semibold uppercase tracking-wider text-accent mb-0.5">Capex Plan</p><p className="text-sm text-fg/85">{analysis.capex_guidance}</p></div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Key themes */}
      {analysis.key_themes?.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface p-5">
          <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted"><BarChart3 className="h-3.5 w-3.5" /> Key Themes</p>
          <div className="flex flex-wrap gap-2">
            {analysis.key_themes.map((t, i) => (
              <span key={i} className={`rounded-xl px-3 py-1.5 text-sm font-medium ring-1 ${THEME_COLORS[i % THEME_COLORS.length]}`}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* Financial highlights + Margin analysis */}
      <div className="grid gap-4 lg:grid-cols-2">
        {analysis.financial_highlights?.length > 0 && (
          <Section icon={TrendingUp} title="Financial Highlights" accent="text-up">
            <ul className="mt-3 space-y-3">
              {analysis.financial_highlights.map((h, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-up/10 text-[10px] font-bold text-up">{i + 1}</span>
                  <span className="text-sm text-fg/85 leading-relaxed">{h}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}
        {analysis.margin_analysis && (
          <Section icon={PieChart} title="Margin Analysis" accent="text-saffron">
            <div className="mt-3 space-y-3">
              {[
                { label: "Gross Margin", val: analysis.margin_analysis.gross_margin },
                { label: "EBITDA Margin", val: analysis.margin_analysis.ebitda_margin },
                { label: "PAT Margin", val: analysis.margin_analysis.pat_margin },
              ].map(({ label, val }) => val && val !== "N/A" && (
                <div key={label} className="flex items-center justify-between rounded-lg bg-raised/60 px-3.5 py-2.5">
                  <span className="text-xs font-medium text-muted">{label}</span>
                  <span className="text-sm font-semibold text-fg">{val}</span>
                </div>
              ))}
              {analysis.margin_analysis.margin_commentary && (
                <p className="mt-1 text-xs text-muted leading-relaxed border-t border-border pt-3">{analysis.margin_analysis.margin_commentary}</p>
              )}
            </div>
          </Section>
        )}
      </div>

      {/* Revenue breakdown */}
      {analysis.revenue_breakdown?.length > 0 && analysis.revenue_breakdown[0] !== "N/A" && (
        <Section icon={DollarSign} title="Revenue Breakdown" accent="text-accent">
          <ul className="mt-3 space-y-2">
            {analysis.revenue_breakdown.map((r, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-fg/85">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent/60" />{r}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Management commitments */}
      {analysis.management_promises?.length > 0 && (
        <Section icon={Target} title="Management Commitments & Promises" accent="text-saffron">
          <div className="mt-3 space-y-3">
            {analysis.management_promises.map((p, i) => (
              <div key={i} className="rounded-xl border border-saffron/20 bg-saffron/5 p-4">
                <p className="text-sm font-medium text-fg leading-snug">{p.commitment}</p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  {p.timeline && <span className="flex items-center gap-1 text-xs text-saffron font-medium"><span className="h-1.5 w-1.5 rounded-full bg-saffron" /> By: {p.timeline}</span>}
                  {p.metric && <span className="flex items-center gap-1 text-xs text-muted"><span className="h-1.5 w-1.5 rounded-full bg-muted" /> Target: {p.metric}</span>}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Key management quotes */}
      {analysis.key_management_quotes?.length > 0 && (
        <Section icon={Quote} title="Key Management Quotes" accent="text-accent">
          <div className="mt-3 space-y-3">
            {analysis.key_management_quotes.map((q, i) => (
              <blockquote key={i} className="flex items-start gap-3 rounded-xl border-l-4 border-accent/40 bg-accent/5 pl-4 pr-4 py-3">
                <p className="text-sm text-fg/85 italic leading-relaxed">"{q}"</p>
              </blockquote>
            ))}
          </div>
        </Section>
      )}

      {/* Risks + Strategic initiatives */}
      <div className="grid gap-4 lg:grid-cols-2">
        {analysis.risks_and_concerns?.length > 0 && (
          <Section icon={TrendingDown} title="Risks & Concerns" accent="text-down">
            <ul className="mt-3 space-y-2.5">
              {analysis.risks_and_concerns.map((r, i) => (
                <li key={i} className="flex items-start gap-2.5">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-down/70" />
                  <span className="text-sm text-fg/85 leading-relaxed">{r}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}
        {analysis.strategic_initiatives?.length > 0 && (
          <Section icon={Lightbulb} title="Strategic Initiatives" accent="text-accent">
            <ul className="mt-3 space-y-2.5">
              {analysis.strategic_initiatives.map((s, i) => (
                <li key={i} className="flex items-start gap-2.5">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent/70" />
                  <span className="text-sm text-fg/85 leading-relaxed">{s}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      {/* Suggested questions */}
      {analysis.suggested_questions?.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface p-5">
          <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted"><MessageSquare className="h-3.5 w-3.5" /> Suggested Follow-up Questions</p>
          <div className="flex flex-wrap gap-2">
            {analysis.suggested_questions.map((q, i) => (
              <button key={i} onClick={() => { onQuestion(q); inputRef.current?.focus(); }}
                className="rounded-xl border border-saffron/20 bg-saffron/5 px-3 py-2 text-left text-sm text-fg/80 hover:border-saffron/40 hover:bg-saffron/10 hover:text-saffron transition-all">
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat */}
      <div className="rounded-2xl border border-border bg-surface p-5 space-y-4">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted"><MessageSquare className="h-3.5 w-3.5" /> Ask About This Document</p>
        {chat.length > 0 && (
          <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
            {chat.map((msg, i) => (
              <div key={i} className={clsx("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
                {msg.role === "ai" && (
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-saffron/15 ring-1 ring-saffron/25">
                    <Sparkles className="h-3.5 w-3.5 text-saffron" />
                  </div>
                )}
                <div className={clsx("max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                  msg.role === "user" ? "bg-saffron/15 text-fg/90 rounded-tr-sm" : "bg-raised border border-border text-fg/90 rounded-tl-sm")}>
                  {msg.text}
                  {msg.role === "ai" && msg.confidence && <p className={`mt-1.5 text-[11px] font-medium ${CONF_STYLE[msg.confidence] ?? "text-muted"}`}>Confidence: {msg.confidence}</p>}
                  {msg.role === "ai" && msg.source && <p className="mt-1.5 text-[11px] text-muted italic border-l-2 border-saffron/30 pl-2">{msg.source}</p>}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-saffron/15 ring-1 ring-saffron/25">
                  <Sparkles className="h-3.5 w-3.5 text-saffron animate-pulse" />
                </div>
                <div className="rounded-2xl rounded-tl-sm bg-raised border border-border px-4 py-3">
                  <div className="flex gap-1.5">{[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />)}</div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}
        <div className="flex gap-2 border-t border-border pt-4">
          <input ref={inputRef} value={chatInput} onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && chatInput.trim()) onSend(); }}
            placeholder="Ask anything about this document…" disabled={chatLoading}
            className="flex-1 rounded-xl border border-border bg-raised/60 px-4 py-2.5 text-sm placeholder:text-muted focus:border-saffron/50 focus:outline-none focus:ring-1 focus:ring-saffron/30 disabled:opacity-50 transition-all"
          />
          <button onClick={onSend} disabled={!chatInput.trim() || chatLoading}
            className="flex items-center gap-1.5 rounded-xl bg-saffron px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Upload section (shown when no concall data) ──────────────────────────────
function UploadSection({ symbol, company: initialCompany }: { symbol?: string; company?: string }) {
  const [tab, setTab] = useState<"pdf" | "paste">("pdf");
  const [docText, setDocText] = useState("");
  const [company, setCompany] = useState(initialCompany ?? "");
  const [filename, setFilename] = useState("");
  const [mode, setMode] = useState<"idle" | "loading-pdf" | "loading-analysis" | "results">("idle");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [aiModel, setAiModel] = useState<"groq" | "minimax" | "deepseek">("deepseek");
  const runAnalysisRef = useRef<((text: string, co?: string) => Promise<void>) | null>(null);

  const runAnalysis = useCallback(async (text: string, co?: string) => {
    setMode("loading-analysis");
    setError("");
    try {
      const res = await fetch("/api/documents/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, company: co ?? company, model: aiModel }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: "Analysis failed." })); throw new Error(e.detail); }
      const data = await res.json();
      setAnalysis(data);
      if (data.company_name) setCompany(data.company_name);
      setChat([]);
      setMode("results");
    } catch (e: any) { setError(e.message || "AI analysis failed."); setMode("idle"); }
  }, [company, aiModel]);
  runAnalysisRef.current = runAnalysis;

  const handleFile = useCallback(async (file: File) => {
    setMode("loading-pdf");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/documents/upload-pdf", { method: "POST", body: form });
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: "PDF extraction failed." })); throw new Error(e.detail); }
      const data = await res.json();
      setDocText(data.text);
      setFilename(file.name);
      await runAnalysisRef.current!(data.text);
    } catch (e: any) { setError(e.message || "Failed to extract PDF."); setMode("idle"); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const sendChat = useCallback(async () => {
    if (!chatInput.trim() || chatLoading) return;
    const question = chatInput.trim();
    setChatInput("");
    setChat((prev) => [...prev, { role: "user", text: question }]);
    setChatLoading(true);
    try {
      const res = await fetch("/api/documents/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: docText, question, company }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Q&A failed.");
      setChat((prev) => [...prev, { role: "ai", text: data.answer, confidence: data.confidence, source: data.source_context }]);
    } catch (e: any) { setChat((prev) => [...prev, { role: "ai", text: `Error: ${e.message}` }]); }
    finally { setChatLoading(false); }
  }, [chatInput, chatLoading, docText, company]);

  const reset = () => { setMode("idle"); setDocText(""); setAnalysis(null); setChat([]); setError(""); setFilename(""); };

  if (mode === "loading-pdf" || mode === "loading-analysis") {
    return (
      <Card className="p-8 text-center space-y-5">
        <div className="mx-auto h-12 w-12 rounded-2xl bg-saffron/10 flex items-center justify-center">
          <Sparkles className="h-6 w-6 text-saffron animate-pulse" />
        </div>
        <div className="space-y-3">
          {[
            { label: mode === "loading-pdf" ? "Extracting text from PDF…" : "Text extracted ✓", done: mode !== "loading-pdf" },
            { label: mode === "loading-analysis" ? `Analyzing with ${aiModel === "deepseek" ? "Qwen3-32B (reasoning)" : aiModel === "minimax" ? "Llama 4 Scout" : "Llama 3.3 70B"} — parsing financials, margins, promises…` : "Pending", done: false },
          ].map((step, i) => (
            <div key={i} className="flex items-center gap-3 text-left">
              <div className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${step.done ? "bg-up/20" : "bg-saffron/20"}`}>
                {step.done ? <CheckCircle2 className="h-3 w-3 text-up" /> : <span className="h-2 w-2 rounded-full bg-saffron animate-pulse" />}
              </div>
              <span className={`text-sm ${step.done ? "text-muted line-through" : "text-fg"}`}>{step.label}</span>
            </div>
          ))}
        </div>
        <div className="h-1 w-full overflow-hidden rounded-full bg-raised">
          <div className="h-full rounded-full bg-gradient-to-r from-saffron to-up animate-pulse" style={{ width: mode === "loading-pdf" ? "30%" : "75%" }} />
        </div>
        <p className="text-xs text-muted">{aiModel === "deepseek" ? "~4s" : aiModel === "minimax" ? "~3s" : "~2s"} — analysing first ~4 pages of document</p>
      </Card>
    );
  }

  if (mode === "results" && analysis) {
    return (
      <div>
        {filename && (
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-border bg-raised/40 px-4 py-2.5">
            <FileText className="h-4 w-4 text-saffron shrink-0" />
            <span className="text-sm font-medium text-fg truncate max-w-xs">{filename}</span>
            <span className="text-xs text-muted ml-auto shrink-0">{(docText.length / 1000).toFixed(0)}K chars</span>
          </div>
        )}
        <AnalysisPanel analysis={analysis} company={company} chat={chat} chatLoading={chatLoading}
          chatInput={chatInput} setChatInput={setChatInput} onSend={sendChat} onReset={reset}
          onQuestion={(q) => setChatInput(q)} />
      </div>
    );
  }

  const AI_MODELS = [
    {
      id: "groq" as const,
      name: "Llama 3.3 70B",
      badge: "Quick",
      badgeColor: "bg-up/10 text-up",
      icon: "⚡",
      time: "~2s",
      desc: "Fast overview of key numbers, highlights and sentiment — best for a quick read",
    },
    {
      id: "minimax" as const,
      name: "Llama 4 Scout",
      badge: "Standard",
      badgeColor: "bg-saffron/10 text-saffron",
      icon: "⚖️",
      time: "~3s",
      desc: "Newer Llama 4 model — full 17-field analysis with margin breakdowns and management quotes",
    },
    {
      id: "deepseek" as const,
      name: "Qwen3 32B",
      badge: "Detailed",
      badgeColor: "bg-blue-500/10 text-blue-400",
      icon: "🔬",
      time: "~4s",
      desc: "Reasoning model — thinks through the document before answering, best for complex concalls",
    },
  ] as const;

  return (
    <div className="space-y-4">
      {error && (
        <Card className="p-4 border-down/25 bg-down/5 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-down mt-0.5" />
          <p className="text-sm text-fg/80 flex-1">{error}</p>
          <button onClick={() => setError("")}><X className="h-4 w-4 text-muted hover:text-fg" /></button>
        </Card>
      )}

      {/* AI Model picker */}
      <div className="rounded-2xl border border-border bg-surface p-4 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5" /> Choose AI Model
        </p>
        <div className="grid grid-cols-3 gap-2">
          {AI_MODELS.map((m) => (
            <button
              key={m.id}
              onClick={() => setAiModel(m.id)}
              className={clsx(
                "flex flex-col gap-1.5 rounded-xl p-3 text-left ring-1 transition-all",
                aiModel === m.id
                  ? "ring-saffron/60 bg-saffron/5"
                  : "ring-border bg-raised/60 hover:ring-saffron/30 hover:bg-raised"
              )}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-base leading-none">{m.icon}</span>
                <span className={clsx("rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide", m.badgeColor)}>
                  {m.badge}
                </span>
              </div>
              <p className="text-xs font-semibold text-fg">{m.name}</p>
              <p className="text-[10px] text-muted leading-snug">{m.desc}</p>
              <p className="text-[10px] font-medium text-saffron">{m.time}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Company context */}
      <div className="rounded-2xl border border-border bg-surface p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-1.5">
          <Building2 className="h-3.5 w-3.5" /> Company Context
          <span className="font-normal text-muted/60">(optional)</span>
        </p>
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted pointer-events-none" />
          <input value={company} onChange={(e) => setCompany(e.target.value)}
            placeholder="e.g. Reliance Industries, TCS, HDFC Bank…"
            className="w-full rounded-xl border border-border bg-raised/60 py-2.5 pl-10 pr-4 text-sm text-fg placeholder:text-muted focus:border-saffron/50 focus:outline-none focus:ring-1 focus:ring-saffron/30 transition-all" />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex rounded-xl bg-raised p-1 ring-1 ring-border">
        {(["pdf", "paste"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={clsx("flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-medium transition-all",
              tab === t ? "bg-surface shadow-sm text-fg ring-1 ring-border" : "text-muted hover:text-fg")}>
            {t === "pdf" ? <Upload className="h-4 w-4" /> : <ClipboardPaste className="h-4 w-4" />}
            {t === "pdf" ? "Upload PDF" : "Paste Text"}
          </button>
        ))}
      </div>

      {tab === "pdf" && <UploadZone onFile={handleFile} />}
      {tab === "paste" && (
        <div className="space-y-3">
          <textarea value={pasteText} onChange={(e) => setPasteText(e.target.value)}
            placeholder="Paste concall transcript, management commentary, earnings release or any financial document text here…"
            className="h-64 w-full resize-none rounded-xl border border-border bg-raised/60 px-4 py-3 text-sm text-fg placeholder:text-muted focus:border-saffron/50 focus:outline-none focus:ring-1 focus:ring-saffron/30 transition-all font-mono leading-relaxed" />
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted">{pasteText.length.toLocaleString()} chars · min 100</p>
            <button disabled={pasteText.trim().length < 100} onClick={() => { setDocText(pasteText.trim()); runAnalysis(pasteText.trim()); }}
              className="flex items-center gap-2 rounded-xl bg-saffron px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-saffron/20 transition-all hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed">
              <Sparkles className="h-4 w-4" /> Analyze Document
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        {[
          { icon: Mic2, label: "Concall transcripts", desc: "BSE/NSE filings, Screener.in" },
          { icon: FileText, label: "Annual reports", desc: "Full year financials & MD&A" },
          { icon: BarChart3, label: "Investor decks", desc: "Quarterly decks, DRHP" },
        ].map(({ icon: Icon, label, desc }) => (
          <div key={label} className="rounded-xl border border-border bg-raised/40 p-3 text-center">
            <Icon className="mx-auto mb-1.5 h-5 w-5 text-saffron" />
            <p className="text-xs font-semibold text-fg">{label}</p>
            <p className="text-[10px] text-muted mt-0.5">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── ConcallResults ───────────────────────────────────────────────────────────
function ConcallResults({ symbol, company }: { symbol: string; company: string }) {
  const { data, isLoading } = useSWR(`/api/stocks/${symbol}/concall-summary`, fetcher, { revalidateOnFocus: false });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Card key={i} className="p-5 space-y-3">
            <div className="skeleton h-5 w-32 rounded" /><div className="skeleton h-4 w-full rounded" /><div className="skeleton h-4 w-3/4 rounded" />
          </Card>
        ))}
      </div>
    );
  }

  if (data?.error || !data?.quarters?.length) {
    return (
      <div className="space-y-6">
        {/* No-data notice */}
        <div className="rounded-2xl border border-saffron/20 bg-saffron/5 p-5 flex items-start gap-3">
          <Mic2 className="h-5 w-5 shrink-0 text-saffron mt-0.5" />
          <div>
            <p className="font-semibold text-fg">No automated concall data for {company}</p>
            <p className="mt-1 text-sm text-muted">
              Upload the transcript below for an instant deep analysis — margins, management promises, revenue breakdown, risks, and more.
            </p>
          </div>
        </div>
        <UploadSection symbol={symbol} company={company} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-saffron text-white">
          <Mic2 className="h-4 w-4" />
        </div>
        <div>
          <p className="font-semibold">{company}</p>
          <p className="text-xs text-muted">{data.quarters.length} quarters · AI-powered analysis</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Calendar className="h-3.5 w-3.5 text-muted" />
          <span className="text-xs text-muted">Last {data.quarters.length}Q</span>
        </div>
      </Card>
      {data.quarters.map((q: Quarter, i: number) => (
        <QuarterCard key={q.label} q={q} company={company} isFirst={i === 0} symbol={symbol} />
      ))}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function ConcallPage() {
  const [selected, setSelected] = useState<{ symbol: string; name: string } | null>(null);

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Hero */}
      <div className="text-center space-y-3">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-saffron/10 ring-2 ring-saffron/20">
          <Mic2 className="h-7 w-7 text-saffron" />
        </div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold">Concall Intelligence</h1>
        <p className="text-muted max-w-xl mx-auto text-sm leading-relaxed">
          Search any NSE/BSE stock for AI-powered quarter summaries, or upload a concall transcript for instant deep analysis.
        </p>
      </div>

      {/* Search */}
      <div className="mx-auto max-w-xl">
        <SearchBox placeholder="Search any stock — RELIANCE, TCS, HDFC…" onSelect={(symbol, name) => setSelected({ symbol, name })} autoFocus />
        {selected && (
          <p className="mt-2 text-center text-xs text-muted">
            Showing concall data for <span className="font-semibold text-saffron">{selected.name} ({selected.symbol.replace(/\.(NS|BO)$/, "")})</span>
          </p>
        )}
      </div>

      {selected ? (
        <ConcallResults symbol={selected.symbol} company={selected.name} />
      ) : (
        <div className="space-y-8">
          {/* Popular picks */}
          <div className="mx-auto max-w-2xl">
            <p className="mb-4 text-center text-xs text-muted uppercase tracking-wider font-semibold">Popular stocks</p>
            <div className="flex flex-wrap justify-center gap-2">
              {[
                { symbol: "RELIANCE.NS", name: "Reliance Industries" },
                { symbol: "TCS.NS", name: "TCS" },
                { symbol: "HDFCBANK.NS", name: "HDFC Bank" },
                { symbol: "INFY.NS", name: "Infosys" },
                { symbol: "ICICIBANK.NS", name: "ICICI Bank" },
                { symbol: "WIPRO.NS", name: "Wipro" },
                { symbol: "HINDUNILVR.NS", name: "HUL" },
                { symbol: "BAJFINANCE.NS", name: "Bajaj Finance" },
              ].map((s) => (
                <button key={s.symbol} onClick={() => setSelected(s)}
                  className="rounded-xl bg-raised px-4 py-2 text-sm font-medium text-fg ring-1 ring-border hover:ring-saffron/40 hover:bg-saffron/5 hover:text-saffron transition-all">
                  {s.name}
                </button>
              ))}
            </div>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-4 max-w-2xl mx-auto">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">or upload your own transcript</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Upload section always visible on landing */}
          <div className="mx-auto max-w-2xl">
            <UploadSection />
          </div>
        </div>
      )}
    </div>
  );
}
