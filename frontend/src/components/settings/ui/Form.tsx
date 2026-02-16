import React, { ChangeEvent, type CSSProperties } from "react"
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
  const isLegacyVariant = (v: unknown): v is LegacyVariant =>
    ["contained", "outlined", "text"].includes(v as string)
  const isLegacySize = (s: unknown): s is LegacySize =>
    ["small", "medium", "large"].includes(s as string)

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
  "text-text-primary border-glass-border bg-glass-bg",
  "shadow-glass backdrop-blur-glass transition-all duration-base",
  "dark:bg-glass-tint1 dark:border-white/(--opacity-subtle)"
)

export { TextField } from "@/components/ui/TextField"

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
        "cursor-pointer transition-all duration-base",
        "hover:bg-(--primary-main)/(--opacity-faint) border border-transparent",
        className
      )}
      {...props}
    >
      {React.isValidElement(control)
        ? React.cloneElement(control as React.ReactElement<{ value?: string }>, { value })
        : control}
      <span className="text-sm font-bold text-text-primary transition-colors">{label}</span>
    </label>
  )
}
