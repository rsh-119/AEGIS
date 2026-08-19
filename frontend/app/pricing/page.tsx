"use client";

import Link from "next/link";
import { Check, Minus, Sparkles, Crown, Zap } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Reveal } from "@/components/motion";

type Feature = {
  label: string;
  free: string | boolean;
  pro: string | boolean;
};

const GROUPS: { title: string; items: Feature[] }[] = [
  {
    title: "Market data",
    items: [
      { label: "Live NSE & BSE quotes and charts", free: true, pro: true },
      { label: "Peer comparison", free: true, pro: true },
      { label: "Watchlist", free: "Up to 10 stocks", pro: "Unlimited" },
      { label: "Price alerts", free: "Up to 3 active", pro: "Unlimited" },
      { label: "Full financials, ratios & cash flow history", free: false, pro: true },
    ],
  },
  {
    title: "AEGIS AI",
    items: [
      { label: "Ask AI (chat, per stock & portfolio)", free: "5 questions/day", pro: "Unlimited" },
      { label: "AI stock health checks", free: true, pro: true },
      { label: "AI concall summaries", free: false, pro: true },
      { label: "Chat with any PDF / document", free: false, pro: true },
      { label: "Priority AI queue — faster responses", free: false, pro: true },
    ],
  },
  {
    title: "Portfolio",
    items: [
      { label: "Manual portfolio tracking", free: true, pro: true },
      { label: "AI portfolio review & risk analysis", free: false, pro: true },
      { label: "Portfolio news digest", free: false, pro: true },
    ],
  },
];

function Cell({ value }: { value: string | boolean }) {
  if (value === true) return <Check className="h-4 w-4 text-up" />;
  if (value === false) return <Minus className="h-3.5 w-3.5 text-muted/50" />;
  return <span className="text-xs font-medium text-fg/80">{value}</span>;
}

export default function PricingPage() {
  const { toast } = useToast();

  function notifyPro() {
    toast({
      variant: "info",
      title: "Pro is launching soon",
      description: "We'll email you the moment upgrades open up.",
    });
  }

  return (
    <div className="mx-auto max-w-4xl space-y-10 animate-fade-up">
      {/* Header */}
      <Reveal>
        <div className="text-center">
          <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-saffron">Pricing</p>
          <h1 className="mt-3 font-display text-[clamp(1.9rem,4.5vw,2.75rem)] font-medium leading-[1.12] tracking-[-0.015em] text-fg">
            Start free. Upgrade when you need more.
          </h1>
          <p className="mx-auto mt-3 max-w-lg text-[15px] leading-relaxed text-muted">
            Every plan gets live NSE &amp; BSE data and AEGIS AI. Pro removes the limits and adds
            deeper research tools for active investors.
          </p>
        </div>
      </Reveal>

      {/* Plan cards */}
      <Reveal delay={80}>
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Free */}
          <Card className="flex flex-col p-6">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-muted" />
              <h2 className="font-display text-lg font-semibold">Free</h2>
            </div>
            <p className="mt-1 text-xs text-muted">Everything you need to track and research stocks.</p>
            <p className="mt-5 flex items-end gap-1">
              <span className="font-display text-4xl font-semibold text-fg">₹0</span>
              <span className="pb-1 text-xs text-muted">/ forever</span>
            </p>
            <Button asChild variant="ghost" className="mt-5 w-full">
              <Link href="/login">Get started</Link>
            </Button>
          </Card>

          {/* Pro */}
          <Card className="relative flex flex-col overflow-hidden p-6 ring-1 ring-saffron/30">
            <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-saffron/10 blur-2xl" />
            <span className="absolute right-4 top-4 rounded-full border border-saffron/25 bg-saffron/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-saffron">
              Coming soon
            </span>
            <div className="flex items-center gap-2">
              <Crown className="h-4 w-4 text-saffron" />
              <h2 className="font-display text-lg font-semibold">Pro</h2>
            </div>
            <p className="mt-1 text-xs text-muted">Unlimited AI, deeper data, priority speed.</p>
            <p className="mt-5 flex items-end gap-1">
              <span className="font-display text-4xl font-semibold text-fg">₹499</span>
              <span className="pb-1 text-xs text-muted">/ month</span>
            </p>
            <Button onClick={notifyPro} className="mt-5 w-full">
              <Zap className="h-4 w-4" /> Notify me
            </Button>
          </Card>
        </div>
      </Reveal>

      {/* Comparison table */}
      <Reveal delay={140}>
        <Card className="overflow-hidden">
          <div className="grid grid-cols-[1fr_5rem_5rem] items-center gap-2 border-b border-border bg-raised/40 px-5 py-3 sm:grid-cols-[1fr_7rem_7rem] sm:px-6">
            <span className="text-xs font-semibold text-muted">Compare plans</span>
            <span className="text-center text-xs font-semibold text-muted">Free</span>
            <span className="text-center text-xs font-semibold text-saffron">Pro</span>
          </div>

          {GROUPS.map((group) => (
            <div key={group.title}>
              <div className="bg-raised/20 px-5 py-2 sm:px-6">
                <p className="text-micro-cap font-semibold uppercase tracking-wide text-muted">{group.title}</p>
              </div>
              {group.items.map((f) => (
                <div
                  key={f.label}
                  className="grid grid-cols-[1fr_5rem_5rem] items-center gap-2 border-b border-border/60 px-5 py-3 last:border-b-0 sm:grid-cols-[1fr_7rem_7rem] sm:px-6"
                >
                  <span className="text-sm text-fg/90">{f.label}</span>
                  <span className="flex justify-center"><Cell value={f.free} /></span>
                  <span className="flex justify-center"><Cell value={f.pro} /></span>
                </div>
              ))}
            </div>
          ))}
        </Card>
      </Reveal>

      <p className="pb-6 text-center text-xs text-muted">
        Questions?{" "}
        <Link href="/" className="text-saffron hover:underline">
          Reach out from the homepage
        </Link>{" "}
        and we&apos;ll help you pick a plan.
      </p>
    </div>
  );
}
