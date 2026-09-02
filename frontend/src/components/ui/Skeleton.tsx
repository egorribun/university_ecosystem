import type { HTMLAttributes } from "react"
import { cn } from "@/utils/cn"
import { cva, type VariantProps } from "class-variance-authority"

const skeletonVariants = cva("skeleton bg-muted animate-pulse", {
  variants: {
    rounded: {
      true: "rounded-(--radius-md)",
      false: "rounded-none",
      full: "rounded-full",
      sm: "rounded-(--radius-sm)",
      md: "rounded-(--radius-md)",
      lg: "rounded-(--radius-lg)",
      xl: "rounded-(--radius-xl)",
    },
  },
  defaultVariants: {
    rounded: true,
  },
})

type SkeletonProps = Omit<HTMLAttributes<HTMLDivElement>, "width" | "height"> &
  Omit<VariantProps<typeof skeletonVariants>, "rounded"> & {
    width?: number | string
    height?: number | string
    rounded?: VariantProps<typeof skeletonVariants>["rounded"] | string
    ariaLabel?: string
    // Allow custom rounding string for backward compatibility or strict values
    customRounding?: string
  }

export function Skeleton({
  width,
  height,
  rounded,
  customRounding,
  className,
  ariaLabel,
  style,
  "aria-hidden": ariaHidden,
  ...rest
}: SkeletonProps) {
  // Handle standard variants and custom CSS values for rounding
  let variantRounding: VariantProps<typeof skeletonVariants>["rounded"] = true
  let styleBorderRadius: string | undefined = undefined

  if (typeof rounded === "boolean") {
    variantRounding = rounded
  } else if (typeof rounded === "string") {
    // Check if it's a known variant key
    if (["full", "md", "lg", "xl"].includes(rounded)) {
      variantRounding = rounded as VariantProps<typeof skeletonVariants>["rounded"]
    } else {
      // It's a custom CSS value
      variantRounding = false // disable class
      styleBorderRadius = rounded
    }
  }

  return (
    <div
      {...rest}
      role={ariaLabel ? "status" : undefined}
      aria-live={ariaLabel ? "polite" : undefined}
      aria-busy="true"
      aria-hidden={ariaLabel ? undefined : (ariaHidden ?? true)}
      aria-label={ariaLabel}
      className={cn(skeletonVariants({ rounded: variantRounding }), className)}
      style={{
        width,
        height,
        borderRadius: styleBorderRadius || customRounding,
        ...style,
      }}
    />
  )
}

Skeleton.displayName = "Skeleton"
