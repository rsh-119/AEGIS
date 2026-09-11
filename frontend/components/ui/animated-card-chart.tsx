"use client";

import * as React from "react";
import { useId } from "react";
import { cn } from "@/lib/utils";
import { cardBaseClasses } from "@/components/ui/card";

// ─── ChartCard — wraps any existing chart with Visual3-inspired hover effects ──

/**
 * Drop-in replacement for `<Card className="overflow-hidden">` on chart sections.
 * On hover:
 *   - Colored top accent line sweeps in from the left
 *   - Gradient tint rises from the bottom
 *   - Border glows in the chart's color
 */
export function ChartCard({
  children,
  color = "#F5A524",
  className,
}: {
  children: React.ReactNode;
  color?: string;
  className?: string;
}) {
  const uid = useId().replace(/:/g, "");

  return (
    <div
      className={cn(
        "group/animated-card relative overflow-hidden transition-all duration-300",
        cardBaseClasses,
        className
      )}
    >
      {/* Top accent line — sweeps left→right on hover (like Visual3 top badge) */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 z-10 h-[2px] origin-left scale-x-0 transition-transform duration-500 ease-[cubic-bezier(0.6,0.6,0,1)] group-hover/animated-card:scale-x-100"
        style={{ background: color }}
      />

      {/* Bottom gradient tint — slides up on hover (Visual3 Layer3 style) */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 z-0 h-1/3 translate-y-4 opacity-0 transition-all duration-500 ease-[cubic-bezier(0.6,0.6,0,1)] group-hover/animated-card:translate-y-0 group-hover/animated-card:opacity-100"
        style={{ background: `linear-gradient(to top, ${color}20 0%, transparent 100%)` }}
      />

      {/* Border glow ring — appears on hover */}
      <div
        className="pointer-events-none absolute inset-0 z-10 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover/animated-card:opacity-100"
        style={{ boxShadow: `inset 0 0 0 1px ${color}40, 0 4px 24px ${color}15` }}
      />

      {/* SVG ellipse glow (Visual3 EllipseGradient style) — subtly tints center */}
      <div className="pointer-events-none absolute inset-0 z-0 opacity-0 transition-opacity duration-500 group-hover/animated-card:opacity-100">
        <svg width="100%" height="100%" preserveAspectRatio="none" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <radialGradient id={`eg-${uid}`} cx="50%" cy="50%" r="50%" gradientUnits="userSpaceOnUse">
              <stop stopColor={color} stopOpacity="0.08" />
              <stop offset="0.6" stopColor={color} stopOpacity="0.03" />
              <stop offset="1" stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect width="100%" height="100%" fill={`url(#eg-${uid})`} />
        </svg>
      </div>

      {/* Content — no z-index wrapper so chart canvases stay in natural stacking */}
      {children}
    </div>
  );
}
