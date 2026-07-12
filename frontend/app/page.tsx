"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { motion, useScroll, useTransform } from "framer-motion";
import { SearchBox } from "@/components/SearchBox";
import { Reveal, Stagger, MotionNumber } from "@/components/motion";
import { InteractiveHoverButton } from "@/components/ui/interactive-hover-button";
import { AuroraBackground } from "@/components/ui/aurora-background";
import { BentoGrid } from "@/components/ui/bento-grid";
import { BarChart3, Activity, Bell, Bookmark, ChevronRight } from "lucide-react";

/* ─── Section heading — mono eyebrow + calm display title ── */
function SectionHeading({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-saffron">{eyebrow}</p>
      <h2 className="mt-3 font-display text-[clamp(2rem,4.5vw,3rem)] font-medium leading-[1.12] tracking-[-0.015em] text-fg">
        {title}
      </h2>
      {sub && <p className="mt-3 text-[15px] leading-relaxed text-muted">{sub}</p>}
    </div>
  );
}

/* ─── Product showcase — Wealthsimple-style alternating band:
       copy on one side, a soft-tinted panel holding a product mock on the other ── */
function Showcase({
  eyebrow, title, description, link, linkLabel, panelClass, flip, accents, children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  link: string;
  linkLabel: string;
  panelClass: string;
  flip?: boolean;
  /** Floating accent chips, absolutely positioned inside the panel. */
  accents?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="grid items-center gap-8 lg:grid-cols-2 lg:gap-14">
      <Reveal className={clsx("max-w-lg", flip && "lg:order-2 lg:justify-self-end")}>
        <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-saffron">{eyebrow}</p>
        <h3 className="mt-3 font-display text-[clamp(2rem,4vw,2.875rem)] font-medium leading-[1.1] tracking-[-0.015em] text-fg">{title}</h3>
        <p className="mt-4 text-[15px] leading-relaxed text-muted">{description}</p>
        <InteractiveHoverButton href={link} className="mt-7">
          {linkLabel}
        </InteractiveHoverButton>
      </Reveal>
      <Reveal
        delay={140}
        onMouseMove={spotlightMove}
        className={clsx(
          "group relative flex items-center justify-center overflow-hidden rounded-3xl border border-border/50 px-6 py-12 sm:py-16",
          "panel-dots",
          panelClass,
          flip && "lg:order-1",
        )}
      >
        <div className="spotlight-layer" aria-hidden />
        {accents}
        {/* Gentle settle + tilt on hover; Parallax drifts the mock as you scroll */}
        <Parallax className="w-full">
          <div className="flex w-full justify-center transition-transform duration-500 ease-out group-hover:-translate-y-1.5 group-hover:rotate-[0.5deg]">
            {children}
          </div>
        </Parallax>
      </Reveal>
    </div>
  );
}

/* Cursor spotlight: writes the pointer position into CSS vars consumed by
   the .spotlight-layer radial highlight. */
function spotlightMove(e: React.MouseEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--sx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--sy", `${e.clientY - r.top}px`);
}

/* Scroll parallax: drifts children vertically as the element crosses the
   viewport. Transform-only (composited) so it stays smooth. */
function Parallax({ amount = 26, className, children }: {
  amount?: number; className?: string; children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [amount, -amount]);
  return (
    <motion.div ref={ref} style={{ y }} className={className}>
      {children}
    </motion.div>
  );
}

/* Full-bleed keyword marquee — a moving strip of product vocabulary that
   breaks the page into chapters between the hero and the showcases. */
function KeywordMarquee() {
  const words = [
    "Concall Briefs", "Live Quotes", "Peer Medians", "XIRR",
    "52-Week Radar", "Price Shockers", "Smart Alerts", "Ask AI",
  ];
  const row = (copy: string) =>
    words.map((w) => (
      <span key={`${copy}-${w}`} className="flex shrink-0 items-center gap-8">
        <span className="font-display text-xl font-medium text-muted/50 transition-colors duration-300 hover:text-saffron sm:text-2xl">
          {w}
        </span>
        <span className="h-1.5 w-1.5 rounded-full bg-saffron/40" aria-hidden />
      </span>
    ));

  return (
    <div className="relative -mx-4 overflow-hidden border-y border-border bg-raised/40 py-5 sm:-mx-6 md:-mx-10 lg:-mx-14">
      <div className="animate-marquee flex w-max items-center gap-8" style={{ animationDuration: "45s" }}>
        <div className="flex shrink-0 items-center gap-8">{row("a")}</div>
        <div className="flex shrink-0 items-center gap-8" aria-hidden>{row("b")}</div>
      </div>
      {/* Edge fades so the strip dissolves at both ends */}
      <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-ink to-transparent" aria-hidden />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-ink to-transparent" aria-hidden />
    </div>
  );
}

