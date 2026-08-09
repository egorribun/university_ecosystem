"use client"

import * as React from "react"
import { m, AnimatePresence } from "framer-motion"
import { cn } from "@/utils/cn"

interface RadioGroupProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  value?: string
  onChange?: (event: React.ChangeEvent<HTMLInputElement> | null, value: string) => void
  disabled?: boolean
  name?: string
  row?: boolean
}

const RadioGroupContext = React.createContext<{
  value?: string
  onChange: (value: string) => void
  disabled?: boolean
  name?: string
} | null>(null)

const RadioGroup = React.forwardRef<HTMLDivElement, RadioGroupProps>(
  ({ className, value, onChange, disabled, name, row, ...props }, ref) => {
    const handleValueChange = (val: string) => {
      onChange?.(null, val)
    }

    return (
      <RadioGroupContext.Provider value={{ value, onChange: handleValueChange, disabled, name }}>
        <div
          ref={ref}
          className={cn(row ? "flex flex-row flex-wrap gap-4" : "grid gap-2", className)}
          {...props}
        />
      </RadioGroupContext.Provider>
    )
  }
)
RadioGroup.displayName = "RadioGroup"

interface RadioGroupItemProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  value?: string
}

const RadioGroupItem = React.forwardRef<HTMLInputElement, RadioGroupItemProps>(
  ({ className, value, disabled, ...props }, ref) => {
    const context = React.useContext(RadioGroupContext)
    if (!context) throw new Error("RadioGroupItem must be used within a RadioGroup")

    const isSelected = context.value === value
    const isDisabled = context.disabled || disabled

    return (
      // Keep the item phrasing-only so consumers can wrap it in a
      // FormControlLabel without producing invalid nested <label> elements.
      <>
        <input
          type="radio"
          ref={ref}
          className="peer sr-only"
          value={value}
          checked={isSelected}
          disabled={isDisabled}
          name={context.name}
          onChange={() => value && context.onChange(value)}
          {...props}
        />
        <span
          aria-hidden="true"
          className={cn(
            "relative inline-flex cursor-pointer items-center p-1",
            isDisabled && "cursor-not-allowed opacity-medium grayscale"
          )}
        >
          <span
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full border-2 transition-all duration-base",
              "border-glass-border bg-glass-bg backdrop-blur-glass shadow-glass",
              "hover:border-brand/(--opacity-medium) hover:bg-glass-tint1",
              "peer-focus-visible:ring-4 peer-focus-visible:ring-brand/(--opacity-dim)",
              isSelected && "border-brand bg-brand/(--opacity-subtle) shadow-glow-primary",
              className
            )}
          >
            <AnimatePresence>
              {isSelected && (
                <m.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  exit={{ scale: 0 }}
                  transition={{ type: "spring", stiffness: 500, damping: 30 }}
                  className="h-2.5 w-2.5 rounded-full bg-brand"
                />
              )}
            </AnimatePresence>
          </span>
        </span>
      </>
    )
  }
)
RadioGroupItem.displayName = "RadioGroupItem"

export { RadioGroup, RadioGroupItem }
