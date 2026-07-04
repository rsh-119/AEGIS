"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2, TrendingUp, X } from "lucide-react";
import clsx from "clsx";
import { Badge } from "@/components/ui/badge";

type Suggestion = { symbol: string; name: string; exchange: string };

function Highlight({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-saffron/20 text-fg font-semibold rounded-sm">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export function SearchBox({
  autoFocus = false,
  placeholder = "Search stocks — RELIANCE, TCS…",
  onSelect,
  size = "default",
}: {
  autoFocus?: boolean;
  placeholder?: string;
  onSelect?: (symbol: string, name: string) => void;
  /** "hero" = full pill-shaped, large, animated rotating border */
  size?: "default" | "hero";
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(-1);
  const [focused, setFocused] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const isHero = size === "hero";

  useEffect(() => {
    const trimmed = q.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setOpen(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    const id = setTimeout(async () => {
      try {
        const r = await fetch(`/api/stocks/search?q=${encodeURIComponent(trimmed)}`, {
          headers: { "Cache-Control": "max-age=900" },  // respect backend 15min cache
        });
        const data: Suggestion[] = await r.json();
        setResults(data);
        setOpen(true);
        setActive(-1);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
        setFocused(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const go = useCallback(
    (symbol: string, name: string) => {
      setOpen(false);
      setFocused(false);
      if (onSelect) {
        setQ(symbol.replace(/\.(NS|BO)$/, ""));
        onSelect(symbol, name);
      } else {
        setQ("");
        router.push(`/stock/${encodeURIComponent(symbol)}`);
      }
    },
    [router, onSelect]
  );

  const clear = () => {
    setQ("");
    setResults([]);
    setOpen(false);
    inputRef.current?.focus();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0 && results[active]) go(results[active].symbol, results[active].name);
      else if (q.trim()) go(q.trim().toUpperCase(), "");
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  /* ── Hero variant ─────────────────────────────── */
  if (isHero) {
    return (
      <div ref={boxRef} className="relative w-full">
        {/* Rotating conic-gradient border wrapper */}
        <div className="hero-search-outer">
          <div className="hero-search-inner">
            <div className="relative flex items-center">
              {/* Search icon */}
              <Search
                className={clsx(
                  "pointer-events-none absolute left-5 h-5 w-5 transition-all duration-300",
                  focused ? "text-saffron scale-110" : "text-muted"
                )}
              />

              <input
                ref={inputRef}
                autoFocus={autoFocus}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onKey}
                onFocus={() => { setFocused(true); if (results.length) setOpen(true); }}
                onBlur={() => setTimeout(() => setFocused(false), 150)}
                placeholder={placeholder}
                className={clsx(
                  "w-full rounded-full bg-transparent py-4 pl-14 pr-12 text-base text-fg outline-none",
                  "placeholder-muted/50 transition-all duration-300"
                )}
                aria-label="Search Indian stocks"
                autoComplete="off"
                spellCheck={false}
              />

              {/* Right: spinner / clear */}
              <div className="absolute right-4">
                {loading ? (
                  <Loader2 className="h-5 w-5 animate-spin text-saffron" />
                ) : q ? (
                  <button
                    onClick={clear}
                    tabIndex={-1}
                    aria-label="Clear"
                    className="grid h-6 w-6 place-items-center rounded-full text-muted transition hover:bg-raised hover:text-fg"
                  >
                    <X className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {/* Dropdown — wider, floats below */}
        {open && (
          <div className="absolute z-50 mt-3 w-full overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/20 animate-scale-in">
            {results.length === 0 && !loading ? (
              <div className="flex items-center gap-2 px-5 py-4 text-sm text-muted">
                <Search className="h-4 w-4 shrink-0" />
                No NSE/BSE matches for &ldquo;{q}&rdquo;
              </div>
            ) : (
              <ul role="listbox">
                {results.map((s, i) => {
                  const bare = s.symbol.replace(/\.(NS|BO)$/, "");
                  const isAct = active === i;
                  return (
                    <li key={s.symbol} role="option" aria-selected={isAct}
                      className={clsx(
                        "border-b border-border/50 last:border-0 transition-colors duration-100",
                        isAct ? "bg-saffron/8" : "hover:bg-raised/60"
                      )}
                    >
                      <button
                        onMouseEnter={() => setActive(i)}
                        onClick={() => go(s.symbol, s.name)}
                        className="flex w-full items-center justify-between gap-4 px-5 py-3.5 text-left"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={clsx(
                            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-150",
                            isAct ? "bg-saffron text-white" : "bg-raised text-saffron"
                          )}>
                            <TrendingUp className="h-4 w-4" />
                          </span>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-fg">
                              <Highlight text={s.name} query={q} />
                            </div>
                            <div className="font-mono text-xs text-muted">
                              <Highlight text={bare} query={q.toUpperCase()} />
                            </div>
                          </div>
                        </div>
                        <Badge className={clsx(
                          "shrink-0 ring-1 text-[10px] font-bold transition-all",
                          s.exchange === "NSE"
                            ? isAct ? "bg-saffron text-white ring-saffron" : "bg-saffron/10 text-saffron ring-saffron/20"
                            : "bg-raised text-muted ring-border"
                        )}>
                          {s.exchange}
                        </Badge>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="border-t border-border/50 bg-raised/30 px-5 py-2.5">
              <p className="text-[10px] text-muted">↑↓ navigate · Enter to open · Esc to close</p>
            </div>
          </div>
        )}
      </div>
    );
  }

  /* ── Default (nav / portfolio) variant ───────── */
  return (
    <div ref={boxRef} className="relative w-full">
      <div className={clsx(
        "relative rounded-xl transition-all duration-300",
        focused
          ? "shadow-[0_0_0_3px_rgb(var(--color-saffron)/0.25)] ring-1 ring-saffron/60"
          : "ring-1 ring-border hover:ring-saffron/30 hover:shadow-[0_0_0_2px_rgb(var(--color-saffron)/0.10)]"
      )}>
        <Search className={clsx(
          "pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 transition-all duration-300",
          focused ? "text-saffron scale-110" : "text-muted"
        )} />

        <input
          ref={inputRef}
          autoFocus={autoFocus}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          onFocus={() => { setFocused(true); if (results.length) setOpen(true); }}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          placeholder={placeholder}
          className={clsx(
            "w-full rounded-xl bg-raised/80 py-2.5 pl-9 pr-8 text-sm text-fg outline-none",
            "placeholder-muted/50 transition-all duration-300",
            focused ? "bg-surface" : "hover:bg-raised"
          )}
          aria-label="Search Indian stocks"
          autoComplete="off"
          spellCheck={false}
        />

        <div className="absolute right-2.5 top-1/2 -translate-y-1/2">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-saffron" />
          ) : q ? (
            <button onClick={clear} tabIndex={-1} aria-label="Clear"
              className="grid h-5 w-5 place-items-center rounded-full text-muted transition hover:bg-raised hover:text-fg">
              <X className="h-3 w-3" />
            </button>
          ) : null}
        </div>

        <div className={clsx(
          "absolute bottom-0 left-0 h-[2px] rounded-b-xl bg-gradient-to-r from-saffron/0 via-saffron to-saffron/0 transition-all duration-500",
          focused ? "opacity-100 w-full" : "opacity-0 w-0"
        )} />
      </div>

      {open && (
        <div className="absolute z-50 mt-2 w-full overflow-hidden rounded-xl border border-border bg-surface shadow-2xl shadow-black/25 ring-1 ring-border/50 animate-scale-in">
          {results.length === 0 && !loading ? (
            <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted">
              <Search className="h-3.5 w-3.5 shrink-0" />
              No NSE/BSE matches for &ldquo;{q}&rdquo;
            </div>
          ) : (
            <ul role="listbox">
              {results.map((s, i) => {
                const bare = s.symbol.replace(/\.(NS|BO)$/, "");
                const isAct = active === i;
                return (
                  <li key={s.symbol} role="option" aria-selected={isAct}
                    className={clsx(
                      "border-b border-border/50 last:border-0 transition-colors duration-100",
                      isAct ? "bg-saffron/8" : "hover:bg-raised/60"
                    )}
                  >
                    <button
                      onMouseEnter={() => setActive(i)}
                      onClick={() => go(s.symbol, s.name)}
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span className={clsx(
                          "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-all duration-150",
                          isAct ? "bg-saffron text-white" : "bg-raised text-saffron"
                        )}>
                          <TrendingUp className="h-3.5 w-3.5" />
                        </span>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-fg">
                            <Highlight text={s.name} query={q} />
                          </div>
                          <div className="font-mono text-xs text-muted">
                            <Highlight text={bare} query={q.toUpperCase()} />
                          </div>
                        </div>
                      </div>
                      <Badge className={clsx(
                        "shrink-0 ring-1 text-[10px] font-bold transition-all duration-150",
                        s.exchange === "NSE"
                          ? isAct ? "bg-saffron text-white ring-saffron" : "bg-saffron/10 text-saffron ring-saffron/20"
                          : "bg-raised text-muted ring-border"
                      )}>
                        {s.exchange}
                      </Badge>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="border-t border-border/50 bg-raised/30 px-4 py-2">
            <p className="text-[10px] text-muted">↑↓ navigate · Enter to open · Esc to close</p>
          </div>
        </div>
      )}
    </div>
  );
}
