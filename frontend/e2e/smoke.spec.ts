import { test, expect, stubApi, FREE_USER, PRO_USER } from "./fixtures";

/**
 * Core user journeys against the real production build.
 *
 * Scope is deliberately small. These cover the paths where a break is
 * invisible to `tsc` and to `next build` — client-side hydration, the auth
 * bootstrap, gated rendering, and the failure states — and nothing else.
 */

test.describe("public pages render", () => {
  test("homepage loads and hydrates", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    await stubApi(page);
    await page.goto("/");

    await expect(page.locator("body")).toBeVisible();
    await expect(page.locator("header").first()).toBeVisible();
    expect(errors, `uncaught page errors: ${errors.join("\n")}`).toEqual([]);
  });

  test("the hardened CSP does not block the app's own scripts", async ({ page }) => {
    // Dropping 'unsafe-eval' from script-src is only safe if nothing in the
    // production bundle evals. A violation here means React never hydrates and
    // the whole app is static HTML.
    const violations: string[] = [];
    page.on("console", (m) => {
      const t = m.text();
      if (/Content Security Policy|Refused to (execute|evaluate|load)/i.test(t)) {
        violations.push(t);
      }
    });

    await stubApi(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    expect(violations, `CSP blocked something: ${violations.join("\n")}`).toEqual([]);
  });

  test("security headers are present on a real response", async ({ page }) => {
    await stubApi(page);
    const res = await page.goto("/");
    const h = res!.headers();

    expect(h["x-frame-options"]).toBe("DENY");
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["strict-transport-security"]).toContain("max-age=");
    expect(h["content-security-policy"]).toBeTruthy();
    expect(
      h["content-security-policy"],
      "'unsafe-eval' is back in the production CSP"
    ).not.toContain("unsafe-eval");
    expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  });

  test("stock page renders quote data", async ({ page }) => {
    await stubApi(page);
    await page.goto("/stock/TCS.NS");
    await expect(page.getByText(/Tata Consultancy Services/i).first()).toBeVisible();
  });

  test("login page renders its form", async ({ page }) => {
    await stubApi(page);
    await page.goto("/login");
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });
});

test.describe("authentication", () => {
  test("an anonymous visitor is not shown as signed in", async ({ page }) => {
    await stubApi(page, { user: null });
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(new RegExp(FREE_USER.username, "i"))).toHaveCount(0);
  });

  test("login posts to the SAME ORIGIN, never to NEXT_PUBLIC_API_URL", async ({ page }) => {
    // The regression this guards is invisible locally and fatal in production:
    // session cookies are SameSite=Strict, so a cross-site login request never
    // receives them.
    const authUrls: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/auth/")) authUrls.push(r.url());
    });

    await stubApi(page);
    await page.route("**/api/auth/login", (r) =>
      r.fulfill({ status: 200, contentType: "application/json",
                  body: JSON.stringify(FREE_USER) })
    );

    await page.goto("/login");
    await page.locator('input[type="email"]').fill("free@aegis.test");
    await page.locator('input[type="password"]').fill("CorrectHorse1!x");
    await page.locator('button[type="submit"]').first().click();
    await page.waitForTimeout(1500);

    expect(authUrls.length, "no auth request was made at all").toBeGreaterThan(0);
    const origin = new URL(page.url()).origin;
    for (const u of authUrls) {
      expect(new URL(u).origin, `auth request went cross-origin: ${u}`).toBe(origin);
    }
  });

  test("a signed-in user is reflected in the UI, and logout clears it", async ({ page }) => {
    await stubApi(page, { user: FREE_USER });
    await page.goto("/account");
    await expect(page.getByText(FREE_USER.email).first()).toBeVisible();
  });
});

test.describe("Pro gating", () => {
  test("a free user sees the upgrade gate, not the feature", async ({ page }) => {
    await stubApi(page, { user: FREE_USER });
    await page.goto("/concall");
    await expect(page.getByText(/is a Pro feature/i).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /upgrade to pro/i }).first()).toBeVisible();
  });

  test("an anonymous visitor is gated too", async ({ page }) => {
    await stubApi(page, { user: null });
    await page.goto("/concall");
    await expect(page.getByText(/is a Pro feature/i).first()).toBeVisible();
  });

  test("a Pro user is not shown the gate", async ({ page }) => {
    await stubApi(page, { user: PRO_USER });
    await page.goto("/concall");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/is a Pro feature/i)).toHaveCount(0);
  });
});

test.describe("protected pages for anonymous visitors", () => {
  for (const path of ["/portfolio", "/watchlist", "/alerts"]) {
    test(`${path} renders without crashing when signed out`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(String(e)));

      await stubApi(page, { user: null });
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      await expect(page.locator("body")).toBeVisible();
      expect(errors, `${path} threw: ${errors.join("\n")}`).toEqual([]);
    });
  }
});

test.describe("API failure states", () => {
  test("a 500 from the backend does not white-screen the page", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    await stubApi(page);
    await page.route("**/api/**", (r) =>
      r.fulfill({ status: 500, contentType: "application/json",
                  body: JSON.stringify({ detail: "upstream down" }) })
    );

    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("header").first()).toBeVisible();
    expect(errors, `a backend 500 crashed the page: ${errors.join("\n")}`).toEqual([]);
  });

  test("a network failure degrades instead of crashing", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    await page.route("**/api/**", (r) => r.abort("failed"));
    await page.goto("/stock/TCS.NS");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("body")).toBeVisible();
    expect(errors, `an aborted API call crashed the page: ${errors.join("\n")}`).toEqual([]);
  });
});

test.describe("error boundaries", () => {
  test("a page-level render error keeps the app shell usable", async ({ page }) => {
    // Regression for a real gap this suite found: with no app/error.tsx, any
    // render error escaped to the global boundary, which replaces the whole
    // document — nav, footer and all — so one broken page was
    // indistinguishable from the entire site being down, with no way to
    // navigate out.
    await stubApi(page);
    await page.route("**/api/stocks/*/core**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: "{}" })
    );

    await page.goto("/stock/TCS.NS");
    await page.waitForLoadState("networkidle");

    await expect(
      page.locator("header").first(),
      "the root layout was torn down by a single page's error"
    ).toBeVisible();
    await expect(page.getByRole("link", { name: /go to dashboard/i })).toBeVisible();
  });

  test("an error boundary discloses no stack, message or internal path", async ({ page }) => {
    await stubApi(page);
    await page.route("**/api/stocks/*/core**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: "{}" })
    );

    await page.goto("/stock/TCS.NS");
    await page.waitForLoadState("networkidle");
    const body = (await page.locator("body").innerText()).toLowerCase();

    for (const leak of ["typeerror", "cannot read", "undefined is not", "at Object.", "/home/", "webpack"]) {
      expect(body, `the error screen leaked "${leak}"`).not.toContain(leak.toLowerCase());
    }
  });
});
