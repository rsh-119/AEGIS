"use client";

import { useEffect, useState } from "react";
import { UserCircle, KeyRound, Save } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { LoginPrompt } from "@/components/LoginPrompt";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { patch, post } from "@/lib/api";

export default function AccountPage() {
  const { user, isLoading: authLoading, refreshUser } = useAuth();
  const { toast } = useToast();

  // ── Profile details ──────────────────────────────────────────────────────
  const [username, setUsername] = useState("");
  const [email, setEmail]       = useState("");
  // Only asked for when the email is actually being changed — email is the
  // account-recovery channel, so the backend requires re-proving identity
  // for that specific change (not for a username-only edit).
  const [emailConfirmPassword, setEmailConfirmPassword] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  useEffect(() => {
    if (user) { setUsername(user.username); setEmail(user.email); }
  }, [user]);

  const emailChanged = !!user && email !== user.email;
  const profileDirty = !!user && (username !== user.username || emailChanged);
  const canSaveProfile = profileDirty && (!emailChanged || emailConfirmPassword.length > 0);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    if (!canSaveProfile) return;
    setSavingProfile(true);
    try {
      await patch("/api/auth/me", {
        username,
        email,
        ...(emailChanged ? { current_password: emailConfirmPassword } : {}),
      });
      setEmailConfirmPassword("");
      await refreshUser();
      toast({ variant: "success", title: "Profile updated" });
    } catch (err) {
      toast({ variant: "error", title: "Couldn't update profile", description: (err as Error).message });
    } finally {
      setSavingProfile(false);
    }
  }

  // ── Password ──────────────────────────────────────────────────────────────
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword]         = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword]   = useState(false);

  const passwordMismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;
  const canChangePassword = currentPassword.length > 0 && newPassword.length >= 6 && !passwordMismatch;

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    if (!canChangePassword) return;
    setSavingPassword(true);
    try {
      await post("/api/auth/me/password", { current_password: currentPassword, new_password: newPassword });
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      toast({ variant: "success", title: "Password changed" });
    } catch (err) {
      toast({ variant: "error", title: "Couldn't change password", description: (err as Error).message });
    } finally {
      setSavingPassword(false);
    }
  }

  if (authLoading) return null;
  if (!user) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
        <PageHeader />
        <LoginPrompt what="your account" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 animate-fade-up">
      <div>
        <PageHeader />
        <p className="mt-2 pl-[46px] text-sm text-muted">
          Update your username, email, or password.
        </p>
      </div>

      {/* Profile details */}
      <Card className="p-6" asChild>
        <form onSubmit={saveProfile}>
          <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
            <UserCircle className="h-3.5 w-3.5 text-saffron" /> Profile details
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label className="mb-1.5 block">Username</Label>
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={3}
                maxLength={30}
                pattern="[a-zA-Z0-9_]+"
                required
              />
            </div>
            <div>
              <Label className="mb-1.5 block">Email</Label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          {emailChanged && (
            <div className="mt-4">
              <Label className="mb-1.5 block">Current password <span className="normal-case text-muted/70">— required to change your email</span></Label>
              <Input
                type="password"
                value={emailConfirmPassword}
                onChange={(e) => setEmailConfirmPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
          )}

          <Button type="submit" disabled={!canSaveProfile || savingProfile} className="mt-5 flex items-center gap-2">
            <Save className="h-4 w-4" />
            {savingProfile ? "Saving…" : "Save changes"}
          </Button>
        </form>
      </Card>

      {/* Change password */}
      <Card className="p-6" asChild>
        <form onSubmit={changePassword}>
          <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
            <KeyRound className="h-3.5 w-3.5 text-saffron" /> Change password
          </h2>
          <div className="space-y-4">
            <div>
              <Label className="mb-1.5 block">Current password</Label>
              <Input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label className="mb-1.5 block">New password</Label>
                <Input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={6}
                  required
                />
              </div>
              <div>
                <Label className="mb-1.5 block">Confirm new password</Label>
                <Input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
                {passwordMismatch && <p className="mt-1.5 text-xs text-down">Passwords don&apos;t match</p>}
              </div>
            </div>
          </div>
          <Button type="submit" disabled={!canChangePassword || savingPassword} className="mt-5 flex items-center gap-2">
            <Save className="h-4 w-4" />
            {savingPassword ? "Updating…" : "Update password"}
          </Button>
        </form>
      </Card>
    </div>
  );
}

function PageHeader() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-saffron/10 ring-1 ring-saffron/20">
        <UserCircle className="h-4 w-4 text-saffron" />
      </div>
      <h1 className="font-display text-2xl font-semibold tracking-tight">Account</h1>
    </div>
  );
}
