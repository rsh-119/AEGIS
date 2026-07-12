"use client";

import { Children } from "react";
import { Reveal } from "./Reveal";

/** Wraps each direct child in a Reveal with an incremental delay, so groups
 * (stat tiles, card rows) cascade in ~70ms apart instead of landing at once. */
export function Stagger({
  children,
  step = 70,
  className,
  itemClassName,
}: {
  children: React.ReactNode;
  step?: number;
  className?: string;
  itemClassName?: string;
}) {
  return (
    <div className={className}>
      {Children.map(children, (child, i) => (
        <Reveal delay={i * step} className={itemClassName}>
          {child}
        </Reveal>
      ))}
    </div>
  );
}
