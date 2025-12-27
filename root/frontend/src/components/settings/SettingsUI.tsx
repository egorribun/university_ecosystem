/**
 * Settings UI Components
 *
 * Reusable UI primitives extracted from Settings.tsx for use across the settings page sections.
 * These components follow the glassmorphism design language of the application.
 */
import React, {
  useState,
  useEffect,
  useMemo,
  ChangeEvent,
  FocusEvent,
  type CSSProperties,
} from "react"
import ReactDOM from "react-dom"
import { motion, useAnimation } from "framer-motion"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/SmartImage"
import type { AlertProps } from "@mui/material/Alert"

// Types
export type ThemeMode = "system" | "light" | "dark"

// Helper functions
export const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

export const securityStatusChipClassName = cn(
  "font-semibold tracking-tight",
  "text-[color:color-mix(in_srgb,var(--page-text)_92%,rgba(15,79,170,0.16)_8%)]",
  "border border-[color:color-mix(in_srgb,var(--glass-border)_86%,transparent)]",
  "bg-[color:color-mix(in_srgb,var(--card-bg)_94%,rgba(255,255,255,0.1)_6%)]",
  "shadow-[0_16px_40px_rgba(15,40,85,0.12)] backdrop-blur",
  "dark:text-[color:color-mix(in_srgb,var(--page-text)_96%,rgba(148,163,184,0.45)_4%)]",
  "dark:border-[rgba(148,163,184,0.35)]",
  "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_80%,rgba(2,6,23,0.9)_20%)]",
  "dark:shadow-[0_20px_50px_rgba(2,6,23,0.55)]"
)

