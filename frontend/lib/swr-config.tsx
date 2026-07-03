"use client";

import { useEffect, useRef } from "react";
import { SWRConfig, type State } from "swr";
import { idbGet, idbSet, idbDelete, idbGetAll } from "./idb";

// ── TTL / deduping maps (ms) by request URL prefix ────────────────────────────
// IDB persistence TTL — how long stale data is served from browser store
const URL_TTL: [string, number][] = [
  ["/api/mf/",         60 * 60_000],    // 1 h  — NAV end-of-day
  ["/api/mf",          60 * 60_000],    // 1 h  — MF list
  ["/api/etf",         10 * 60_000],    // 10 m — ETF prices
  ["/api/market",      15 * 60_000],    // 15 m — indices/movers (backend overview cache is 12 min)
  ["/api/sector",      30 * 60_000],    // 30 m
  ["/api/peers",       30 * 60_000],    // 30 m
  ["/api/stocks/batch", 2 * 60_000],    // 2 m  — batch quotes
  ["/api/stocks",       2 * 60_000],    // 2 m  — live prices
  ["/api/portfolio",    1 * 60_000],    // 1 m  — user data (never proxy-cached)
  ["/api/watchlist",    1 * 60_000],    // 1 m
];
const DEFAULT_TTL = 5 * 60_000;

// SWR dedupingInterval — suppress duplicate in-flight fetches for same key
// Set to match IDB TTL so repeated renders within the window don't cause extra requests
const URL_DEDUP: [string, number][] = [
  ["/api/mf",          30 * 60_000],   // 30 m  — NAV changes once a day
  ["/api/etf",          5 * 60_000],   // 5 m
  ["/api/market",      10 * 60_000],   // 10 m — match HomeRefreshTask overview interval
  ["/api/sector",      10 * 60_000],   // 10 m
  ["/api/peers",       10 * 60_000],   // 10 m
  ["/api/stocks/batch", 2 * 60_000],   // 2 m
  ["/api/stocks",       2 * 60_000],   // 2 m
  ["/api/portfolio",   30 * 1_000],    // 30 s — needs reasonably fresh P&L
  ["/api/watchlist",   30 * 1_000],    // 30 s
];
const DEFAULT_DEDUP = 5_000;

export function dedupFor(key: string): number {
  for (const [prefix, ms] of URL_DEDUP) {
    if (key.startsWith(prefix)) return ms;
  }
  return DEFAULT_DEDUP;
}

function ttlFor(key: string): number {
  for (const [prefix, ms] of URL_TTL) {
    if (key.startsWith(prefix)) return ms;
  }
  return DEFAULT_TTL;
}

// ── Internal cache entry shape ────────────────────────────────────────────────
type Entry = { v: unknown; ts: number };

// SWR cache keys that are internal machinery — never persist these
function isInternalKey(k: string) {
  return k.startsWith("$") || k.startsWith("_") || !k.startsWith("/api");
}

// ── Cache provider factory ─────────────────────────────────────────────────────
function makeIDBProvider() {
  // In-memory map is the source of truth; IDB is the persistence layer.
  const map = new Map<string, Entry>();

  // Hydrate in-memory map from IDB synchronously before SWR makes first requests.
  // This runs immediately when the provider is created (inside useEffect below).
  let hydrated = false;
  const hydration = (async () => {
    try {
      const all = await idbGetAll() as Record<string, Entry>;
      const now = Date.now();
      for (const [key, entry] of Object.entries(all)) {
        if (!entry || isInternalKey(key)) continue;
        if (now - entry.ts < ttlFor(key)) {
          map.set(key, entry);
        } else {
          // Evict stale entry from IDB
          idbDelete(key).catch(() => {});
        }
      }
    } catch {}
    hydrated = true;
  })();

  return {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    get(key: string): State<any, any> | undefined {
      if (isInternalKey(key)) return undefined;
      const entry = map.get(key);
      if (!entry) return undefined;
      if (Date.now() - entry.ts > ttlFor(key)) {
        map.delete(key);
        idbDelete(key).catch(() => {});
        return undefined;
      }
      return entry.v as State<any, any>;
    },

    set(key: string, val: unknown) {
      if (isInternalKey(key)) return;
      const entry: Entry = { v: val, ts: Date.now() };
      map.set(key, entry);
      // Persist in background — don't await, never block the UI
      idbSet(key, entry).catch(() => {});
    },

    delete(key: string) {
      map.delete(key);
      idbDelete(key).catch(() => {});
    },

    keys(): IterableIterator<string> {
      return map.keys();
    },
  };
}

// ── Provider component ────────────────────────────────────────────────────────
let _provider: ReturnType<typeof makeIDBProvider> | null = null;

export function SWRCacheProvider({ children }: { children: React.ReactNode }) {
  const providerRef = useRef<ReturnType<typeof makeIDBProvider> | null>(null);

  if (!providerRef.current) {
    // Singleton across renders — same provider instance for the app's lifetime
    if (!_provider) _provider = makeIDBProvider();
    providerRef.current = _provider;
  }

  return (
    <SWRConfig
      value={{
        provider: () => providerRef.current!,
        // Global SWR defaults
        revalidateOnFocus:      false,
        revalidateOnReconnect:  true,
        // dedupingInterval set per-key via the `use` middleware below
        dedupingInterval:       5_000,
        errorRetryCount:        2,
        shouldRetryOnError:     true,
        keepPreviousData:       true,
        // Middleware: override dedupingInterval based on URL prefix
        use: [
          (useSWRNext) => (key, fetcher, config) => {
            const url = typeof key === "string" ? key : Array.isArray(key) ? key[0] : "";
            return useSWRNext(key, fetcher, {
              ...config,
              dedupingInterval: dedupFor(url),
            });
          },
        ],
      }}
    >
      {children}
    </SWRConfig>
  );
}
