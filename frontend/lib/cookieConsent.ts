"use client";

/**
 * Cookie consent — a tiny pub/sub over localStorage, not a context provider.
 *
 * Why not React context: the choice has to be readable from `layout.tsx`
 * (to gate <Analytics/>) before React has hydrated, and by any future
 * script (e.g. a Sentry init) that runs outside the component tree. A
 * module-level store with a subscribe() hook keeps that possible without
 * threading a provider through the root shell twice.
 */

export type ConsentChoice = "all" | "necessary";
const STORAGE_KEY = "aegis-cookie-consent";
const STORAGE_VERSION = 1; // bump to re-prompt everyone (e.g. policy change)

interface StoredConsent {
  choice: ConsentChoice;
  version: number;
  decidedAt: string; // ISO timestamp — useful if this ever needs an audit trail
}

function safeRead(): StoredConsent | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredConsent;
    if (parsed.version !== STORAGE_VERSION) return null; // stale — re-prompt
    return parsed;
  } catch {
    return null; // private browsing / storage blocked — treat as undecided
  }
}

/** Null = no decision recorded yet (or storage unavailable) — banner should show. */
export function getConsent(): ConsentChoice | null {
  return safeRead()?.choice ?? null;
}

export function setConsent(choice: ConsentChoice) {
  try {
    const record: StoredConsent = { choice, version: STORAGE_VERSION, decidedAt: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    // Storage unavailable — the choice just won't persist across reloads.
    // Fail open rather than throwing from a banner click.
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: choice }));
}

const EVENT = "aegis-cookie-consent-change";

/** Re-renders callers (e.g. the Analytics gate) when consent changes without a reload. */
export function subscribeConsent(cb: (choice: ConsentChoice) => void): () => void {
  const handler = (e: Event) => cb((e as CustomEvent<ConsentChoice>).detail);
  window.addEventListener(EVENT, handler);
  return () => window.removeEventListener(EVENT, handler);
}
