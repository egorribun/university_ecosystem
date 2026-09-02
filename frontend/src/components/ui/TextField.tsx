import React, { ChangeEvent, FocusEvent, useId } from "react"
import { cn } from "@/utils/cn"
import { Input, Textarea } from "@/components/ui"

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
    fullWidth?: boolean
    autoComplete?: string
    className?: string
    multiline?: boolean
    rows?: number
    trailingIcon?: React.ReactNode
    leadingIcon?: React.ReactNode
    inputClassName?: string
    id?: string
    size?: "sm" | "md" | "lg"
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
      inputClassName = "",
      multiline = false,
      rows,
      trailingIcon,
      leadingIcon,
      size = "md",
      id,
      ...props
    },
    ref
  ) => {
    const helperId = useId()
    const generatedControlId = useId()
    const controlId = id ?? generatedControlId

    return (
      <div className={cn("flex flex-col gap-1.5", fullWidth && "w-full", className)}>
        {label && (
          <label
            htmlFor={controlId}
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
              id={controlId}
              aria-describedby={helperText ? helperId : undefined}
              aria-invalid={error || undefined}
              className={cn(
                "resize-none",
                leadingIcon ? "pl-11" : "",
                trailingIcon ? "pr-11" : "",
                inputClassName
              )}
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
              size={size}
              fullWidth={fullWidth}
              id={controlId}
              aria-describedby={helperText ? helperId : undefined}
              className={cn(
                leadingIcon ? "pl-11" : "",
                trailingIcon ? "pr-11" : "",
                inputClassName
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
            id={helperId}
            role={error ? "alert" : undefined}
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
