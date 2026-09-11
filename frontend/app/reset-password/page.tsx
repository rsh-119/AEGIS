"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Eye, EyeOff, KeyRound } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";

// NEXT_PUBLIC-relevant note: this page's Referrer-Policy is overridden to
// "no-referrer" in next.config.js's headers() — the reset token below lives
// in this page's URL, and the app-wide default policy would otherwise leak
// it via Referer to any same-origin link a user clicked from here.

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";

  const [password, setPassword]   = useState("");
  const [showPw, setShowPw]       = useState(false);
  const [error, setError]         = useState("");
  const [busy, setBusy]           = useState(false);
  const [done, setDone]           = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setBusy(true);
    try {
      await post("/api/auth/reset-password", { token, new_password: password });
      setDone(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <div className="w-full max-w-sm animate-scale-in">
        <div className="mb-8 text-center">
          <h1 className="font-display text-3xl font-bold">Set a new password</h1>
          <p className="mt-2 text-sm text-muted">Choose a new password for your account</p>
        </div>

        <Card asChild>
          <form onSubmit={submit} className="p-6 space-y-4">
            {error && (
              <div className="rounded-lg bg-down/10 border border-down/20 px-4 py-3 text-sm text-down">
                {error}
              </div>
            )}

            {!token ? (
              <div className="rounded-lg bg-down/10 border border-down/20 px-4 py-3 text-sm text-down">
                This link is missing its reset token — request a new one from the{" "}
                <Link href="/forgot-password" className="underline">forgot password</Link> page.
              </div>
            ) : done ? (
              <>
                <div className="rounded-lg bg-up/10 border border-up/20 px-4 py-3 text-sm text-up">
                  Password has been reset. Please log in again — every other device has been signed out.
                </div>
                <Button
                  type="button"
                  onClick={() => router.push("/login")}
                  className="w-full"
                >
                  Go to sign in
                </Button>
              </>
            ) : (
              <>
                <div className="space-y-1">
                  <Label className="text-xs">New password</Label>
                  <div className="relative">
                    <Input
                      type={showPw ? "text" : "password"}
                      autoComplete="new-password"
                      required
                      minLength={6}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      className="w-full pr-10"
                      placeholder="Min. 6 characters"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPw(p => !p)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-foreground"
                    >
                      {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <Button
                  type="submit"
                  disabled={busy}
                  className="w-full flex items-center justify-center gap-2"
                >
                  <KeyRound className="h-4 w-4" />
                  {busy ? "Resetting…" : "Reset password"}
                </Button>
              </>
            )}
          </form>
        </Card>

        <p className="mt-4 text-center text-sm text-muted">
          <Link href="/login" className="text-saffron hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
