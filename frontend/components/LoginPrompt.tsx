"use client";

import Link from "next/link";
import { LogIn } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function LoginPrompt({ what }: { what: string }) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <LogIn className="h-8 w-8 text-muted" />
      <div>
        <p className="font-semibold">Sign in to use {what}</p>
        <p className="mt-1 text-sm text-muted">
          {what[0].toUpperCase() + what.slice(1)} is saved to your account, so you'll need to log in first.
        </p>
      </div>
      <Button asChild className="mt-1">
        <Link href="/login">Sign in</Link>
      </Button>
    </Card>
  );
}
