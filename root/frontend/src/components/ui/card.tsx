import type { ComponentPropsWithoutRef, ElementType } from "react"
import { cn } from "@/utils/cn"
import { cardHoverStyles, type CardHoverOptions } from "@/constants/cardHover"

type CardPadding = "none" | "sm" | "md" | "lg"

const paddingClasses: Record<CardPadding, string> = {
  none: "p-0",
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
}

type CardOwnProps = {
  as?: ElementType
  hoverable?: boolean | CardHoverOptions
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
  const hoverOptions = typeof hoverable === "boolean" ? {} : hoverable
  const hover = hoverable ? cardHoverStyles(hoverOptions) : null

  return (
    <Component
      className={cn(
        "relative flex flex-col rounded-ue-xl border border-[color-mix(in_srgb,var(--page-text)_8%,transparent)] bg-surface text-page-foreground shadow-surface",
        paddingClasses[padding],
        hover?.className,
        className
      )}
      style={{ ...hover?.style, ...style }}
      {...rest}
    >
      {children}
    </Component>
  )
}

Card.displayName = "Card"