// Section Components
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
        "relative flex flex-col gap-3 overflow-hidden rounded-[24px] px-6 py-6",
        "border border-[color:var(--glass-border)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(255,255,255,0.94)_4%)] text-[var(--page-text)]",
        "shadow-[0_28px_64px_rgba(15,40,85,0.08)] transition-colors duration-300",
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:opacity-70 before:mix-blend-screen",
        'before:content-[""] before:bg-[radial-gradient(circle_at_0%_0%,rgba(15,79,170,0.12),transparent_60%)]',
        "after:pointer-events-none after:absolute after:-top-16 after:-left-16 after:h-40 after:w-40 after:rounded-full after:opacity-70 after:blur-[2px]",
        'after:content-[""] after:bg-[radial-gradient(circle,rgba(255,255,255,0.42),transparent_62%)]',
        "dark:border-[rgba(148,163,184,0.22)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_92%,rgba(10,18,32,0.94)_8%)] dark:text-[var(--page-text)]",
        "dark:shadow-[0_28px_80px_rgba(5,9,17,0.62)]",
        "dark:before:bg-[radial-gradient(circle_at_0%_0%,rgba(127,182,230,0.2),transparent_60%)]",
        "dark:after:bg-[radial-gradient(circle,rgba(127,182,230,0.28),transparent_60%)]",
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
  const sizeClasses =
    variant === "subtitle1"
      ? "text-base"
      : variant === "subtitle2"
        ? "text-sm"
        : variant === "h6"
          ? "text-lg"
          : "text-base"
  return (
    <Component
      className={cn(
        "font-semibold tracking-tight text-[color:color-mix(in_srgb,var(--page-text)_92%,rgba(15,79,170,0.08)_8%)]",
        "dark:text-[color:color-mix(in_srgb,var(--page-text)_96%,rgba(127,182,230,0.16)_4%)]",
        sizeClasses,
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
  const sizeClasses =
    variant === "body2" ? "text-sm" : variant === "caption" ? "text-xs" : "text-sm"
  return (
    <p
      className={cn(
        "text-[color:color-mix(in_srgb,var(--secondary-text)_82%,white_18%)]",
        "dark:text-[color:color-mix(in_srgb,var(--page-text)_82%,rgba(148,163,184,0.55)_18%)]",
        "leading-relaxed",
        sizeClasses,
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
        "group relative flex items-stretch justify-between gap-4 rounded-[20px] px-4 py-3",
        "border border-[color:color-mix(in_srgb,var(--glass-border)_90%,transparent)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_94%,rgba(15,79,170,0.08)_6%)] text-[var(--page-text)]",
        "transition-all duration-300 ease-out",
        "hover:-translate-y-[1px] hover:border-[color:color-mix(in_srgb,var(--nav-link)_34%,transparent)] hover:shadow-[0_20px_48px_rgba(15,40,85,0.12)]",
        "max-sm:flex-col max-sm:items-start",
        "dark:border-[rgba(148,163,184,0.26)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_88%,rgba(10,18,32,0.94)_12%)]",
        "dark:hover:border-[color:rgba(127,182,230,0.5)] dark:hover:shadow-[0_24px_60px_rgba(5,9,17,0.65)]",
        "data-[revoked=true]:border-dashed data-[revoked=true]:border-[color:color-mix(in_srgb,var(--secondary-text)_38%,transparent)]",
        "data-[revoked=true]:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,rgba(59,73,92,0.15)_6%)] data-[revoked=true]:shadow-none",
        "dark:data-[revoked=true]:border-[rgba(148,163,184,0.24)] dark:data-[revoked=true]:bg-[color:color-mix(in_srgb,var(--card-bg)_88%,rgba(59,73,92,0.32)_12%)]",
        "data-[revoked=true]:hover:translate-y-0 data-[revoked=true]:hover:shadow-none data-[revoked=true]:hover:border-[color:color-mix(in_srgb,var(--secondary-text)_45%,transparent)]",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function AccordionSection({
  title,
  subtitle,
  children,
  defaultExpanded = false,
  className = "",
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
  defaultExpanded?: boolean
  className?: string
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border transition-all duration-200",
        "border-[color:color-mix(in_srgb,var(--glass-border)_88%,transparent)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(15,79,170,0.04)_4%)]",
        "dark:border-[rgba(148,163,184,0.24)]",
        "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_90%,rgba(10,18,32,0.92)_10%)]",
        expanded
          ? "shadow-[0_8px_24px_rgba(15,40,85,0.12)] dark:shadow-[0_12px_32px_rgba(5,9,17,0.32)]"
          : "shadow-[0_4px_12px_rgba(15,40,85,0.08)] dark:shadow-[0_6px_16px_rgba(5,9,17,0.24)]",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 text-left transition-colors hover:bg-[color:color-mix(in_srgb,var(--nav-link)_4%,transparent)] dark:hover:bg-[color:color-mix(in_srgb,var(--nav-link)_6%,transparent)]"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-col gap-1 min-w-0">
            <h3 className="text-sm font-semibold text-[color:color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)]">
              {title}
            </h3>
            {subtitle && (
              <p className="text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_70%,transparent)]">
                {subtitle}
              </p>
            )}
          </div>
          <svg
            className={cn(
              "h-5 w-5 flex-shrink-0 text-[color:var(--nav-link)] transition-transform duration-200",
              expanded && "rotate-180"
            )}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
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

// Form Components
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
  onChange: (e: ChangeEvent<HTMLInputElement>) => void
  onBlur?: (e: FocusEvent<HTMLInputElement>) => void
  type?: string
  disabled?: boolean
  error?: boolean
  helperText?: string
  placeholder?: string
  size?: "small" | "medium"
  fullWidth?: boolean
  autoComplete?: string
  className?: string
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "size" | "onChange" | "onBlur">) {
  const sizeClasses = size === "small" ? "px-3 py-1.5 text-sm" : "px-4 py-2"
  const widthClass = fullWidth ? "w-full" : ""
  const timeInputClasses =
    type === "time" ? "max-w-full sm:max-w-[200px] text-center tabular-nums" : ""

  return (
    <div className={cn("flex flex-col gap-1", widthClass, className)}>
      {label && (
        <label
          className={cn(
            "mb-1 block px-1 text-xs font-semibold uppercase tracking-[0.2em]",
            "text-[color:color-mix(in_srgb,var(--secondary-text)_78%,var(--nav-link)_22%)]",
            "dark:text-[color:color-mix(in_srgb,var(--page-text)_82%,rgba(127,182,230,0.55)_18%)]"
          )}
        >
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
        className={cn(
          widthClass,
          sizeClasses,
          timeInputClasses,
          "rounded-xl border text-[var(--page-text)] transition-all duration-200",
          "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(255,255,255,0.88)_4%)]",
          "border-[color:color-mix(in_srgb,var(--glass-border)_90%,transparent)]",
          "shadow-[0_10px_26px_rgba(15,40,85,0.08)]",
          "placeholder:text-[color:var(--placeholder-fg)]",
          "hover:border-[color:color-mix(in_srgb,var(--nav-link)_32%,transparent)]",
          "focus:outline-none focus:border-[color:var(--nav-link)] focus:shadow-[0_0_0_4px_rgba(15,79,170,0.14)]",
          "disabled:cursor-not-allowed disabled:bg-[color:color-mix(in_srgb,var(--card-bg)_92%,rgba(148,163,184,0.28)_8%)]",
          "disabled:border-[color:color-mix(in_srgb,var(--glass-border)_68%,transparent)] disabled:text-[color:rgba(59,73,92,0.58)] disabled:shadow-none",
          error
            ? [
                "border-[#D14343] hover:border-[#C13B3B]",
                "focus:border-[#D14343] focus:shadow-[0_0_0_4px_rgba(209,67,67,0.18)]",
                "shadow-[0_0_0_1px_rgba(209,67,67,0.4)]",
              ]
            : null
        )}
        {...props}
      />
      {helperText && (
        <p
          className={cn(
            "mt-1 text-xs",
            error
              ? "text-[#D14343]"
              : "text-[color:color-mix(in_srgb,var(--secondary-text)_74%,white_26%)]"
          )}
        >
          {helperText}
        </p>
      )}
    </div>
  )
}

export function RadioGroup({
  children,
  value,
  onChange,
  row = false,
  "aria-label": ariaLabel,
}: {
  children: React.ReactNode
  value: string
  onChange: (e: ChangeEvent<HTMLInputElement>, value: string) => void
  row?: boolean
  "aria-label"?: string
}) {
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    onChange(e, e.target.value)
  }

  return (
    <div
      className={`${row ? "flex flex-wrap gap-4" : "flex flex-col gap-2"}`}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {React.Children.map(children, (child) => {
        if (React.isValidElement(child)) {
          return React.cloneElement(
            child as React.ReactElement<{
              groupValue?: string
              groupOnChange?: (e: ChangeEvent<HTMLInputElement>) => void
            }>,
            {
              groupValue: value,
              groupOnChange: handleChange,
            }
          )
        }
        return child
      })}
    </div>
  )
}

export function FormControlLabel({
  value,
  control,
  label,
  className = "",
  groupValue,
  groupOnChange,
}: {
  value: string
  control: React.ReactNode
  label: React.ReactNode
  className?: string
  groupValue?: string
  groupOnChange?: (e: ChangeEvent<HTMLInputElement>) => void
}) {
  const inputId = useMemo(
    () => `radio-${value}-${Math.random().toString(36).substr(2, 9)}`,
    [value]
  )
  const selected = groupValue === value

  return (
    <label
      htmlFor={inputId}
      className={cn(
        "group inline-flex items-center gap-2.5 rounded-full px-2.5 py-1.5",
        "cursor-pointer transition-all duration-200",
        "border-2",
        "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_8%,transparent)]",
        "dark:hover:bg-[rgba(255,255,255,0.06)]",
        selected
          ? "bg-[color:color-mix(in_srgb,var(--nav-link)_10%,transparent)] border-[color:color-mix(in_srgb,var(--nav-link)_40%,transparent)]"
          : "border-transparent hover:border-[color:color-mix(in_srgb,var(--nav-link)_25%,transparent)] dark:hover:border-[rgba(255,255,255,0.15)]",
        className
      )}
    >
      {React.isValidElement(control)
        ? React.cloneElement(
            control as React.ReactElement<{
              checked?: boolean
              value?: string
              name?: string
              id?: string
              onChange?: (e: ChangeEvent<HTMLInputElement>) => void
            }>,
            {
              checked: groupValue === value,
              value: value,
              name: "radio-group",
              id: inputId,
              onChange: groupOnChange,
            }
          )
        : control}
      <span
        className={cn(
          "text-sm font-semibold tracking-tight transition-colors duration-200",
          selected
            ? "text-[color:var(--nav-link)]"
            : "text-[color:color-mix(in_srgb,var(--page-text)_82%,var(--secondary-text)_18%)]"
        )}
      >
        {label}
      </span>
    </label>
  )
}

export function Radio({
  checked,
  onChange,
  value,
  name,
  id,
}: {
  checked?: boolean
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void
  value?: string
  name?: string
  id?: string
}) {
  return (
    <div className="relative inline-flex items-center justify-center">
      <input
        type="radio"
        checked={checked}
        onChange={onChange}
        value={value}
        name={name}
        id={id}
        className="peer sr-only"
      />
      <div
        className={cn(
          "h-4 w-4 cursor-pointer rounded-full border-2 transition-all duration-200",
          "flex items-center justify-center",
          "border-[color:var(--nav-link)]",
          "peer-focus-visible:outline-none peer-focus-visible:shadow-[var(--shadow-focus)]",
          "peer-checked:border-[color:var(--nav-link)] peer-checked:bg-[color:color-mix(in_srgb,var(--nav-link)_10%,transparent)]",
          "dark:border-[color:var(--nav-link)]",
          "dark:peer-checked:border-[color:var(--nav-link)] dark:peer-checked:bg-[color:color-mix(in_srgb,var(--nav-link)_20%,transparent)]"
        )}
      >
        <div
          className={cn(
            "h-2 w-2 rounded-full transition-all duration-200",
            "bg-[color:var(--nav-link)]",
            checked ? "scale-100 opacity-100" : "scale-0 opacity-0"
          )}
        />
      </div>
    </div>
  )
}

// Feedback Components
export function Alert({
  severity = "info",
  variant = "filled",
  children,
  onClose,
  className = "",
}: {
  severity?: "info" | "error" | "warning" | "success"
  variant?: "filled" | "outlined"
  children: React.ReactNode
  onClose?: () => void
  className?: string
}) {
  const palette = {
    info: {
      filled:
        "bg-[linear-gradient(132deg,#0F4FAA,#123F84)] text-white shadow-[0_18px_40px_rgba(15,79,170,0.22)]",
      outlined:
        "border-[color:color-mix(in_srgb,var(--nav-link)_36%,transparent)] text-[color:var(--nav-link)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(15,79,170,0.08)_4%)]",
    },
    error: {
      filled:
        "bg-[linear-gradient(132deg,#D14343,#B23131)] text-white shadow-[0_18px_40px_rgba(209,67,67,0.22)]",
      outlined:
        "border-[#D14343] text-[#C13B3B] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(209,67,67,0.08)_4%)]",
    },
    warning: {
      filled:
        "bg-[linear-gradient(132deg,#F59E0B,#B7791F)] text-[color:color-mix(in_srgb,#102033_82%,white_18%)] shadow-[0_18px_40px_rgba(183,121,31,0.22)]",
      outlined:
        "border-[color:color-mix(in_srgb,#B7791F_40%,transparent)] text-[#8A5F16] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(183,121,31,0.08)_4%)]",
    },
    success: {
      filled:
        "bg-[linear-gradient(132deg,#2E7D32,#1B5E20)] text-white shadow-[0_18px_40px_rgba(46,125,50,0.22)]",
      outlined:
        "border-[color:color-mix(in_srgb,#2E7D32_36%,transparent)] text-[#276b2b] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(46,125,50,0.08)_4%)]",
    },
  } satisfies Record<NonNullable<AlertProps["severity"]>, { filled: string; outlined: string }>

  const styleSet = palette[severity][variant === "outlined" ? "outlined" : "filled"]

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-[16px] px-4 py-2.5 transition-colors duration-300",
        variant === "outlined"
          ? "border bg-[color:color-mix(in_srgb,var(--card-bg)_97%,white_3%)]"
          : "",
        styleSet,
        className
      )}
    >
      <span className="flex-1">{children}</span>
      {onClose && (
        <button
          onClick={onClose}
          className="ml-2 rounded-full p-1 text-current/80 transition hover:text-current/95 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
        >
          ×
        </button>
      )}
    </div>
  )
}

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
  const baseClasses = cn(
    "inline-flex items-center rounded-full font-semibold tracking-tight",
    "transition-colors duration-200"
  )
  const sizeClasses = size === "small" ? "px-3 py-1 text-xs" : "px-3.5 py-1.5 text-sm"
  let toneClasses = ""

  if (color === "success") {
    toneClasses =
      variant === "outlined"
        ? "border-[color:color-mix(in_srgb,#2E7D32_45%,transparent)] text-[#276b2b] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(46,125,50,0.08)_4%)]"
        : "border border-transparent text-[#1f5423] bg-[color:color-mix(in_srgb,#9FDEB0_32%,white_68%)] shadow-[0_8px_20px_rgba(46,125,50,0.18)]"
  } else if (color === "primary") {
    toneClasses =
      variant === "outlined"
        ? "border-[color:color-mix(in_srgb,var(--nav-link)_34%,transparent)] text-[color:var(--nav-link)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(15,79,170,0.08)_4%)]"
        : "border border-transparent text-[color:color-mix(in_srgb,var(--nav-link)_85%,var(--nav-text)_15%)] bg-[color:color-mix(in_srgb,var(--nav-link)_14%,white_86%)] shadow-[0_10px_22px_rgba(15,79,170,0.18)]"
  } else {
    toneClasses =
      variant === "outlined"
        ? "border-[color:color-mix(in_srgb,var(--glass-border)_80%,transparent)] text-[color:color-mix(in_srgb,var(--page-text)_78%,var(--secondary-text)_22%)] bg-[color:color-mix(in_srgb,var(--card-bg)_97%,rgba(15,40,85,0.05)_3%)]"
        : "border border-transparent text-[color:color-mix(in_srgb,var(--page-text)_85%,var(--secondary-text)_15%)] bg-[color:color-mix(in_srgb,var(--nav-link)_8%,white_92%)] shadow-[0_8px_20px_rgba(15,40,85,0.12)]"
  }

  return <span className={cn(baseClasses, sizeClasses, toneClasses, className)}>{label}</span>
}

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
        "h-px w-full border-0",
        "bg-[linear-gradient(90deg,rgba(15,79,170,0.22)_0%,rgba(15,79,170,0.06)_50%,rgba(15,79,170,0.22)_100%)]",
        "dark:bg-[linear-gradient(90deg,rgba(127,182,230,0.24)_0%,rgba(127,182,230,0.08)_50%,rgba(127,182,230,0.24)_100%)]",
        flexItem ? "self-stretch" : "",
        className
      )}
    />
  )
}

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

