import type { HTMLAttributes } from "react"
import { cn } from "@/utils/cn"
import { cva, type VariantProps } from "class-variance-authority"

const skeletonVariants = cva("skeleton bg-muted animate-pulse", {
  variants: {
    rounded: {
      true: "rounded-lg",
      false: "rounded-none",
      full: "rounded-full",
      md: "rounded-md",
      lg: "rounded-lg",
      xl: "rounded-xl",
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
  ...rest
}: SkeletonProps) {
  // If rounded is boolean/standard variant, use cva.
  // If it's a custom string (rare legacy case), use customRounding or inline style.
  // The original component accepted `boolean | string` for rounded.
  // To verify: if `rounded` is a string like "20px", it won't match keys in cva, so it falls back to null class.
  // We can handle the "string as CSS value" case via style prop or custom logic.

  let variantRounding: VariantProps<typeof skeletonVariants>["rounded"] = true
  let styleBorderRadius: string | undefined = undefined

  if (typeof rounded === "boolean") {
    variantRounding = rounded ? true : false
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
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
      className={cn(skeletonVariants({ rounded: variantRounding }), className)}
      style={{
        width,
        height,
        borderRadius: styleBorderRadius || customRounding,
        ...style,
      }}
      {...rest}
    />
  )
}

Skeleton.displayName = "Skeleton"
