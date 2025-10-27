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
        "relative flex flex-col rounded-ue-xl border border-[color-mix(in_srgb,var(--page-text)_8%,transparent)] bg-surface text-page-foreground shadow-surface transition-[transform,box-shadow] duration-500 ease-out",
        paddingClasses[padding],
        hoverable
          ? "hover:-translate-y-[2px] hover:shadow-surface-strong focus-visible:outline-none focus-visible:shadow-focus motion-reduce:hover:translate-y-0 motion-reduce:transition-[box-shadow]"
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
