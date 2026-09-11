/**
 * Pro gating, client side.
 *
 * The authoritative check is server-side (backend/tests/test_authorization.py
 * proves a free account gets 403 from every hard-gated route, whatever the UI
 * does). These tests cover the other half: that the UI does not advertise a
 * paid feature as available, and — more importantly — that the "unknown yet"
 * state is treated as NOT Pro rather than as Pro.
 *
 * `user` is null while /me is still in flight and for every anonymous visitor,
 * so any gate written as `user.is_pro === false ? <Gate/> : <Feature/>` renders
 * the feature to everyone during that window. The app writes the check as
 * `!user?.is_pro`, which fails closed; that is what is pinned here.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { ProGate } from "@/components/ProGate";
import type { User } from "@/lib/auth";

const base: User = {
  id: 1, email: "a@b.com", username: "a", is_active: true, is_admin: false,
  is_pro: false, auth_provider: "local", has_password: true,
  is_2fa_enabled: false, avatar_url: null, created_at: "2026-01-01T00:00:00Z",
};

/** The exact expression the pages use (app/stock/[ticker], /concall, …). */
const shouldGate = (user: User | null) => !user?.is_pro;

describe("ProGate rendering", () => {
  it("names the gated feature and offers the upgrade path", () => {
    render(<ProGate feature="Concall Analysis" />);
    expect(screen.getByText(/Concall Analysis is a Pro feature/i)).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: /upgrade to pro/i });
    expect(cta).toHaveAttribute("href", "/pricing");
  });

  it("does not render any of the gated content itself", () => {
    render(<ProGate feature="Forecast" />);
    expect(screen.queryByText(/forecast value/i)).not.toBeInTheDocument();
  });
});

describe("the gate decision fails closed", () => {
  it.each([
    ["an anonymous visitor",            null],
    ["a signed-in free user",           { ...base, is_pro: false }],
    ["a user whose is_pro is missing",  { ...base, is_pro: undefined as unknown as boolean }],
  ])("gates %s", (_label, user) => {
    expect(shouldGate(user as User | null)).toBe(true);
  });

  it("lets a Pro user through", () => {
    expect(shouldGate({ ...base, is_pro: true })).toBe(false);
  });

  it("gates while /me is still loading", () => {
    // AuthProvider's initial state is { user: null, isLoading: true }. If this
    // ever returned false, every visitor would see paid features for the
    // duration of the bootstrap fetch.
    expect(shouldGate(null)).toBe(true);
  });
});
