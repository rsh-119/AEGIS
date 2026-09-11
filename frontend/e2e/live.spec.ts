import { test, expect, type Page } from "@playwright/test";

/**
 * LIVE validation against a real running stack — no stubs, opt-in.
 *
 * Everything in e2e/smoke.spec.ts is deterministic and offline: it stubs every
 * /api/* call, so it can run anywhere. This file is the opposite and
 * deliberately so — it drives the real Next.js production server, the real
 * FastAPI backend, real Postgres and real Redis, which is the only way to
 * observe things that only exist end-to-end: actual Set-Cookie flags, the
 * same-origin rewrite, CSP enforcement in a real browser, and hydration.
 *
 * It is SKIPPED unless E2E_LIVE=1, because it needs infrastructure and two
 * seeded accounts. Running it:
 *
 *   docker compose up -d db redis
 *   (cd backend && uvicorn app.main:app --port 8000)      # APP_ENV=development
 *   (cd frontend && npm run build && npx next start -p 3100)
 *   # seed audit@example.com (free) and auditpro@example.com (Pro),
 *   # both with password AuditPass123!x
 *   E2E_LIVE=1 E2E_BASE_URL=http://127.0.0.1:3100 npx playwright test e2e/live.spec.ts
 *
 * Note the accounts use @example.com, not a .test domain: pydantic's EmailStr
 * rejects reserved TLDs, so a .test address fails validation before login is
 * ever attempted.
 */
test.skip(
  process.env.E2E_LIVE !== "1",
  "live stack tests — set E2E_LIVE=1 with a running backend+frontend (see file header)"
);


const PAGES = ["/", "/market", "/portfolio", "/watchlist", "/alerts",
               "/stock/TCS.NS", "/ask", "/concall", "/pricing", "/login", "/mf"];

type Probe = { csp: string[]; errors: string[]; hydration: string[] };
function watch(page: Page): Probe {
  const p: Probe = { csp: [], errors: [], hydration: [] };
  page.on("console", (m) => {
    const t = m.text();
    if (/Content Security Policy|Refused to (execute|evaluate|load|connect)/i.test(t)) p.csp.push(t);
    else if (m.type() === "error" && !/Failed to load resource/i.test(t)) p.errors.push(t);
    if (/Hydration failed|did not match|hydrating/i.test(t)) p.hydration.push(t);
  });
  page.on("pageerror", (e) => p.errors.push(String(e)));
  return p;
}

for (const path of PAGES) {
  test(`LIVE ${path}`, async ({ page }) => {
    const p = watch(page);
    const res = await page.goto(path, { waitUntil: "networkidle" });
    expect(res?.status(), `${path} HTTP status`).toBeLessThan(400);
    await expect(page.locator("header").first()).toBeVisible();
    expect(p.csp, `${path} CSP violations`).toEqual([]);
    expect(p.hydration, `${path} hydration errors`).toEqual([]);
    expect(p.errors, `${path} console/page errors`).toEqual([]);
  });
}

test("LIVE login -> protected read -> logout, all same-origin", async ({ page }) => {
  const p = watch(page);
  const authUrls: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/api/auth/")) authUrls.push(r.url()); });

  // Watch the login response itself. Without this, a 429 from AUTH_LIMIT
  // (5/15min per IP — easily hit by repeated local runs) surfaces further down
  // as the far more alarming "no session cookies were set", which reads like a
  // broken auth flow rather than a working rate limiter.
  const loginStatus = page.waitForResponse(
    (r) => r.url().includes("/api/auth/login") && r.request().method() === "POST"
  );

  await page.goto("/login");
  await page.locator('input[type="email"]').fill("audit@example.com");
  await page.locator('input[type="password"]').fill("AuditPass123!x");
  await page.locator('button[type="submit"]').first().click();

  const res = await loginStatus;
  expect(
    res.status(),
    res.status() === 429
      ? "login was rate-limited (AUTH_LIMIT 5/15min per IP). That is the limiter " +
        "working, not an auth defect — clear the bucket and re-run: " +
        "docker exec aegis-redis-1 redis-cli -n 3 FLUSHDB"
      : `login failed: HTTP ${res.status()}`
  ).toBe(200);
  await page.waitForTimeout(1500);

  // Cookies must be httpOnly + SameSite=Strict and host-only.
  const cookies = (await page.context().cookies()).filter((c) => c.name.startsWith("aegis_"));
  expect(cookies.length, "no aegis_* session cookies were set by login").toBeGreaterThan(0);
  for (const c of cookies) {
    expect(c.httpOnly, `${c.name} is not httpOnly`).toBe(true);
    expect(c.sameSite, `${c.name} SameSite`).toBe("Strict");
    expect(c.domain.startsWith("."), `${c.name} is not host-only`).toBe(false);
  }
  const refresh = cookies.find((c) => c.name.includes("refresh"));
  if (refresh) expect(refresh.path, "refresh cookie path scope").toContain("/api/auth");

  const origin = new URL(page.url()).origin;
  expect(authUrls.length).toBeGreaterThan(0);
  for (const u of authUrls) expect(new URL(u).origin, `cross-origin auth: ${u}`).toBe(origin);

  await page.goto("/portfolio", { waitUntil: "networkidle" });
  const me = await page.evaluate(async () =>
    (await fetch("/api/auth/me", { credentials: "include" })).status);
  expect(me, "authenticated /me after login").toBe(200);

  await page.goto("/account", { waitUntil: "networkidle" });
  await expect(page.getByText("audit@example.com").first()).toBeVisible();

  expect(p.csp, "CSP violations during the auth flow").toEqual([]);
  expect(p.errors, "console/page errors during the auth flow").toEqual([]);
});

test("LIVE Pro gate blocks a free account", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("audit@example.com");
  await page.locator('input[type="password"]').fill("AuditPass123!x");
  await page.locator('button[type="submit"]').first().click();
  await page.waitForTimeout(2500);
  await page.goto("/concall", { waitUntil: "networkidle" });
  await expect(page.getByText(/is a Pro feature/i).first()).toBeVisible();
});

test("LIVE Pro account is not gated", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill("auditpro@example.com");
  await page.locator('input[type="password"]').fill("AuditPass123!x");
  await page.locator('button[type="submit"]').first().click();
  await page.waitForTimeout(2500);
  await page.goto("/concall", { waitUntil: "networkidle" });
  await expect(page.getByText(/is a Pro feature/i)).toHaveCount(0);
});
