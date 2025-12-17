// Settings UI Components
// Extracted from Settings.tsx for better maintainability

import React, { useEffect, useMemo, type CSSProperties } from "react"
import ReactDOM from "react-dom"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/SmartImage"

// ============================================================================
// CONSTANTS
// ============================================================================

export const securityStatusChipClassName = cn(
  "font-semibold tracking-tight",
  "text-[color:color-mix(in_srgb,var(--page-text)_92%,rgba(15,79,170,0.16)_8%)]",
  "border border-[color:color-mix(in_srgb,var(--glass-border)_86%,transparent)]",
  "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(15,79,170,0.08)_4%)]",
  "shadow-[0_12px_28px_rgba(15,40,85,0.12)]",
  "dark:border-[rgba(148,163,184,0.35)]",
  "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_80%,rgba(2,6,23,0.9)_20%)]",
  "dark:shadow-[0_20px_50px_rgba(2,6,23,0.55)]"
)

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

export function fadeDelayStyle(value: string): CSSProperties {
  return { "--fade-delay": value } as CSSProperties
}

// ============================================================================
// SECTION COMPONENTS
// ============================================================================

export function SectionCard({
  children,
  className = "",
  component = "div",
  ...props
}: {
  children: React.ReactNode
  className?: string
  component?: React.ElementType
} & React.HTMLAttributes<HTMLElement>) {
  const Component = component
  return (
    <Component
      className={cn(
        "glass glass--panel relative overflow-hidden rounded-[24px] p-6",
        "border border-[color:var(--glass-border)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(255,255,255,0.92)_4%)]",
        "shadow-[0_34px_88px_rgba(15,40,85,0.18)]",
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:opacity-60 before:content-[''] before:bg-[radial-gradient(ellipse_at_0%_0%,rgba(15,79,170,0.12),transparent_60%)]",
        "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_92%,rgba(10,18,32,0.94)_8%)]",
        "dark:border-[rgba(148,163,184,0.24)] dark:shadow-[0_40px_96px_rgba(5,9,17,0.7)]",
        "dark:before:bg-[radial-gradient(ellipse_at_0%_0%,rgba(127,182,230,0.18),transparent_60%)]",
        className
      )}
      {...props}
    >
      {children}
    </Component>
  )
}

export function SectionTitle({
  children,
  className = "",
  component = "h2",
  variant = "subtitle1",
  ...props
}: {
  children: React.ReactNode
  className?: string
  component?: React.ElementType
  variant?: string
} & React.HTMLAttributes<HTMLElement>) {
  const Component = component
  return (
    <Component
      className={cn(
        "mb-2 text-[color:color-mix(in_srgb,var(--page-text)_92%,var(--nav-link)_8%)]",
        variant === "subtitle1"
          ? "text-[1.15rem] font-extrabold leading-tight tracking-tight"
          : variant === "h6"
            ? "text-[1.35rem] font-extrabold leading-tight tracking-tight"
            : "",
        className
      )}
      {...props}
    >
      {children}
    </Component>
  )
}

export function SectionSubtitle({
  children,
  className = "",
  variant = "body2",
  ...props
}: {
  children: React.ReactNode
  className?: string
  variant?: string
} & React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn(
        "text-[color:color-mix(in_srgb,var(--page-text)_74%,var(--secondary-text)_26%)]",
        variant === "body2"
          ? "text-sm leading-relaxed"
          : variant === "caption"
            ? "text-xs leading-snug"
            : "",
        className
      )}
      {...props}
    >
      {children}
    </p>
  )
}

export function SessionItem({
  children,
  className = "",
  ...props
}: {
  children: React.ReactNode
  className?: string
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[16px] p-4",
        "border border-[color:color-mix(in_srgb,var(--glass-border)_88%,transparent)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_95%,rgba(255,255,255,0.88)_5%)]",
        "shadow-[0_12px_28px_rgba(15,40,85,0.10)]",
        "transition-all duration-200",
        "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_90%,rgba(10,18,32,0.92)_10%)]",
        "dark:border-[rgba(148,163,184,0.22)] dark:shadow-[0_16px_36px_rgba(5,9,17,0.6)]",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

// ============================================================================
// DIALOG COMPONENTS
// ============================================================================

export function Dialog({
  open,
  onClose,
  maxWidth = "md",
  fullWidth = false,
  children,
}: {
  open: boolean
  onClose: () => void
  maxWidth?: string
  fullWidth?: boolean
  children: React.ReactNode
}) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => {
      document.body.style.overflow = ""
    }
  }, [open])

  if (!open) return null

  const maxWidthClasses =
    {
      xs: "max-w-xs",
      sm: "max-w-sm",
      md: "max-w-md",
      lg: "max-w-lg",
      xl: "max-w-xl",
    }[maxWidth] || "max-w-md"

  const dialogContent = (
    <div
      role="presentation"
      className="fixed inset-0 z-[var(--ue-z-index-overlay)] flex items-center justify-center bg-[color:rgba(12,21,34,0.38)]/90 backdrop-blur-[14px] p-4"
      style={{ position: "fixed" }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "glass glass--panel relative overflow-hidden rounded-[24px]",
          "border border-[color:var(--glass-border)]",
          "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(255,255,255,0.92)_4%)] text-[var(--page-text)]",
          "shadow-[0_34px_88px_rgba(15,40,85,0.18)]",
          "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_92%,rgba(10,18,32,0.94)_8%)] dark:border-[rgba(148,163,184,0.24)] dark:shadow-[0_40px_96px_rgba(5,9,17,0.7)]",
          fullWidth ? "w-full" : "",
          maxWidthClasses
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )

  if (typeof document !== "undefined") {
    return ReactDOM.createPortal(dialogContent, document.body)
  }

  return dialogContent
}

