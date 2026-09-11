"use client";

import { useEffect, useRef } from "react";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (resp: { credential: string }) => void }) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
        };
      };
    };
  }
}

let _scriptPromise: Promise<void> | null = null;

function loadGisScript(): Promise<void> {
  if (_scriptPromise) return _scriptPromise;
  _scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
    if (existing) return resolve();
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load Google Sign-In"));
    document.head.appendChild(script);
  });
  return _scriptPromise;
}

/**
 * Renders Google's own button asset via Google Identity Services (GIS) — a
 * deliberate exception to components/ui/button.tsx's "only default/ghost
 * variants" rule, since Google's branding guidelines require using their
 * rendered button, not a custom-styled one. Renders nothing if
 * NEXT_PUBLIC_GOOGLE_CLIENT_ID isn't set — same disabled-until-configured
 * pattern as the rest of this app's optional integrations.
 */
export function GoogleSignInButton({ onCredential }: { onCredential: (credential: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!CLIENT_ID || !ref.current) return;
    let cancelled = false;
    loadGisScript()
      .then(() => {
        if (cancelled || !window.google || !ref.current) return;
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (resp) => onCredential(resp.credential),
        });
        window.google.accounts.id.renderButton(ref.current, {
          theme: "outline",
          size: "large",
          width: 320,
          text: "continue_with",
        });
      })
      .catch(() => {
        // Script failed to load (offline, ad-blocker, etc.) — the button
        // simply never renders; email/password sign-in is unaffected.
      });
    return () => {
      cancelled = true;
    };
  }, [onCredential]);

  if (!CLIENT_ID) return null;

  return (
    <div className="flex flex-col items-center gap-3">
      <div ref={ref} />
      <div className="flex w-full items-center gap-3 text-xs text-muted">
        <div className="h-px flex-1 bg-border" />
        or
        <div className="h-px flex-1 bg-border" />
      </div>
    </div>
  );
}
