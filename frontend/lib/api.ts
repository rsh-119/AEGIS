// lib/api.ts — typed fetch helpers + formatters for the AEGIS frontend

// Read the stored token without importing the AuthContext (avoids circular deps).
function _getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aegis_access_token");
}

function _authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = _getToken();
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

// Singleton promise — prevents parallel 401s from triggering multiple refresh calls
let _refreshing: Promise<boolean> | null = null;

async function _tryRefresh(): Promise<boolean> {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    const refresh = localStorage.getItem("aegis_refresh_token");
    if (!refresh) return false;
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      localStorage.setItem("aegis_access_token", data.access_token);
      localStorage.setItem("aegis_refresh_token", data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      _refreshing = null;
    }
  })();
  return _refreshing;
}

export const fetcher = async (url: string) => {
  let r = await fetch(url, { headers: _authHeaders() });
  if (r.status === 401) {
    const ok = await _tryRefresh();
    if (ok) r = await fetch(url, { headers: _authHeaders() });
  }
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};

async function _request(method: string, url: string, body?: unknown): Promise<Response> {
  const headers = _authHeaders(body !== undefined ? { "Content-Type": "application/json" } : {});
  const init: RequestInit = { method, headers, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) };
  let r = await fetch(url, init);
  if (r.status === 401) {
    const ok = await _tryRefresh();
    if (ok) r = await fetch(url, { ...init, headers: _authHeaders(body !== undefined ? { "Content-Type": "application/json" } : {}) });
  }
  return r;
}

export async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await _request("POST", url, body);
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed (${r.status})`);
  }
  return r.json();
}

export async function patch<T>(url: string, body: unknown): Promise<T> {
  const r = await _request("PATCH", url, body);
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed (${r.status})`);
  }
  return r.json();
}

export async function del(url: string) {
  const r = await _request("DELETE", url);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

// ── formatters (INR-first) ────────────────────────────────────────────────────

export const inr = (v: number | null | undefined) =>
  v == null || isNaN(v)
    ? "—"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
      }).format(v);

const _fmt = (n: number, d = 2) =>
  new Intl.NumberFormat("en-IN", { maximumFractionDigits: d }).format(n);

export const inrCompact = (v: number | null | undefined) => {
  if (v == null || isNaN(v)) return "—";
  if (v >= 1e12) return `₹${_fmt(v / 1e12, 2)} L Cr`;  // ≥ 1 lakh crore
  if (v >= 1e9)  return `₹${_fmt(v / 1e7, 0)} Cr`;     // ≥ 100 crore — no decimals
  if (v >= 1e7)  return `₹${_fmt(v / 1e7, 2)} Cr`;     // ≥ 1 crore
  if (v >= 1e5)  return `₹${_fmt(v / 1e5, 2)} L`;      // ≥ 1 lakh
  return inr(v);
};

export const pct = (v: number | null | undefined) =>
  v == null || isNaN(v) ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

export const signCls = (v: number | null | undefined) =>
  (v ?? 0) >= 0 ? "text-up" : "text-down";

export const num = (v: number | null | undefined, d = 2) =>
  v == null || isNaN(v) ? "—" : v.toFixed(d);
