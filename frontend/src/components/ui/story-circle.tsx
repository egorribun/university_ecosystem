import { cn } from "@/utils/cn"
import type { CSSProperties, ElementType } from "react"
import type { PolymorphicComponentProps } from "@/types/polymorphic"

export type StoryCircleSize = "sm" | "md" | "lg"

export const STORY_CIRCLE_SIZE_MAP: Record<StoryCircleSize, number> = {
  sm: 76.8,
  md: 91.2,
  lg: 110.4,
}

type StoryCircleOwnProps = {
  size?: StoryCircleSize
  borderWidth?: number
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
  const dimension = STORY_CIRCLE_SIZE_MAP[size]

  return (
    <Component
      className={cn(
        "group/story relative inline-flex items-center justify-center overflow-visible rounded-full text-white",
        "bg-linear-to-br from-(--primary-main) to-(--primary-main) shadow-lg",
        "transition-all duration-300 ease-premium transform-gpu",
        "hover:shadow-xl hover:-translate-y-0.5",
        "focus-visible:outline-(--primary-main) focus-visible:ring-4 focus-visible:ring-(--primary-main)/20",
        "motion-reduce:hover:translate-y-0",
        className
      )}
      style={{
        width: dimension,
        height: dimension,
        minWidth: dimension,
        minHeight: dimension,
        border: `${borderWidth}px solid color-mix(in srgb, var(--text-primary) 16%, transparent)`,
        ...style,
      }}
      {...rest}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-full border border-(--primary-main)/10 opacity-0 transition-opacity duration-300 group-focus-visible/story:opacity-100 group-hover/story:opacity-40"
        style={{ outlineOffset: 3 }}
      />
      <span className="relative z-(--z-deep) flex h-full w-full items-center justify-center overflow-hidden rounded-full">
        {children}
      </span>
    </Component>
  )
}

StoryCircle.displayName = "StoryCircle"




