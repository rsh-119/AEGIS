import * as React from "react"
import { Slot } from "@radix-ui/react-slot"

import { cn } from "@/lib/utils"

// Aegis only ever uses cards as a single flat wrapper — no header/title/
// footer sub-structure anywhere in the app — so this is one simple
// component, not shadcn's usual compound Card/CardHeader/CardTitle family.
// `cardBaseClasses` is exported so components/ui/animated-card-chart.tsx's
// ChartCard (which composes this same look) can reuse it instead of a
// separate copy.
export const cardBaseClasses =
  "bg-surface border border-border rounded-card shadow-sm dark:shadow-[var(--shadow-sm),inset_0_1px_0_rgba(255,255,255,0.04)]"

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Render the card look onto the child element (e.g. a <form>) instead of wrapping it in an extra <div>. */
  asChild?: boolean
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "div"
    return <Comp ref={ref} className={cn(cardBaseClasses, className)} {...props} />
  }
)
Card.displayName = "Card"

export { Card }
