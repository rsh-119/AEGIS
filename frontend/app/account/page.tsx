"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  UserCircle, KeyRound, Save, ShieldCheck, ShieldOff,
  Camera, Loader2, Trash2, Sparkles, Mail,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useAuth } from "@/lib/auth";
import { LoginPrompt } from "@/components/LoginPrompt";
import { UserAvatar } from "@/components/UserAvatar";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { patch, post, del, uploadFile } from "@/lib/api";

const MAX_AVATAR_BYTES = 8 * 1024 * 1024;

export default function AccountPage() {
  const { user, isLoading: authLoading, refreshUser } = useAuth();
  const { toast } = useToast();

  // ── Profile photo ────────────────────────────────────────────────────────
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  async function handleAvatarFile(file: File) {
    if (!file.type.startsWith("image/")) {
      toast({ variant: "error", title: "Please choose an image file" });
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      toast({ variant: "error", title: "Image too large", description: "Max 8 MB — try a smaller photo." });
      return;
    }
    const localUrl = URL.createObjectURL(file);
    setAvatarPreview(localUrl);   // instant feedback while the upload/resize round-trips
    setAvatarBusy(true);
    try {
      await uploadFile("/api/auth/me/avatar", "file", file);
      await refreshUser();
      toast({ variant: "success", title: "Profile photo updated" });
    } catch (err) {
      toast({ variant: "error", title: "Couldn't update photo", description: (err as Error).message });
    } finally {
      setAvatarBusy(false);
      URL.revokeObjectURL(localUrl);
      setAvatarPreview(null);
    }
  }

  async function removeAvatar() {
    setAvatarBusy(true);
    try {
      await del("/api/auth/me/avatar");
      await refreshUser();
      toast({ variant: "success", title: "Profile photo removed" });
    } catch (err) {
      toast({ variant: "error", title: "Couldn't remove photo", description: (err as Error).message });
    } finally {
      setAvatarBusy(false);
    }
  }

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

  const memberSince = new Date(user.created_at).toLocaleDateString("en-IN", {
    month: "long", year: "numeric",
  });
  const displayAvatar = avatarPreview ?? user.avatar_url;

  return (
    <div className="mx-auto max-w-2xl space-y-6 animate-fade-up">
      <PageHeader />

      {/* ── Hero: photo + identity ──────────────────────────────────────── */}
      <Card className="overflow-hidden">
        <div className="h-1 w-full bg-gradient-to-r from-saffron via-amber-400 to-up" />
        <div className="flex flex-col items-center gap-5 p-6 text-center sm:flex-row sm:items-center sm:text-left sm:p-8">
          <div
            className={clsx(
              "relative shrink-0 rounded-full transition-shadow",
              dragOver && "ring-2 ring-saffron ring-offset-2 ring-offset-surface",
            )}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const file = e.dataTransfer.files?.[0];
              if (file) handleAvatarFile(file);
            }}
          >
            <UserAvatar
              avatarUrl={displayAvatar}
              username={user.username}
              sizeClass="h-24 w-24"
              textClass="text-2xl"
              className="ring-4 ring-surface shadow-md"
            />

            {avatarBusy && (
              <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50">
                <Loader2 className="h-6 w-6 animate-spin text-white" />
              </div>
            )}

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={avatarBusy}
              aria-label={displayAvatar ? "Change profile photo" : "Upload profile photo"}
              className="absolute -bottom-1 -right-1 flex h-10 w-10 items-center justify-center rounded-full bg-fg text-ink shadow-md ring-4 ring-surface transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saffron/50 disabled:pointer-events-none disabled:opacity-60"
            >
              <Camera className="h-4 w-4" />
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";   // allow re-picking the same file later
                if (file) handleAvatarFile(file);
              }}
            />
          </div>

          <div className="min-w-0 flex-1">
            <h2 className="font-display text-2xl font-semibold tracking-tight text-fg">{user.username}</h2>
            <p className="mt-0.5 flex items-center justify-center gap-1.5 text-sm text-muted sm:justify-start">
              <Mail className="h-3.5 w-3.5 shrink-0" /> {user.email}
            </p>

            <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5 sm:justify-start">
              {user.is_pro && (
                <Badge className="bg-saffron/10 text-saffron ring-1 ring-saffron/20">
                  <Sparkles className="h-3 w-3" /> Pro
                </Badge>
              )}
              {user.auth_provider === "google" && (
                <Badge className="bg-raised text-muted ring-1 ring-border">Signed in with Google</Badge>
              )}
              {user.is_2fa_enabled && (
                <Badge className="bg-up/10 text-up ring-1 ring-up/20">
                  <ShieldCheck className="h-3 w-3" /> 2FA on
                </Badge>
              )}
              <Badge className="bg-raised text-muted ring-1 ring-border">Member since {memberSince}</Badge>
            </div>

            {displayAvatar && !avatarBusy && (
              <button
                type="button"
                onClick={removeAvatar}
                className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-muted transition-colors hover:text-down"
              >
                <Trash2 className="h-3 w-3" /> Remove photo
              </button>
            )}
          </div>
        </div>
      </Card>

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

      {/* Change password — a Google-only account has none to change yet */}
      <Card className="p-6" asChild>
        {user.has_password ? (
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
        ) : (
          <div>
            <h2 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
              <KeyRound className="h-3.5 w-3.5 text-saffron" /> Password
            </h2>
            <p className="text-sm text-muted">
              You signed up with Google, so there&apos;s no password on this account yet.
            </p>
          </div>
        )}
      </Card>

      <TwoFactorSection />
    </div>
  );
}

