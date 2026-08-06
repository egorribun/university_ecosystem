import { memo, type ComponentPropsWithoutRef, type ElementType } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/utils/cn"

const cardVariants = cva(
  "relative flex flex-col rounded-xl border border-border-subtle bg-(--bg-surface) text-text-primary shadow-surface transition-premium",
  {
    variants: {
      padding: {
        none: "p-0",
        sm: "p-3",
        md: "p-4",
        lg: "p-6",
      },
      hoverable: {
        true: "hover:-translate-y-1.5 hover:scale-hover-lift hover:shadow-premium-lift focus-ring-premium motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 motion-reduce:transition-shadow",
        false: "",
      },
    },
    defaultVariants: {
      padding: "md",
      hoverable: false,
    },
  }
)

type CardOwnProps = VariantProps<typeof cardVariants> & {
  as?: ElementType
}

export type CardProps<T extends ElementType = "div"> = CardOwnProps &
  Omit<ComponentPropsWithoutRef<T>, keyof CardOwnProps>

export const Card = memo(function Card<T extends ElementType = "div">({
  as,
  hoverable,
  padding,
  className,
  children,
  style,
  ...rest
}: CardProps<T>) {
  const Component = (as ?? "div") as ElementType

  return (
    <Component
      className={cn(cardVariants({ padding, hoverable }), className)}
      style={style}
      {...rest}
    >
      {children}
    </Component>
  )
})

Card.displayName = "Card"
