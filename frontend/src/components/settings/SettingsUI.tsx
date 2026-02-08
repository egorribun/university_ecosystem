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
  useCallback,
  ChangeEvent,
  FocusEvent,
  type CSSProperties,
  type ReactNode,
  forwardRef,
} from "react"
import ReactDOM from "react-dom"
import { motion, AnimatePresence } from "framer-motion"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/SmartImage"
import {
  Button as GlobalButton,
  Input,
  Switch,
  RadioGroup,
  RadioGroupItem as Radio,
} from "@/components/ui"

export { Input, Switch, RadioGroup, Radio }

// Compatible Button wrapper
export function Button({
  variant,
  startIcon,
  endIcon,
  ...props
}: any) {
  const mappedVariant =
    variant === "contained" ? "solid" :
    variant === "outlined" ? "outline" :
    variant === "text" ? "ghost" :
    variant || "solid"

  return (
    <GlobalButton
      variant={mappedVariant}
      leadingIcon={startIcon}
      trailingIcon={endIcon}
      {...props}
    />
  )
}

// Types
export type ThemeMode = "system" | "light" | "dark"

// Helper functions
export const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

export const securityStatusChipClassName = cn(
  "font-bold tracking-tight px-3 py-1 rounded-full text-xs",
  "text-primary-text border border-glass-border bg-surface/40",
  "shadow-glass backdrop-blur-xl transition-all duration-300",
  "dark:bg-surface/20 dark:border-white/10"
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
        "relative flex flex-col gap-3 overflow-hidden rounded-3xl px-6 py-6",
        "border border-glass-border bg-surface/40 text-primary-text",
        "shadow-glass transition-all duration-500",
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:opacity-30",
        "before:bg-[radial-gradient(circle_at_0%_0%,var(--primary-main),transparent_60%)]",
        "dark:before:bg-[radial-gradient(circle_at_0%_0%,var(--primary-subtle),transparent_60%)]",
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
        "font-bold tracking-tight text-primary-text",
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
        "text-secondary-text leading-relaxed",
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
        "group relative flex items-stretch justify-between gap-4 rounded-2xl px-4 py-3",
        "border border-glass-border bg-surface/30 text-primary-text",
        "transition-all duration-500 ease-out backdrop-blur-sm",
        "hover:-translate-y-px hover:border-brand/30 hover:bg-surface/50 hover:shadow-glass",
        "max-sm:flex-col max-sm:items-start",
        "data-[revoked=true]:border-dashed data-[revoked=true]:border-border-subtle",
        "data-[revoked=true]:bg-surface/10 data-[revoked=true]:shadow-none data-[revoked=true]:backdrop-blur-none",
        "data-[revoked=true]:hover:translate-y-0",
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
        "overflow-hidden rounded-2xl border transition-all duration-500",
        "border-glass-border bg-surface/30 backdrop-blur-sm",
        expanded
          ? "shadow-glass border-brand/20 bg-surface/50"
          : "shadow-sm border-transparent",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 text-left transition-colors hover:bg-brand/5"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-col gap-1 min-w-0">
            <h3 className="text-sm font-bold text-primary-text">
              {title}
            </h3>
            {subtitle && (
              <p className="text-xs text-secondary-text">
                {subtitle}
              </p>
            )}
          </div>
          <motion.svg
            animate={{ rotate: expanded ? 180 : 0 }}
            className="h-5 w-5 shrink-0 text-brand transition-transform duration-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </motion.svg>
        </div>
      </button>
      <div
        className={cn(
          "overflow-hidden transition-all duration-500",
          expanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="px-4 pb-4 pt-2">{children}</div>
      </div>
    </div>
  )
}


// Form Components
// TextField wrapper using global Input
export const TextField = React.forwardRef<
  HTMLInputElement | HTMLTextAreaElement,
  {
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
    multiline?: boolean
    rows?: number
    trailingIcon?: React.ReactNode
    leadingIcon?: React.ReactNode
  } & Omit<React.InputHTMLAttributes<HTMLInputElement | HTMLTextAreaElement>, "size" | "onChange" | "onBlur">
>(({
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
  multiline = false,
  rows,
  trailingIcon,
  leadingIcon,
  ...props
}, ref) => {
  const InputComponent = multiline ? "textarea" : Input

  return (
    <div className={cn("flex flex-col gap-1.5", fullWidth && "w-full", className)}>
      {label && (
        <label className="mb-0.5 block px-1 text-[10px] font-bold uppercase tracking-widest text-secondary-text">
          {label}
        </label>
      )}
      <div className="relative">
        {leadingIcon && (
          <div className="absolute left-4 top-1/2 -translate-y-1/2 text-tertiary-text">
            {leadingIcon}
          </div>
        )}
        {multiline ? (
          <textarea
            ref={ref as React.Ref<HTMLTextAreaElement>}
            value={value}
            onChange={onChange as any}
            onBlur={onBlur as any}
            disabled={disabled}
            placeholder={placeholder}
            rows={rows}
            className={cn(
              "flex w-full rounded-2xl border border-glass-border bg-surface px-4 py-3 text-base font-medium text-primary-text shadow-sm transition-all duration-500",
              "placeholder:text-tertiary-text",
              "focus:border-brand/40 focus:outline-none focus:ring-4 focus:ring-brand/10",
              "disabled:cursor-not-allowed disabled:opacity-50",
              error ? "border-error focus:border-error focus:ring-error/10" : "",
              !fullWidth ? "w-auto" : "",
              "resize-none",
              leadingIcon ? "pl-11" : "",
              trailingIcon ? "pr-11" : ""
            )}
            {...(props as any)}
          />
        ) : (
          <Input
            ref={ref as React.Ref<HTMLInputElement>}
            type={type}
            value={value}
            onChange={onChange}
            onBlur={onBlur}
            disabled={disabled}
            placeholder={placeholder}
            autoComplete={autoComplete}
            error={error}
            className={cn(fullWidth && "w-full", leadingIcon ? "pl-11" : "", trailingIcon ? "pr-11" : "")}
            {...props}
          />
        )}
        {trailingIcon && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2 text-tertiary-text">
            {trailingIcon}
          </div>
        )}
      </div>
      {helperText && (
        <p className={cn("px-1 text-[11px] font-medium leading-tight", error ? "text-error" : "text-tertiary-text/80")}>
          {helperText}
        </p>
      )}
    </div>
  )
})

