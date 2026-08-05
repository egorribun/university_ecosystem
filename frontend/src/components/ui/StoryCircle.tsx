import { cn } from "@/utils/cn"
import type { CSSProperties, ElementType } from "react"
import type { PolymorphicComponentProps } from "@/types/polymorphic"

export type StoryCircleSize = "sm" | "md" | "lg"

type StoryCircleOwnProps = {
  size?: StoryCircleSize
  borderWidth?: number | string
  className?: string
  style?: CSSProperties
}

export type StoryCircleProps<T extends ElementType = "div"> = PolymorphicComponentProps<
  T,
  StoryCircleOwnProps
>

export const StoryCircle = <T extends ElementType = "div">({
  as,
  size = "md",
  borderWidth = 2,
  className,
  children,
  style,
  ...rest
}: StoryCircleProps<T>) => {
  const Component = (as ?? "div") as ElementType

  return (
    <Component
      className={cn(
        "group/story relative inline-flex items-center justify-center overflow-visible rounded-full text-white",
        "bg-linear-to-br from-(--primary-main) to-(--primary-main) shadow-lg",
        "transition-opacity duration-base ease-premium",
        "hover:opacity-80",
        "focus-visible:outline-(--primary-main) focus-visible:ring-1 focus-visible:ring-(--primary-main)/(--opacity-dim)",
        size === "sm" &&
          "h-(--size-story-sm) w-(--size-story-sm) min-h-(--size-story-sm) min-w-(--size-story-sm)",
        size === "md" &&
          "h-(--size-story-md) w-(--size-story-md) min-h-(--size-story-md) min-w-(--size-story-md)",
        size === "lg" &&
          "h-(--size-story-lg) w-(--size-story-lg) min-h-(--size-story-lg) min-w-(--size-story-lg)",
        className
      )}
      style={{
        borderWidth: typeof borderWidth === "number" ? `${borderWidth * 0.0625}rem` : borderWidth,
        borderStyle: "solid",
        borderColor: "color-mix(in srgb, var(--text-primary) 15%, transparent)",
        ...style,
      }}
      {...rest}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-full border border-(--primary-main)/(--opacity-subtle) opacity-0 outline-offset-[0.1875rem] transition-opacity duration-base group-focus-visible/story:opacity-100 group-hover/story:opacity-medium"
      />
      <span className="relative z-deep flex h-full w-full items-center justify-center overflow-hidden rounded-full">
        {children}
      </span>
    </Component>
  )
}

StoryCircle.displayName = "StoryCircle"
