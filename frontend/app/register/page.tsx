"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Eye, EyeOff, UserPlus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();

  const [email, setEmail]       = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw]     = useState(false);
  const [error, setError]       = useState("");
  const [busy, setBusy]         = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setBusy(true);
    try {
      await register(email, username, password);
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
          <h1 className="font-display text-3xl font-bold">Create account</h1>
          <p className="mt-2 text-sm text-muted">Track your Indian market portfolio</p>
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
              <Label className="text-xs">Username</Label>
              <Input
                type="text"
                autoComplete="username"
                required
                pattern="^[a-zA-Z0-9_]+$"
                minLength={3}
                maxLength={30}
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full"
                placeholder="johndoe"
              />
              <p className="text-micro text-muted">Letters, numbers and underscores only</p>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Password</Label>
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
              <UserPlus className="h-4 w-4" />
              {busy ? "Creating account…" : "Create account"}
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center text-sm text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-saffron hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
