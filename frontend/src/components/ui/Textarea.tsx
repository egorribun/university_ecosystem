import { forwardRef, type ComponentPropsWithoutRef } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/utils/cn"

const textareaVariants = cva(
  "flex min-h-(--min-h-textarea) w-full rounded-(--radius-lg) border border-border-subtle bg-(--bg-surface) px-(--space-4) py-(--space-3) text-(--fs-base) font-medium text-text-primary shadow-sm transition-all duration-slow placeholder:text-text-tertiary focus:border-border-focus focus-ring-premium disabled:cursor-not-allowed disabled:opacity-medium",
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

export type TextareaProps = Omit<ComponentPropsWithoutRef<"textarea">, "size"> &
  VariantProps<typeof textareaVariants>

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error, fullWidth, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(textareaVariants({ error, fullWidth }), className)}
        aria-invalid={!!error}
        {...props}
      />
    )
  }
)

Textarea.displayName = "Textarea"
