"use client";

import { useEffect, useRef, useState } from "react";

export type RealtimeTick = {
  price:      number;
  change_pct: number | null;
  volume:     number | null;
  ts:         number;
};

/** Connection tier used — shown as a status badge on the UI */
export type StreamStatus = "connecting" | "live" | "sse" | "polling" | "offline";

/**
 * Polls the regular (server-cached) quote endpoint every 30s.
 *
 * There is no live WebSocket/SSE tick feed — IndianAPI's metered quota can't
 * sustain per-second polling, so this simply re-fetches the same cached quote
 * the rest of the page already uses. Status is always "polling" once a fetch
 * has succeeded, or "connecting" before the first one lands.
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

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const deadRef = useRef(false);

  useEffect(() => {
    deadRef.current = false;

    async function poll() {
      if (deadRef.current) return;
      try {
        const r = await fetch(`/api/stocks/${sym}/quote`);
        if (r.ok) {
          const d = await r.json();
          if (d.current_price) {
            setTick({
              price: d.current_price,
              change_pct: d.previous_close
                ? ((d.current_price - d.previous_close) / d.previous_close) * 100
                : null,
              volume: d.volume ?? null,
              ts: d.fetched_at ?? Date.now() / 1000,
            });
            setStatus("polling");
          }
        }
      } catch {
        /* silent — keep showing last value */
      }
    }

    poll();
    pollRef.current = setInterval(poll, 30_000);

    return () => {
      deadRef.current = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [sym]);

  return { tick, status };
}
