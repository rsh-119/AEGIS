"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

/** Section- or page-scoped Pro paywall — same visual language as LoginPrompt
 * (which only ever replaces a whole page), but this one is used both as a
 * whole-page replacement (/concall, /concall/document) and inline in place
 * of a single card (ForecastCard, TechnicalsCard, AnalystTargetCard,
 * ConcallCard) on the stock detail page. */
export function ProGate({ feature }: { feature: string }) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <Lock className="h-8 w-8 text-muted" />
      <div>
        <p className="font-semibold">{feature} is a Pro feature</p>
        <p className="mt-1 text-sm text-muted">
          Upgrade to AEGIS Pro to unlock {feature.toLowerCase()} and more.
        </p>
      </div>
      <Button asChild className="mt-1">
        <Link href="/pricing">Upgrade to Pro</Link>
      </Button>
    </Card>
  );
}
