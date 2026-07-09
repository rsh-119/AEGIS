"use client";

import { useState, useRef, useEffect } from "react";
import { post } from "@/lib/api";
import { Send, Sparkles, AlertCircle, Plus, FileText, X } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

type Msg = { role: "user" | "ai"; text: string; confidence?: string; source?: string; error?: boolean };

const CONFIDENCE_COLOR: Record<string, string> = {
  High: "text-up",
  Medium: "text-saffron",
  Low: "text-down",
};

const SUGGESTED = [
  "Who is the CEO?",
  "Is the debt level high?",
  "Any bulk deals recently?",
  "How is revenue growth?",
  "How does the valuation compare to peers?",
  "What are the biggest risks right now?",
  "Any recent news I should know about?",
  "Is this a good entry point?",
];

const SUGGESTED_DOC = [
  "What revenue guidance did management give?",
  "What are the key risks mentioned?",
  "What were the main highlights this quarter?",
  "What capex or expansion plans were discussed?",
];

export function AskAI({ ticker }: { ticker: string }) {
  const { toast } = useToast();
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  // Document mode
  const [docText, setDocText] = useState<string | null>(null);
  const [docName, setDocName] = useState("");
  const [docLoading, setDocLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (msgs.length > 0 || busy) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [msgs, busy]);

  async function send(question?: string) {
    const text = (question ?? q).trim();
    if (!text || busy) return;
    setMsgs((m) => [...m, { role: "user", text }]);
    setQ("");
    setBusy(true);
    try {
      if (docText) {
        // Document Q&A mode
        const res = await fetch("/api/documents/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: docText, question: text, company: ticker }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Document Q&A failed");
        setMsgs((m) => [...m, {
          role: "ai",
          text: data.answer,
          confidence: data.confidence,
          source: data.source_context,
        }]);
      } else {
        // Normal stock Q&A mode
        const res = await post<{ answer: string; confidence: string }>("/api/ai/ask", {
          question: text,
          ticker,
        });
        setMsgs((m) => [...m, { role: "ai", text: res.answer, confidence: res.confidence }]);
      }
    } catch (e) {
      setMsgs((m) => [...m, { role: "ai", text: (e as Error).message, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  async function handleFile(file: File) {
    if (file.type !== "application/pdf" && !file.type.startsWith("text/")) {
      toast({ variant: "warning", title: "Unsupported file", description: "Please upload a PDF or text file." });
      return;
    }
    setDocLoading(true);
    try {
      if (file.type === "application/pdf") {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch("/api/documents/upload-pdf", { method: "POST", body: form });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "PDF extraction failed" }));
          throw new Error(err.detail);
        }
        const data = await res.json();
        setDocText(data.text);
        setDocName(file.name);
        setMsgs([{
          role: "ai",
          text: `Document loaded: "${file.name}" (${data.pages} pages, ${Math.round(data.chars / 1000)}K characters). Now ask me anything about this document!`,
        }]);
      } else {
        // Plain text file
        const text = await file.text();
        setDocText(text);
        setDocName(file.name);
        setMsgs([{
          role: "ai",
          text: `Document loaded: "${file.name}" (${Math.round(text.length / 1000)}K characters). Now ask me anything about this document!`,
        }]);
      }
    } catch (e) {
      setMsgs((m) => [...m, { role: "ai", text: `Failed to load file: ${(e as Error).message}`, error: true }]);
    } finally {
      setDocLoading(false);
    }
  }

  function clearDoc() {
    setDocText(null);
    setDocName("");
    setMsgs([]);
    if (fileRef.current) fileRef.current.value = "";
  }

  const bare = ticker.replace(/\.(NS|BO)$/, "");
  const suggested = docText ? SUGGESTED_DOC : SUGGESTED;

  // Follow-up suggestions after the AI's last answer — questions not yet
  // asked this session, so the chips stay useful past the first exchange
  // instead of only ever showing on the empty state.
  const askedSet = new Set(msgs.filter((m) => m.role === "user").map((m) => m.text));
  const lastMsg = msgs[msgs.length - 1];
  const followUps = suggested.filter((s) => !askedSet.has(s)).slice(0, 4);
  const showFollowUps =
    msgs.length > 0 && !busy && !docLoading && lastMsg?.role === "ai" && !lastMsg.error && followUps.length > 0;

  return (
    <Card className="flex flex-col p-5" style={{ minHeight: "360px" }}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-medium">
          <Sparkles className="h-4 w-4 text-saffron" />
          AEGIS AI · {bare}
        </h3>
        {docText && (
          <button
            onClick={clearDoc}
            className="flex items-center gap-1.5 rounded-lg border border-saffron/25 bg-saffron/8 px-2.5 py-1 text-xs text-saffron hover:bg-saffron/15 transition-all"
          >
            <FileText className="h-3 w-3" />
            <span className="max-w-[120px] truncate">{docName}</span>
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Message area */}
      <div className="mb-3 flex-1 space-y-3 overflow-y-auto" style={{ maxHeight: "300px" }}>
        {msgs.length === 0 && (
          <div className="space-y-3">
            <p className="text-xs text-muted">
              Ask anything — answers use live price, ownership, and news data.{" "}
              <span className="text-saffron/80">Or upload a PDF to chat with it.</span>
            </p>
            <div className="flex flex-wrap gap-1.5">
              {suggested.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={busy}
                  className="rounded-full border border-border px-2.5 py-1 text-xs text-muted transition hover:border-saffron/50 hover:text-fg"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            {m.role === "ai" ? (
              <div className="max-w-[92%] space-y-1">
                <div className={`rounded-2xl rounded-tl-sm px-3.5 py-2.5 text-sm leading-relaxed ${m.error ? "bg-down/10 text-down" : "bg-raised text-fg/90"}`}>
                  {m.error && <AlertCircle className="mb-1 h-3.5 w-3.5 inline mr-1" />}
                  {m.text.split("\n").map((line, li) => (
                    <span key={li}>{line}{li < m.text.split("\n").length - 1 && <br />}</span>
                  ))}
                </div>
                {m.confidence && (
                  <p className={`pl-1 text-micro-cap font-medium ${CONFIDENCE_COLOR[m.confidence] ?? "text-muted"}`}>
                    Confidence: {m.confidence}
                  </p>
                )}
                {m.source && (
                  <p className="pl-1 text-[10px] text-muted italic border-l-2 border-border ml-1 pl-2">{m.source}</p>
                )}
              </div>
            ) : (
              <span className="max-w-[80%] rounded-2xl rounded-tr-sm bg-saffron px-3.5 py-2 text-sm text-ink">
                {m.text}
              </span>
            )}
          </div>
        ))}

        {showFollowUps && (
          <div className="flex flex-wrap gap-1.5">
            {followUps.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                disabled={busy}
                className="rounded-full border border-saffron/25 bg-saffron/5 px-2.5 py-1 text-xs text-saffron/80 transition hover:border-saffron/50 hover:text-saffron"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {(busy || docLoading) && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-tl-sm bg-raised px-4 py-2.5">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="inline-block h-1.5 w-1.5 rounded-full bg-muted animate-pulse" style={{ animationDelay: `${i * 150}ms` }} />
                ))}
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input row */}
      <div className="flex gap-2 pt-1 border-t border-border">
        {/* Hidden file input */}
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,text/plain,.txt"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />

        {/* + button to upload file */}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy || docLoading}
          title="Upload PDF or text file to chat with it"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border text-muted transition hover:border-saffron/50 hover:text-saffron hover:bg-saffron/5 disabled:opacity-40"
        >
          <Plus className="h-4 w-4" />
        </button>

        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !busy && send()}
          placeholder={docText ? `Ask about ${docName}…` : "Ask about bulk deals, ownership, growth…"}
          className="flex-1 text-sm"
          disabled={busy || docLoading}
        />
        <Button
          onClick={() => send()}
          disabled={busy || docLoading || !q.trim()}
          className="grid place-items-center px-3 disabled:opacity-40"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </Card>
  );
}
