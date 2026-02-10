"use client"

import * as React from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Check, Minus } from "lucide-react"
import { cn } from "@/utils/cn"

interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "checked"> {
  checked?: boolean | "indeterminate"
  onCheckedChange?: (checked: boolean | "indeterminate") => void
}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, checked, onCheckedChange, disabled, ...props }, ref) => {
    const isIndeterminate = checked === "indeterminate"
    const isChecked = checked === true || isIndeterminate

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      onCheckedChange?.(e.target.checked)
    }

    return (
      <label className="relative inline-flex cursor-pointer items-center">
        <input
          type="checkbox"
          ref={ref}
          className="peer sr-only"
          checked={checked === true}
          disabled={disabled}
          onChange={handleChange}
          {...props}
        />
        <div
          className={cn(
            "flex h-6 w-6 cursor-pointer items-center justify-center rounded-lg border-2 transition-all duration-300",
            "border-glass-border bg-glass-bg backdrop-blur-glass shadow-glass",
            "hover:border-brand/40 hover:bg-glass-tint1",
            "peer-focus-visible:ring-4 peer-focus-visible:ring-brand/20",
            isChecked && "border-brand bg-brand/10 shadow-glow-primary",
            disabled && "cursor-not-allowed opacity-40 grayscale",
            className
          )}
        >
          <AnimatePresence mode="wait">
            {isChecked && (
              <motion.div
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.5, opacity: 0 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                className="text-brand"
              >
                {isIndeterminate ? (
                  <Minus className="h-4 w-4 stroke-[3px]" />
                ) : (
                  <Check className="h-4 w-4 stroke-[4px]" />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </label>
    )
  }
)
Checkbox.displayName = "Checkbox"

export { Checkbox }
