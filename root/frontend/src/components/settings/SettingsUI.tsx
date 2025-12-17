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

// ============================================================================
// BUTTON COMPONENT
// ============================================================================

export function Button({
  children,
  variant = "contained",
  color = "primary",
  size = "medium",
  disabled = false,
  startIcon,
  onClick,
  type = "button",
  className = "",
  ...props
}: {
  children: React.ReactNode
  variant?: "contained" | "outlined" | "text"
  color?: "primary" | "error" | "inherit" | "success"
  size?: "small" | "medium"
  disabled?: boolean
  startIcon?: React.ReactNode
  onClick?: () => void
  type?: "button" | "submit"
  className?: string
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const baseClasses = cn(
    "relative inline-flex items-center justify-center gap-2 font-semibold tracking-tight",
    "rounded-xl transition-all duration-200",
    "focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-[var(--shadow-focus)]",
    "disabled:pointer-events-none disabled:opacity-55",
    "active:translate-y-[1px]"
  )
  const sizeClasses =
    size === "small"
      ? "px-3.5 py-2 text-sm"
      : "px-4.5 py-2.5 text-[calc(theme(fontSize.base)*0.98)] sm:text-base"

  let variantClasses = ""
  if (variant === "contained") {
    if (color === "primary") {
      variantClasses = cn(
        "bg-[color:var(--nav-link)] text-white shadow-[0_14px_34px_rgba(15,79,170,0.26)]",
        "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_94%,white_6%)] hover:shadow-[0_18px_44px_rgba(15,79,170,0.32)]",
        "dark:bg-[color:color-mix(in_srgb,var(--nav-link)_88%,rgba(10,18,32,0.9)_12%)]",
        "dark:hover:bg-[color:color-mix(in_srgb,var(--nav-link)_92%,rgba(10,18,32,0.9)_8%)]",
        "dark:hover:shadow-[0_20px_48px_rgba(8,12,20,0.62)]"
      )
    } else if (color === "error") {
      variantClasses = cn(
        "bg-[#D14343] text-white shadow-[0_14px_32px_rgba(209,67,67,0.24)]",
        "hover:bg-[#c03838] hover:shadow-[0_18px_40px_rgba(192,56,56,0.28)]"
      )
    } else if (color === "success") {
      variantClasses = cn(
        "bg-[#2E7D32] text-white shadow-[0_14px_32px_rgba(46,125,50,0.24)]",
        "hover:bg-[#276b2b] hover:shadow-[0_18px_40px_rgba(39,107,43,0.28)]"
      )
    } else {
      variantClasses = cn(
        "bg-[color:color-mix(in_srgb,var(--card-bg)_94%,rgba(15,79,170,0.18)_6%)]",
        "text-[var(--page-text)] shadow-[0_12px_28px_rgba(15,40,85,0.12)]",
        "hover:shadow-[0_16px_38px_rgba(15,40,85,0.18)]"
      )
    }
  } else if (variant === "outlined") {
    if (color === "primary") {
      variantClasses = cn(
        "border border-[color:color-mix(in_srgb,var(--nav-link)_30%,transparent)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_97%,rgba(15,79,170,0.08)_3%)] text-[color:var(--nav-link)]",
        "shadow-[0_8px_24px_rgba(15,40,85,0.08)]",
        "hover:border-[color:color-mix(in_srgb,var(--nav-link)_45%,transparent)]",
        "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,white_88%)]",
        "hover:text-[color:color-mix(in_srgb,var(--nav-link)_88%,rgba(15,40,85,0.25)_12%)]"
      )
    } else if (color === "error") {
      variantClasses = cn(
        "border border-[#D14343] text-[#D14343]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(209,67,67,0.08)_4%)]",
        "hover:bg-[color:color-mix(in_srgb,rgba(209,67,67,0.12)_16%,white_84%)]"
      )
    } else if (color === "success") {
      variantClasses = cn(
        "border border-[#358E39] text-[#276b2b]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_97%,rgba(46,125,50,0.08)_3%)]",
        "hover:bg-[color:color-mix(in_srgb,rgba(46,125,50,0.12)_16%,white_84%)]"
      )
    } else {
      variantClasses = cn(
        "border border-[color:color-mix(in_srgb,var(--glass-border)_82%,transparent)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_97%,rgba(15,40,85,0.04)_3%)]",
        "hover:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,rgba(15,40,85,0.08)_6%)]"
      )
    }
  } else if (variant === "text") {
    if (color === "error") {
      variantClasses = cn(
        "text-[#C13B3B]",
        "hover:bg-[color:color-mix(in_srgb,rgba(209,67,67,0.12)_32%,white_68%)]"
      )
    } else if (color === "inherit") {
      variantClasses = cn(
        "text-[var(--page-text)]",
        "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_8%,transparent)]"
      )
    } else if (color === "primary") {
      variantClasses = cn(
        "text-[color:var(--nav-link)]",
        "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_10%,transparent)]"
      )
    } else {
      variantClasses = cn(
        "text-[color:color-mix(in_srgb,var(--page-text)_88%,var(--secondary-text)_12%)]",
        "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_8%,transparent)]"
      )
    }
  }

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={cn(baseClasses, sizeClasses, variantClasses, className)}
      {...props}
    >
      {startIcon && <span className="flex items-center text-inherit">{startIcon}</span>}
      {children}
    </button>
  )
}

