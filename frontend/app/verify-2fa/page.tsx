"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { consumePendingPreAuthToken } from "@/lib/twoFactor";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function Verify2faPage() {
  const router = useRouter();
  const { verifyTwoFactor } = useAuth();

  const [preAuthToken, setPreAuthToken] = useState<string | null>(null);
  const [code, setCode]   = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy]   = useState(false);

  // Read (and consume) the pending token once, client-side only — there's
  // nothing to verify against if a user lands here directly without having
  // just password/Google-authenticated.
  useEffect(() => {
    const token = consumePendingPreAuthToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    setPreAuthToken(token);
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!preAuthToken) return;
    setError("");
    setBusy(true);
    try {
      await verifyTwoFactor(preAuthToken, code.trim());
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!preAuthToken) return null;

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <div className="w-full max-w-sm animate-scale-in">
        <div className="mb-8 text-center">
          <h1 className="font-display text-3xl font-bold">Two-factor verification</h1>
          <p className="mt-2 text-sm text-muted">
            Enter the 6-digit code from your authenticator app, or a backup code
          </p>
        </div>

        <Card asChild>
          <form onSubmit={submit} className="p-6 space-y-4">
            {error && (
              <div className="rounded-lg bg-down/10 border border-down/20 px-4 py-3 text-sm text-down">
                {error}
              </div>
            )}

            <div className="space-y-1">
              <Label className="text-xs">Code</Label>
              <Input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                value={code}
                onChange={e => setCode(e.target.value)}
                className="w-full text-center tracking-[0.3em]"
                placeholder="123456"
                maxLength={9}
              />
            </div>

            <Button
              type="submit"
              disabled={busy || !code}
              className="w-full flex items-center justify-center gap-2"
            >
              <ShieldCheck className="h-4 w-4" />
              {busy ? "Verifying…" : "Verify"}
            </Button>
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
