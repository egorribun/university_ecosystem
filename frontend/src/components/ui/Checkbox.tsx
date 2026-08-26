"use client"

import * as React from "react"
import { m, AnimatePresence } from "framer-motion"
import { Check, Minus } from "lucide-react"
import { cn } from "@/utils/cn"

interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "checked"> {
  checked?: boolean | "indeterminate"
  onCheckedChange?: (checked: boolean | "indeterminate") => void
}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, checked, onCheckedChange, disabled, ...props }, ref) => {
    const inputRef = React.useRef<HTMLInputElement>(null)
    const isIndeterminate = checked === "indeterminate"
    const isChecked = checked === true || isIndeterminate

    React.useImperativeHandle(ref, () => inputRef.current as HTMLInputElement)

    React.useEffect(() => {
      // React assigns host refs before effects run, so the input is available
      // for the whole lifetime of this mounted effect.
      inputRef.current!.indeterminate = isIndeterminate
    }, [isIndeterminate])

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      onCheckedChange?.(e.target.checked)
    }

    return (
      <label className="relative inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center">
        <input
          {...props}
          ref={inputRef}
          type="checkbox"
          className="peer sr-only"
          checked={checked === true}
          aria-checked={isIndeterminate ? "mixed" : undefined}
          disabled={disabled}
          onChange={handleChange}
        />
        <div
          className={cn(
            "flex h-6 w-6 cursor-pointer items-center justify-center rounded-lg border-2 transition-all duration-base",
            "border-glass-border bg-glass-bg backdrop-blur-glass shadow-glass",
            "hover:border-brand/(--opacity-medium) hover:bg-glass-tint1",
            "peer-focus-visible:ring-4 peer-focus-visible:ring-brand/(--opacity-dim)",
            isChecked && "border-brand bg-brand/(--opacity-dim) shadow-glow-primary",
            disabled && "cursor-not-allowed grayscale",
            className
          )}
          style={disabled ? { opacity: "var(--opacity-medium)" } : undefined}
        >
          <AnimatePresence mode="wait">
            {isChecked && (
              <m.div
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.5, opacity: 0 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                className="text-brand check-celebrate"
              >
                {isIndeterminate ? (
                  <Minus className="h-4 w-4" style={{ strokeWidth: 3 }} />
                ) : (
                  <Check className="h-4 w-4" style={{ strokeWidth: 4 }} />
                )}
              </m.div>
            )}
          </AnimatePresence>
        </div>
      </label>
    )
  }
)
Checkbox.displayName = "Checkbox"

export { Checkbox }
