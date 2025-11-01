import { forwardRef, useMemo, type ButtonHTMLAttributes } from "react"
import { cn } from "@/utils/cn"

type IconButtonVariant = "solid" | "soft" | "ghost"
type IconButtonSize = "sm" | "md" | "lg"

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: IconButtonVariant
  size?: IconButtonSize
  loading?: boolean
}

const sizeStyles: Record<IconButtonSize, string> = {
  sm: "h-9 w-9 text-base",
  md: "h-10 w-10 text-lg",
  lg: "h-12 w-12 text-xl",
}

const variantStyles: Record<IconButtonVariant, string> = {
  solid: cn(
    "bg-btn-gradient text-white",
    "hover:bg-btn-gradient-hover",
    "active:translate-y-[1px]",
    "disabled:opacity-60"
  ),
  soft: cn(
    "border border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/95 text-[color:var(--nav-link)]",
    "hover:bg-[color:var(--menu-hover-bg)] hover:text-[color:var(--menu-hover-text)]",
    "disabled:opacity-60"
  ),
  ghost: cn(
    "bg-transparent text-[color:var(--nav-link)]",
    "hover:bg-[color:var(--menu-hover-bg)]/60",
    "disabled:opacity-60"
  ),
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    { variant = "soft", size = "md", className, children, loading = false, disabled, ...rest },
    ref
  ) => {
    const isDisabled = disabled || loading
    const spinnerClass = useMemo(
      () =>
        cn(
          "absolute inset-0 flex items-center justify-center",
          size === "sm" && "text-xs",
          size === "md" && "text-sm",
          size === "lg" && "text-base"
        ),
      [size]
    )

    return (
      <button
        ref={ref}
        type="button"
        className={cn(
          "group relative inline-flex items-center justify-center rounded-full transition-all duration-200",
          "focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]",
          "motion-reduce:transition-none",
          sizeStyles[size],
          variantStyles[variant],
          isDisabled && "pointer-events-none",
          className
        )}
        aria-disabled={isDisabled ? "true" : undefined}
        disabled={isDisabled}
        {...rest}
      >
        <span
          className={cn("transition-opacity duration-150", loading && "opacity-0")}
          style={loading ? { visibility: "hidden" } : undefined}
          aria-hidden={loading ? "true" : undefined}
        >
          {children}
        </span>
        {loading ? (
          <span className={spinnerClass} aria-hidden>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-[color:rgba(148,163,184,0.35)] border-t-[color:var(--nav-link)]" />
          </span>
        ) : null}
      </button>
    )
  }
)

IconButton.displayName = "IconButton"
