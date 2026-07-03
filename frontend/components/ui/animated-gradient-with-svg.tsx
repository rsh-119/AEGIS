"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useDimensions } from "@/components/hooks/use-debounced-dimensions";

interface AnimatedGradientProps {
  colors: string[];
  speed?: number;
  blur?: "light" | "medium" | "heavy";
}

interface CircleValues {
  top: number;
  left: number;
  tx1: number; ty1: number;
  tx2: number; ty2: number;
  tx3: number; ty3: number;
  tx4: number; ty4: number;
  wMult: number;
  hMult: number;
}

function makeValues(count: number): CircleValues[] {
  return Array.from({ length: count }, () => ({
    top:   Math.random() * 50,
    left:  Math.random() * 50,
    tx1: Math.random() - 0.5, ty1: Math.random() - 0.5,
    tx2: Math.random() - 0.5, ty2: Math.random() - 0.5,
    tx3: Math.random() - 0.5, ty3: Math.random() - 0.5,
    tx4: Math.random() - 0.5, ty4: Math.random() - 0.5,
    wMult: 0.5 + Math.random(),
    hMult: 0.5 + Math.random(),
  }));
}

const AnimatedGradient: React.FC<AnimatedGradientProps> = ({
  colors,
  speed = 5,
  blur = "light",
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const dimensions = useDimensions(containerRef);

  // All random values are generated client-side only to avoid SSR hydration mismatch
  const [circles, setCircles] = useState<CircleValues[] | null>(null);
  useEffect(() => {
    setCircles(makeValues(colors.length));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colors.length]);

  const circleSize = useMemo(
    () => Math.max(dimensions.width, dimensions.height),
    [dimensions.width, dimensions.height]
  );

  const blurClass =
    blur === "light"
      ? "blur-2xl"
      : blur === "medium"
      ? "blur-3xl"
      : "blur-[100px]";

  return (
    <div ref={containerRef} className="absolute inset-0 overflow-hidden">
      <div className={cn("absolute inset-0", blurClass)}>
        {circles &&
          colors.map((color, index) => {
            const v = circles[index];
            return (
              <svg
                key={index}
                className="absolute animate-background-gradient"
                style={
                  {
                    top:  `${v.top}%`,
                    left: `${v.left}%`,
                    "--background-gradient-speed": `${1 / speed}s`,
                    "--tx-1": v.tx1, "--ty-1": v.ty1,
                    "--tx-2": v.tx2, "--ty-2": v.ty2,
                    "--tx-3": v.tx3, "--ty-3": v.ty3,
                    "--tx-4": v.tx4, "--ty-4": v.ty4,
                  } as React.CSSProperties
                }
                width={circleSize * v.wMult}
                height={circleSize * v.hMult}
                viewBox="0 0 100 100"
              >
                <circle
                  cx="50"
                  cy="50"
                  r="50"
                  fill={color}
                  className="opacity-30 dark:opacity-[0.15]"
                />
              </svg>
            );
          })}
      </div>
    </div>
  );
};

export { AnimatedGradient };
