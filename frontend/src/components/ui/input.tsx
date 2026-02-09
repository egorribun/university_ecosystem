import { forwardRef, type ComponentPropsWithoutRef, type ElementType } from "react"
import { cn } from "@/utils/cn"

export type InputProps = ComponentPropsWithoutRef<"input"> & {
  error?: boolean
  fullWidth?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, fullWidth = true, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          "flex min-h-12 w-full rounded-ue-md border border-border-subtle bg-(--bg-surface) px-4 py-3 text-base font-medium text-(--text-primary) shadow-sm transition-all duration-500",
          "placeholder:text-text-tertiary",
          "focus:border-border-focus focus:outline-none focus:shadow-focus",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          error && "border-error-text focus:border-error-text focus:ring-error-text/10",
          !fullWidth && "w-auto",
          className
        )}
        {...props}
      />
    )
  }
)

Input.displayName = "Input"




