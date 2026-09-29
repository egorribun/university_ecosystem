import { forwardRef, type ComponentPropsWithoutRef } from "react"
import { cva } from "class-variance-authority"
import { cn } from "@/utils/cn"

type InputVariantProps = {
  error?: boolean | null
  fullWidth?: boolean | null
  size?: "sm" | "md" | "lg" | null
}

type InputVariantFn = (props?: InputVariantProps) => string

let inputVariantsCache: InputVariantFn | null = null

/**
 * Build the class-variance contract on first render and reuse it afterwards.
 *
 * Keeping the factory in a function body makes the runtime visual contract
 * observable to mutation tests (and avoids treating a large module-level
 * literal as a static-only mutant), while the cache keeps repeated renders
 * allocation-free in the hot input path.
 */
function inputVariants(props?: InputVariantProps): string {
  if (inputVariantsCache === null) {
    inputVariantsCache = cva(
      "flex min-h-12 w-full rounded-lg border border-border-subtle bg-surface px-4 py-3 text-base font-medium text-text-primary shadow-sm transition-all duration-slow placeholder:text-text-tertiary focus:border-border-focus input-focus-glow disabled:cursor-not-allowed disabled:opacity-medium file:border-0 file:bg-transparent file:text-sm file:font-medium",
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
          size: {
            sm: "px-3 py-2 text-sm min-h-11",
            md: "px-4 py-3 text-base min-h-12",
            lg: "px-5 py-4 text-lg min-h-14",
          },
        },
        defaultVariants: {
          error: false,
          fullWidth: true,
          size: "md",
        },
      }
    ) as InputVariantFn
  }
  return inputVariantsCache(props)
}

export type InputProps = Omit<ComponentPropsWithoutRef<"input">, "size"> &
  InputVariantProps & {
    size?: "sm" | "md" | "lg"
  }

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, fullWidth, size, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(inputVariants({ error, fullWidth, size }), className)}
        aria-invalid={!!error}
        {...props}
      />
    )
  }
)

Input.displayName = "Input"
