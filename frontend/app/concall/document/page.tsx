"use client";

import { useCallback, useRef, useState } from "react";
import {
  Upload, FileText, ClipboardPaste, Sparkles, Send,
  AlertTriangle, CheckCircle2, Target, TrendingUp, Lightbulb,
  BarChart3, Mic2, RefreshCw, X, ArrowLeft, MessageSquare,
  Search, Quote, PieChart, Building2, TrendingDown, Hammer,
  DollarSign, ChevronDown, ChevronUp,
} from "lucide-react";
import Link from "next/link";
import clsx from "clsx";
import { Card } from "@/components/ui/card";

// ── types ──────────────────────────────────────────────────────────────────────
type Promise = { commitment: string; timeline: string; metric: string };
type MarginAnalysis = {
  gross_margin: string;
  ebitda_margin: string;
  pat_margin: string;
  margin_commentary: string;
};
type Analysis = {
  executive_summary: string;
  document_type: string;
  company_name: string | null;
  period: string | null;
  key_themes: string[];
  financial_highlights: string[];
  margin_analysis: MarginAnalysis | null;
  revenue_breakdown: string[];
  key_management_quotes: string[];
  management_promises: Promise[];
  risks_and_concerns: string[];
  strategic_initiatives: string[];
  guidance: string | null;
  capex_guidance: string | null;
  sentiment: string;
  sentiment_reason: string;
  suggested_questions: string[];
};
type ChatMsg = { role: "user" | "ai"; text: string; confidence?: string; source?: string };

// ── Sentiment styling ──────────────────────────────────────────────────────────
const SENTIMENT_STYLE: Record<string, string> = {
  "Positive":              "text-emerald-400 bg-emerald-400/10 ring-emerald-400/30",
  "Cautiously optimistic": "text-up bg-up/10 ring-up/30",
  "Neutral":               "text-saffron bg-saffron/10 ring-saffron/30",
  "Cautious":              "text-orange-400 bg-orange-400/10 ring-orange-400/30",
  "Negative":              "text-down bg-down/10 ring-down/30",
};
const SENTIMENT_ICON: Record<string, React.FC<{ className?: string }>> = {
  "Positive": CheckCircle2, "Cautiously optimistic": CheckCircle2,
  "Neutral": BarChart3, "Cautious": AlertTriangle, "Negative": AlertTriangle,
};
const CONF_STYLE: Record<string, string> = {
  High: "text-up", Medium: "text-saffron", Low: "text-muted",
};

