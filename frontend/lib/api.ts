// lib/api.ts — typed fetch helpers + formatters for the AEGIS frontend
//
// Auth is cookie-based (httpOnly aegis_access/aegis_refresh cookies set by
// the backend) — every request needs `credentials: "include"` so the
// browser attaches them; there is no token to read or attach by hand
// anymore. See lib/auth.tsx for the AuthProvider that consumes this file's
// _tryRefresh via the same 401-retry path used here.

// Singleton promise — prevents parallel 401s from triggering multiple refresh calls
let _refreshing: Promise<boolean> | null = null;

export async function tryRefresh(): Promise<boolean> {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      _refreshing = null;
    }
  })();
  return _refreshing;
}

export const fetcher = async (url: string) => {
  let r = await fetch(url, { credentials: "include" });
  if (r.status === 401) {
    const ok = await tryRefresh();
    if (ok) r = await fetch(url, { credentials: "include" });
  }
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};

async function _request(method: string, url: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = body !== undefined ? { "Content-Type": "application/json" } : {};
  const init: RequestInit = {
    method,
    headers,
    credentials: "include",
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
  let r = await fetch(url, init);
  if (r.status === 401) {
    const ok = await tryRefresh();
    if (ok) r = await fetch(url, init);
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

/** DELETE that treats a 404 as an already-achieved success (stale list,
 * double-click, etc.) instead of an error — the desired end state (item
 * gone) is already true. Returns an error message only for genuine failures. */
export async function deleteTolerant404(url: string): Promise<{ ok: true } | { ok: false; message: string }> {
  try {
    await del(url);
    return { ok: true };
  } catch (e) {
    if (e instanceof Error && e.message.includes("404")) return { ok: true };
    return { ok: false, message: e instanceof Error ? e.message : "Request failed" };
  }
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
