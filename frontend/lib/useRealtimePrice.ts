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

const MAX_CONSECUTIVE_ERRORS = 3;
const POLL_INTERVAL_MS = 30_000;

/**
 * Live price via Server-Sent Events (backend: price_stream_service.py — one
 * shared poll loop per ticker, fanned out to every connected client, so N
 * open tabs no longer mean N independent /quote polls).
 *
 * Falls back to the old 30s fetch-poll of /quote if the stream can't connect
 * or drops repeatedly (EventSource retries forever on its own with no
 * give-up, so this hook enforces one: after MAX_CONSECUTIVE_ERRORS failures
 * it stops relying on SSE and switches to polling instead, e.g. for
 * corporate proxies/networks that block long-lived connections).
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

  useEffect(() => {
    let dead = false;
    let es: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let errorCount = 0;

    function applyTick(d: {
      price?: number; current_price?: number;
      change_pct?: number | null; previous_close?: number | null;
      volume?: number | null; ts?: number; fetched_at?: number;
    }) {
      const price = d.price ?? d.current_price;
      if (price == null) return;
      setTick({
        price,
        change_pct: d.change_pct != null
          ? d.change_pct
          : d.previous_close
            ? ((price - d.previous_close) / d.previous_close) * 100
            : null,
        volume: d.volume ?? null,
        ts: d.ts ?? d.fetched_at ?? Date.now() / 1000,
      });
    }

    async function pollOnce() {
      if (dead) return;
      try {
        const r = await fetch(`/api/stocks/${sym}/quote`);
        if (r.ok) {
          applyTick(await r.json());
          setStatus("polling");
        }
      } catch {
        /* silent — keep showing last value */
      }
    }

    function startPolling() {
      if (pollTimer) return;
      setStatus("polling");
      pollOnce();
      pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
    }

    function startStream() {
      es = new EventSource(`/api/stocks/${sym}/stream`);

      es.onmessage = (ev) => {
        if (dead) return;
        errorCount = 0;
        try {
          applyTick(JSON.parse(ev.data));
          setStatus("sse");
        } catch {
          /* malformed frame — ignore, wait for the next one */
        }
      };

      es.onerror = () => {
        if (dead) return;
        errorCount += 1;
        if (errorCount >= MAX_CONSECUTIVE_ERRORS) {
          es?.close();
          es = null;
          startPolling();   // fall back — SSE isn't reaching this client
        }
      };
    }

    startStream();

    return () => {
      dead = true;
      es?.close();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [sym]);

  return { tick, status };
}
