"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Eye, EyeOff, LogIn } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw]     = useState(false);
  const [error, setError]       = useState("");
  const [busy, setBusy]         = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      router.replace("/");
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
          <h1 className="font-display text-3xl font-bold">Welcome back</h1>
          <p className="mt-2 text-sm text-muted">Sign in to your Aegis account</p>
        </div>

        <Card asChild>
          <form onSubmit={submit} className="p-6 space-y-4">
            {error && (
              <div className="rounded-lg bg-down/10 border border-down/20 px-4 py-3 text-sm text-down">
                {error}
              </div>
            )}

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

            <div className="space-y-1">
              <Label className="text-xs">Password</Label>
              <div className="relative">
                <Input
                  type={showPw ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full pr-10"
                  placeholder="••••••••"
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
              <LogIn className="h-4 w-4" />
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center text-sm text-muted">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-saffron hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
