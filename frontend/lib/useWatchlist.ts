"use client";

import useSWR, { mutate as globalMutate } from "swr";
import { fetcher, post, del } from "@/lib/api";

type WatchItem = { id: number; ticker: string; company_name: string };

export function useWatchlist() {
  const { data } = useSWR<{ items: WatchItem[] }>("/api/watchlist", fetcher, {
    revalidateOnFocus: false,
  });

  const items = data?.items ?? [];
  const byTicker = new Map(items.map((i) => [i.ticker, i.id]));

  function isWatched(ticker: string) {
    return byTicker.has(ticker);
  }

  async function toggle(ticker: string, name: string) {
    if (byTicker.has(ticker)) {
      await del(`/api/watchlist/${byTicker.get(ticker)}`);
    } else {
      try {
        await post("/api/watchlist", { ticker, company_name: name });
      } catch (e: unknown) {
        // 409 = already exists, safe to ignore
        if (!(e instanceof Error) || !e.message.includes("409")) throw e;
      }
    }
    globalMutate("/api/watchlist");
  }

  return { isWatched, toggle };
}