// Modal Components
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

export function Snackbar({
  open,
  onClose,
  autoHideDuration,
  anchorOrigin,
  children,
}: {
  open: boolean
  onClose: () => void
  autoHideDuration?: number
  anchorOrigin?: { vertical: string; horizontal: string }
  children: React.ReactNode
}) {
  useEffect(() => {
    if (open && autoHideDuration) {
      const timer = setTimeout(onClose, autoHideDuration)
      return () => clearTimeout(timer)
    }
  }, [open, autoHideDuration, onClose])

  if (!open) return null

  const positionClasses =
    anchorOrigin?.vertical === "bottom"
      ? "bottom-4"
      : anchorOrigin?.vertical === "top"
        ? "top-4"
        : "top-1/2 -translate-y-1/2"
  const horizontalClasses =
    anchorOrigin?.horizontal === "center"
      ? "left-1/2 -translate-x-1/2"
      : anchorOrigin?.horizontal === "right"
        ? "right-4"
        : "left-4"

  return (
    <div
      className={cn(
        "fixed z-[calc(var(--ue-z-index-toast))] pointer-events-none",
        positionClasses,
        horizontalClasses
      )}
    >
      <div className="pointer-events-auto">{children}</div>
    </div>
  )
}

// Navigation Components
export function Tabs({
  value,
  onChange,
  variant,
  scrollButtons,
  children,
  className = "",
}: {
  value: number
  onChange: (e: unknown, value: number) => void
  variant?: string
  scrollButtons?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      role="tablist"
      className={cn(
        "relative flex flex-wrap items-center gap-1.5 overflow-x-auto rounded-[16px] px-1.5 py-1.5",
        "border border-[color:color-mix(in_srgb,var(--glass-border)_92%,transparent)]",
        "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(255,255,255,0.9)_4%)]",
        "shadow-[0_20px_48px_rgba(15,40,85,0.12)]",
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:opacity-60",
        'before:content-[""] before:bg-[radial-gradient(circle_at_0%_0%,rgba(15,79,170,0.12),transparent_60%)]',
        "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_90%,rgba(10,18,32,0.94)_10%)]",
        "dark:border-[rgba(148,163,184,0.24)] dark:shadow-[0_24px_56px_rgba(5,9,17,0.68)]",
        "dark:before:bg-[radial-gradient(circle_at_0%_0%,rgba(127,182,230,0.18),transparent_60%)]",
        className
      )}
    >
      {React.Children.map(children, (child, index) => {
        if (React.isValidElement(child)) {
          return React.cloneElement(
            child as React.ReactElement<{ selected?: boolean; onClick?: () => void }>,
            {
              selected: value === index,
              onClick: () => onChange(null, index),
            }
          )
        }
        return child
      })}
    </div>
  )
}

