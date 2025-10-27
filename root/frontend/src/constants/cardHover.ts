import type { CSSProperties } from "react"
import { cn } from "@/utils/cn"

export type CardHoverOptions = {
  disabled?: boolean
  hoverTransform?: string | null
  hoverBoxShadow?: string | null
  activeTransform?: string | null
  extraTransitions?: string[]
}

export type CardHoverResult = {
  className: string
  style: CSSProperties
}

const DEFAULT_TRANSFORM = "scale(1.03)"
const DEFAULT_ACTIVE_TRANSFORM = "scale(0.997)"
const DEFAULT_HOVER_SHADOW = "0 12px 28px rgba(0,0,0,0.18)"

export const cardHoverStyles = ({
  disabled = false,
  hoverTransform = DEFAULT_TRANSFORM,
  hoverBoxShadow = DEFAULT_HOVER_SHADOW,
  activeTransform = DEFAULT_ACTIVE_TRANSFORM,
  extraTransitions = [],
}: CardHoverOptions = {}): CardHoverResult => {
  const transitions = [
    "transform 0.25s ease",
    "box-shadow 0.25s ease",
    ...extraTransitions.filter((value) => Boolean(value?.trim?.() ?? value)),
  ]

  const style: (CSSProperties & Record<string, string | number | undefined>) = {
    transition: transitions.join(", ") || undefined,
  }

  const hoverClasses: string[] = []

  if (hoverTransform !== null && hoverTransform !== undefined) {
    hoverClasses.push("hover:[transform:var(--card-hover-transform,scale(1.03))]")
    if (hoverTransform) {
      style["--card-hover-transform"] = hoverTransform
    }
  }

  if (hoverBoxShadow !== null && hoverBoxShadow !== undefined) {
    hoverClasses.push("hover:[box-shadow:var(--card-hover-shadow,0_12px_28px_rgba(0,0,0,0.18))]")
    if (hoverBoxShadow) {
      style["--card-hover-shadow"] = hoverBoxShadow
    }
  }

  if (activeTransform !== null && activeTransform !== undefined) {
    hoverClasses.push("active:[transform:var(--card-hover-active-transform,scale(0.997))]")
    if (activeTransform) {
      style["--card-hover-active-transform"] = activeTransform
    }
  }

  const className = cn(
    "rounded-ue-xl shadow-surface transition-[transform,box-shadow] duration-[var(--card-hover-duration,250ms)] ease-out",
    "will-change-transform motion-reduce:transition-[box-shadow]",
    disabled
      ? ""
      : cn(
          hoverClasses,
          "motion-reduce:hover:[transform:none] motion-reduce:active:[transform:none]"
        )
  )

  return { className, style }
}

