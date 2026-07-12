"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";

/** Scroll-triggered reveal: children fade in and rise ~26px the first time
 * they enter the viewport. Pure CSS transition (see `.reveal` in globals.css —
 * opacity + transform only, both compositable, so it never repaints); this
 * component only toggles the visible class. `delay` staggers siblings.
 * The `.reveal-visible` class also drives the in-mock micro-animations
 * (sparkline draw, allocation growth, concall bullet stagger). */
export function Reveal({
  children,
  delay = 0,
  className,
  onMouseMove,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  onMouseMove?: React.MouseEventHandler<HTMLDivElement>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          obs.disconnect();
        }
      },
      // Fire once the element's top clears the bottom ~8% of the viewport,
      // so the rise is visible rather than already finished off-screen.
      { rootMargin: "0px 0px -8% 0px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
      className={clsx("reveal", visible && "reveal-visible", className)}
      onMouseMove={onMouseMove}
    >
      {children}
    </div>
  );
}