export function Tab({
  label,
  selected,
  onClick,
  layoutId = "settings-tab-indicator",
}: {
  label: string
  selected?: boolean
  onClick?: () => void
  layoutId?: string
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className={cn(
        "relative min-h-[44px] whitespace-nowrap rounded-[14px] px-4 py-2 text-sm font-semibold tracking-tight",
        "transition-colors duration-200 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]",
        selected
          ? "text-[color:color-mix(in_srgb,var(--nav-link)_90%,var(--nav-text)_10%)]"
          : "text-[color:color-mix(in_srgb,var(--page-text)_82%,var(--secondary-text)_18%)] hover:bg-[color:color-mix(in_srgb,var(--nav-link)_10%,white_90%)] hover:text-[color:var(--nav-link)]"
      )}
    >
      {selected && (
        <motion.span
          layoutId={layoutId}
          className="absolute inset-0 rounded-[14px] bg-[color:color-mix(in_srgb,var(--nav-link)_18%,white_82%)] shadow-[0_12px_28px_rgba(15,79,170,0.22)] dark:bg-[color:color-mix(in_srgb,var(--nav-link)_24%,rgba(10,18,32,0.76))] dark:shadow-[0_8px_24px_rgba(5,9,17,0.45)]"
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        />
      )}
      <span className="relative z-10 flex items-center gap-1.5">
        {selected && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="h-2 w-2 rounded-full bg-[color:var(--nav-link)] shadow-[0_0_0_3px_rgba(15,79,170,0.2)]"
          />
        )}
        {label}
      </span>
    </button>
  )
}

