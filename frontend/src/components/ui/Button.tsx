import {
  forwardRef,
  type ElementType,
  type ReactElement,
  type ReactNode,
  type MouseEvent,
} from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/utils/cn"
import type { PolymorphicComponentProps, PolymorphicRef } from "@/types/polymorphic"

const buttonVariants = cva(
  "group/button btn-ripple relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-md font-bold tracking-tight text-base transition-premium focus-ring-premium no-underline hover:no-underline focus-visible:no-underline motion-reduce:transition-shadow motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
  {
    variants: {
      variant: {
        solid: cn(
          "bg-linear-brand text-inverse-text shadow-surface ring-brand/(--opacity-dim) transition-all duration-slow",
          "hover:shadow-premium-lift hover:scale-hover hover:opacity-heavy",
          "active:scale-95",
          "motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 motion-reduce:active:translate-y-0 motion-reduce:active:scale-100",
          "disabled:bg-(--border-subtle) disabled:text-(--text-tertiary)"
        ),
        outline: cn(
          "border border-border-subtle text-text-primary shadow-surface bg-transparent",
          "hover:border-brand hover:text-brand hover:bg-brand-subtle hover:shadow-surface-strong",
          "active:scale-95",
          "motion-reduce:hover:translate-y-0 motion-reduce:active:translate-y-0",
          "disabled:border-(--border-subtle) disabled:text-(--text-tertiary)"
        ),
        ghost: cn(
          "bg-transparent text-(--text-secondary)",
          "hover:bg-(--bg-surface-hover) hover:text-text-primary",
          "active:bg-(--bg-surface-hover)",
          "motion-reduce:transition-none"
        ),
        glass: cn(
          "bg-glass backdrop-blur-glass text-text-primary border border-glass-border shadow-glass",
          "hover:bg-glass-tint1 hover:scale-hover",
          "active:scale-95 transition-all duration-base"
        ),
        gradient: cn(
          "bg-linear-brand text-inverse-text shadow-lg border-none",
          "hover:shadow-premium-lift hover:saturate-150 hover:scale-hover hover:opacity-heavy",
          "active:scale-95 transition-all duration-slow"
        ),
      },
      size: {
        sm: "min-h-11 px-3 py-2 text-(--fs-sm)",
        md: "min-h-12 px-5 py-2.5 text-(--fs-base)",
        lg: "min-h-14 px-7 py-3 text-(--fs-lg)",
        icon: "h-11 w-11 min-h-11 min-w-11 p-0 rounded-lg",
      },
      fullWidth: {
        true: "w-full",
        false: "",
      },
    },
    defaultVariants: {
      variant: "solid",
      size: "md",
      fullWidth: false,
    },
  }
)

type ButtonOwnProps = VariantProps<typeof buttonVariants> & {
  loading?: boolean
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  className?: string
  disabled?: boolean
  haptics?: boolean | "light" | "medium" | "heavy" | "success" | "warning" | "error"
}

export type ButtonProps<T extends ElementType = "button"> = PolymorphicComponentProps<
  T,
  ButtonOwnProps
>

const ButtonBase = <T extends ElementType = "button">(
  {
    as,
    variant,
    size,
    fullWidth,
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

  const Component = (as ?? "button") as ElementType
  const isButtonElement = typeof Component === "string" && Component === "button"
  const isDisabled = Boolean(disabled || loading)

  const handleClick = (e: MouseEvent) => {
    if (isDisabled) return

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
        buttonVariants({ variant, size, fullWidth }),
        isDisabled && "pointer-events-none opacity-strong",
        className
      )}
      disabled={isButtonElement ? isDisabled : undefined}
      aria-busy={loading ? "true" : undefined}
      onClick={handleClick}
      {...sharedProps}
      data-haptic={haptics ? (typeof haptics === "string" ? haptics : "light") : undefined}
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
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent opacity-medium" />
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
