import * as React from "react"

import { cn } from "@/lib/utils"

// Exported so native <select> elements (which keep native semantics rather
// than becoming a Radix Select — see the migration plan) can be styled
// identically to <Input> with the same class string.
export const inputBaseClasses =
  "flex w-full rounded-[6px] border border-border bg-surface px-3 py-2 text-sm font-light text-fg placeholder:text-muted/60 outline-none transition-all duration-150 focus:border-saffron focus:shadow-[0_0_0_3px_rgba(21,128,61,0.10)] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-raised dark:shadow-[inset_0_1px_3px_rgba(0,0,0,0.25)] dark:focus:shadow-[inset_0_1px_3px_rgba(0,0,0,0.25),0_0_0_3px_rgba(74,222,128,0.12)]"

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(inputBaseClasses, className)}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
