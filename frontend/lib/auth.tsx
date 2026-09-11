"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { tryRefresh } from "./api";
import { guestDataPayload, hasGuestData, clearGuestData } from "./guestData";

// Auth calls go to SAME-ORIGIN /api/auth/* — deliberately, and not through
// NEXT_PUBLIC_API_URL. The session cookies the backend sets are
// SameSite=Strict, which means the browser will NOT attach them to a
// cross-site request; pointing these calls straight at the backend origin
// (e.g. https://aegis-backend-*.onrender.com) therefore breaks login the
// moment the frontend is served from a different host, silently and only in
// production. Every other call in the app already goes same-origin via
// lib/api.ts, and next.config.js's /api/:path* rewrite proxies the lot to
// FastAPI server-side, so the browser only ever sees one origin.
//
// Do not reintroduce an absolute base URL here without also changing the
// cookie's SameSite attribute in backend/app/core/auth.py — which would be a
// downgrade, not a fix.

// ── Types ─────────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  is_pro: boolean;
  auth_provider: string;     // "local" | "google"
  has_password: boolean;     // false for a Google-only account with no password set
  is_2fa_enabled: boolean;
  avatar_url: string | null; // data:image/webp;base64,... — see backend/app/core/avatar.py
  created_at: string;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
}

/** login()/loginWithGoogle() can't always complete a session in one call —
 * if the account has 2FA enabled, the backend returns a pre_auth_token
 * instead of cookies, and the caller must route to /verify-2fa before a
 * real session exists. See verifyTwoFactor below for the second step. */
export type LoginResult =
  | { requiresTwoFactor: false }
  | { requiresTwoFactor: true; preAuthToken: string };

interface AuthContextValue extends AuthState {
  login:    (email: string, password: string) => Promise<LoginResult>;
  loginWithGoogle: (credential: string) => Promise<LoginResult>;
  /** Completes a login that was diverted into the 2FA challenge — code is
   * either a live 6-digit TOTP code or an "XXXX-XXXX" backup code. */
  verifyTwoFactor: (preAuthToken: string, code: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout:   () => Promise<void>;
  /** Re-fetch /me and swap it into state — call after editing profile details
   * so the nav/account page reflect the change without a full re-login. */
  refreshUser: () => Promise<void>;
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthCtx = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
  });

  // ── Bootstrap: auth lives in httpOnly cookies, so just ask /me. If the
  // access cookie is expired, /me 401s — try one cookie-based refresh (which
  // rotates both cookies) and retry once before concluding logged-out. ──────
  useEffect(() => {
    (async () => {
      let me = await _fetchMe();
      if (!me) {
        const ok = await tryRefresh();
        if (ok) me = await _fetchMe();
      }
      setState({ user: me, isLoading: false });
    })();
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Login failed");
    }
    return _handleLoginResponse(await res.json(), setState);
  }, []);

  const loginWithGoogle = useCallback(async (credential: string) => {
    const res = await fetch("/api/auth/google", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Google sign-in failed");
    }
    return _handleLoginResponse(await res.json(), setState);
  }, []);

  const verifyTwoFactor = useCallback(async (preAuthToken: string, code: string) => {
    const res = await fetch("/api/auth/2fa/verify-login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pre_auth_token: preAuthToken, code }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Verification failed");
    }
    const user = await res.json();
    setState({ user, isLoading: false });
    await _syncGuestData();
  }, []);

  const register = useCallback(
    async (email: string, username: string, password: string) => {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, username, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Registration failed");
      }
      const user = await res.json();
      setState({ user, isLoading: false });
      await _syncGuestData();
    },
    []
  );

  const logout = useCallback(async () => {
    // Stateful now (blocklists the current access token server-side) — must
    // actually hit the endpoint, not just clear local state.
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch {
      // best-effort — cookies are httpOnly so we can't clear them client-side
      // regardless, and the user should see themselves logged out either way.
    }
    setState({ user: null, isLoading: false });
  }, []);

  const refreshUser = useCallback(async () => {
    const me = await _fetchMe();
    if (me) setState(s => ({ ...s, user: me }));
  }, []);

  return (
    <AuthCtx.Provider value={{ ...state, login, loginWithGoogle, verifyTwoFactor, register, logout, refreshUser }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Shared by login() and loginWithGoogle() — both endpoints return either a
 * full user object (real session, cookies already set by the response) or
 * {requires_2fa, pre_auth_token} (password/Google verified, second factor
 * still pending). Only the former touches state or syncs guest data — a
 * pre_auth_token is not a session, so nothing should act like one yet. */
function _handleLoginResponse(
  data: any,
  setState: (s: AuthState) => void
): LoginResult | Promise<LoginResult> {
  if (data?.requires_2fa) {
    return { requiresTwoFactor: true, preAuthToken: data.pre_auth_token };
  }
  setState({ user: data as User, isLoading: false });
  return _syncGuestData().then(() => ({ requiresTwoFactor: false as const }));
}

async function _fetchMe(): Promise<User | null> {
  try {
    const res = await fetch("/api/auth/me", { credentials: "include" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/** Imports this browser's guest holdings/watchlist (lib/guestData.ts) into
 * the account that just logged in or registered — best-effort, and
 * deliberately silent (no toast) so a sync hiccup never overshadows a
 * successful login. Only clears localStorage on a confirmed 2xx; leaves it
 * intact otherwise so the same data gets retried on the next login (see
 * sync-guest-data's docstring in backend/app/routers/auth.py). Portfolio/
 * watchlist pages pick up the imported rows on their own — their SWR keys
 * go from `null` to `/api/portfolio` / `/api/watchlist` the moment `user`
 * is set above, which fetches fresh. */
async function _syncGuestData(): Promise<void> {
  if (!hasGuestData()) return;
  try {
    const res = await fetch("/api/auth/sync-guest-data", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(guestDataPayload()),
    });
    if (res.ok) clearGuestData();
  } catch {
    // network error — guest data stays put, retried next successful login
  }
}