TextField.displayName = "TextField"

// Ported SwitchControl to use global Switch
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
  return (
    <Switch
      id={inputId}
      checked={checked}
      disabled={disabled}
      aria-label={ariaLabel}
      onCheckedChange={(c: boolean) => onChange({ target: { checked: c } } as any, c)}
    />
  )
}

// Wrapper for radio/checkbox with label
export function FormControlLabel({
  value,
  control,
  label,
  className = "",
}: {
  value?: string
  control: React.ReactNode
  label: React.ReactNode
  className?: string
}) {
  return (
    <label
      className={cn(
        "group inline-flex items-center gap-3 rounded-xl px-2 py-1.5",
        "cursor-pointer transition-all duration-300",
        "hover:bg-brand/5 border border-transparent",
        className
      )}
    >
      {React.isValidElement(control)
        ? React.cloneElement(control as React.ReactElement, { value } as any)
        : control}
      <span className="text-sm font-bold text-primary-text transition-colors">
        {label}
      </span>
    </label>
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
    info: "bg-brand/10 text-brand border-brand/20",
    error: "bg-error/10 text-error border-error/20",
    warning: "bg-warning/10 text-warning border-warning/20",
    success: "bg-success/10 text-success border-success/20",
  }

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-2xl border px-4 py-3 backdrop-blur-md shadow-sm",
        palette[severity],
        className
      )}
    >
      <span className="flex-1 text-sm font-semibold leading-relaxed">{children}</span>
      {onClose && (
        <button
          onClick={onClose}
          className="rounded-lg p-1 transition hover:bg-black/5 dark:hover:bg-white/5"
        >
          ×
        </button>
      )}
    </div>
  )
}

export function Chip({
  label,
  color = "default",
  variant = "filled",
  className = "",
  ...props
}: {
  label: string
  size?: "small" | "medium"
  color?: "default" | "success" | "primary"
  variant?: "filled" | "outlined"
  className?: string
} & React.HTMLAttributes<HTMLSpanElement>) {
  const colorMap = {
      default: "text-secondary-text bg-surface/50 border-glass-border",
      success: "text-success bg-success/10 border-success/20",
      primary: "text-brand bg-brand/10 border-brand/20",
  }

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-bold tracking-tight shadow-sm backdrop-blur-md",
        colorMap[color],
        className
      )}
      {...props}
    >
      {label}
    </span>
  )
}

