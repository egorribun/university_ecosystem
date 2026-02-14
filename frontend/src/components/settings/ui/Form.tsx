import React, { ChangeEvent, FocusEvent, type CSSProperties } from "react"
import { cn } from "@/utils/cn"
import {
  Button as GlobalButton,
  type ButtonProps as GlobalButtonProps,
  Input,
  Textarea,
  Switch,
  RadioGroup,
  RadioGroupItem as Radio,
} from "@/components/ui"

export { Input, Textarea, Switch, RadioGroup, Radio }

// Compatible Button wrapper types
type LegacyVariant = "contained" | "outlined" | "text"
type LegacySize = "small" | "medium" | "large"

export function Button<T extends React.ElementType = "button">({
  variant,
  size,
  startIcon,
  endIcon,
  leadingIcon,
  trailingIcon,
  ...props
}: Omit<GlobalButtonProps<T>, "variant" | "size"> & {
  variant?: GlobalButtonProps<T>["variant"] | LegacyVariant
  size?: GlobalButtonProps<T>["size"] | LegacySize
  startIcon?: React.ReactNode
  endIcon?: React.ReactNode
}) {
  const isLegacyVariant = (v: any): v is LegacyVariant =>
    ["contained", "outlined", "text"].includes(v)
  const isLegacySize = (s: any): s is LegacySize => ["small", "medium", "large"].includes(s)

  const mappedVariant = (
    isLegacyVariant(variant)
      ? variant === "contained"
        ? "solid"
        : variant === "outlined"
          ? "outline"
          : "ghost"
      : variant || "solid"
  ) as GlobalButtonProps<T>["variant"]

  const mappedSize = (
    isLegacySize(size) ? (size === "small" ? "sm" : size === "medium" ? "md" : "lg") : size || "md"
  ) as GlobalButtonProps<T>["size"]

  return (
    <GlobalButton
      variant={mappedVariant}
      size={mappedSize}
      leadingIcon={leadingIcon ?? startIcon}
      trailingIcon={trailingIcon ?? endIcon}
      {...(props as React.ComponentPropsWithoutRef<T>)}
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
  "text-(--text-primary) border-glass-border bg-glass-bg",
  "shadow-glass backdrop-blur-glass transition-all duration-300",
  "dark:bg-glass-tint1 dark:border-white/(--opacity-subtle)"
)

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
    size?: "small" | "medium" | "sm" | "md"
    fullWidth?: boolean
    autoComplete?: string
    className?: string
    multiline?: boolean
    rows?: number
    trailingIcon?: React.ReactNode
    leadingIcon?: React.ReactNode
  } & Omit<
    React.InputHTMLAttributes<HTMLInputElement | HTMLTextAreaElement>,
    "size" | "onChange" | "onBlur"
  >
>(
  (
    {
      label,
      value,
      onChange,
      onBlur,
      type = "text",
      disabled = false,
      error = false,
      helperText,
      placeholder,
      fullWidth = false,
      autoComplete,
      className = "",
      multiline = false,
      rows,
      trailingIcon,
      leadingIcon,
      ...props
    },
    ref
  ) => {
    // InputComponent removed as it was unused

    return (
      <div className={cn("flex flex-col gap-1.5", fullWidth && "w-full", className)}>
        {label && (
          <label
            htmlFor={props.id}
            className="mb-0.5 block px-1 text-xs font-bold uppercase tracking-widest text-(--text-secondary)"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {leadingIcon && (
            <div className="absolute left-4 top-1/2 -translate-y-1/2 text-(--text-tertiary)">
              {leadingIcon}
            </div>
          )}
          {multiline ? (
            <Textarea
              ref={ref as React.Ref<HTMLTextAreaElement>}
              value={value}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                onChange(e as unknown as React.ChangeEvent<HTMLInputElement>)
              }
              onBlur={(e: React.FocusEvent<HTMLTextAreaElement>) =>
                onBlur?.(e as unknown as React.FocusEvent<HTMLInputElement>)
              }
              disabled={disabled}
              placeholder={placeholder}
              rows={rows}
              className={cn("resize-none", leadingIcon ? "pl-11" : "", trailingIcon ? "pr-11" : "")}
              {...props}
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
              className={cn(
                fullWidth && "w-full",
                leadingIcon ? "pl-11" : "",
                trailingIcon ? "pr-11" : ""
              )}
              {...props}
            />
          )}
          {trailingIcon && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2 text-(--text-tertiary)">
              {trailingIcon}
            </div>
          )}
        </div>
        {helperText && (
          <p
            className={cn(
              "px-1 text-xs font-medium leading-tight",
              error ? "text-(--error-text)" : "text-(--text-tertiary)/(--opacity-strong)"
            )}
          >
            {helperText}
          </p>
        )}
      </div>
    )
  }
)

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
      onCheckedChange={(c: boolean) =>
        onChange({ target: { checked: c } } as React.ChangeEvent<HTMLInputElement>, c)
      }
    />
  )
}

// Wrapper for radio/checkbox with label
export function FormControlLabel({
  value,
  control,
  label,
  className = "",
  ...props
}: {
  value?: string
  control: React.ReactNode
  label: React.ReactNode
  className?: string
} & React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "group inline-flex items-center gap-3 rounded-sm px-2 py-1.5",
        "cursor-pointer transition-all duration-300",
        "hover:bg-(--primary-main)/5 border border-transparent",
        className
      )}
      {...props}
    >
      {React.isValidElement(control)
        ? React.cloneElement(control as React.ReactElement<{ value?: string }>, { value })
        : control}
      <span className="text-sm font-bold text-(--text-primary) transition-colors">{label}</span>
    </label>
  )
}
