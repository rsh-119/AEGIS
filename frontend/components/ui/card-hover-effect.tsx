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
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div className={clsx("grid gap-4 sm:grid-cols-3", className)}>
      {items.map((item, idx) => (
        <Link
          href={item.link}
          key={item.link}
          className="group relative block h-full w-full p-1"
          onMouseEnter={() => setHoveredIndex(idx)}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <AnimatePresence>
            {hoveredIndex === idx && (
              <motion.span
                layoutId="feature-hover-bg"
                className="absolute inset-0 block rounded-2xl bg-raised"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.15 } }}
                exit={{ opacity: 0, transition: { duration: 0.15, delay: 0.1 } }}
              />
            )}
          </AnimatePresence>

          <div className="relative z-10 flex h-full flex-col gap-4 overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-[var(--shadow-sm)] transition-colors duration-200">
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
      ))}
    </div>
  );
}
