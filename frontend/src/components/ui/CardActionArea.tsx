import { forwardRef, type ElementType, type ComponentPropsWithoutRef, type ReactNode } from "react"
import { m, type HTMLMotionProps } from "framer-motion"
import { cn } from "@/utils/cn"
import { EASING } from "@/utils/motion"
import { motion as motionTokens } from "@/theme/tokens"

export type CardActionAreaProps<T extends ElementType = "button"> = {
  as?: T
  children: ReactNode
  className?: string
  disabled?: boolean
} & ComponentPropsWithoutRef<T> &
  HTMLMotionProps<"button">

export const CardActionArea = forwardRef<HTMLButtonElement, CardActionAreaProps>(
  ({ as: Component = "button", className, children, disabled, ...props }, ref) => {
    // If it's a button, we ensure type="button" to prevent form submission
    const typeProps = Component === "button" ? { type: "button" as const } : {}

    return (
      <m.button
        ref={ref}
        {...typeProps}
        className={cn(
          "group w-full outline-none text-left p-0 border-0 bg-transparent block relative",
          "focus-visible:ring-2 focus-visible:ring-brand focus-visible:rounded-fluid-lg",
          disabled && "pointer-events-none opacity-60",
          className
        )}
        whileHover={{
          y: -4,
          transition: { duration: motionTokens.durationFast, ease: EASING.premium },
        }}
        whileTap={{ scale: 0.98 }}
        disabled={disabled}
        {...props}
      >
        {children}
      </m.button>
    )
  }
)

CardActionArea.displayName = "CardActionArea"
