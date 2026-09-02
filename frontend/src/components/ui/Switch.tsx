"use client"

import * as React from "react"
import { m } from "framer-motion"
import { cn } from "@/utils/cn"

interface SwitchProps extends React.InputHTMLAttributes<HTMLInputElement> {
  checked: boolean
  onCheckedChange?: (checked: boolean) => void
}

const Switch = React.forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, checked, onCheckedChange, disabled, ...props }, ref) => {
    const [hover, setHover] = React.useState(false)
    const [focus, setFocus] = React.useState(false)
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      onCheckedChange?.(e.target.checked)
    }

    return (
      <span
        className={cn(
          "relative inline-flex min-h-11 w-14 cursor-pointer items-center rounded-full",
          "touch-manipulation select-none transition-premium",
          disabled ? "cursor-not-allowed opacity-medium" : "hover:scale-105 active:scale-95",
          className
        )}
        onMouseEnter={() => !disabled && setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        {/* Focus ring */}
        <span
          className={cn(
            "pointer-events-none absolute inset-x-0 top-2 h-7 rounded-full transition-premium",
            focus && !disabled
              ? "scale-100 opacity-100 ring-4 ring-brand/(--opacity-dim)"
              : "scale-90 opacity-0"
          )}
        />

        {/* Track */}
        <m.span
          className={cn(
            "absolute inset-x-0 top-2 h-7 rounded-full border border-border-subtle transition-colors duration-base",
            "bg-(--bg-surface)-tint backdrop-blur-sm",
            checked && "bg-brand/(--opacity-dim) border-brand/(--opacity-soft)"
          )}
          animate={{
            borderColor: checked
              ? "var(--primary-main)"
              : hover && !disabled
                ? "var(--primary-hover)"
                : "var(--border-subtle)",
            backgroundColor: checked
              ? "color-mix(in srgb, var(--primary-main) 15%, transparent)"
              : hover && !disabled
                ? "var(--bg-surface-hover)"
                : "var(--bg-surface)",
          }}
          transition={{ duration: 0.2 }}
        />

        {/* Thumb */}
        <m.span
          initial={{ x: checked ? 28 : 0, scale: 1 }}
          animate={{
            x: checked ? 28 : 0,
            scale: hover ? 1.1 : 1,
          }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
          className={cn(
            "relative z-deep ml-0.5 block h-5.5 w-5.5 rounded-full bg-surface shadow-surface",
            "border border-glass-border-subtle",
            "bg-surface",
            checked && "bg-surface"
          )}
          style={{
            transformOrigin: checked ? "left center" : "right center",
          }}
        />

        <input
          type="checkbox"
          role="switch"
          ref={ref}
          checked={checked}
          disabled={disabled}
          onChange={handleChange}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          {...props}
        />
      </span>
    )
  }
)
Switch.displayName = "Switch"

export { Switch }
