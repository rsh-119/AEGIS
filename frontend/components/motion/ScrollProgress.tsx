"use client";

import { motion, useScroll } from "framer-motion";

/** Thin page-scroll progress bar pinned above the nav. Scroll-linked (not
 * time-based) so there's nothing to bounce; hidden under reduced motion. */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  return (
    <motion.div
      aria-hidden
      style={{ scaleX: scrollYProgress }}
      className="fixed inset-x-0 top-0 z-[60] h-[2px] origin-left bg-saffron motion-reduce:hidden"
    />
  );
}
