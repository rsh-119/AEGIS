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

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  is_pro: boolean;
  created_at: string;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login:    (email: string, password: string) => Promise<void>;
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
    const res = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Login failed");
    }
    const user = await res.json();
    setState({ user, isLoading: false });
    await _syncGuestData();
  }, []);

  const register = useCallback(
    async (email: string, username: string, password: string) => {
      const res = await fetch(`${API}/api/auth/register`, {
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
      await fetch(`${API}/api/auth/logout`, { method: "POST", credentials: "include" });
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
    <AuthCtx.Provider value={{ ...state, login, register, logout, refreshUser }}>
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

async function _fetchMe(): Promise<User | null> {
  try {
    const res = await fetch(`${API}/api/auth/me`, { credentials: "include" });
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
    const res = await fetch(`${API}/api/auth/sync-guest-data`, {
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