/* Small floating pill used as a panel accent */
function FloatChip({
  className, dur = 5, delay = 0, children,
}: {
  className?: string; dur?: number; delay?: number; children: React.ReactNode;
}) {
  return (
    <span
      className={clsx(
        "float-chip pointer-events-none absolute hidden rounded-full border border-border/70 bg-surface px-3 py-1.5 font-mono text-[10px] shadow-sm sm:block",
        className,
      )}
      style={{ "--float-dur": `${dur}s`, "--float-delay": `${delay}s` } as React.CSSProperties}
      aria-hidden
    >
      {children}
    </span>
  );
}

/* ─── Product mocks — static, token-driven ── */
function ConcallMock() {
  return (
    <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 text-left shadow-lg shadow-black/5">
      <div className="flex items-start justify-between gap-3 border-b border-border pb-3.5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Q3 FY26 · Earnings call</p>
          <p className="mt-1 text-sm font-semibold text-fg">Tata Consultancy Services</p>
        </div>
        <span className="shrink-0 rounded-full bg-saffron/10 px-2.5 py-1 font-mono text-[10px] text-saffron">AI brief</span>
      </div>
      <ul className="mt-3.5 space-y-2.5 text-[13px] leading-relaxed">
        <li className="brief-li flex gap-2">
          <span className="shrink-0 text-up">▲</span>
          <span className="text-fg">Guidance raised — deal TCV at an all-time high</span>
        </li>
        <li className="brief-li flex gap-2">
          <span className="shrink-0 text-muted">—</span>
          <span className="text-muted">Margins up 40 bps QoQ on utilisation gains</span>
        </li>
        <li className="brief-li flex gap-2">
          <span className="shrink-0 text-muted">—</span>
          <span className="text-muted">BFSI recovery: management sees early green shoots</span>
        </li>
      </ul>
    </div>
  );
}

