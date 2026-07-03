"use client";

import { useEffect, useRef, useState } from "react";

// Direct backend URLs — Next.js proxy doesn't support WS or SSE streaming
const WS_BASE  = process.env.NEXT_PUBLIC_WS_URL  || "ws://localhost:8000";
const API_BASE = process.env.NEXT_PUBLIC_API_URL  || "http://localhost:8000";

export type RealtimeTick = {
  price:      number;
  change_pct: number | null;
  volume:     number | null;
  ts:         number;
};

/** Connection tier used — shown as a status badge on the UI */
export type StreamStatus = "connecting" | "live" | "sse" | "polling" | "offline";

/**
 * Three-tier real-time price feed with automatic fallback and reconnect:
 *
 *   Tier 1 — WebSocket  (sub-second, batched, delta-filtered)
 *   Tier 2 — SSE        (1-second cadence, lighter than WS, auto-reconnects natively)
 *   Tier 3 — REST poll  (5-second, works everywhere, highest latency)
 *
 * WS reconnects with exponential back-off (500ms → 30s).
 * After 4 WS failures it demotes to SSE; SSE failure demotes to REST poll.
 */
export function useRealtimePrice(ticker: string): {
  tick:   RealtimeTick | null;
  status: StreamStatus;
} {
  const sym = ticker.includes(".")
    ? ticker.toUpperCase()
    : `${ticker.toUpperCase()}.NS`;

  const [tick,   setTick]   = useState<RealtimeTick | null>(null);
  const [status, setStatus] = useState<StreamStatus>("connecting");

  const wsRef    = useRef<WebSocket | null>(null);
  const esRef    = useRef<EventSource | null>(null);
  const pollRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const pingRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryRef = useRef(0);
  const deadRef  = useRef(false);

  useEffect(() => {
    deadRef.current = false;

    function stopAll() {
      wsRef.current?.close();
      esRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
      if (pingRef.current) clearInterval(pingRef.current);
      wsRef.current   = null;
      esRef.current   = null;
      pollRef.current = null;
      pingRef.current = null;
    }

    // ── Tier 3: REST polling ─────────────────────────────────────────────────
    function startPolling() {
      if (deadRef.current) return;
      stopAll();
      setStatus("polling");
      pollRef.current = setInterval(async () => {
        try {
          const r = await fetch(`/api/stream/price/${sym}`);
          if (r.ok) {
            const d = await r.json();
            if (d.price) setTick({ price: d.price, change_pct: d.change_pct ?? null, volume: d.volume ?? null, ts: d.ts ?? Date.now() / 1000 });
          }
        } catch { /* silent — already showing last cached value */ }
      }, 5000);
    }

    // ── Tier 2: Server-Sent Events ───────────────────────────────────────────
    function startSSE() {
      if (deadRef.current) return;
      stopAll();
      setStatus("sse");
      const es = new EventSource(`${API_BASE}/api/stream/sse?tickers=${sym}`);
      esRef.current = es;
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          const t = data[sym];
          if (t?.price) setTick({ price: t.price, change_pct: t.change_pct ?? null, volume: t.volume ?? null, ts: t.ts ?? Date.now() / 1000 });
        } catch { /* ignore malformed frame */ }
      };
      es.onerror = () => {
        es.close();
        startPolling();
      };
    }

    // ── Tier 1: WebSocket ────────────────────────────────────────────────────
    function applyMsg(msg: Record<string, unknown>) {
      if (msg.type === "batch") {
        const ticks = msg.ticks as Record<string, RealtimeTick> | undefined;
        const t = ticks?.[sym];
        if (t?.price) setTick({ price: t.price, change_pct: t.change_pct ?? null, volume: t.volume ?? null, ts: t.ts ?? Date.now() / 1000 });
      } else if (msg.type === "tick" && msg.ticker === sym) {
        const t = msg as unknown as RealtimeTick & { ticker: string };
        if (t.price) setTick({ price: t.price, change_pct: t.change_pct ?? null, volume: t.volume ?? null, ts: t.ts ?? Date.now() / 1000 });
      } else if (msg.type === "snapshot") {
        const data = msg.data as Record<string, RealtimeTick> | undefined;
        const t = data?.[sym];
        if (t?.price) setTick({ price: t.price, change_pct: t.change_pct ?? null, volume: t.volume ?? null, ts: t.ts ?? Date.now() / 1000 });
      }
    }

    function connectWS() {
      if (deadRef.current) return;
      setStatus("connecting");
      try {
        const ws = new WebSocket(`${WS_BASE}/ws/stocks`);
        wsRef.current = ws;

        ws.onopen = () => {
          if (deadRef.current) { ws.close(); return; }
          retryRef.current = 0;
          setStatus("live");
          ws.send(JSON.stringify({ action: "subscribe", tickers: [sym] }));
          // 25-second keepalive ping so proxies don't close idle connections
          pingRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ action: "ping" }));
            } else {
              clearInterval(pingRef.current!);
            }
          }, 25_000);
        };

        ws.onmessage = (e) => {
          try { applyMsg(JSON.parse(e.data)); } catch { /* ignore */ }
        };

        ws.onclose = () => {
          if (deadRef.current) return;
          clearInterval(pingRef.current!);
          retryRef.current++;
          if (retryRef.current > 4) {
            // WS persistently failing — step down to SSE
            startSSE();
          } else {
            setStatus("connecting");
            const delay = Math.min(500 * 2 ** (retryRef.current - 1), 30_000);
            setTimeout(connectWS, delay);
          }
        };

        ws.onerror = () => ws.close();
      } catch {
        // WebSocket constructor throws in some SSR contexts
        startSSE();
      }
    }

    connectWS();

    return () => {
      deadRef.current = true;
      stopAll();
    };
  }, [sym]);

  return { tick, status };
}