export function DialogTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="px-6 pt-6 pb-2 text-[1.35rem] font-extrabold leading-tight tracking-tight text-[color:color-mix(in_srgb,var(--page-text)_92%,var(--nav-link)_8%)]">
      {children}
    </h2>
  )
}

export function DialogContent({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-6 py-4 text-[color:color-mix(in_srgb,var(--page-text)_84%,var(--secondary-text)_16%)] leading-relaxed">
      {children}
    </div>
  )
}

export function DialogActions({ children }: { children: React.ReactNode }) {
  return <div className="flex justify-end gap-3 px-6 pb-6 pt-2">{children}</div>
}

// ============================================================================
// AVATAR COMPONENT
// ============================================================================

export function Avatar({
  src,
  alt,
  imgProps,
  className = "",
}: {
  src: string
  alt: string
  imgProps?: React.ImgHTMLAttributes<HTMLImageElement>
  className?: string
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-full p-[2px]",
        "bg-[conic-gradient(from_210deg_at_50%_50%,rgba(15,79,170,0.42),rgba(15,79,170,0.08),rgba(15,79,170,0.42))]",
        "shadow-[0_12px_28px_rgba(15,40,85,0.18)]",
        "dark:bg-[conic-gradient(from_210deg_at_50%_50%,rgba(127,182,230,0.36),rgba(39,53,72,0.2),rgba(127,182,230,0.36))]",
        className
      )}
    >
      <div className="relative h-full w-full overflow-hidden rounded-full bg-[color:color-mix(in_srgb,var(--card-bg)_94%,rgba(15,40,85,0.08)_6%)]">
        <SmartImage
          srcRaw={src}
          alt={alt}
          className="h-full w-full object-cover"
          responsiveWidths={[64, 96, 128, 196]}
          sizes="(max-width: 640px) 96px, 144px"
          {...imgProps}
        />
      </div>
    </div>
  )
}

// ============================================================================
// LOADING INDICATOR
// ============================================================================

export function CircularProgress({
  size = 24,
  color = "primary",
  className = "",
}: {
  size?: number
  color?: string
  className?: string
}) {
  return (
    <svg
      className={cn("animate-spin text-[color:var(--nav-link)]", className)}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={color ? { color } : undefined}
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )
}

// ============================================================================
// CHIP/BADGE
// ============================================================================

export function Chip({
  label,
  size = "medium",
  color = "default",
  variant = "filled",
  className = "",
}: {
  label: string
  size?: "small" | "medium"
  color?: "default" | "success" | "primary"
  variant?: "filled" | "outlined"
  className?: string
}) {
  const sizeClasses = size === "small" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm"
  const colorClasses = useMemo(() => {
    if (color === "success") {
      return variant === "filled"
        ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
        : "border-green-500 text-green-700 dark:border-green-600 dark:text-green-400"
    }
    if (color === "primary") {
      return variant === "filled"
        ? "bg-[color:color-mix(in_srgb,var(--nav-link)_18%,white_82%)] text-[color:var(--nav-link)]"
        : "border-[color:var(--nav-link)] text-[color:var(--nav-link)]"
    }
    return variant === "filled"
      ? "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
      : "border-gray-400 text-gray-600 dark:border-gray-600 dark:text-gray-400"
  }, [color, variant])

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-medium",
        sizeClasses,
        colorClasses,
        variant === "outlined" ? "border bg-transparent" : "",
        className
      )}
    >
      {label}
    </span>
  )
}

// ============================================================================
// DIVIDER
// ============================================================================

export function Divider({
  className = "",
  flexItem,
  component,
}: {
  className?: string
  flexItem?: boolean
  component?: React.ElementType
}) {
  const Component = component || "hr"
  return (
    <Component
      className={cn(
        "border-0 border-t border-[color:color-mix(in_srgb,var(--glass-border)_75%,transparent)]",
        flexItem ? "self-stretch" : "w-full",
        className
      )}
    />
  )
}