function MarketMock() {
  const rows = [
    { t: "RELIANCE", p: "2,981.40", c: "+1.24%", up: true },
    { t: "HDFCBANK", p: "1,714.85", c: "+0.86%", up: true },
    { t: "TCS",      p: "4,102.10", c: "−0.38%", up: false },
  ];
  return (
    <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 text-left shadow-lg shadow-black/5">
      <div className="flex items-baseline justify-between">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Nifty 50</p>
          <p className="nums mt-0.5 text-xl font-semibold text-fg">24,206.90</p>
        </div>
        <span className="nums tick-pulse text-sm font-semibold text-up">+1.02%</span>
      </div>
      <svg viewBox="0 0 240 56" className="mt-3 h-14 w-full text-up" preserveAspectRatio="none" aria-hidden>
        <path
          className="spark-fill"
          d="M0 46 L24 42 L48 45 L72 34 L96 38 L120 26 L144 30 L168 18 L192 22 L216 12 L240 14 L240 56 L0 56 Z"
          fill="currentColor"
        />
        <path
          className="spark-path"
          pathLength={1}
          d="M0 46 L24 42 L48 45 L72 34 L96 38 L120 26 L144 30 L168 18 L192 22 L216 12 L240 14"
          fill="none" stroke="currentColor" strokeWidth="1.5"
        />
      </svg>
      <div className="mt-3 divide-y divide-border border-t border-border">
        {rows.map((r) => (
          <div key={r.t} className="flex items-center justify-between py-2 text-[13px]">
            <span className="font-mono text-muted">{r.t}</span>
            <span className="nums flex items-center gap-3 text-fg">
              ₹{r.p}
              <span className={clsx("nums w-14 text-right font-semibold", r.up ? "text-up" : "text-down")}>{r.c}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PortfolioMock() {
  return (
    <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 text-left shadow-lg shadow-black/5">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Your portfolio</p>
      <div className="mt-1 flex items-baseline justify-between">
        <p className="nums text-xl font-semibold text-fg">₹12,40,318</p>
        <span className="rounded-md bg-up/10 px-2 py-1 font-mono text-[10.5px] text-up">XIRR +18.4%</span>
      </div>
      {/* Allocation bar */}
      <div className="mt-4 flex h-2.5 w-full overflow-hidden rounded-full">
        <span className="alloc-seg w-[38%] bg-saffron" />
        <span className="alloc-seg w-[27%] bg-blue-400" />
        <span className="alloc-seg w-[21%] bg-up" />
        <span className="alloc-seg w-[14%] bg-border" />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[10.5px] text-muted">
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-saffron" />Financials 38%</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-blue-400" />IT 27%</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-up" />Energy 21%</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-border" />Other 14%</span>
      </div>
      <p className="mt-4 border-t border-border pt-3 font-mono text-[10.5px] text-muted">
        vs Nifty 50 <span className="text-up">+7.2% alpha</span> · 1Y
      </p>
    </div>
  );
}

/* ─── Bento card backgrounds — quiet decorative readouts, top-anchored ── */
function PeerBarsBg() {
  const bars = [
    { t: "TCS",   w: "72%", hl: true,  v: "ROE 28%" },
    { t: "INFY",  w: "58%", hl: false, v: "ROE 22%" },
    { t: "WIPRO", w: "41%", hl: false, v: "ROE 16%" },
  ];
  return (
    <div className="absolute inset-x-6 top-6 space-y-3 opacity-80">
      {bars.map((b) => (
        <div key={b.t} className="flex items-center gap-3 font-mono text-[10px] text-muted">
          <span className="w-12 shrink-0">{b.t}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-raised">
            <div className={clsx("h-full origin-left rounded-full transition-transform duration-500 ease-out group-hover:scale-x-[1.06]", b.hl ? "bg-saffron/70" : "bg-border")} style={{ width: b.w }} />
          </div>
          <span className="w-14 shrink-0 text-right">{b.v}</span>
        </div>
      ))}
    </div>
  );
}

function AskAiBg() {
  return (
    <div className="absolute inset-x-6 top-6 space-y-2 text-[11px] leading-snug">
      <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-saffron/10 px-3 py-1.5 text-fg">
        How is LTCG taxed on equity?
      </div>
      <div className="w-fit max-w-[90%] rounded-2xl rounded-bl-sm border border-border bg-raised/60 px-3 py-1.5 text-muted">
        Gains above ₹1.25L a year are taxed at 12.5% — here&apos;s how it applies…
      </div>
    </div>
  );
}

function AlertsBg() {
  return (
    <div className="absolute inset-x-6 top-6 space-y-2 font-mono text-[10px]">
      <div className="flex items-center justify-between rounded-xl border border-up/20 bg-up/5 px-3 py-2 transition-transform duration-300 group-hover:translate-x-1">
        <span className="text-fg">RELIANCE ≥ ₹3,000</span>
        <span className="text-up">Triggered ▲</span>
      </div>
      <div className="flex items-center justify-between rounded-xl border border-border bg-raised/50 px-3 py-2 transition-transform duration-300 delay-75 group-hover:translate-x-1">
        <span className="text-muted">TCS ≤ ₹4,000</span>
        <span className="text-muted">Watching</span>
      </div>
    </div>
  );
}

function WatchlistBg() {
  const rows = [
    { t: "ITC",        p: "₹512.40",   c: "+0.82%", up: true },
    { t: "HDFCBANK",   p: "₹1,714.85", c: "+0.86%", up: true },
    { t: "TATASTEEL",  p: "₹171.20",   c: "−0.64%", up: false },
  ];
  return (
    <div className="absolute inset-x-6 top-5 divide-y divide-border/70 opacity-90">
      {rows.map((r) => (
        <div key={r.t} className="flex items-center justify-between py-2 font-mono text-[10px] transition-transform duration-300 group-hover:translate-x-0.5">
          <span className="text-muted">{r.t}</span>
          <span className="nums text-fg">
            {r.p} <span className={r.up ? "text-up" : "text-down"}>{r.c}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/* ─── Page ──────────────────────────────────────── */
export default function Home() {
  return (
    <div className="space-y-24 sm:space-y-32">

      {/* ── Hero — short, monochrome, sentence case, aurora backdrop ── */}
      <section className="relative -mx-4 sm:-mx-6 md:-mx-10 lg:-mx-14">
        <AuroraBackground className="px-4 pb-20 pt-20 sm:px-6 md:px-10 lg:px-14 lg:pb-28 lg:pt-28">

        <div className="relative z-10 mx-auto max-w-3xl text-center">
          {/* Per-word blur-in stagger (.hero-word); not a .hero-el so the words
              own their entrance instead of double-fading with the wrapper */}
          <h1 className="font-display text-[clamp(3rem,7.5vw,5.25rem)] font-medium leading-[1.04] tracking-[-0.02em]">
            <span className="text-muted/70">
              <span className="hero-word" style={{ "--wi": 0 } as React.CSSProperties}>Stop</span>{" "}
              <span className="hero-word" style={{ "--wi": 1 } as React.CSSProperties}>guessing.</span>
            </span>
            <br />
            {/* Gradient lives on an inner span — .hero-word and .hero-gradient-text
                both declare `animation`, so on one element the gradient flow
                overrides word-in and the text never fades in */}
            <span className="hero-word" style={{ "--wi": 2 } as React.CSSProperties}>
              <span className="hero-gradient-text">Start knowing.</span>
            </span>
          </h1>

          <p className="hero-el mx-auto mt-7 max-w-xl text-[1.05rem] leading-[1.7] text-muted">
            Institutional-grade research for every Indian investor — concall briefs,
            live fundamentals, peer benchmarks and portfolio intelligence.{" "}
            <span className="font-semibold text-fg">Completely free.</span>
          </p>

          {/* Search — the front door */}
          {/* relative z-20: .hero-el's fade-up animation creates a stacking
              context, so without an explicit z-index the dropdown paints
              behind later hero-el siblings in DOM order. */}
          <div className="hero-el relative z-20 mx-auto mt-9 max-w-2xl">
            <SearchBox
              size="hero"
              autoFocus
              placeholder="Search any company — RELIANCE, TCS, HDFC…"
            />
          </div>

          {/* Trending tickers */}
          <div className="hero-el mt-5 flex flex-wrap items-center justify-center gap-2">
            <span className="text-xs font-semibold text-muted">Trending:</span>
            {["ITC", "RELIANCE", "HDFCBANK", "TCS", "INFY", "BAJFINANCE", "SBIN", "TATASTEEL"].map((t) => (
              <Link
                key={t}
                href={`/stock/${t}.NS`}
                className="rounded-full border border-border/60 bg-surface/70 px-3 py-1 text-xs font-semibold text-muted backdrop-blur-sm transition-all duration-200 hover:scale-105 hover:border-saffron/50 hover:bg-saffron/8 hover:text-saffron hover:-translate-y-0.5 hover:shadow-sm"
              >
                {t}
              </Link>
            ))}
          </div>
        </div>
        </AuroraBackground>
      </section>

      {/* ── Keyword marquee — moving chapter break ── */}
      <KeywordMarquee />

      {/* ── Product showcases — one product per band, alternating sides ── */}
      <section className="space-y-20 sm:space-y-24">
        <Showcase
          eyebrow="Live Market Dashboard"
          title="The whole market, one glance."
          description="Real-time Nifty 50, Sensex and sector indices with market movers, 52-week highs and lows, IPOs and price shockers — the terminal view, without the terminal fee."
          link="/market"
          linkLabel="Open the dashboard"
          panelClass="bg-[#e4ecf4] dark:bg-surface"
          accents={
            <>
              <FloatChip className="right-8 top-8" dur={5.5}>
                <span className="text-up">▲ +1.02% today</span>
              </FloatChip>
              <FloatChip className="bottom-8 left-8" dur={6.5} delay={1.2}>
                <span className="text-muted">52W HIGH · </span>
                <span className="text-fg">SENSEX</span>
              </FloatChip>
            </>
          }
        >
          <MarketMock />
        </Showcase>

        <Showcase
          flip
          eyebrow="Portfolio & XIRR"
          title="Know what you actually earn."
          description="Log your holdings once. Aegis computes XIRR the way institutions do, benchmarks you against the Nifty, and shows exactly where your gains and losses come from."
          link="/portfolio"
          linkLabel="Track your portfolio"
          panelClass="bg-[#e7ede5] dark:bg-surface"
          accents={
            <>
              <FloatChip className="left-8 top-8" dur={6} delay={0.6}>
                <span className="text-up">+7.2% alpha</span>
              </FloatChip>
              <FloatChip className="bottom-8 right-8" dur={5} delay={1.8}>
                <span className="text-muted">vs NIFTY 50</span>
              </FloatChip>
            </>
          }
        >
          <PortfolioMock />
        </Showcase>

        <Showcase
          eyebrow="AI Concall Analysis"
          title="Earnings calls, read for you."
          description="Every quarter, Aegis distils the full concall into a brief you can read in two minutes — guidance, management commentary, and the numbers that moved, with real news context."
          link="/concall"
          linkLabel="Read a brief"
          panelClass="bg-[#f2ede3] dark:bg-surface"
          accents={
            <>
              <FloatChip className="right-8 top-8" dur={5.8} delay={0.4}>
                <span className="text-up">▲ Guidance raised</span>
              </FloatChip>
              <FloatChip className="bottom-8 left-8" dur={6.8} delay={1.5}>
                <span className="text-saffron">AI</span>
                <span className="text-muted"> · 2-min read</span>
              </FloatChip>
            </>
          }
        >
          <ConcallMock />
        </Showcase>
      </section>

      {/* ── Secondary tools — full-bleed contrasting band ── */}
      <section className="-mx-4 space-y-10 border-y border-border bg-raised/40 px-4 py-20 sm:-mx-6 sm:px-6 sm:py-24 md:-mx-10 md:px-10 lg:-mx-14 lg:px-14">
        <Reveal>
          <SectionHeading
            eyebrow="Also included"
            title="Sharper tools for daily decisions."
          />
        </Reveal>
        <BentoGrid
          items={[
            {
              Icon: BarChart3,
              name: "Peer Comparison",
              description: "Any stock against its sector peers on P/E, ROE and growth — with sector medians.",
              href: "/peers",
              cta: "Compare peers",
              className: "lg:col-span-2",
              background: <PeerBarsBg />,
              content: (
                <>
                  <p>
                    Pick any NSE or BSE stock and Aegis lines it up against its real sector peers —
                    P/E, ROE, revenue growth and margins — with the sector median as your baseline.
                  </p>
                  <p>
                    One view tells you whether a stock is expensive for its quality, or quietly
                    undervalued against the companies it actually competes with — no tab-hopping
                    between screeners.
                  </p>
                </>
              ),
            },
            {
              Icon: Activity,
              name: "Ask AI Anything",
              description: "An Indian-market expert on call — taxation, sector outlooks, FII flows and more.",
              href: "/ask",
              cta: "Ask a question",
              className: "lg:col-span-1",
              background: <AskAiBg />,
              content: (
                <>
                  <p>
                    Ask in plain English — how a capital gain on a specific sale is taxed, what
                    sustained FII outflows mean for banks, or how to read a company&apos;s order book.
                  </p>
                  <p>
                    Answers are grounded in Indian market context — SEBI rules, Indian tax slabs,
                    NSE/BSE conventions — not generic global boilerplate.
                  </p>
                </>
              ),
            },
            {
              Icon: Bell,
              name: "Smart Alerts",
              description: "Precise price alerts with custom conditions and instant delivery.",
              href: "/alerts",
              cta: "Set an alert",
              className: "lg:col-span-1",
              background: <AlertsBg />,
              content: (
                <>
                  <p>
                    Set a level once — above, below, or a percent move — and Aegis watches the tape
                    for you, on every stock in your watchlist.
                  </p>
                  <p>
                    When it triggers you get an instant notification with the price that crossed,
                    so decisions happen at your levels — not whenever you remember to check.
                  </p>
                </>
              ),
            },
            {
              Icon: Bookmark,
              name: "Watchlist",
              description: "The stocks you care about on one page — live prices, your alerts beside them.",
              href: "/watchlist",
              cta: "Build yours",
              className: "lg:col-span-2",
              background: <WatchlistBg />,
              content: (
                <>
                  <p>
                    Pin the stocks you actually follow and get one page with live prices, day
                    change, and your alert status side by side.
                  </p>
                  <p>
                    It syncs with alerts and your portfolio, so the same list drives what you
                    track, what pings you, and what you measure.
                  </p>
                </>
              ),
            },
          ]}
        />
      </section>

      {/* ── Stats band ── */}
      <Stagger
        step={120}
        className="grid gap-10 border-y border-border py-12 sm:grid-cols-3 sm:gap-6 sm:py-14"
        itemClassName="text-center"
      >
        <div>
          <p className="font-display text-4xl font-medium tracking-tight text-fg sm:text-5xl">
            <MotionNumber value={5000} suffix="+" />
          </p>
          <p className="mt-2.5 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted">NSE &amp; BSE stocks</p>
        </div>
        <div>
          <p className="nums font-display text-4xl font-medium tracking-tight text-fg sm:text-5xl">₹0</p>
          <p className="mt-2.5 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted">Free, forever</p>
        </div>
        <div>
          <p className="font-display text-4xl font-medium tracking-tight text-fg sm:text-5xl">Live</p>
          <p className="mt-2.5 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted">NSE · BSE quotes</p>
        </div>
      </Stagger>

      {/* ── How It Works — ledger rows: the steps are a real sequence ── */}
      <section className="space-y-10">
        <Reveal>
          <SectionHeading
            eyebrow="The workflow"
            title="From curious to informed."
          />
        </Reveal>
        <div className="overflow-hidden rounded-2xl border border-border bg-surface">
          {[
            {
              n: "01",
              title: "Search any stock",
              description: "Type a ticker or company name. Get price, charts, and AI insights instantly.",
              href: "/market",
              cta: "Explore the market",
            },
            {
              n: "02",
              title: "Build your watchlist",
              description: "Pin stocks you care about and set price alerts to catch the right moment.",
              href: "/watchlist",
              cta: "Open watchlist",
            },
            {
              n: "03",
              title: "Track your portfolio",
              description: "Log your holdings. Aegis calculates XIRR and benchmarks against Nifty.",
              href: "/portfolio",
              cta: "Set up portfolio",
            },
          ].map((step, i) => (
            <Reveal key={step.n} delay={i * 110} className={clsx(i > 0 && "border-t border-border")}>
              <Link
                href={step.href}
                className="group grid grid-cols-[52px_1fr_auto] items-center gap-x-5 px-5 py-7 transition-colors duration-200 hover:bg-raised/50 sm:grid-cols-[110px_1fr_auto] sm:gap-x-8 sm:px-10 sm:py-9"
              >
                <span
                  className="nums font-mono text-4xl text-muted/30 transition-colors duration-300 group-hover:text-saffron sm:text-6xl"
                  aria-hidden
                >
                  {step.n}
                </span>
                <div className="min-w-0">
                  <h3 className="text-base font-semibold text-fg sm:text-lg">{step.title}</h3>
                  <p className="mt-1 max-w-xl text-sm leading-relaxed text-muted">{step.description}</p>
                  <span className="mt-2 inline-block text-xs font-semibold text-saffron opacity-0 transition-all duration-300 group-hover:opacity-100 sm:mt-2.5">
                    {step.cta} →
                  </span>
                </div>
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-border text-muted transition-all duration-300 group-hover:border-saffron group-hover:bg-saffron group-hover:text-white sm:h-11 sm:w-11">
                  <ChevronRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
                </span>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Closing CTA — inverted band: near-black in light, cream in dark ── */}
      <Reveal>
      <section className="relative overflow-hidden rounded-[2.5rem] bg-fg px-6 py-20 text-center text-ink sm:py-28">
        {/* Inverted dot grid + saffron crown glow */}
        <div className="panel-dots-invert absolute inset-0 opacity-60" aria-hidden />
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-56"
          style={{ background: "radial-gradient(ellipse 55% 100% at 50% 0%, rgb(var(--color-saffron)/0.22), transparent 70%)" }}
          aria-hidden
        />
        {/* Ghost wordmark */}
        <span
          className="pointer-events-none absolute inset-x-0 -bottom-4 select-none text-center font-display text-[6rem] font-bold leading-none tracking-tighter text-ink/5 sm:-bottom-10 sm:text-[13rem]"
          aria-hidden
        >
          AEGIS
        </span>

        <div className="relative">
          <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-saffron">Get started</p>
          <h2 className="mt-4 font-display text-[clamp(2.25rem,5.5vw,3.75rem)] font-medium leading-[1.08] tracking-[-0.015em]">
            Ready when you are.
          </h2>
          <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-ink/60">
            Research like the institutions do — without paying like one.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-5">
            <Link
              href="/register"
              className="btn-sheen rounded-full bg-saffron px-7 py-3.5 text-sm font-semibold text-white shadow-lg shadow-saffron/25 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-saffron/40 active:scale-[0.98] active:translate-y-0"
            >
              Get started — it&apos;s free
            </Link>
            <Link href="/market" className="group text-sm font-medium text-ink/80 transition-colors hover:text-ink">
              <span className="link-sweep">or browse the market</span>
              <span className="inline-block transition-transform duration-300 group-hover:translate-x-1"> →</span>
            </Link>
          </div>
          {/* Mono proofline */}
          <div className="mt-11 flex flex-wrap items-center justify-center gap-x-3 gap-y-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ink/40">
            <span>5,000+ stocks</span>
            <span className="h-3 w-px bg-ink/20" aria-hidden />
            <span>NSE · BSE live</span>
            <span className="h-3 w-px bg-ink/20" aria-hidden />
            <span>₹0 forever</span>
          </div>
        </div>
      </section>
      </Reveal>

    </div>
  );
}