// ── Section card wrapper ───────────────────────────────────────────────────────
function Section({
  icon: Icon, title, accent, children, collapsible = false,
}: {
  icon: React.FC<{ className?: string }>;
  title: string;
  accent: string; // Tailwind class for icon+title color
  children: React.ReactNode;
  collapsible?: boolean;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className={`rounded-2xl border bg-surface overflow-hidden ${accent.includes("up") ? "border-up/15" : accent.includes("saffron") ? "border-saffron/15" : accent.includes("down") ? "border-down/15" : accent.includes("accent") ? "border-accent/15" : "border-border"}`}>
      <button
        className="flex w-full items-center justify-between px-5 py-4"
        onClick={() => collapsible && setOpen(!open)}
        style={{ cursor: collapsible ? "pointer" : "default" }}
      >
        <div className="flex items-center gap-2.5">
          <div className={`flex h-8 w-8 items-center justify-center rounded-xl ${accent.includes("up") ? "bg-up/10" : accent.includes("saffron") ? "bg-saffron/10" : accent.includes("down") ? "bg-down/10" : accent.includes("accent") ? "bg-accent/10" : "bg-raised"}`}>
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

// ── Upload zone ────────────────────────────────────────────────────────────────
function UploadZone({ onFile }: { onFile: (f: File) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = (file: File) => {
    if (file.type !== "application/pdf") { alert("Please upload a PDF file."); return; }
    onFile(file);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
      onClick={() => fileRef.current?.click()}
      className={clsx(
        "group relative flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed px-8 py-14 cursor-pointer transition-all duration-200",
        dragging ? "border-saffron bg-saffron/8 scale-[1.01]" : "border-border hover:border-saffron/50 hover:bg-saffron/3"
      )}
    >
      <input ref={fileRef} type="file" accept="application/pdf" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
      <div className={clsx("flex h-16 w-16 items-center justify-center rounded-2xl ring-2 transition-all", dragging ? "bg-saffron/20 ring-saffron/40" : "bg-raised ring-border group-hover:ring-saffron/30")}>
        <Upload className={clsx("h-7 w-7 transition-colors", dragging ? "text-saffron" : "text-muted group-hover:text-saffron")} />
      </div>
      <div className="text-center">
        <p className="font-semibold text-fg">Drop your PDF here</p>
        <p className="mt-1 text-sm text-muted">Concall transcript, annual report, investor presentation</p>
        <p className="mt-2 text-xs text-muted/60">Max 30 MB · Text-based PDFs only</p>
      </div>
      <span className="rounded-lg bg-saffron/10 px-4 py-1.5 text-sm font-medium text-saffron ring-1 ring-saffron/20">Browse file</span>
    </div>
  );
}

// ── Paste zone ─────────────────────────────────────────────────────────────────
function PasteZone({ onSubmit }: { onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <div className="space-y-3">
      <textarea value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Paste concall transcript, management commentary, earnings release, or any financial document text here…"
        className="h-72 w-full resize-none rounded-xl border border-border bg-raised/60 px-4 py-3 text-sm text-fg placeholder:text-muted focus:border-saffron/50 focus:outline-none focus:ring-1 focus:ring-saffron/30 transition-all font-mono leading-relaxed"
      />
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">{text.length.toLocaleString()} chars · min 100</p>
        <button disabled={text.trim().length < 100} onClick={() => onSubmit(text.trim())}
          className="flex items-center gap-2 rounded-xl bg-saffron px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-saffron/20 transition-all hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Sparkles className="h-4 w-4" /> Analyze Document
        </button>
      </div>
    </div>
  );
}

// ── Analysis panel ─────────────────────────────────────────────────────────────
function AnalysisPanel({
  analysis, company, onQuestion, chat, chatLoading, chatInput, setChatInput, onSend, onReset,
}: {
  analysis: Analysis; company: string;
  onQuestion: (q: string) => void;
  chat: ChatMsg[]; chatLoading: boolean;
  chatInput: string; setChatInput: (v: string) => void;
  onSend: () => void; onReset: () => void;
}) {
  const sentStyle = SENTIMENT_STYLE[analysis.sentiment] ?? "text-muted bg-raised ring-border";
  const SentIcon = SENTIMENT_ICON[analysis.sentiment] ?? BarChart3;
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const THEME_COLORS = [
    "bg-up/8 text-up ring-up/20", "bg-saffron/8 text-saffron ring-saffron/20",
    "bg-accent/8 text-accent ring-accent/20", "bg-down/8 text-down ring-down/20",
    "bg-muted/10 text-fg ring-border",
  ];

  return (
    <div className="space-y-5 animate-fade-up">

      {/* ── Header card ──────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-border bg-surface overflow-hidden">
        {/* Gradient bar top */}
        <div className="h-1 w-full bg-gradient-to-r from-saffron via-amber-400 to-up" />
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="rounded-lg bg-raised px-2.5 py-1 text-xs font-medium text-muted ring-1 ring-border">{analysis.document_type}</span>
                {analysis.period && (
                  <span className="rounded-lg bg-saffron/10 px-2.5 py-1 text-xs font-semibold text-saffron ring-1 ring-saffron/20">{analysis.period}</span>
                )}
                <span className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold ring-1 ${sentStyle}`}>
                  <SentIcon className="h-3 w-3" /> {analysis.sentiment}
                </span>
              </div>
              <h2 className="mt-3 text-2xl font-bold text-fg">{analysis.company_name || company || "Document Analysis"}</h2>
              <p className="mt-1 text-sm text-muted">{analysis.sentiment_reason}</p>
            </div>
            <button onClick={onReset}
              className="flex shrink-0 items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs text-muted hover:text-fg hover:border-saffron/30 transition-all">
              <RefreshCw className="h-3.5 w-3.5" /> New
            </button>
          </div>

          {/* Executive summary */}
          <div className="mt-5 rounded-xl bg-raised/60 border border-border p-4">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-saffron">
              <Sparkles className="h-3.5 w-3.5" /> Executive Summary
            </p>
            <p className="text-sm leading-relaxed text-fg/90">{analysis.executive_summary}</p>
          </div>

          {/* Guidance + Capex side by side */}
          {(analysis.guidance || analysis.capex_guidance) && (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {analysis.guidance && (
                <div className="flex items-start gap-3 rounded-xl border border-up/20 bg-up/5 px-4 py-3">
                  <TrendingUp className="mt-0.5 h-4 w-4 shrink-0 text-up" />
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-up mb-0.5">Forward Guidance</p>
                    <p className="text-sm text-fg/85">{analysis.guidance}</p>
                  </div>
                </div>
              )}
              {analysis.capex_guidance && (
                <div className="flex items-start gap-3 rounded-xl border border-accent/20 bg-accent/5 px-4 py-3">
                  <Hammer className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-accent mb-0.5">Capex Plan</p>
                    <p className="text-sm text-fg/85">{analysis.capex_guidance}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Key themes chips ─────────────────────────────────────────────── */}
      {analysis.key_themes?.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface p-5">
          <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
            <BarChart3 className="h-3.5 w-3.5" /> Key Themes
          </p>
          <div className="flex flex-wrap gap-2">
            {analysis.key_themes.map((t, i) => (
              <span key={i} className={`rounded-xl px-3 py-1.5 text-sm font-medium ring-1 ${THEME_COLORS[i % THEME_COLORS.length]}`}>
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Financial highlights + Margin analysis ───────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {analysis.financial_highlights?.length > 0 && (
          <Section icon={TrendingUp} title="Financial Highlights" accent="text-up" collapsible>
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
          <Section icon={PieChart} title="Margin Analysis" accent="text-saffron" collapsible>
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
                <p className="mt-1 text-xs text-muted leading-relaxed border-t border-border pt-3">
                  {analysis.margin_analysis.margin_commentary}
                </p>
              )}
            </div>
          </Section>
        )}
      </div>

      {/* ── Revenue breakdown ─────────────────────────────────────────────── */}
      {analysis.revenue_breakdown?.length > 0 && analysis.revenue_breakdown[0] !== "N/A" && (
        <Section icon={DollarSign} title="Revenue Breakdown" accent="text-accent" collapsible>
          <ul className="mt-3 space-y-2">
            {analysis.revenue_breakdown.map((r, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-fg/85">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent/60" />
                {r}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ── Management promises ──────────────────────────────────────────── */}
      {analysis.management_promises?.length > 0 && (
        <Section icon={Target} title="Management Commitments & Promises" accent="text-saffron" collapsible>
          <div className="mt-3 space-y-3">
            {analysis.management_promises.map((p, i) => (
              <div key={i} className="rounded-xl border border-saffron/20 bg-saffron/5 p-4">
                <p className="text-sm font-medium text-fg leading-snug">{p.commitment}</p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  {p.timeline && (
                    <span className="flex items-center gap-1 text-xs text-saffron font-medium">
                      <span className="h-1.5 w-1.5 rounded-full bg-saffron" /> By: {p.timeline}
                    </span>
                  )}
                  {p.metric && (
                    <span className="flex items-center gap-1 text-xs text-muted">
                      <span className="h-1.5 w-1.5 rounded-full bg-muted" /> Target: {p.metric}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Key management quotes ────────────────────────────────────────── */}
      {analysis.key_management_quotes?.length > 0 && (
        <Section icon={Quote} title="Key Management Quotes" accent="text-accent" collapsible>
          <div className="mt-3 space-y-3">
            {analysis.key_management_quotes.map((q, i) => (
              <blockquote key={i} className="flex items-start gap-3 rounded-xl border-l-4 border-accent/40 bg-accent/5 pl-4 pr-4 py-3">
                <p className="text-sm text-fg/85 italic leading-relaxed">"{q}"</p>
              </blockquote>
            ))}
          </div>
        </Section>
      )}

      {/* ── Risks + Strategic initiatives ────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        {analysis.risks_and_concerns?.length > 0 && (
          <Section icon={TrendingDown} title="Risks & Concerns" accent="text-down" collapsible>
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
          <Section icon={Lightbulb} title="Strategic Initiatives" accent="text-accent" collapsible>
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

      {/* ── Suggested questions ──────────────────────────────────────────── */}
      {analysis.suggested_questions?.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface p-5">
          <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
            <MessageSquare className="h-3.5 w-3.5" /> Suggested Follow-up Questions
          </p>
          <div className="flex flex-wrap gap-2">
            {analysis.suggested_questions.map((q, i) => (
              <button key={i}
                onClick={() => { onQuestion(q); inputRef.current?.focus(); }}
                className="rounded-xl border border-saffron/20 bg-saffron/5 px-3 py-2 text-left text-sm text-fg/80 transition-all hover:border-saffron/40 hover:bg-saffron/10 hover:text-saffron"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Chat ─────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-border bg-surface p-5 space-y-4">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted">
          <MessageSquare className="h-3.5 w-3.5" /> Ask About This Document
        </p>

        {chat.length > 0 && (
          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {chat.map((msg, i) => (
              <div key={i} className={clsx("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
                {msg.role === "ai" && (
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-saffron/15 ring-1 ring-saffron/25">
                    <Sparkles className="h-3.5 w-3.5 text-saffron" />
                  </div>
                )}
                <div className={clsx(
                  "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "bg-saffron/15 text-fg/90 rounded-tr-sm"
                    : "bg-raised border border-border text-fg/90 rounded-tl-sm"
                )}>
                  {msg.text}
                  {msg.role === "ai" && msg.confidence && (
                    <p className={`mt-1.5 text-[11px] font-medium ${CONF_STYLE[msg.confidence] ?? "text-muted"}`}>
                      Confidence: {msg.confidence}
                    </p>
                  )}
                  {msg.role === "ai" && msg.source && (
                    <p className="mt-1.5 text-[11px] text-muted italic border-l-2 border-saffron/30 pl-2">{msg.source}</p>
                  )}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-saffron/15 ring-1 ring-saffron/25">
                  <Sparkles className="h-3.5 w-3.5 text-saffron animate-pulse" />
                </div>
                <div className="rounded-2xl rounded-tl-sm bg-raised border border-border px-4 py-3">
                  <div className="flex gap-1.5">
                    {[0, 1, 2].map((i) => (
                      <span key={i} className="h-1.5 w-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}

        <div className="flex gap-2 border-t border-border pt-4">
          <input ref={inputRef} value={chatInput} onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && chatInput.trim()) onSend(); }}
            placeholder="Ask anything about this document…"
            disabled={chatLoading}
            className="flex-1 rounded-xl border border-border bg-raised/60 px-4 py-2.5 text-sm placeholder:text-muted focus:border-saffron/50 focus:outline-none focus:ring-1 focus:ring-saffron/30 disabled:opacity-50 transition-all"
          />
          <button onClick={onSend} disabled={!chatInput.trim() || chatLoading}
            className="flex items-center gap-1.5 rounded-xl bg-saffron px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* hidden ref for scroll */}
      <div ref={chatEndRef} />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
type Mode = "landing" | "loading-pdf" | "loading-analysis" | "results";

export default function DocumentPage() {
  const [mode, setMode] = useState<Mode>("landing");
  const [tab, setTab] = useState<"pdf" | "paste">("pdf");
  const [docText, setDocText] = useState("");
  const [company, setCompany] = useState("");
  const [filename, setFilename] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loadingMsg, setLoadingMsg] = useState("");
  const [error, setError] = useState("");
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const handleFile = useCallback(async (file: File) => {
    setMode("loading-pdf");
    setLoadingMsg("Extracting text from PDF…");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/documents/upload-pdf", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "PDF extraction failed." }));
        throw new Error(err.detail);
      }
      const data = await res.json();
      setDocText(data.text);
      setFilename(file.name);
      await runAnalysis(data.text);
    } catch (e: any) {
      setError(e.message || "Failed to extract PDF text.");
      setMode("landing");
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const runAnalysis = useCallback(async (text: string, co?: string) => {
    setMode("loading-analysis");
    setLoadingMsg("Analyzing document with AI…");
    setError("");
    try {
      const res = await fetch("/api/documents/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, company: co ?? company }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Analysis failed." }));
        throw new Error(err.detail);
      }
      const data = await res.json();
      setAnalysis(data);
      if (data.company_name) setCompany(data.company_name);
      setChat([]);
      setMode("results");
    } catch (e: any) {
      setError(e.message || "AI analysis failed. Please try again.");
      setMode("landing");
    }
  }, [company]);

  const handlePaste = useCallback((text: string) => {
    setDocText(text);
    runAnalysis(text);
  }, [runAnalysis]);

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
      setChat((prev) => [...prev, {
        role: "ai", text: data.answer, confidence: data.confidence, source: data.source_context,
      }]);
    } catch (e: any) {
      setChat((prev) => [...prev, { role: "ai", text: `Error: ${e.message}` }]);
    } finally {
      setChatLoading(false);
    }
  }, [chatInput, chatLoading, docText, company]);

  const reset = () => {
    setMode("landing"); setDocText(""); setAnalysis(null);
    setChat([]); setError(""); setFilename(""); setCompany("");
  };

  const loadingSteps = [
    { done: mode !== "loading-pdf", label: mode === "loading-pdf" ? "Extracting text from PDF…" : "Text extracted" },
    { done: mode === "results", label: mode === "loading-analysis" ? "Analyzing with AI — parsing financials, margins, promises…" : mode === "results" ? "Analysis complete" : "Pending AI analysis" },
  ];

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Nav */}
      <div className="flex items-center gap-3">
        <Link href="/concall" className="flex items-center gap-1.5 text-sm text-muted hover:text-fg transition-colors">
          <ArrowLeft className="h-4 w-4" /> Concall Intelligence
        </Link>
        <span className="text-border">/</span>
        <span className="text-sm text-fg font-medium">Document Analyzer</span>
      </div>

      {/* Hero */}
      <div className="text-center space-y-3">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-saffron/10 ring-2 ring-saffron/20">
          <FileText className="h-7 w-7 text-saffron" />
        </div>
        <h1 className="font-display text-3xl font-bold tracking-tight">Concall Document Analyzer</h1>
        <p className="text-muted max-w-xl mx-auto text-sm leading-relaxed">
          Upload any concall transcript, annual report, or financial PDF — get instant deep analysis covering margins, management promises, revenue breakdown, risks, and suggested analyst questions.
        </p>
      </div>

      {/* Loading state */}
      {(mode === "loading-pdf" || mode === "loading-analysis") && (
        <Card className="mx-auto max-w-lg p-8 text-center space-y-5">
          <div className="mx-auto h-12 w-12 rounded-2xl bg-saffron/10 flex items-center justify-center">
            <Sparkles className="h-6 w-6 text-saffron animate-pulse" />
          </div>
          <div className="space-y-3">
            {loadingSteps.map((step, i) => (
              <div key={i} className="flex items-center gap-3 text-left">
                <div className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${step.done ? "bg-up/20" : "bg-saffron/20"}`}>
                  {step.done
                    ? <CheckCircle2 className="h-3 w-3 text-up" />
                    : <span className="h-2 w-2 rounded-full bg-saffron animate-pulse" />
                  }
                </div>
                <span className={`text-sm ${step.done ? "text-muted line-through" : "text-fg"}`}>{step.label}</span>
              </div>
            ))}
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-raised">
            <div className="h-full rounded-full bg-gradient-to-r from-saffron to-up animate-pulse" style={{ width: mode === "loading-pdf" ? "30%" : "70%" }} />
          </div>
          <p className="text-xs text-muted">15–30 seconds for large documents</p>
        </Card>
      )}

      {/* Error */}
      {error && (
        <Card className="mx-auto max-w-lg p-5 border-down/25 bg-down/5 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-down mt-0.5" />
          <div className="flex-1">
            <p className="font-medium text-down">Something went wrong</p>
            <p className="text-sm text-fg/80 mt-0.5">{error}</p>
          </div>
          <button onClick={() => setError("")} className="text-muted hover:text-fg"><X className="h-4 w-4" /></button>
        </Card>
      )}

      {/* Landing — search + upload or paste */}
      {mode === "landing" && (
        <div className="mx-auto max-w-2xl space-y-5">

          {/* Company search bar */}
          <div className="rounded-2xl border border-border bg-surface p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5" /> Company Context <span className="font-normal text-muted/60">(optional — helps AI focus analysis)</span>
            </p>
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted pointer-events-none" />
              <input
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="e.g. Reliance Industries, TCS, HDFC Bank…"
                className="w-full rounded-xl border border-border bg-raised/60 py-2.5 pl-10 pr-4 text-sm text-fg placeholder:text-muted focus:border-saffron/50 focus:outline-none focus:ring-1 focus:ring-saffron/30 transition-all"
              />
            </div>
          </div>

          {/* Tabs */}
          <div className="flex rounded-xl bg-raised p-1 ring-1 ring-border">
            {(["pdf", "paste"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={clsx(
                  "flex flex-1 items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-medium transition-all",
                  tab === t ? "bg-surface shadow-sm text-fg ring-1 ring-border" : "text-muted hover:text-fg"
                )}
              >
                {t === "pdf" ? <Upload className="h-4 w-4" /> : <ClipboardPaste className="h-4 w-4" />}
                {t === "pdf" ? "Upload PDF" : "Paste Text"}
              </button>
            ))}
          </div>

          {tab === "pdf" && <UploadZone onFile={handleFile} />}
          {tab === "paste" && <PasteZone onSubmit={handlePaste} />}

          {/* Tip cards */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { icon: Mic2,      label: "Concall transcripts", desc: "BSE/NSE filings, Screener.in" },
              { icon: FileText,  label: "Annual reports",       desc: "Full year financials & MD&A" },
              { icon: BarChart3, label: "Investor decks",       desc: "Quarterly decks, DRHP" },
            ].map(({ icon: Icon, label, desc }) => (
              <div key={label} className="rounded-xl border border-border bg-raised/40 p-3 text-center">
                <Icon className="mx-auto mb-1.5 h-5 w-5 text-saffron" />
                <p className="text-xs font-semibold text-fg">{label}</p>
                <p className="text-[10px] text-muted mt-0.5">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {mode === "results" && analysis && (
        <div className="mx-auto max-w-3xl">
          {filename && (
            <div className="mb-4 flex items-center gap-2 rounded-xl border border-border bg-raised/40 px-4 py-2.5">
              <FileText className="h-4 w-4 text-saffron shrink-0" />
              <span className="text-sm font-medium text-fg truncate max-w-xs">{filename}</span>
              <span className="text-muted text-xs ml-auto shrink-0">{(docText.length / 1000).toFixed(0)}K chars</span>
            </div>
          )}
          <AnalysisPanel
            analysis={analysis} company={company}
            onQuestion={(q) => setChatInput(q)}
            chat={chat} chatLoading={chatLoading}
            chatInput={chatInput} setChatInput={setChatInput}
            onSend={sendChat} onReset={reset}
          />
        </div>
      )}
    </div>
  );
}
