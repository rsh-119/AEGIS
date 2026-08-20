// lib/guestData.ts — anonymous, browser-local holdings/watchlist storage.
//
// Mirrors backend HoldingCreate/WatchCreate exactly (backend/app/schemas.py)
// so a guest's data can be POSTed to /api/auth/sync-guest-data verbatim on
// login/register — see lib/auth.tsx for the caller and
// backend/app/routers/auth.py's sync_guest_data for the import side.
//
// Anonymous only: a logged-in user's holdings/watchlist live in Postgres via
// /api/portfolio and /api/watchlist, never here. Every reader of this module
// must gate on `!user` — see app/portfolio/page.tsx and app/watchlist/page.tsx.

const HOLDINGS_KEY = "aegis_guest_holdings";
const WATCHLIST_KEY = "aegis_guest_watchlist";

export interface GuestHolding {
  id: string; // client-generated, local only — never sent to the backend
  ticker: string;
  shares: number;
  avg_price: number;
  buy_date: string; // YYYY-MM-DD
  company_name?: string | null;
  sector?: string | null;
  notes?: string | null;
}

export interface GuestWatchItem {
  id: string; // client-generated, local only — never sent to the backend
  ticker: string;
  target_price?: number | null;
  company_name?: string | null;
}

function read<T>(key: string): T[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function write<T>(key: string, items: T[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(items));
  } catch {
    // storage full / private browsing — the add still reflects in this tab's
    // React state, it just won't survive a reload
  }
}

const uid = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// ── Holdings ──────────────────────────────────────────────────────────────

export function getGuestHoldings(): GuestHolding[] {
  return read<GuestHolding>(HOLDINGS_KEY);
}

export function addGuestHolding(h: Omit<GuestHolding, "id">): GuestHolding {
  const item: GuestHolding = { ...h, id: uid() };
  write(HOLDINGS_KEY, [...getGuestHoldings(), item]);
  return item;
}

export function removeGuestHolding(id: string): void {
  write(HOLDINGS_KEY, getGuestHoldings().filter((h) => h.id !== id));
}

// ── Watchlist ─────────────────────────────────────────────────────────────

export function getGuestWatchlist(): GuestWatchItem[] {
  return read<GuestWatchItem>(WATCHLIST_KEY);
}

export function isGuestWatched(ticker: string): boolean {
  return getGuestWatchlist().some((w) => w.ticker === ticker);
}

/** No-ops (returns null) if the ticker is already on the guest watchlist —
 * mirrors the backend's 409-on-duplicate behavior for logged-in users. */
export function addGuestWatch(w: Omit<GuestWatchItem, "id">): GuestWatchItem | null {
  if (isGuestWatched(w.ticker)) return null;
  const item: GuestWatchItem = { ...w, id: uid() };
  write(WATCHLIST_KEY, [...getGuestWatchlist(), item]);
  return item;
}

export function removeGuestWatch(id: string): void {
  write(WATCHLIST_KEY, getGuestWatchlist().filter((w) => w.id !== id));
}

// ── Sync (called once, right after login/register succeeds — see lib/auth.tsx) ──

export function hasGuestData(): boolean {
  return getGuestHoldings().length > 0 || getGuestWatchlist().length > 0;
}

/** Body for POST /api/auth/sync-guest-data (backend schemas.GuestDataSync)
 * — strips the client-only `id` field, which the backend doesn't know about
 * and HoldingCreate/WatchCreate don't declare. */
export function guestDataPayload() {
  return {
    holdings: getGuestHoldings().map(({ id: _id, ...rest }) => rest),
    watchlist: getGuestWatchlist().map(({ id: _id, ...rest }) => rest),
  };
}

/** Only call after a confirmed 2xx from sync-guest-data — see that
 * endpoint's docstring on why a failed sync must leave localStorage intact
 * for a retry on the next login. */
export function clearGuestData(): void {
  try {
    localStorage.removeItem(HOLDINGS_KEY);
    localStorage.removeItem(WATCHLIST_KEY);
  } catch {
    // ignore
  }
}
