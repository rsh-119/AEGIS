/**
 * lib/guestData.ts — the anonymous holdings/watchlist store.
 *
 * This is the only copy of an anonymous user's portfolio: it lives in
 * localStorage until a login imports it via POST /api/auth/sync-guest-data.
 * A bug here loses real user data with no server-side backup, which is why it
 * is worth testing directly rather than through a page.
 *
 * The payload shape also has to keep matching backend HoldingCreate /
 * WatchCreate (backend/app/schemas.py) — the backend rejects unknown fields'
 * neighbours silently enough that a drift shows up as "the import did
 * nothing", so the client-only `id` must not be sent.
 */
import { describe, expect, it, beforeEach } from "vitest";

import {
  addGuestHolding, getGuestHoldings, removeGuestHolding,
  addGuestWatch, getGuestWatchlist, removeGuestWatch, isGuestWatched,
  hasGuestData, guestDataPayload, clearGuestData,
} from "@/lib/guestData";

const HOLDING = {
  ticker: "TCS.NS", shares: 10, avg_price: 3500, buy_date: "2026-01-15",
  company_name: "Tata Consultancy Services", sector: "IT",
};

beforeEach(() => localStorage.clear());

describe("guest holdings", () => {
  it("round-trips a holding", () => {
    addGuestHolding(HOLDING);
    const [saved] = getGuestHoldings();
    expect(saved).toMatchObject(HOLDING);
    expect(saved.id, "every row needs a local id so it can be removed").toBeTruthy();
  });

  it("keeps rows distinct rather than overwriting", () => {
    addGuestHolding(HOLDING);
    addGuestHolding({ ...HOLDING, ticker: "INFY.NS" });
    expect(getGuestHoldings().map((h) => h.ticker)).toEqual(["TCS.NS", "INFY.NS"]);
    expect(new Set(getGuestHoldings().map((h) => h.id)).size).toBe(2);
  });

  it("removes only the targeted row", () => {
    addGuestHolding(HOLDING);
    addGuestHolding({ ...HOLDING, ticker: "INFY.NS" });
    const target = getGuestHoldings()[0];
    removeGuestHolding(target.id);
    expect(getGuestHoldings().map((h) => h.ticker)).toEqual(["INFY.NS"]);
  });

  it("survives corrupt storage instead of throwing", () => {
    localStorage.setItem("aegis_guest_holdings", "{not json");
    expect(getGuestHoldings()).toEqual([]);
  });
});

describe("guest watchlist", () => {
  it("round-trips and removes", () => {
    addGuestWatch({ ticker: "TCS.NS", target_price: 4000 });
    expect(getGuestWatchlist()).toHaveLength(1);
    removeGuestWatch(getGuestWatchlist()[0].id);
    expect(getGuestWatchlist()).toHaveLength(0);
  });

  it("refuses a duplicate ticker instead of adding a second row", () => {
    expect(addGuestWatch({ ticker: "TCS.NS" })).not.toBeNull();
    expect(
      addGuestWatch({ ticker: "TCS.NS", target_price: 9999 }),
      "a duplicate watch must return null — the backend's uq_watchlist_user_ticker " +
        "constraint would reject the second row on import anyway"
    ).toBeNull();
    expect(getGuestWatchlist()).toHaveLength(1);
  });

  it("reports membership for the watch-toggle UI", () => {
    expect(isGuestWatched("TCS.NS")).toBe(false);
    addGuestWatch({ ticker: "TCS.NS" });
    expect(isGuestWatched("TCS.NS")).toBe(true);
  });
});

describe("sync payload", () => {
  it("reports no data when storage is empty", () => {
    expect(hasGuestData()).toBe(false);
  });

  it("reports data once anything is stored", () => {
    addGuestWatch({ ticker: "TCS.NS" });
    expect(hasGuestData()).toBe(true);
  });

  it("omits the client-only id from what is POSTed to the backend", () => {
    addGuestHolding(HOLDING);
    addGuestWatch({ ticker: "INFY.NS", target_price: 1800 });
    const payload = guestDataPayload();

    for (const row of payload.holdings) {
      expect(row, "the local id must not be sent — it is not a backend field")
        .not.toHaveProperty("id");
    }
    for (const row of payload.watchlist) {
      expect(row).not.toHaveProperty("id");
    }
    expect(payload.holdings[0]).toMatchObject({
      ticker: "TCS.NS", shares: 10, avg_price: 3500, buy_date: "2026-01-15",
    });
    expect(payload.watchlist[0]).toMatchObject({ ticker: "INFY.NS", target_price: 1800 });
  });

  it("clearGuestData removes both stores", () => {
    addGuestHolding(HOLDING);
    addGuestWatch({ ticker: "INFY.NS" });
    clearGuestData();
    expect(getGuestHoldings()).toEqual([]);
    expect(getGuestWatchlist()).toEqual([]);
    expect(hasGuestData()).toBe(false);
  });
});