// ── Two-factor authentication ─────────────────────────────────────────────
// Uses toast (not the login/register pages' inline banner) for errors —
// matches this settings page's existing convention for the profile/password
// forms above, since this is a settings action rather than a full-page auth
// form. current_password reproof for disable mirrors saveProfile's
// email-change guard above: turning off a second factor is exactly as
// security-sensitive as changing the recovery email.
function TwoFactorSection() {
  const { user, refreshUser } = useAuth();
  const { toast } = useToast();

  const [stage, setStage] = useState<"idle" | "setup" | "backup-codes">("idle");
  const [secret, setSecret]         = useState("");
  const [otpauthUri, setOtpauthUri] = useState("");
  const [code, setCode]             = useState("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [savedAck, setSavedAck]     = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [busy, setBusy]             = useState(false);

  async function startSetup() {
    setBusy(true);
    try {
      const res = await post<{ secret: string; otpauth_uri: string }>("/api/auth/2fa/setup", {});
      setSecret(res.secret);
      setOtpauthUri(res.otpauth_uri);
      setStage("setup");
    } catch (err) {
      toast({ variant: "error", title: "Couldn't start 2FA setup", description: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function confirmEnable(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await post<{ backup_codes: string[] }>("/api/auth/2fa/enable", { code });
      setBackupCodes(res.backup_codes);
      setStage("backup-codes");
      setCode("");
    } catch (err) {
      toast({ variant: "error", title: "Invalid code", description: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function finishBackupCodesAck() {
    await refreshUser();
    setStage("idle");
    setSavedAck(false);
    setBackupCodes([]);
    toast({ variant: "success", title: "Two-factor authentication enabled" });
  }

  async function disable(e: React.FormEvent) {
    e.preventDefault();
    if (!disablePassword) return;
    setBusy(true);
    try {
      await post("/api/auth/2fa/disable", { current_password: disablePassword });
      setDisablePassword("");
      await refreshUser();
      toast({ variant: "success", title: "Two-factor authentication disabled" });
    } catch (err) {
      toast({ variant: "error", title: "Couldn't disable 2FA", description: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  if (!user) return null;

  return (
    <Card className="p-6">
      <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
        <ShieldCheck className="h-3.5 w-3.5 text-saffron" /> Two-factor authentication
      </h2>

      {user.is_2fa_enabled ? (
        <form onSubmit={disable} className="space-y-4">
          <p className="text-sm text-muted">
            2FA is enabled on your account. Enter your password to disable it.
          </p>
          <div>
            <Label className="mb-1.5 block">Current password</Label>
            <Input
              type="password"
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <Button type="submit" variant="ghost" disabled={!disablePassword || busy} className="flex items-center gap-2">
            <ShieldOff className="h-4 w-4" />
            {busy ? "Disabling…" : "Disable 2FA"}
          </Button>
        </form>
      ) : stage === "idle" ? (
        <>
          <p className="mb-4 text-sm text-muted">
            Add an extra layer of security — you&apos;ll need a code from an authenticator
            app (like Google Authenticator or Authy) every time you sign in.
          </p>
          <Button onClick={startSetup} disabled={busy} className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            {busy ? "Starting…" : "Set up 2FA"}
          </Button>
        </>
      ) : stage === "setup" ? (
        <form onSubmit={confirmEnable} className="space-y-4">
          <p className="text-sm text-muted">
            Scan this QR code with your authenticator app, or enter the secret manually.
          </p>
          <div className="flex justify-center rounded-lg bg-white p-4">
            <QRCodeSVG value={otpauthUri} size={180} />
          </div>
          <div className="text-center">
            <Label className="mb-1 block">Manual entry code</Label>
            <code className="text-xs tracking-wider text-muted">{secret}</code>
          </div>
          <div>
            <Label className="mb-1.5 block">Enter the 6-digit code to confirm</Label>
            <Input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="text-center tracking-[0.3em]"
              placeholder="123456"
              maxLength={6}
              required
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={!code || busy} className="flex items-center gap-2">
              {busy ? "Verifying…" : "Confirm and enable"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setStage("idle")}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg bg-saffron/10 border border-saffron/20 px-4 py-3 text-sm">
            Save these backup codes somewhere safe — each one can be used once to sign in
            if you lose access to your authenticator app. They won&apos;t be shown again.
          </div>
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-raised/40 p-4 font-mono text-sm">
            {backupCodes.map((c) => (
              <span key={c}>{c}</span>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={savedAck} onChange={(e) => setSavedAck(e.target.checked)} />
            I&apos;ve saved these backup codes
          </label>
          <Button onClick={finishBackupCodesAck} disabled={!savedAck}>
            Done
          </Button>
        </div>
      )}
    </Card>
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
