"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import clsx from "clsx";
import {
  Send, Bot, User, Sparkles, TrendingUp, BarChart3,
  IndianRupee, RefreshCw, Copy, Check, TrendingDown,
} from "lucide-react";

/* ─── Types ──────────────────────────────────────── */
type Role = "user" | "assistant";
type StockSnippet = {
  ticker: string;
  symbol: string;
  name?: string;
  price?: number | null;
  change_pct?: number | null;
  pe?: number | null;
};
type Message = {
  id: string;
  role: Role;
  content: string;
  loading?: boolean;
  suggestions?: string[];
  stocks?: StockSnippet[];
};

/* ─── Markdown-lite renderer ─────────────────────── */
function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("### ") || line.startsWith("## ") || line.startsWith("# ")) {
      // Flatten all heading levels to bold inline text — keeps chat feel
      const text = line.replace(/^#+\s*/, "");
      elements.push(
        <p key={i} className="mt-3 mb-0.5 text-sm font-bold text-fg">
          <InlineMarkdown text={text} />
        </p>
      );
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      elements.push(
        <li key={i} className="ml-4 list-disc text-sm leading-relaxed text-fg/90">
          <InlineMarkdown text={line.slice(2)} />
        </li>
      );
    } else if (/^\d+\. /.test(line)) {
      elements.push(
        <li key={i} className="ml-4 list-decimal text-sm leading-relaxed text-fg/90">
          <InlineMarkdown text={line.replace(/^\d+\. /, "")} />
        </li>
      );
    } else if (line.startsWith("```")) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <pre key={i} className="my-2 overflow-x-auto rounded-lg bg-raised p-3 text-xs font-mono text-fg ring-1 ring-border">
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
    } else if (line.startsWith("> ")) {
      elements.push(
        <blockquote key={i} className="my-1 border-l-2 border-saffron pl-3 text-sm italic text-muted">
          <InlineMarkdown text={line.slice(2)} />
        </blockquote>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={i} className="h-2" />);
    } else {
      elements.push(
        <p key={i} className="text-sm leading-relaxed text-fg/90">
          <InlineMarkdown text={line} />
        </p>
      );
    }
    i++;
  }
  return <div className="space-y-0.5">{elements}</div>;
}

function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|₹[\d,]+(?:\.\d+)?(?:\s*(?:Cr|Lakh|K|M|B|T))?)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**"))
          return <strong key={i} className="font-bold text-fg">{part.slice(2, -2)}</strong>;
        if (part.startsWith("*") && part.endsWith("*"))
          return <em key={i} className="italic">{part.slice(1, -1)}</em>;
        if (part.startsWith("`") && part.endsWith("`"))
          return <code key={i} className="rounded bg-raised px-1 py-0.5 font-mono text-xs text-saffron ring-1 ring-border">{part.slice(1, -1)}</code>;
        if (part.startsWith("₹"))
          return <span key={i} className="font-semibold text-saffron">{part}</span>;
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

