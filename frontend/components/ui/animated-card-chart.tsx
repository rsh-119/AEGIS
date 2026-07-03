"use client";

import * as React from "react";
import { useId, useState } from "react";
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ─── Base card parts ──────────────────────────────────────────────────────────

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {}

export function AnimatedCard({ className, ...props }: CardProps) {
  return (
    <div
      role="region"
      aria-labelledby="card-title"
      aria-describedby="card-description"
      className={cn(
        "group/animated-card relative w-[356px] overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-900 dark:bg-black",
        className
      )}
      {...props}
    />
  );
}

export function CardBody({ className, ...props }: CardProps) {
  return (
    <div
      role="group"
      className={cn(
        "flex flex-col space-y-1.5 border-t border-zinc-200 p-4 dark:border-zinc-900",
        className
      )}
      {...props}
    />
  );
}

interface CardTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {}
export function CardTitle({ className, ...props }: CardTitleProps) {
  return (
    <h3
      className={cn(
        "text-lg font-semibold leading-none tracking-tight text-black dark:text-white",
        className
      )}
      {...props}
    />
  );
}

interface CardDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {}
export function CardDescription({ className, ...props }: CardDescriptionProps) {
  return (
    <p
      className={cn("text-sm text-neutral-500 dark:text-neutral-400", className)}
      {...props}
    />
  );
}

export function CardVisual({ className, ...props }: CardProps) {
  return (
    <div className={cn("h-[180px] w-[356px] overflow-hidden", className)} {...props} />
  );
}

// ─── Visual3 (bar chart demo) ─────────────────────────────────────────────────

interface Visual3Props {
  mainColor?: string;
  secondaryColor?: string;
  gridColor?: string;
}

export function Visual3({
  mainColor = "#8b5cf6",
  secondaryColor = "#fbbf24",
  gridColor = "#80808015",
}: Visual3Props) {
  const [hovered, setHovered] = useState(false);

  return (
    <>
      <div
        className="absolute inset-0 z-20"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{ "--color": mainColor, "--secondary-color": secondaryColor } as React.CSSProperties}
      />
      <div className="relative h-[180px] w-[356px] overflow-hidden rounded-t-lg">
        <Layer4 color={mainColor} secondaryColor={secondaryColor} hovered={hovered} />
        <Layer3 color={mainColor} />
        <Layer2 color={mainColor} />
        <Layer1 color={mainColor} secondaryColor={secondaryColor} />
        <EllipseGradient color={mainColor} />
        <GridLayer color={gridColor} />
      </div>
    </>
  );
}

interface LayerProps { color: string; secondaryColor?: string; hovered?: boolean; }

const GridLayer: React.FC<{ color: string }> = ({ color }) => (
  <div
    style={{ "--grid-color": color } as React.CSSProperties}
    className="pointer-events-none absolute inset-0 z-[4] h-full w-full bg-transparent bg-[linear-gradient(to_right,var(--grid-color)_1px,transparent_1px),linear-gradient(to_bottom,var(--grid-color)_1px,transparent_1px)] bg-[size:20px_20px] bg-center opacity-70 [mask-image:radial-gradient(ellipse_50%_50%_at_50%_50%,#000_60%,transparent_100%)]"
  />
);

const EllipseGradient: React.FC<{ color: string }> = ({ color }) => (
  <div className="absolute inset-0 z-[5] flex h-full w-full items-center justify-center">
    <svg width="356" height="196" viewBox="0 0 356 180" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="356" height="180" fill="url(#paint0_radial_12_207)" />
      <defs>
        <radialGradient id="paint0_radial_12_207" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse"
          gradientTransform="translate(178 98) rotate(90) scale(98 178)">
          <stop stopColor={color} stopOpacity="0.25" />
          <stop offset="0.34" stopColor={color} stopOpacity="0.15" />
          <stop offset="1" stopOpacity="0" />
        </radialGradient>
      </defs>
    </svg>
  </div>
);

const Layer1: React.FC<LayerProps> = ({ color, secondaryColor }) => (
  <div
    className="absolute top-4 left-4 z-[8] flex items-center gap-1"
    style={{ "--color": color, "--secondary-color": secondaryColor } as React.CSSProperties}
  >
    <div className="flex shrink-0 items-center rounded-full border border-zinc-200 bg-white/25 px-1.5 py-0.5 backdrop-blur-sm transition-opacity duration-300 ease-in-out group-hover/animated-card:opacity-0 dark:border-zinc-800 dark:bg-black/25">
      <div className="h-1.5 w-1.5 rounded-full bg-[var(--color)]" />
      <span className="ml-1 text-[10px] text-black dark:text-white">+15,2%</span>
    </div>
    <div className="flex shrink-0 items-center rounded-full border border-zinc-200 bg-white/25 px-1.5 py-0.5 backdrop-blur-sm transition-opacity duration-300 ease-in-out group-hover/animated-card:opacity-0 dark:border-zinc-800 dark:bg-black/25">
      <div className="h-1.5 w-1.5 rounded-full bg-[var(--secondary-color)]" />
      <span className="ml-1 text-[10px] text-black dark:text-white">+18,7%</span>
    </div>
  </div>
);

