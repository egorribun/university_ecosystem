import type { ComponentPropsWithoutRef, ElementType } from "react"
import { cn } from "@/utils/cn"

type CardPadding = "none" | "sm" | "md" | "lg"

const paddingClasses: Record<CardPadding, string> = {
  none: "p-0",
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
}

type CardOwnProps = {
  as?: ElementType
  hoverable?: boolean
  padding?: CardPadding
  className?: string
}

export type CardProps<T extends ElementType = "div"> = CardOwnProps &
  Omit<ComponentPropsWithoutRef<T>, keyof CardOwnProps>

export const Card = <T extends ElementType = "div">({
  as,
  hoverable = false,
  padding = "md",
  className,
  children,
  style,
  ...rest
}: CardProps<T>) => {
  const Component = (as ?? "div") as ElementType

  return (
    <Component
      className={cn(
        "relative flex flex-col rounded-2xl border border-border-subtle bg-(--bg-surface) text-(--text-primary) shadow-surface transition-premium",
        paddingClasses[padding],
        hoverable
          ? "hover:-translate-y-1.5 hover:scale-[1.015] hover:shadow-premium-lift focus-visible:outline-none focus-visible:shadow-focus motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 motion-reduce:transition-shadow"
          : "",
        className
      )}
      style={style}
      {...rest}
    >
      {children}
    </Component>
  )
}

Card.displayName = "Card"
