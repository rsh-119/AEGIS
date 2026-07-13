"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

/* MagicUI "Interactive Hover Button", adapted to Aegis tokens.
 * Rest: bordered surface pill with a small fg dot beside the label.
 * Hover: the dot scales ~100x into a full fg fill while a contrast-colored
 * copy of the label plus an arrow slides in — resolving into the same
 * black-pill CTA language the landing page already uses (cream pill in dark
 * mode, since fg/ink invert per theme).
 * Renders a Next <Link> when `href` is given, otherwise a <button>. */
interface InteractiveHoverButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  href?: string;
}

export function InteractiveHoverButton({
  children,
  className,
  href,
  ...props
}: InteractiveHoverButtonProps) {
  const classes = cn(
    "group relative w-auto cursor-pointer overflow-hidden rounded-full border border-border bg-surface px-6 py-2.5 text-center text-sm font-semibold text-fg shadow-sm transition-transform active:scale-[0.97]",
    className,
  );

  const inner = (
    <>
      <div className="flex items-center gap-2">
        <div className="h-2 w-2 rounded-full bg-fg transition-all duration-300 group-hover:scale-[100.8]" />
        <span className="inline-block whitespace-nowrap transition-all duration-300 group-hover:translate-x-12 group-hover:opacity-0">
          {children}
        </span>
      </div>
      <div className="absolute left-0 top-0 z-10 flex h-full w-full translate-x-12 items-center justify-center gap-2 whitespace-nowrap text-ink opacity-0 transition-all duration-300 group-hover:-translate-x-1 group-hover:opacity-100">
        <span>{children}</span>
        <ArrowRight className="h-4 w-4" />
      </div>
    </>
  );

  if (href) {
    return (
      <Link href={href} className={cn("inline-block", classes)}>
        {inner}
      </Link>
    );
  }
  return (
    <button className={classes} {...props}>
      {inner}
    </button>
  );
}
