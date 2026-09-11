// lib/twoFactor.ts — holds a pending pre_auth_token between login (or Google
// sign-in) diverting into the 2FA challenge and the /verify-2fa page
// completing it.
//
// sessionStorage, not a URL query param: the token is short-lived (5 min,
// single-purpose) and explicitly re-sent by the verify-2fa page's own POST
// body — putting it in the URL instead would leak it into browser history
// and any Referer header sent from that page.

export const PRE_AUTH_TOKEN_KEY = "aegis_pre_auth_token";

export function setPendingPreAuthToken(token: string): void {
  try {
    sessionStorage.setItem(PRE_AUTH_TOKEN_KEY, token);
  } catch {
    // sessionStorage unavailable (private browsing, etc.) — verify-2fa page
    // will find nothing and bounce back to /login, same as an expired token.
  }
}

export function consumePendingPreAuthToken(): string | null {
  try {
    const token = sessionStorage.getItem(PRE_AUTH_TOKEN_KEY);
    if (token) sessionStorage.removeItem(PRE_AUTH_TOKEN_KEY);
    return token;
  } catch {
    return null;
  }
}