/* ─── CopyButton ─────────────────────────────────── */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy} className="grid h-6 w-6 place-items-center rounded text-muted transition hover:bg-raised hover:text-fg" aria-label="Copy">
      {copied ? <Check className="h-3 w-3 text-up" /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

/* ─── Stock mini card ────────────────────────────── */
function StockCard({ s }: { s: StockSnippet }) {
  const up = (s.change_pct ?? 0) >= 0;
  return (
    <Link
      href={`/stock/${s.ticker}`}
      className="flex items-center justify-between rounded-xl bg-surface px-3 py-2.5 ring-1 ring-border hover:ring-saffron/40 hover:bg-saffron/5 transition-all"
    >
      <div className="min-w-0">
        <p className="text-xs font-bold text-fg truncate">{s.symbol}</p>
        {s.name && <p className="text-[10px] text-muted truncate">{s.name}</p>}
      </div>
      <div className="ml-3 text-right shrink-0">
        {s.price != null ? (
          <>
            <p className="nums text-xs font-semibold text-fg">₹{s.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</p>
            <p className={clsx("text-micro-cap font-medium", up ? "text-up" : "text-down")}>
              {up ? "▲" : "▼"} {Math.abs(s.change_pct ?? 0).toFixed(2)}%
            </p>
          </>
        ) : (
          <p className="text-[10px] text-muted">No data</p>
        )}
      </div>
    </Link>
  );
}

/* ─── MessageBubble ──────────────────────────────── */
function MessageBubble({ msg, onSuggest }: { msg: Message; onSuggest: (q: string) => void }) {
  const isUser = msg.role === "user";
  const hasStocks      = !isUser && (msg.stocks?.length ?? 0) > 0;
  const hasSuggestions = !isUser && (msg.suggestions?.length ?? 0) > 0;

  return (
    <div className={clsx("flex gap-3", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <div className={clsx(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full ring-1",
        isUser ? "bg-saffron text-white ring-saffron/30" : "bg-raised text-saffron ring-border"
      )}>
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div className={clsx("flex flex-col gap-2", isUser ? "items-end max-w-[82%]" : "items-start max-w-[86%]")}>
        {/* Bubble */}
        <div className={clsx(
          "rounded-2xl px-4 py-3 w-full",
          isUser ? "rounded-tr-sm bg-saffron text-white" : "rounded-tl-sm bg-raised ring-1 ring-border"
        )}>
          {msg.loading ? (
            <div className="flex items-center gap-1.5 py-1">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-saffron [animation-delay:0ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-saffron [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-saffron [animation-delay:300ms]" />
            </div>
          ) : isUser ? (
            <p className="text-sm leading-relaxed">{msg.content}</p>
          ) : (
            <div>
              <Markdown text={msg.content} />
              <div className="mt-2 flex justify-end">
                <CopyButton text={msg.content} />
              </div>
            </div>
          )}
        </div>

        {/* Stock cards */}
        {hasStocks && (
          <div className="w-full">
            <p className="mb-1.5 text-micro-cap font-medium text-muted uppercase tracking-wide">Mentioned stocks</p>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
              {msg.stocks!.map((s) => <StockCard key={s.ticker} s={s} />)}
            </div>
          </div>
        )}

        {/* Follow-up suggestions */}
        {hasSuggestions && (
          <div className="w-full">
            <p className="mb-1.5 text-micro-cap font-medium text-muted uppercase tracking-wide">You might also ask</p>
            <div className="flex flex-col gap-1.5">
              {msg.suggestions!.map((s, i) => (
                <button
                  key={i}
                  onClick={() => onSuggest(s)}
                  className="text-left rounded-xl bg-raised px-3 py-2 text-xs text-fg/80 ring-1 ring-border hover:ring-saffron/40 hover:bg-saffron/5 hover:text-fg transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Suggestions ────────────────────────────────── */
const SUGGESTIONS = [
  { icon: TrendingUp,   text: "Which large-cap stocks are likely to outperform in 2025?" },
  { icon: IndianRupee,  text: "Explain LTCG and STCG tax rules for Indian stocks" },
  { icon: BarChart3,    text: "What is the outlook for Indian IT sector stocks?" },
  { icon: Sparkles,     text: "How do FII and DII flows affect Indian markets?" },
  { icon: TrendingDown, text: "Compare Nifty 50 vs Nifty Midcap 150 for long-term SIP" },
  { icon: BarChart3,    text: "What metrics should I check before investing in a pharma stock?" },
];

/* ─── Page ──────────────────────────────────────── */
export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [input]);

  const send = useCallback(async (question: string) => {
    if (!question.trim() || loading) return;
    const q = question.trim();
    setInput("");

    const userMsg: Message = { id: `u${Date.now()}`, role: "user",      content: q };
    const loadMsg: Message = { id: `l${Date.now()}`, role: "assistant", content: "", loading: true };

    setMessages((prev) => [...prev, userMsg, loadMsg]);
    setLoading(true);

    try {
      const history = messages
        .filter((m) => !m.loading)
        .map((m) => ({ role: m.role, content: m.content }));

      const res  = await fetch("/api/chat", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ message: q, history }),
      });
      const data = await res.json();

      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadMsg.id
            ? {
                ...m,
                content:     data.reply ?? "Sorry, I couldn't get a response.",
                loading:     false,
                suggestions: data.suggestions ?? [],
                stocks:      data.stocks ?? [],
              }
            : m
        )
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadMsg.id
            ? { ...m, content: "Network error. Please check your connection and try again.", loading: false }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  }, [loading, messages]);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const reset  = () => { setMessages([]); setInput(""); };
  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-[calc(100vh-130px)] flex-col animate-fade-up">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-saffron/10 ring-2 ring-saffron/20">
            <Sparkles className="h-5 w-5 text-saffron" />
          </div>
          <div>
            <h1 className="font-display text-2xl font-bold">Ask AEGIS AI</h1>
            <p className="text-xs text-muted">Indian stock market expert · Powered by Groq</p>
          </div>
        </div>
        {!isEmpty && (
          <button
            onClick={reset}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-muted ring-1 ring-border hover:bg-raised hover:text-fg transition-all"
          >
            <RefreshCw className="h-3 w-3" /> New chat
          </button>
        )}
      </div>

      {/* Chat area */}
      <div className="relative flex flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-surface/60 backdrop-blur-sm">

        <div className="flex-1 overflow-y-auto p-5 space-y-5" style={{ scrollbarWidth: "thin" }}>
          {isEmpty ? (
            <div className="flex h-full flex-col items-center justify-center">
              <div className="mb-6 text-center">
                <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-saffron/10 ring-2 ring-saffron/20">
                  <Sparkles className="h-8 w-8 text-saffron" />
                </div>
                <h2 className="font-display text-xl font-bold">Ask me anything</h2>
                <p className="mt-1 text-sm text-muted">
                  About Indian stocks, sectors, SEBI rules, IPOs, taxation, and more
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 w-full max-w-2xl">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => send(s.text)}
                    className="flex items-center gap-3 rounded-xl bg-raised p-3 text-left ring-1 ring-border hover:ring-saffron/40 hover:bg-saffron/5 transition-all group"
                  >
                    <s.icon className="h-4 w-4 shrink-0 text-saffron" />
                    <span className="text-xs text-fg/80 group-hover:text-fg transition-colors leading-snug">{s.text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} onSuggest={(q) => send(q)} />
            ))
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-border" />

        <div className="flex items-end gap-3 p-4">
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask about any Indian stock, sector, or market concept…"
              rows={1}
              className={clsx(
                "w-full resize-none rounded-xl bg-raised px-4 py-3 text-sm text-fg outline-none",
                "placeholder-muted/50 ring-1 ring-border transition-all duration-200",
                "focus:ring-saffron/50 focus:bg-surface max-h-44 leading-relaxed"
              )}
              style={{ scrollbarWidth: "thin" }}
              disabled={loading}
            />
          </div>
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || loading}
            className={clsx(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all duration-200",
              input.trim() && !loading
                ? "bg-saffron text-white shadow-lg shadow-saffron/30 hover:bg-saffron/90 hover:scale-105"
                : "bg-raised text-muted ring-1 ring-border cursor-not-allowed"
            )}
            aria-label="Send"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>

        <p className="px-4 pb-3 text-center text-[10px] text-muted">
          For educational purposes only · Not financial advice · Data may be delayed
        </p>
      </div>
    </div>
  );
}
