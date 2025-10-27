import { cn } from "@/utils/cn"
import type { CSSProperties, ElementType } from "react"
import type { PolymorphicComponentProps } from "@/types/polymorphic"

type StoryCircleSize = "sm" | "md" | "lg"

const sizeMap: Record<StoryCircleSize, number> = {
  sm: 64,
  md: 76,
  lg: 92,
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
  const dimension = sizeMap[size]

  return (
    <Component
      className={cn(
        "group/story relative inline-flex items-center justify-center overflow-visible rounded-full text-white",
        "bg-[linear-gradient(135deg,#1d4ed8,#60a5fa)] shadow-[0_8px_20px_rgba(37,99,235,0.18)]",
        "transition-[box-shadow,transform] duration-200 ease-out motion-reduce:transition-[box-shadow]",
        "hover:shadow-[0_12px_28px_rgba(37,99,235,0.28)] hover:-translate-y-0.5",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[rgba(125,172,255,0.65)]",
        "motion-reduce:hover:translate-y-0",
        className
      )}
      style={{
        width: dimension,
        height: dimension,
        minWidth: dimension,
        minHeight: dimension,
        border: `${borderWidth}px solid color-mix(in srgb, var(--page-text) 16%, transparent)`,
        ...style,
      }}
      {...rest}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-full border border-[rgba(125,172,255,0.35)] shadow-[0_0_0_2px_rgba(125,172,255,0.5),0_0_12px_rgba(37,99,235,0.2)] opacity-0 transition-[opacity,transform] duration-200 ease-out group-focus-visible/story:opacity-100 group-hover/story:opacity-70 motion-reduce:transition-none"
        style={{ outlineOffset: 3 }}
      />
      <span className="relative z-[1] flex h-full w-full items-center justify-center overflow-hidden rounded-full">
        {children}
      </span>
    </Component>
  )
}

StoryCircle.displayName = "StoryCircle"