export function Divider({
  className = "",
  flexItem,
}: {
  className?: string
  flexItem?: boolean
  component?: React.ElementType
}) {
  return (
    <hr
      className={cn(
        "h-px w-full border-0 bg-glass-border opacity-50",
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
        "relative overflow-hidden rounded-full p-1",
        "bg-linear-to-tr from-brand to-brand/20 shadow-glass",
        className
      )}
    >
      <div className="relative h-full w-full overflow-hidden rounded-full bg-surface">
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

export function Skeleton({
  variant = "rectangular",
  width,
  height,
  className = "",
  style,
}: {
  variant?: "circular" | "rectangular" | "rounded" | "text"
  width?: string | number
  height?: string | number
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div
      className={cn(
        "animate-pulse bg-white/5 dark:bg-white/10",
        variant === "circular" ? "rounded-full" : variant === "rounded" ? "rounded-2xl" : "rounded-none",
        className
      )}
      style={{
        width: typeof width === "number" ? `${width}px` : width,
        height: typeof height === "number" ? `${height}px` : height,
        ...style,
      }}
    />
  )
}

export function CircularProgress({
  size = 24,
  className = "",
}: {
  size?: number
  color?: string
  className?: string
}) {
  return (
    <svg
      className={cn("animate-spin text-brand", className)}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path
        className="opacity-100"
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

  return ReactDOM.createPortal(
    <div
      role="presentation"
      className="fixed inset-0 z-(--ue-z-index-overlay) flex items-center justify-center p-4"
    >
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-background/80 backdrop-blur-xl"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className={cn(
          "relative z-10 w-full overflow-hidden rounded-3xl border border-glass-border bg-surface shadow-glass",
          fullWidth ? "w-full" : maxWidthClasses
        )}
      >
        {children}
      </motion.div>
    </div>,
    document.body
  )
}

export function DialogTitle({
  children,
  className = "",
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <h2
      className={cn(
        "px-6 pt-6 pb-2 text-xl font-bold tracking-tight text-primary-text border-b border-glass-border/10",
        className
      )}
    >
      {children}
    </h2>
  )
}

export function DialogContent({
  children,
  className = "",
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn("px-6 py-4 text-secondary-text leading-relaxed", className)}>{children}</div>
  )
}

export function DialogActions({
  children,
  className = "",
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-3 border-t border-glass-border/10 px-6 py-4 bg-surface-hover/20",
        className
      )}
    >
      {children}
    </div>
  )
}

export function Snackbar({
  open,
  onClose,
  autoHideDuration,
  anchorOrigin,
  children,
  className = "",
}: {
  open: boolean
  onClose: () => void
  autoHideDuration?: number
  anchorOrigin?: { vertical: string; horizontal: string }
  children: React.ReactNode
  className?: string
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
      ? "bottom-8"
      : anchorOrigin?.vertical === "top"
        ? "top-8"
        : "top-1/2 -translate-y-1/2"
  const horizontalClasses =
    anchorOrigin?.horizontal === "center"
      ? "left-1/2 -translate-x-1/2"
      : anchorOrigin?.horizontal === "right"
        ? "right-8"
        : "left-8"

  return (
    <div
      className={cn("fixed pointer-events-none z-(--ue-z-index-toast)", positionClasses, horizontalClasses, className)}
    >
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.8 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.8 }}
        className="pointer-events-auto"
      >
        {children}
      </motion.div>
    </div>
  )
}

// Navigation Components
export function Tabs({
  value,
  onChange,
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
        "relative flex flex-wrap items-center gap-1.5 overflow-x-auto rounded-2xl px-1.5 py-1.5",
        "border border-glass-border bg-surface/30 backdrop-blur-md shadow-glass",
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
      onClick={onClick}
      className={cn(
        "relative flex h-10 items-center justify-center rounded-xl px-5 text-sm font-black transition-all duration-500",
        selected
          ? "text-primary-text"
          : "text-secondary-text opacity-70 hover:opacity-100 hover:bg-surface-hover/20"
      )}
    >
      {selected && (
        <motion.div
          layoutId={layoutId}
          className="absolute inset-0 z-0 rounded-xl bg-brand/10 ring-1 ring-brand/20"
          transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
        />
      )}
      <span className="relative z-1">{label}</span>
    </button>
  )
}
