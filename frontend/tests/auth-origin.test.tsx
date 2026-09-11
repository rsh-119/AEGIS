/**
 * The auth client must call SAME-ORIGIN /api/auth/*.
 *
 * This is the one frontend regression that cannot be caught by a build, a type
 * check, or by clicking through locally: the backend sets its session cookies
 * with SameSite=Strict, so a cross-site fetch to the backend origin drops them
 * silently. Locally, frontend and backend are both "localhost", so nothing
 * looks wrong. It only breaks once the app is served from Vercel and the
 * backend from Render — i.e. in production, on the login path, for everyone.
 *
 * `lib/auth.tsx` previously built these URLs from NEXT_PUBLIC_API_URL while
 * every other call in the app used a relative path. These tests pin the
 * corrected behaviour by inspecting the URL each action actually fetches.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

import { AuthProvider, useAuth } from "@/lib/auth";

const USER = {
  id: 1, email: "a@b.com", username: "a", is_active: true, is_admin: false,
  is_pro: false, auth_provider: "local", has_password: true,
  is_2fa_enabled: false, avatar_url: null, created_at: "2026-01-01T00:00:00Z",
};

let calls: string[] = [];

function mockFetch(impl?: (url: string) => Response) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push(url);
    if (impl) return impl(url);
    return new Response(JSON.stringify(USER), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** Renders a probe that invokes one AuthContext action on click. */
function Probe({ action }: { action: (a: ReturnType<typeof useAuth>) => Promise<unknown> }) {
  const auth = useAuth();
  return (
    <button onClick={() => { void action(auth).catch(() => {}); }}>go</button>
  );
}

async function clickAction(action: (a: ReturnType<typeof useAuth>) => Promise<unknown>) {
  render(
    <AuthProvider>
      <Probe action={action} />
    </AuthProvider>
  );
  await userEvent.click(await screen.findByRole("button", { name: "go" }));
}

function assertSameOrigin(url: string) {
  expect(
    url.startsWith("/"),
    `auth called "${url}" — an absolute URL makes the request cross-site, and ` +
      `SameSite=Strict session cookies are not sent cross-site, so this breaks ` +
      `login in production while still working locally`
  ).toBe(true);
  expect(url).not.toMatch(/^https?:\/\//);
}

beforeEach(() => { calls = []; });

describe("auth client request origin", () => {
  it("bootstraps /me against the same origin", async () => {
    mockFetch();
    render(<AuthProvider><span>ok</span></AuthProvider>);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(calls.some((u) => u.includes("/api/auth/me"))).toBe(true);
    calls.forEach(assertSameOrigin);
  });

  it.each([
    ["login",        (a: any) => a.login("a@b.com", "pw"),                    "/api/auth/login"],
    ["register",     (a: any) => a.register("a@b.com", "a", "pw"),            "/api/auth/register"],
    ["google login", (a: any) => a.loginWithGoogle("cred"),                   "/api/auth/google"],
    ["2FA verify",   (a: any) => a.verifyTwoFactor("pre", "123456"),          "/api/auth/2fa/verify-login"],
    ["logout",       (a: any) => a.logout(),                                  "/api/auth/logout"],
  ])("calls %s same-origin", async (_name, action, expected) => {
    mockFetch();
    await clickAction(action);
    await waitFor(() => expect(calls.some((u) => u.includes(expected))).toBe(true));
    calls.forEach(assertSameOrigin);
  });

  it("ignores NEXT_PUBLIC_API_URL entirely", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://backend.example.com");
    mockFetch();
    await clickAction((a: any) => a.login("a@b.com", "pw"));
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(
      calls.some((u) => u.includes("backend.example.com")),
      "NEXT_PUBLIC_API_URL leaked back into a browser-side auth call"
    ).toBe(false);
  });

  it("sends credentials on every auth request so cookies are attached", async () => {
    const fn = mockFetch();
    await clickAction((a: any) => a.login("a@b.com", "pw"));
    await waitFor(() => expect(fn).toHaveBeenCalled());
    for (const [url, init] of fn.mock.calls as any[]) {
      if (String(url).includes("/api/auth/")) {
        expect(init?.credentials, `${url} did not set credentials:"include"`).toBe("include");
      }
    }
  });
});

describe("guest-data sync on login", () => {
  it("only clears local guest data after a confirmed 2xx", async () => {
    localStorage.setItem(
      "aegis_guest_watchlist",
      JSON.stringify([{ id: "1", ticker: "TCS.NS" }])
    );

    mockFetch((url) => {
      if (url.includes("sync-guest-data")) {
        return new Response("boom", { status: 500 });
      }
      return new Response(JSON.stringify(USER), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    });

    await clickAction((a: any) => a.login("a@b.com", "pw"));
    await waitFor(() =>
      expect(calls.some((u) => u.includes("sync-guest-data"))).toBe(true)
    );

    expect(
      localStorage.getItem("aegis_guest_watchlist"),
      "guest data was cleared despite the import failing — the user's " +
        "holdings/watchlist are gone with nothing on the server"
    ).not.toBeNull();
  });

  it("clears local guest data once the import succeeds", async () => {
    localStorage.setItem(
      "aegis_guest_watchlist",
      JSON.stringify([{ id: "1", ticker: "TCS.NS" }])
    );
    mockFetch();
    await clickAction((a: any) => a.login("a@b.com", "pw"));
    await waitFor(() =>
      expect(localStorage.getItem("aegis_guest_watchlist")).toBeNull()
    );
  });
});
