"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";

/** Counts up to `value` (easeOutQuart — settles, no bounce) the first time it
 * scrolls into view. Renders with tabular figures so digits don't jitter.
 * Under prefers-reduced-motion it jumps straight to the final value. */
export function MotionNumber({
  value,
  prefix = "",
  suffix = "",
  duration = 1400,
  className,
  locale = "en-IN",
}: {
  value: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  className?: string;
  locale?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        obs.disconnect();
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
          setDisplay(value);
          return;
        }
        const start = performance.now();
        const tick = (now: number) => {
          const p = Math.min((now - start) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 4);
          setDisplay(Math.round(value * eased));
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      },
      { threshold: 0.5 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [value, duration]);

  return (
    <span ref={ref} className={clsx("nums", className)}>
      {prefix}{display.toLocaleString(locale)}{suffix}
    </span>
  );
}
