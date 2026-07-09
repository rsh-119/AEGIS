"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import clsx from "clsx";
import { ChevronRight } from "lucide-react";

export type HoverEffectItem = {
  icon: React.ReactNode;
  title: string;
  description: string;
  link: string;
  color: string;
  accentColor: string;
};

export function HoverEffect({
  items,
  className,
}: {
  items: HoverEffectItem[];
  className?: string;
}) {
  return (
    <HoverEffectGroup count={items.length} layoutId="feature-hover-bg" className={clsx("grid gap-4 sm:grid-cols-3", className)}>
      {(idx) => {
        const item = items[idx];
        return (
          <Link href={item.link} className="group relative block h-full w-full p-1">
            <div className="relative z-10 flex h-full flex-col gap-4 overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-sm transition-colors duration-200">
              {/* Top gradient line */}
              <div className={clsx("absolute inset-x-0 top-0 h-[2px] opacity-0 transition-opacity duration-300 group-hover:opacity-100", item.accentColor)} />

              <span className={clsx(
                "flex h-11 w-11 items-center justify-center rounded-xl ring-1 transition-all duration-200",
                item.color
              )}>
                {item.icon}
              </span>
              <div className="flex-1">
                <h3 className="font-semibold text-fg">{item.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{item.description}</p>
              </div>
              <div className="flex items-center gap-1 text-xs font-semibold text-saffron">
                Explore <ChevronRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
              </div>
            </div>
          </Link>
        );
      }}
    </HoverEffectGroup>
  );
}

/** Shared hover-highlight mechanism behind HoverEffect, generalized so cards
 * with their own internal links (e.g. a widget with several linked rows)
 * can use the same sliding highlight without being wrapped in one outer
 * <Link> — which would break the nested links. Each group needs its own
 * unique `layoutId` so framer-motion's shared layout animation doesn't try
 * to animate a highlight between two unrelated groups on the same page. */
export function HoverEffectGroup({
  count,
  layoutId,
  className,
  children,
}: {
  count: number;
  layoutId: string;
  className?: string;
  children: (idx: number) => React.ReactNode;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div className={className}>
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className="group relative h-full w-full"
          onMouseEnter={() => setHoveredIndex(idx)}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <AnimatePresence>
            {hoveredIndex === idx && (
              <motion.span
                layoutId={layoutId}
                className="absolute -inset-1 block rounded-2xl bg-saffron/10 ring-1 ring-saffron/25"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.15 } }}
                exit={{ opacity: 0, transition: { duration: 0.15, delay: 0.1 } }}
              />
            )}
          </AnimatePresence>
          <div className="relative z-10 h-full transition-transform duration-200 group-hover:-translate-y-0.5">
            {children(idx)}
          </div>
        </div>
      ))}
    </div>
  );
}
