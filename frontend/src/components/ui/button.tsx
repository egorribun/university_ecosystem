import {
  forwardRef,
  type ElementType,
  type ReactElement,
  type ReactNode,
  type MouseEvent,
} from "react"
import { cn } from "@/utils/cn"
import type { PolymorphicComponentProps, PolymorphicRef } from "@/types/polymorphic"
import { useHaptics } from "@/hooks/useHaptics"

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
  disabled?: boolean
  haptics?: boolean | "light" | "medium" | "heavy"
}

export type ButtonProps<T extends ElementType = "button"> = PolymorphicComponentProps<
  T,
  ButtonOwnProps
>

const sizeStyles: Record<ButtonSize, string> = {
  sm: "min-h-10 px-3 py-2 text-sm", // ~40px
  md: "min-h-12 px-5 py-2.5 text-base", // ~48px
  lg: "min-h-14 px-7 py-3 text-lg", // ~56px
}

const variantStyles: Record<ButtonVariant, string> = {
  solid: cn(
    "bg-gradient-brand text-inverse-text shadow-surface ring-brand/20 transition-all duration-500",
    "hover:shadow-[0_4px_20px_-6px_rgba(var(--primary-main),0.5)] hover:scale-[1.02] hover:opacity-90",
    "active:translate-y-[1px] active:scale-[0.98]",
    "motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 motion-reduce:active:translate-y-0 motion-reduce:active:scale-100",
    "disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-slate-800 dark:disabled:text-slate-600"
  ),
  outline: cn(
    "border border-border-subtle text-primary-text shadow-surface bg-transparent",
    "hover:border-brand hover:text-brand hover:bg-brand-subtle hover:shadow-surface-strong",
    "active:translate-y-[1px]",
    "motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
    "disabled:border-slate-200 disabled:text-slate-300 dark:disabled:border-slate-700 dark:disabled:text-slate-600"
  ),
  ghost: cn(
    "bg-transparent text-secondary-text",
    "hover:bg-surface-hover hover:text-primary-text",
    "active:bg-surface-hover",
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
  const {
    disabled,
    haptics = true,
    onClick,
    ...otherProps
  } = rest as typeof rest & {
    disabled?: boolean
    onClick?: (e: MouseEvent) => void
  }
  const { trigger } = useHaptics()
  const Component = (as ?? "button") as ElementType
  const isButtonElement = typeof Component === "string" && Component === "button"
  const isDisabled = Boolean(disabled || loading)

  const handleClick = (e: any) => {
    if (isDisabled) return
    if (haptics) {
      trigger(typeof haptics === "string" ? haptics : "light")
    }
    onClick?.(e)
  }

  const sharedProps: Record<string, unknown> = {}
  if (isDisabled) {
    sharedProps["aria-disabled"] = "true"
  }

  return (
    <Component
      ref={ref}
      className={cn(
        "group/button relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-ue-lg font-bold tracking-tight text-[0.95rem] transition-all duration-500 ease-out focus-visible:outline-none focus-visible:shadow-focus",
        "no-underline hover:no-underline focus-visible:no-underline",
        "motion-reduce:transition-shadow motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
        sizeStyles[size],
        variantStyles[variant],
        fullWidth ? "w-full" : "w-auto",
        isDisabled && "pointer-events-none opacity-60",
        className
      )}
      disabled={isButtonElement ? isDisabled : undefined}
      aria-busy={loading ? "true" : undefined}
      onClick={handleClick}
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
