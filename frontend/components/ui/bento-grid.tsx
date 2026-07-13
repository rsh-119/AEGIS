"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Reveal } from "@/components/motion";
import { useOutsideClick } from "@/hooks/use-outside-click";

/* MagicUI "Bento Grid" + Aceternity "Expandable Card", merged and ported to
 * Aegis tokens. Collapsed cards keep the bento hover choreography (content
 * lifts, icon shrinks, CTA hint slides up). Clicking a card morphs it — via
 * framer-motion shared layoutIds — into a centered modal with the card's
 * background visual on top, longer `content` copy, and a real CTA link.
 * Modal closes on Escape, backdrop click, or the close button. */

export type BentoItem = {
  Icon: React.ElementType;
  name: string;
  description: string;
  href: string;
  cta: string;
  /** Grid-placement classes for the bento rhythm (e.g. "lg:col-span-2"). */
  className?: string;
  /** Decorative readout rendered in the card's upper area and the modal header. */
  background: React.ReactNode;
  /** Expanded copy shown only in the modal. */
  content: React.ReactNode;
};

const MotionLink = motion.create(Link);

export function BentoGrid({ items, className }: { items: BentoItem[]; className?: string }) {
  const [active, setActive] = useState<BentoItem | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setActive(null);
    }
    document.body.style.overflow = active ? "hidden" : "auto";
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active]);

  useOutsideClick(ref, () => setActive(null));

  return (
    <>
      {/* Backdrop */}
      <AnimatePresence>
        {active && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 h-full w-full bg-black/30 backdrop-blur-[2px]"
          />
        )}
      </AnimatePresence>

      {/* Expanded card */}
      <AnimatePresence>
        {active && (
          <div className="fixed inset-0 z-50 grid place-items-center p-4">
            <motion.div
              layoutId={`bento-card-${active.name}-${id}`}
              ref={ref}
              className="flex w-full max-w-lg flex-col overflow-hidden rounded-3xl border border-border bg-surface shadow-2xl shadow-black/20"
            >
              {/* Visual header — the card's readout, given room to breathe */}
              <motion.div
                layoutId={`bento-bg-${active.name}-${id}`}
                className="relative h-40 shrink-0 border-b border-border bg-raised/40"
              >
                {active.background}
                <button
                  onClick={() => setActive(null)}
                  aria-label="Close"
                  className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full border border-border bg-surface text-muted transition-colors hover:text-fg"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </motion.div>

              <div className="flex items-start justify-between gap-4 p-6 pb-4">
                <div className="min-w-0">
                  <motion.h3
                    layoutId={`bento-title-${active.name}-${id}`}
                    className="font-display text-xl font-semibold text-fg"
                  >
                    {active.name}
                  </motion.h3>
                  <motion.p
                    layoutId={`bento-desc-${active.name}-${id}`}
                    className="mt-1 text-sm leading-relaxed text-muted"
                  >
                    {active.description}
                  </motion.p>
                </div>
                <MotionLink
                  layoutId={`bento-cta-${active.name}-${id}`}
                  href={active.href}
                  className="shrink-0 rounded-full bg-fg px-4 py-2 text-sm font-semibold text-ink shadow-sm transition-transform hover:-translate-y-0.5"
                >
                  {active.cta}
                </MotionLink>
              </div>

              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="max-h-52 space-y-3 overflow-auto px-6 pb-6 text-sm leading-relaxed text-muted [-ms-overflow-style:none] [mask:linear-gradient(to_bottom,white,white,transparent)] [scrollbar-width:none]"
              >
                {active.content}
              </motion.div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Collapsed grid */}
      <div className={cn("grid w-full auto-rows-[17.5rem] grid-cols-3 gap-4", className)}>
        {items.map((item, i) => (
          <Reveal key={item.name} delay={i * 100} className={cn("col-span-3", item.className)}>
            <motion.div
              layoutId={`bento-card-${item.name}-${id}`}
              onClick={() => setActive(item)}
              onMouseMove={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                e.currentTarget.style.setProperty("--sx", `${e.clientX - r.left}px`);
                e.currentTarget.style.setProperty("--sy", `${e.clientY - r.top}px`);
              }}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setActive(item); } }}
              role="button"
              tabIndex={0}
              aria-haspopup="dialog"
              className="group relative flex h-full w-full cursor-pointer flex-col justify-end overflow-hidden rounded-3xl border border-border bg-surface shadow-sm transition-[box-shadow,transform] duration-300 hover:shadow-lg hover:shadow-black/5 active:scale-[0.99]"
            >
              {/* Background slot */}
              <motion.div
                layoutId={`bento-bg-${item.name}-${id}`}
                className="pointer-events-none absolute inset-0"
                aria-hidden
              >
                {item.background}
              </motion.div>
              {/* Legibility fade over the background's lower half */}
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-surface via-surface/60 to-transparent" aria-hidden />
              <div className="spotlight-layer" aria-hidden />

              {/* Content — lifts on hover to make room for the CTA hint */}
              <div className="pointer-events-none relative z-10 flex flex-col gap-1 p-6 transition-all duration-300 group-hover:-translate-y-8">
                <item.Icon className="h-10 w-10 origin-left text-fg transition-all duration-300 ease-in-out group-hover:-rotate-6 group-hover:scale-75 group-hover:text-saffron" />
                <motion.h3
                  layoutId={`bento-title-${item.name}-${id}`}
                  className="mt-2 font-display text-xl font-semibold text-fg transition-colors duration-300 group-hover:text-saffron"
                >
                  {item.name}
                </motion.h3>
                <motion.p
                  layoutId={`bento-desc-${item.name}-${id}`}
                  className="max-w-lg text-sm leading-relaxed text-muted"
                >
                  {item.description}
                </motion.p>
              </div>

              {/* CTA hint — slides up into the vacated space */}
              <div className="pointer-events-none absolute bottom-0 z-10 flex w-full translate-y-10 items-center p-6 opacity-0 transition-all duration-300 group-hover:translate-y-0 group-hover:opacity-100">
                <motion.span
                  layoutId={`bento-cta-${item.name}-${id}`}
                  className="flex items-center gap-1.5 text-xs font-semibold text-saffron"
                >
                  {item.cta} <ArrowRight className="h-3.5 w-3.5" />
                </motion.span>
              </div>

              {/* Hover scrim */}
              <div className="pointer-events-none absolute inset-0 transition-all duration-300 group-hover:bg-fg/[.02]" aria-hidden />
            </motion.div>
          </Reveal>
        ))}
      </div>
    </>
  );
}
