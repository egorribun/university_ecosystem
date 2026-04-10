import { useEffect, useState, useMemo } from "react"
import { motion, useMotionValue, useTransform, animate, useReducedMotion } from "framer-motion"
import { EASE_OUT_EXPO } from "./activityTypes"
import { motion as motionTokens } from "@/theme/tokens"

function useAnimatedNumber(target: number, duration = motionTokens.durationLazy, fraction = 0) {
  const reduce = useReducedMotion()
  const mv = useMotionValue(reduce ? target : 0)
  const [val, setVal] = useState<number>(reduce ? target : 0)
  useEffect(() => {
    const controls = animate(mv, target, { duration: reduce ? 0 : duration, ease: EASE_OUT_EXPO })
    const unsubscribe = mv.on("change", (value: number) => setVal(value))
    return () => {
      controls.stop()
      unsubscribe()
    }
  }, [target, duration, reduce, mv])
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
}

export default function AnimatedRing({
  value,
  max = 100,
  mode = "percent",
  size = 96,
  colorVar,
  fraction,
}: AnimatedRingProps) {
  const reduce = useReducedMotion()
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r

  // Compute fill percentage based on mode
  const fillPercent = useMemo(() => {
    if (mode === "percent") return Math.max(0, Math.min(100, value))
    if (mode === "gauge") return max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
    // count mode: fill is value/max (goal)
    return max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  }, [mode, value, max])

  const mv = useMotionValue(reduce ? fillPercent : 0)

  useEffect(() => {
    const controls = animate(mv, fillPercent, {
      duration: reduce ? 0 : motionTokens.durationLazy,
      ease: EASE_OUT_EXPO,
    })
    return () => controls.stop()
  }, [fillPercent, reduce, mv])

  const dash = useTransform(mv, (v) => c - (Math.max(0, Math.min(100, v)) / 100) * c)

  // Determine fraction digits for inner text
  const displayFraction = fraction ?? (mode === "gauge" ? 1 : 0)

  // Inner label text
  const innerLabel = useMemo(() => {
    if (mode === "percent") return `${Math.round(value)}%`
    if (mode === "gauge") return `${Number(value).toFixed(displayFraction)}`
    return `${Math.round(value)}`
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
  const bgStrokeColor = `color-mix(in srgb, ${strokeColor} 15%, transparent)`

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="block">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={bgStrokeColor}
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={strokeColor}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          style={{ strokeDashoffset: dash }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-black tracking-tighter tabular-nums lining-nums text-text-primary leading-none">
          {innerLabel}
        </span>
        {subLabel && (
          <span className="text-[0.6em] text-text-secondary leading-none">{subLabel}</span>
        )}
      </div>
    </div>
  )
}

export { useAnimatedNumber }
