/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import path from "node:path";

// Component/unit tests for the business-critical frontend logic — the auth
// client, the Pro gate, and the guest-data store that feeds
// POST /api/auth/sync-guest-data.
//
// Deliberately NOT a "render every component" suite. These cover behaviour
// where a silent regression costs something real: an auth call going
// cross-origin (which breaks SameSite=Strict cookies in production only), a
// Pro feature rendering for a free user, or guest holdings being cleared
// before the server confirmed the import.
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "./") },
  },
  // JSX is transformed here rather than by @vitejs/plugin-react: that plugin
  // exists for Fast Refresh, which tests do not use, and its current release
  // drags in @babel/plugin-transform-runtime@8.0.0-rc, which conflicts with the
  // @babel/core 7 already in this tree.
  //
  // tsconfig.json says `"jsx": "preserve"` because Next.js compiles JSX
  // itself, so the bundler here has to be told explicitly to use the automatic
  // runtime — otherwise it hands raw JSX to the parser and every .tsx test
  // fails to load. `oxc` is the Vite 7 / Rolldown key (Vitest 4); on Vitest 3
  // the equivalent was `esbuild: { jsx: "automatic" }`.
  oxc: { jsx: { runtime: "automatic", importSource: "react" } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    // e2e/ is Playwright's; it must not be collected here.
    exclude: ["node_modules/**", "e2e/**", ".next/**"],
    restoreMocks: true,
    clearMocks: true,
  },
});
