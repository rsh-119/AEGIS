"use client";

import { useState } from "react";
import Link from "next/link";
import { KeyRound } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail]   = useState("");
  const [error, setError]   = useState("");
  const [busy, setBusy]     = useState(false);
  const [sent, setSent]     = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      // Always succeeds with a generic message, even for an unregistered
      // email — the backend is enumeration-safe by design (see
      // routers/auth.py's forgot_password), so this page shows the same
      // "check your email" state either way rather than branching on it.
      await post("/api/auth/forgot-password", { email });
      setSent(true);
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
          <h1 className="font-display text-3xl font-bold">Reset your password</h1>
          <p className="mt-2 text-sm text-muted">
            Enter your email and we&apos;ll send you a reset link
          </p>
        </div>

        <Card asChild>
          <form onSubmit={submit} className="p-6 space-y-4">
            {error && (
              <div className="rounded-lg bg-down/10 border border-down/20 px-4 py-3 text-sm text-down">
                {error}
              </div>
            )}

            {sent ? (
              <div className="rounded-lg bg-up/10 border border-up/20 px-4 py-3 text-sm text-up">
                If that email is registered, a reset link has been sent — check your inbox.
              </div>
            ) : (
              <>
                <div className="space-y-1">
                  <Label className="text-xs">Email</Label>
                  <Input
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="w-full"
                    placeholder="you@example.com"
                  />
                </div>

                <Button
                  type="submit"
                  disabled={busy}
                  className="w-full flex items-center justify-center gap-2"
                >
                  <KeyRound className="h-4 w-4" />
                  {busy ? "Sending…" : "Send reset link"}
                </Button>
              </>
            )}
          </form>
        </Card>

        <p className="mt-4 text-center text-sm text-muted">
          Remembered it?{" "}
          <Link href="/login" className="text-saffron hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
