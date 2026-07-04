"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

type RippleSpan = { id: number; x: number; y: number; size: number };

// Material-style expanding ripple on click, layered onto a real Next.js
// <Link> (keeps middle-click/open-in-new-tab working, unlike a <button>).
export function RippleLink({
  href,
  className,
  rippleClassName = "bg-saffron/20",
  children,
  onClick,
}: {
  href: string;
  className?: string;
  rippleClassName?: string;
  children: React.ReactNode;
  onClick?: () => void;
}) {
  const [ripples, setRipples] = useState<RippleSpan[]>([]);
  const nextId = useRef(0);

  function spawnRipple(e: React.MouseEvent<HTMLAnchorElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const id = nextId.current++;
    setRipples((r) => [
      ...r,
      { id, x: e.clientX - rect.left - size / 2, y: e.clientY - rect.top - size / 2, size },
    ]);
    setTimeout(() => setRipples((r) => r.filter((rp) => rp.id !== id)), 500);
  }

  return (
    <Link
      href={href}
      className={cn("relative overflow-hidden", className)}
      onClick={(e) => { spawnRipple(e); onClick?.(); }}
    >
      {children}
      {ripples.map((r) => (
        <span
          key={r.id}
          className={cn("pointer-events-none absolute rounded-full animate-ripple", rippleClassName)}
          style={{ left: r.x, top: r.y, width: r.size, height: r.size }}
        />
      ))}
    </Link>
  );
}