// ============================================================================
// TEXT FIELD COMPONENT
// ============================================================================

export function TextField({
  label,
  value,
  onChange,
  onBlur,
  type = "text",
  disabled = false,
  error = false,
  helperText,
  placeholder,
  size = "medium",
  fullWidth = false,
  autoComplete,
  className = "",
  ...props
}: {
  label?: string
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  onBlur?: (e: React.FocusEvent<HTMLInputElement>) => void
  type?: string
  disabled?: boolean
  error?: boolean
  helperText?: string
  placeholder?: string
  size?: "small" | "medium"
  fullWidth?: boolean
  autoComplete?: string
  className?: string
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "size" | "onChange" | "onBlur" | "value">) {
  const inputClasses = cn(
    "peer w-full rounded-xl border bg-transparent px-4 py-3 text-[var(--page-text)] transition-all duration-200",
    "placeholder:text-[color:color-mix(in_srgb,var(--page-text)_50%,transparent)]",
    "focus:outline-none focus:ring-0",
    error
      ? "border-[#D14343] focus:border-[#D14343]"
      : cn(
          "border-[color:color-mix(in_srgb,var(--glass-border)_75%,transparent)]",
          "focus:border-[color:var(--nav-link)]"
        ),
    disabled ? "cursor-not-allowed opacity-60" : "",
    size === "small" ? "py-2 text-sm" : ""
  )

  return (
    <div className={cn(fullWidth ? "w-full" : "", className)}>
      {label && (
        <label className="mb-1.5 block text-sm font-medium text-[color:color-mix(in_srgb,var(--page-text)_80%,var(--secondary-text)_20%)]">
          {label}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={onChange}
        onBlur={onBlur}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className={inputClasses}
        {...props}
      />
      {helperText && (
        <p
          className={cn(
            "mt-1.5 text-xs",
            error
              ? "text-[#D14343]"
              : "text-[color:color-mix(in_srgb,var(--page-text)_60%,var(--secondary-text)_40%)]"
          )}
        >
          {helperText}
        </p>
      )}
    </div>
  )
}

// ============================================================================
// SWITCH / TOGGLE COMPONENT
// ============================================================================

export function Switch({
  checked,
  onChange,
  disabled = false,
  size = "medium",
  className = "",
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  size?: "small" | "medium"
  className?: string
}) {
  const sizeClasses = size === "small" ? "h-5 w-9" : "h-6 w-11"
  const thumbSizeClasses = size === "small" ? "h-3.5 w-3.5" : "h-4 w-4"
  const translateClasses = size === "small" ? "translate-x-4" : "translate-x-5"

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200",
        sizeClasses,
        checked
          ? "bg-[color:var(--nav-link)]"
          : "bg-[color:color-mix(in_srgb,var(--glass-border)_60%,transparent)]",
        disabled ? "cursor-not-allowed opacity-50" : "",
        className
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block transform rounded-full bg-white shadow-md transition-transform duration-200",
          thumbSizeClasses,
          checked ? translateClasses : "translate-x-1"
        )}
      />
    </button>
  )
}

// ============================================================================
// ACCORDION / COLLAPSIBLE COMPONENT
// ============================================================================

export function Accordion({
  expanded,
  onChange,
  title,
  children,
  className = "",
}: {
  expanded: boolean
  onChange: () => void
  title: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-[color:var(--glass-border)]",
        className
      )}
    >
      <button
        type="button"
        onClick={onChange}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-[color:color-mix(in_srgb,var(--card-bg)_95%,rgba(15,79,170,0.08)_5%)]"
        aria-expanded={expanded}
      >
        <span className="font-medium text-[var(--page-text)]">{title}</span>
        <svg
          className={cn(
            "h-5 w-5 text-[color:color-mix(in_srgb,var(--page-text)_60%,transparent)] transition-transform duration-200",
            expanded ? "rotate-180" : ""
          )}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div
        className={cn(
          "overflow-hidden transition-all duration-200",
          expanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="px-4 pb-4 pt-2">{children}</div>
      </div>
    </div>
  )
}
