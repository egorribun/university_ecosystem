"use client"

import * as React from "react"
import { motion, useAnimation } from "framer-motion"
import { cn } from "@/utils/cn"

interface SwitchProps extends React.InputHTMLAttributes<HTMLInputElement> {
  checked: boolean
  onCheckedChange?: (checked: boolean) => void
}

const Switch = React.forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, checked, onCheckedChange, disabled, ...props }, ref) => {
    const [hover, setHover] = React.useState(false)
    const [focus, setFocus] = React.useState(false)
    const controls = useAnimation()
    const isFirstRender = React.useRef(true)

    React.useEffect(() => {
      if (isFirstRender.current) {
        isFirstRender.current = false
        return
      }
      controls.start({
        x: checked ? 26 : 0,
        scaleX: [1, 1.6, 0.85, 1.1, 1],
        scaleY: [1, 0.7, 1.15, 0.95, 1],
        transition: {
          x: { type: "spring", stiffness: 200, damping: 20 },
          scaleX: { duration: 0.5, ease: "easeInOut", times: [0, 0.4, 0.7, 0.9, 1] },
          scaleY: { duration: 0.5, ease: "easeInOut", times: [0, 0.4, 0.7, 0.9, 1] },
        },
      })
    }, [checked, controls])

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      onCheckedChange?.(e.target.checked)
    }

    return (
      <span
        className={cn(
          "relative inline-flex h-[28px] w-[56px] cursor-pointer items-center rounded-full p-[3px]",
          "touch-manipulation select-none transition-transform duration-200",
          disabled ? "cursor-not-allowed opacity-50" : "hover:scale-[1.02] active:scale-[0.98]",
          className
        )}
        onMouseEnter={() => !disabled && setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        {/* Focus ring */}
        <span
          className={cn(
            "pointer-events-none absolute -inset-1 rounded-full transition-all duration-300",
            focus && !disabled
              ? "scale-100 opacity-100 ring-4 ring-brand/20"
              : "scale-90 opacity-0"
          )}
        />

        {/* Track */}
        <motion.span
          className={cn(
            "absolute inset-0 rounded-full border border-border-subtle transition-colors duration-300",
            "bg-surface/50 backdrop-blur-sm",
            checked && "bg-brand/20 border-brand/30"
          )}
          animate={{
            borderColor: checked
              ? "var(--primary-main)"
              : hover && !disabled
                ? "var(--primary-hover)"
                : "var(--border-strong)",
            backgroundColor: checked
              ? "color-mix(in srgb, var(--primary-main) 20%, transparent)"
              : hover && !disabled
                ? "var(--bg-surface-hover)"
                : "var(--bg-surface)",
          }}
          transition={{ duration: 0.2 }}
        />

        {/* Thumb */}
        <motion.span
          initial={{ x: checked ? 26 : 0, scaleX: 1, scaleY: 1 }}
          animate={controls}
          className={cn(
            "relative z-10 block h-[22px] w-[22px] rounded-full bg-white shadow-sm",
            "border border-white/20",
            "dark:bg-slate-200 dark:shadow-md",
            checked && "bg-white"
          )}
          style={{
            transformOrigin: (checked ? "left center" : "right center") as any,
          }}
        />

        <input
          type="checkbox"
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
