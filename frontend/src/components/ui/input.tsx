import { forwardRef, type ComponentPropsWithoutRef } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/utils/cn"

const inputVariants = cva(
  "flex min-h-(--space-12) w-full rounded-lg border border-border-subtle bg-(--bg-surface) px-4 py-3 text-base font-medium text-(--text-primary) shadow-sm transition-all duration-500 placeholder:text-text-tertiary focus:border-border-focus focus:outline-none focus:shadow-focus disabled:cursor-not-allowed disabled:opacity-(--opacity-medium) file:border-0 file:bg-transparent file:text-sm file:font-medium",
  {
    variants: {
      error: {
        true: "border-error-text focus:border-error-text focus:ring-error-text/(--opacity-subtle)",
        false: "",
      },
      fullWidth: {
        true: "w-full",
        false: "w-auto",
      },
    },
    defaultVariants: {
      error: false,
      fullWidth: true,
    },
  }
)

export type InputProps = Omit<ComponentPropsWithoutRef<"input">, "size"> &
  VariantProps<typeof inputVariants>

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, fullWidth, ...props }, ref) => {
    return (
      <input ref={ref} className={cn(inputVariants({ error, fullWidth }), className)} {...props} />
    )
  }
)

Input.displayName = "Input"
