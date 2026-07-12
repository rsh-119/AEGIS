"use client";

// useSWRConfig().mutate, not the bare `mutate` export — the app runs on a
// custom SWR cache provider (lib/swr-config), and the global mutate operates
// on the default cache instead, so revalidation silently no-ops.
import useSWR, { useSWRConfig } from "swr";
import { useRouter } from "next/navigation";
import { fetcher, post, del } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type WatchItem = { id: number; ticker: string; company_name: string };

export function useWatchlist() {
  const { user } = useAuth();
  const router = useRouter();
  const { mutate } = useSWRConfig();

  // Don't even attempt the request when logged out — avoids a guaranteed 401.
  const { data } = useSWR<{ items: WatchItem[] }>(user ? "/api/watchlist" : null, fetcher, {
    revalidateOnFocus: false,
  });

  const items = data?.items ?? [];
  const byTicker = new Map(items.map((i) => [i.ticker, i.id]));

  function isWatched(ticker: string) {
    return byTicker.has(ticker);
  }

  async function toggle(ticker: string, name: string) {
    if (!user) {
      router.push("/login");
      return;
    }
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
    mutate("/api/watchlist");
  }

  return { isWatched, toggle, isLoggedIn: !!user };
}
