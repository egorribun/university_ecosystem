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

export default function AnimatedRing({
  value,
  size = 96,
  tone,
}: {
  value: number
  size?: number
  tone: "success" | "info" | "warning"
}) {
  const reduce = useReducedMotion()
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const mv = useMotionValue(reduce ? value : value)

  useEffect(() => {
    const controls = animate(mv, value, {
      duration: reduce ? 0 : motionTokens.durationLazy,
      ease: EASE_OUT_EXPO,
    })
    return () => controls.stop()
  }, [value, reduce, mv])

  const dash = useTransform(mv, (v) => c - (Math.max(0, Math.min(100, v)) / 100) * c)

  const colorClasses = {
    success: "stroke-success-text",
    info: "stroke-brand",
    warning: "stroke-warning-text",
  }

  const bgColorClasses = {
    success: "stroke-success-text/(--opacity-dim)",
    info: "stroke-brand/(--opacity-dim)",
    warning: "stroke-warning-text/(--opacity-dim)",
  }

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="block">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          className={bgColorClasses[tone]}
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          className={colorClasses[tone]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          style={{ strokeDashoffset: dash }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center font-black tracking-tighter tabular-nums lining-nums text-text-primary">
        {Math.round(value)}%
      </div>
    </div>
  )
}

export { useAnimatedNumber }
