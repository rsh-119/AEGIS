"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ACCESS_KEY  = "aegis_access_token";
const REFRESH_KEY = "aegis_refresh_token";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login:    (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout:   () => void;
  getToken: () => string | null;   // always returns the freshest access token
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthCtx = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isLoading: true,
  });

  // ── Bootstrap: restore token from localStorage, validate via /me ──────────
  useEffect(() => {
    const access  = localStorage.getItem(ACCESS_KEY);
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (!access && !refresh) {
      setState(s => ({ ...s, isLoading: false }));
      return;
    }
    (async () => {
      let token = access;
      // Try existing access token first; refresh if expired
      if (token) {
        const me = await _fetchMe(token);
        if (me) {
          setState({ user: me, accessToken: token, isLoading: false });
          return;
        }
      }
      // Access token invalid/expired — try refresh
      if (refresh) {
        try {
          const res = await fetch(`${API}/api/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refresh }),
          });
          if (res.ok) {
            const data = await res.json();
            localStorage.setItem(ACCESS_KEY, data.access_token);
            localStorage.setItem(REFRESH_KEY, data.refresh_token);
            const me = await _fetchMe(data.access_token);
            setState({ user: me, accessToken: data.access_token, isLoading: false });
            return;
          }
        } catch { /* fall through */ }
      }
      // Both failed — clear and show login
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
      setState({ user: null, accessToken: null, isLoading: false });
    })();
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Login failed");
    }
    const data = await res.json();
    localStorage.setItem(ACCESS_KEY, data.access_token);
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    const me = await _fetchMe(data.access_token);
    setState({ user: me, accessToken: data.access_token, isLoading: false });
  }, []);

  const register = useCallback(
    async (email: string, username: string, password: string) => {
      const res = await fetch(`${API}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, username, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Registration failed");
      }
      const data = await res.json();
      localStorage.setItem(ACCESS_KEY, data.access_token);
      localStorage.setItem(REFRESH_KEY, data.refresh_token);
      const me = await _fetchMe(data.access_token);
      setState({ user: me, accessToken: data.access_token, isLoading: false });
    },
    []
  );

  const logout = useCallback(() => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    setState({ user: null, accessToken: null, isLoading: false });
  }, []);

  const getToken = useCallback(() => {
    return state.accessToken ?? localStorage.getItem(ACCESS_KEY);
  }, [state.accessToken]);

  return (
    <AuthCtx.Provider value={{ ...state, login, register, logout, getToken }}>
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

async function _fetchMe(token: string): Promise<User | null> {
  try {
    const res = await fetch(`${API}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
