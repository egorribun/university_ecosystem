import { forwardRef, type ElementType, type ReactElement, type ReactNode } from "react"
import { cn } from "@/utils/cn"
import type { PolymorphicComponentProps, PolymorphicRef } from "@/types/polymorphic"

type ButtonVariant = "solid" | "outline" | "ghost"
type ButtonSize = "sm" | "md" | "lg"

type ButtonOwnProps = {
  variant?: ButtonVariant
  size?: ButtonSize
  fullWidth?: boolean
  loading?: boolean
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  className?: string
}

export type ButtonProps<T extends ElementType = "button"> = PolymorphicComponentProps<
  T,
  ButtonOwnProps
>

const sizeStyles: Record<ButtonSize, string> = {
  sm: "min-h-9 px-3 py-2 text-sm", // ~36px tall
  md: "min-h-11 px-4 py-2.5 text-base",
  lg: "min-h-12 px-5 py-3 text-lg",
}

const variantStyles: Record<ButtonVariant, string> = {
  solid: cn(
    "bg-btn-gradient text-white shadow-surface",
    "hover:bg-btn-gradient-hover hover:shadow-surface-strong",
    "active:translate-y-[1px]",
    "motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
    "disabled:bg-[color:var(--btn-disabled-bg,rgba(148,163,184,0.36))]",
    "disabled:text-[color:var(--btn-disabled-fg,#f1f5f9)]"
  ),
  outline: cn(
    "border border-button-border text-nav-text shadow-surface bg-[color:var(--btn-outline-bg,transparent)]",
    "hover:bg-surface-accent/80 hover:shadow-surface-strong",
    "active:translate-y-[1px]",
    "motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
    "disabled:border-[color:var(--btn-disabled-border,rgba(148,163,184,0.38))]",
    "disabled:text-[color:var(--btn-disabled-fg,#cbd5f5)]"
  ),
  ghost: cn(
    "bg-transparent text-nav-link",
    "hover:bg-surface-accent/70",
    "active:bg-surface-accent",
    "motion-reduce:transition-none"
  ),
}

const ButtonBase = <T extends ElementType = "button">(
  {
    as,
    variant = "solid",
    size = "md",
    fullWidth = false,
    loading = false,
    leadingIcon,
    trailingIcon,
    className,
    children,
    ...rest
  }: ButtonProps<T>,
  ref: PolymorphicRef<T>
) => {
  const { disabled, ...otherProps } = rest as typeof rest & { disabled?: boolean }
  const Component = (as ?? "button") as ElementType
  const isButtonElement = typeof Component === "string" && Component === "button"
  const isDisabled = Boolean(disabled || loading)

  const sharedProps: Record<string, unknown> = {}
  if (isDisabled) {
    sharedProps["aria-disabled"] = "true"
  }

  return (
    <Component
      ref={ref}
      className={cn(
        "group/button relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-ue-lg font-semibold tracking-wide text-[0.95rem] transition-[transform,box-shadow,background-color,border-color,color] duration-200 ease-out focus-visible:outline-none focus-visible:shadow-focus",
        "motion-reduce:transition-[box-shadow] motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
        sizeStyles[size],
        variantStyles[variant],
        fullWidth ? "w-full" : "w-auto",
        isDisabled && "pointer-events-none opacity-60",
        className
      )}
      disabled={isButtonElement ? isDisabled : undefined}
      aria-busy={loading ? "true" : undefined}
      {...sharedProps}
      {...otherProps}
    >
      {leadingIcon ? <span className="-ml-1 inline-flex items-center">{leadingIcon}</span> : null}
      <span className={cn("relative", loading && "opacity-0")}>{children}</span>
      {trailingIcon ? <span className="-mr-1 inline-flex items-center">{trailingIcon}</span> : null}
      {loading ? (
        <span
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
          aria-hidden
        >
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
        </span>
      ) : null}
    </Component>
  )
}

export const Button = forwardRef(
  ButtonBase as unknown as (
    props: ButtonProps<ElementType>,
    ref: PolymorphicRef<ElementType>
  ) => ReactElement | null
) as <T extends ElementType = "button">(
  props: ButtonProps<T> & { ref?: PolymorphicRef<T> }
) => ReactElement | null
;(Button as { displayName?: string }).displayName = "Button"