const Layer2: React.FC<{ color: string }> = ({ color }) => (
  <div
    className="group relative h-full w-[356px]"
    style={{ "--color": color } as React.CSSProperties}
  >
    <div className="ease-[cubic-bezier(0.6,0.6,0,1)] absolute inset-0 z-[7] flex w-[356px] translate-y-full items-start justify-center bg-transparent p-4 transition-transform duration-500 group-hover/animated-card:translate-y-0">
      <div className="ease-[cubic-bezier(0.6,0,1)] rounded-md border border-zinc-200 bg-white/25 p-1.5 opacity-0 backdrop-blur-sm transition-opacity duration-500 group-hover/animated-card:opacity-100 dark:border-zinc-800 dark:bg-black/25">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 shrink-0 rounded-full bg-[var(--color)]" />
          <p className="text-xs text-black dark:text-white">Random Data Visualization</p>
        </div>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">Displaying some interesting stats.</p>
      </div>
    </div>
  </div>
);

const Layer3: React.FC<{ color: string }> = ({ color }) => (
  <div className="ease-[cubic-bezier(0.6,0.6,0,1)] absolute inset-0 z-[6] flex translate-y-full items-center justify-center opacity-0 transition-all duration-500 group-hover/animated-card:translate-y-0 group-hover/animated-card:opacity-100">
    <svg width="356" height="180" viewBox="0 0 356 180" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="356" height="180" fill="url(#paint0_linear_29_3)" />
      <defs>
        <linearGradient id="paint0_linear_29_3" x1="178" y1="0" x2="178" y2="180" gradientUnits="userSpaceOnUse">
          <stop offset="0.35" stopColor={color} stopOpacity="0" />
          <stop offset="1" stopColor={color} stopOpacity="0.3" />
        </linearGradient>
      </defs>
    </svg>
  </div>
);

const Layer4: React.FC<LayerProps> = ({ color, secondaryColor, hovered }) => {
  const rectsData = [
    { width: 15, height: 20, y: 110, hoverHeight: 20, hoverY: 130, x: 40,  fill: "currentColor", hoverFill: secondaryColor },
    { width: 15, height: 20, y: 90,  hoverHeight: 20, hoverY: 130, x: 60,  fill: color, hoverFill: color },
    { width: 15, height: 40, y: 70,  hoverHeight: 30, hoverY: 120, x: 80,  fill: color, hoverFill: color },
    { width: 15, height: 30, y: 80,  hoverHeight: 50, hoverY: 100, x: 100, fill: color, hoverFill: color },
    { width: 15, height: 30, y: 110, hoverHeight: 40, hoverY: 110, x: 120, fill: "currentColor", hoverFill: secondaryColor },
    { width: 15, height: 50, y: 110, hoverHeight: 20, hoverY: 130, x: 140, fill: "currentColor", hoverFill: secondaryColor },
    { width: 15, height: 50, y: 60,  hoverHeight: 30, hoverY: 120, x: 160, fill: color, hoverFill: color },
    { width: 15, height: 30, y: 80,  hoverHeight: 20, hoverY: 130, x: 180, fill: color, hoverFill: color },
    { width: 15, height: 20, y: 110, hoverHeight: 40, hoverY: 110, x: 200, fill: "currentColor", hoverFill: secondaryColor },
    { width: 15, height: 40, y: 70,  hoverHeight: 60, hoverY: 90,  x: 220, fill: color, hoverFill: color },
    { width: 15, height: 30, y: 110, hoverHeight: 70, hoverY: 80,  x: 240, fill: "currentColor", hoverFill: secondaryColor },
    { width: 15, height: 50, y: 110, hoverHeight: 50, hoverY: 100, x: 260, fill: "currentColor", hoverFill: secondaryColor },
    { width: 15, height: 20, y: 110, hoverHeight: 80, hoverY: 70,  x: 280, fill: "currentColor", hoverFill: secondaryColor },
    { width: 15, height: 30, y: 80,  hoverHeight: 90, hoverY: 60,  x: 300, fill: color, hoverFill: color },
  ];

  return (
    <div className="ease-[cubic-bezier(0.6,0.6,0,1)] absolute inset-0 z-[8] flex h-[180px] w-[356px] items-center justify-center text-neutral-800/10 transition-transform duration-500 group-hover/animated-card:scale-150 dark:text-white/15">
      <svg width="356" height="180" xmlns="http://www.w3.org/2000/svg">
        {rectsData.map((rect, index) => (
          <rect
            key={index}
            width={rect.width}
            height={hovered ? rect.hoverHeight : rect.height}
            x={rect.x}
            y={hovered ? rect.hoverY : rect.y}
            fill={hovered ? rect.hoverFill : rect.fill}
            rx="2" ry="2"
            className="ease-[cubic-bezier(0.6,0.6,0,1)] transition-all duration-500"
          />
        ))}
      </svg>
    </div>
  );
};

// ─── ChartCard — wraps any existing chart with Visual3-inspired hover effects ──

/**
 * Drop-in replacement for `<div className="card overflow-hidden">` on chart sections.
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
        "group/animated-card card relative overflow-hidden transition-all duration-300",
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
