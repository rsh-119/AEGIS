import * as React from "react"
import { Slot } from "@radix-ui/react-slot"

import { cn } from "@/lib/utils"

// Matches .pill exactly: a bare shape shell with no baked-in color — every
// call site in the app pairs its own bg-X/10 text-X utility classes on top.
export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Render the badge look onto the child element (e.g. a <Link>) instead of wrapping it. */
  asChild?: boolean
}

function Badge({ className, asChild = false, ...props }: BadgeProps) {
  const Comp = asChild ? Slot : "div"
  return (
    <Comp
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium",
        className
      )}
      {...props}
    />
  )
}

export { Badge }
