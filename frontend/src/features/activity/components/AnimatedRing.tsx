import { useMemo, type CSSProperties } from "react"
import { motion as motionTokens } from "@/theme/tokens"
import { useAnimatedFloat } from "@/hooks/useAnimatedFloat"

// Wave 124 SW1 — Refactored from framer-motion useMotionValue/useTransform/
// animate (require domMax) to shared rAF helper in @/hooks/useAnimatedFloat.
// Same easeOutExpo formula + same durationLazy (0.9s) as the prior framer
// animate() call. UX-equivalent. useReducedMotion handled inside the helper.
function useAnimatedNumber(
  target: number,
  duration: number = motionTokens.durationLazy,
  fraction = 0
) {
  const val = useAnimatedFloat(target, duration)
  return useMemo(() => Number(val).toFixed(fraction), [val, fraction])
}

type AnimatedRingMode = "percent" | "gauge" | "count"

type AnimatedRingProps = {
  /** Current value */
  value: number
  /** Maximum value (used by gauge/count modes to calculate fill %) */
  max?: number
  /** Display mode: percent (default), gauge (value/max), count (raw number) */
  mode?: AnimatedRingMode
  /** Ring diameter in px */
  size?: number
  /** CSS color for the ring stroke — uses --_ring-color CSS variable */
  colorVar?: string
  /** Fraction digits for inner label */
  fraction?: number
  /** Accessible label for the SVG gauge (WCAG) */
  ariaLabel?: string
}

const RING_STROKE_WIDTH = 8

export default function AnimatedRing({
  value,
  max = 100,
  mode = "percent",
  size = 96,
  colorVar,
  fraction,
  ariaLabel,
}: AnimatedRingProps) {
  const stroke = RING_STROKE_WIDTH
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r

  // Compute fill percentage based on mode
  const fillPercent = useMemo(() => {
    if (mode === "percent") return Math.max(0, Math.min(100, value))
    if (mode === "gauge") return max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
    // count mode: fill is value/max (goal)
    return max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  }, [mode, value, max])

  const animatedFillPercent = useAnimatedFloat(fillPercent, motionTokens.durationLazy)
  const dash = c - (Math.max(0, Math.min(100, animatedFillPercent)) / 100) * c

  // Determine fraction digits for inner text
  const displayFraction = fraction ?? (mode === "gauge" ? 1 : 0)

  // Inner label text — NaN guard (M6)
  const innerLabel = useMemo(() => {
    const safe = Number.isFinite(value) ? value : 0
    if (mode === "percent") return `${Math.round(safe)}%`
    if (mode === "gauge") return `${safe.toFixed(displayFraction)}`
    return `${Math.round(safe)}`
  }, [mode, value, displayFraction])

  // Sub-label (below number) for gauge mode
  const subLabel = useMemo(() => {
    if (mode === "gauge") {
      const maxDisplay = max === 4 ? "4.0" : String(max)
      return `/ ${maxDisplay}`
    }
    return null
  }, [mode, max])

  const strokeColor = colorVar ?? "var(--activity-present-accent)"

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size, "--_ring-color": strokeColor } as CSSProperties}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="block"
        role="img"
        aria-label={ariaLabel}
      >
        <circle
          className="activity-ring-track"
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={strokeColor}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={dash}
        />
      </svg>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center"
        style={{ fontSize: Math.round(size * 0.17) }}
      >
        <span className="font-black tracking-tighter tabular-nums lining-nums text-text-primary leading-none">
          {innerLabel}
        </span>
        {subLabel && (
          <span className="text-[0.55em] text-text-secondary leading-none">{subLabel}</span>
        )}
      </div>
    </div>
  )
}

export { useAnimatedNumber }