export function SwitchControl({
  checked,
  disabled,
  onChange,
  inputId,
  "aria-label": ariaLabel,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (e: ChangeEvent<HTMLInputElement>, checked: boolean) => void
  inputId?: string
  "aria-label"?: string
}) {
  const [hover, setHover] = useState(false)
  const [focus, setFocus] = useState(false)

  const controls = useAnimation()
  const isFirstRender = React.useRef(true)

  useEffect(() => {
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
      }
    })
  }, [checked, controls])

  return (
    <span
      className={cn(
        "relative inline-flex h-[28px] w-[56px] cursor-pointer items-center rounded-full p-[3px]",
        "touch-manipulation select-none transition-transform duration-200",
        disabled ? "cursor-not-allowed opacity-60" : "hover:scale-[1.01]"
      )}
      onMouseEnter={() => !disabled && setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {/* Focus ring */}
      <span
        className={cn(
          "pointer-events-none absolute -inset-1 rounded-full transition-all duration-200",
          focus && !disabled
            ? "scale-100 opacity-100 shadow-[0_0_0_4px_rgba(15,79,170,0.25)]"
            : "scale-90 opacity-0"
        )}
      />
      {/* Track */}
      <motion.span
        className={cn(
          "absolute inset-0 rounded-full border",
          "dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]"
        )}
        animate={{
          borderColor: checked
            ? "color-mix(in srgb, var(--nav-link) 36%, transparent)"
            : hover && !disabled
              ? "color-mix(in srgb, var(--nav-link) 22%, transparent)"
              : "color-mix(in srgb, var(--glass-border) 82%, transparent)",
          backgroundColor: checked
            ? "color-mix(in srgb, var(--nav-link) 24%, white 76%)"
            : hover && !disabled
              ? "color-mix(in srgb, var(--card-bg) 95%, rgba(15,79,170,0.12) 5%)"
              : "color-mix(in srgb, var(--card-bg) 96%, rgba(15,40,85,0.06) 4%)",
          boxShadow: checked
            ? "inset 0 1px 0 rgba(255,255,255,0.6)"
            : "none",
        }}
        transition={{ duration: 0.2 }}
      />
      {/* Thumb with stretching animation */}
      <motion.span
        initial={{ x: checked ? 26 : 0, scaleX: 1, scaleY: 1 }}
        animate={controls}
        className={cn(
          "relative z-10 block h-[22px] rounded-full bg-white",
          "shadow-[0_2px_8px_rgba(15,40,85,0.18),0_0_0_1px_rgba(15,40,85,0.1)_inset]",
          "dark:bg-[color:color-mix(in_srgb,#0F1623,rgba(255,255,255,0.85))]",
          "dark:shadow-[0_2px_10px_rgba(5,9,17,0.65),0_0_0_1px_rgba(127,182,230,0.2)_inset]"
        )}
        style={{
          width: 22,
          transformOrigin: checked ? "left center" : "right center",
        }}
      />
      <input
        id={inputId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e, e.target.checked)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        className="absolute opacity-0 w-0 h-0"
      />
    </span>
  )
}
