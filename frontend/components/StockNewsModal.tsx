"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Newspaper, X, ExternalLink } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";

type Article = {
  title: string;
  publisher?: string;
  link?: string;
  date?: string | null;
  sentiment?: number;
};

function sentimentDot(s: number | undefined) {
  if (s == null) return "bg-muted/40";
  if (s >= 0.05) return "bg-up";
  if (s <= -0.05) return "bg-down";
  return "bg-saffron";
}

export function StockNewsModal({
  ticker,
  companyName,
  open,
  onClose,
}: {
  ticker: string;
  companyName?: string;
  open: boolean;
  onClose: () => void;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const { data, isLoading } = useSWR(
    open && ticker ? `/api/stocks/${ticker}/news` : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const articles: Article[] = data?.articles ?? [];
  const bare = ticker.replace(/\.(NS|BO)$/, "");

  if (!mounted) return null;

  return createPortal(
    <>
      <div
        aria-hidden
        className={clsx(
          "fixed inset-0 z-[90] bg-black/50 backdrop-blur-[3px] transition-opacity duration-200",
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        )}
        onClick={onClose}
      />
      <div
        className={clsx(
          "fixed left-1/2 top-1/2 z-[100] w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 transition-all duration-200",
          open ? "scale-100 opacity-100 pointer-events-auto" : "scale-95 opacity-0 pointer-events-none"
        )}
      >
        {open && (
          <Card className="flex max-h-[80vh] flex-col overflow-hidden shadow-[0_25px_70px_-12px_rgba(0,0,0,0.55)]">
            <div className="flex items-center gap-2 border-b border-border px-5 py-4">
              <Newspaper className="h-4 w-4 text-saffron" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{companyName || bare}</p>
                <p className="text-[10px] text-muted">{bare} · {articles.length} recent articles</p>
              </div>
              <button
                onClick={onClose}
                className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-muted hover:bg-raised hover:text-fg transition-colors"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3">
              {isLoading && (
                <div className="space-y-2 p-2">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <div key={i} className="skeleton h-14 w-full rounded-xl" />
                  ))}
                </div>
              )}

              {!isLoading && articles.length === 0 && (
                <p className="p-6 text-center text-sm text-muted">No recent news found for this stock.</p>
              )}

              {!isLoading && articles.length > 0 && (
                <div className="space-y-1.5">
                  {articles.map((a, i) => (
                    <a
                      key={i}
                      href={a.link}
                      target="_blank"
                      rel="noopener"
                      className="group flex items-start gap-2.5 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-raised"
                    >
                      <span className={clsx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", sentimentDot(a.sentiment))} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm leading-snug text-fg/90 group-hover:text-saffron transition-colors">
                          {a.title}
                        </p>
                        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted">
                          {a.publisher && <span>{a.publisher}</span>}
                          {a.publisher && a.date && <span>·</span>}
                          {a.date && <span>{a.date}</span>}
                        </div>
                      </div>
                      {a.link && (
                        <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-muted/60 group-hover:text-saffron transition-colors" />
                      )}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </Card>
        )}
      </div>
    </>,
    document.body
  );
}
