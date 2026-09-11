import { test as base, expect, type Page, type Route } from "@playwright/test";

/**
 * Deterministic API doubles.
 *
 * Every test installs these before navigating, so no test touches IndianAPI,
 * Groq, OpenRouter, NVIDIA, Gemini, Postgres or Redis. That is the point: an
 * E2E suite wired to a metered market-data API is a suite that goes red for
 * reasons unrelated to the code, and one wired to an LLM is also
 * non-deterministic.
 *
 * Ordering matters. Playwright matches route handlers MOST-RECENTLY-REGISTERED
 * first, so the catch-all is registered first and the specific handlers after
 * it. A test that wants a different answer just calls page.route() again.
 */

export const FREE_USER = {
  id: 1, email: "free@aegis.test", username: "freeuser", is_active: true,
  is_admin: false, is_pro: false, auth_provider: "local", has_password: true,
  is_2fa_enabled: false, avatar_url: null, created_at: "2026-01-01T00:00:00Z",
};

export const PRO_USER = { ...FREE_USER, id: 2, username: "prouser", is_pro: true };

export const QUOTE = {
  ticker: "TCS.NS", company_name: "Tata Consultancy Services",
  price: 3521.4, change: 12.3, change_pct: 0.35, previous_close: 3509.1,
  day_high: 3540, day_low: 3500, volume: 1234567, currency: "INR",
  market_cap: 12750000000000, pe_ratio: 28.4, sector: "IT",
};

export function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function stubApi(page: Page, opts: { user?: object | null } = {}) {
  const user = opts.user ?? null;

  // Catch-all FIRST — anything not handled below still gets a valid JSON
  // response instead of escaping to a real backend.
  await page.route("**/api/**", (r) => json(r, {}));

  // Market data. /core is the stock page's single bootstrap call — it must
  // return the real {quote, history, signals} envelope, not a bare quote, or
  // the page renders its error boundary instead of the stock.
  await page.route("**/api/market/**", (r) => json(r, {}));
  await page.route("**/api/stocks/search**", (r) => json(r, { results: [] }));
  await page.route("**/api/stocks/*/history**", (r) => json(r, { candles: [] }));
  await page.route("**/api/stocks/*/quote**", (r) => json(r, QUOTE));
  await page.route("**/api/stocks/*/stream**", (r) =>
    r.fulfill({ status: 200, contentType: "text/event-stream", body: "" })
  );
  await page.route("**/api/stocks/*/core**", (r) =>
    json(r, { quote: QUOTE, history: { ticker: QUOTE.ticker, candles: [] }, signals: [] })
  );

  // User data.
  await page.route("**/api/portfolio**", (r) => json(r, { empty: true, holdings: [] }));
  await page.route("**/api/watchlist**", (r) => json(r, []));
  await page.route("**/api/alerts**", (r) => json(r, []));

  // Auth — the bootstrap /me decides logged-in vs anonymous for the whole app.
  await page.route("**/api/auth/refresh", (r) => json(r, { detail: "no" }, 401));
  await page.route("**/api/auth/logout", (r) => json(r, { detail: "ok" }));
  await page.route("**/api/auth/me", (r) =>
    user ? json(r, user) : json(r, { detail: "Not authenticated" }, 401)
  );
}

export const test = base;
export { expect };
