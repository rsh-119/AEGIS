import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// Pill shape, tight padding — matches the app's .btn-primary/.btn-ghost look.
// Only "default" and "ghost" variants exist because those are the only two
// actually used anywhere in the app (no destructive/outline/secondary/link
// call sites) — see /home/rsh/.claude/plans/composed-rolling-petal.md.
const buttonVariants = cva(
  "relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition-all duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saffron/40 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-saffron text-white shadow-[0_1px_3px_rgba(21,128,61,0.30),inset_0_1px_0_rgba(255,255,255,0.15)] hover:-translate-y-px hover:bg-[rgba(22,101,52,1)] hover:shadow-[0_4px_14px_rgba(21,128,61,0.40),inset_0_1px_0_rgba(255,255,255,0.15)] dark:text-[#022c22] dark:shadow-[0_2px_10px_rgba(74,222,128,0.25),inset_0_1px_0_rgba(255,255,255,0.1)] dark:hover:bg-saffron dark:hover:shadow-[0_4px_20px_rgba(74,222,128,0.38),inset_0_1px_0_rgba(255,255,255,0.15)]",
        ghost:
          "border border-border text-muted hover:bg-raised/80 hover:text-fg",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
