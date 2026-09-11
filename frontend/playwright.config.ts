import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a real production build.
 *
 * Deterministic by construction: every /api/* call is fulfilled by a route
 * handler in e2e/fixtures.ts, so nothing here depends on IndianAPI, Groq,
 * OpenRouter, NVIDIA, Gemini, Postgres or Redis being reachable. That is the
 * point — an E2E suite that talks to a metered market-data API is a suite that
 * goes red for reasons unrelated to the code.
 *
 * `next start` is used rather than `next dev` so the CSP, the security
 * headers, the static prerendering and the bundle under test are the ones that
 * actually ship. (next start warns about `output: "standalone"`; it still
 * serves correctly, and standalone itself is covered by the Docker checks.)
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npx next start -p 3100",
        url: "http://127.0.0.1:3100",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
