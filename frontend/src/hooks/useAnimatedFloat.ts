import { useEffect, useRef, useState } from "react"
import useMediaQuery from "@/hooks/useMediaQuery"

// Wave 124 SW1 — Shared rAF-based numeric animation helper. Replaces
// framer-motion useMotionValue + useSpring + animate (which require domMax
// and pull ~5-7 KB of motion-values runtime). Used by AnimatedRing,
// AttendanceCard, and any other component that needs to smoothly transition
// a numeric value with easeOutExpo.
//
// The closed-form `1 - 2^(-10*t)` approximates the cubic-bezier
// `[0.16, 1, 0.3, 1]` (EASE_OUT_EXPO) UX-equivalently. Single rAF loop +
// one re-render per frame — no MotionValue runtime needed.
//
// Wave 190 SW4 — migrated from framer-motion's `useReducedMotion()` (jsdom-
// incompat per W184 SW6 Gotcha — framer-motion's `initPrefersReducedMotion`
// touches `window.matchMedia(...).addEventListener` through a code path
// jsdom's polyfill doesn't fully cover, producing TypeError as vitest
// unhandled errors in components that mount useAnimatedFloat consumers like
// AnimatedRing + AttendanceCard) to project's `useMediaQuery` DEFAULT export
// (jsdom-safe via setupTests.ts matchMedia polyfill + typeof-check fallback
// at useMediaQuery.ts:50-53). Behavior identical: both return a reactive
// boolean. The W124 SW1 note about "useReducedMotion remains in domAnimation
// set" is now superseded.
export const easeOutExpo = (t: number): number => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t))

export function useAnimatedFloat(target: number, durationSeconds: number): number {
  const reduce = useMediaQuery("(prefers-reduced-motion: reduce)")
  const [val, setVal] = useState<number>(reduce ? target : 0)
  const valRef = useRef<number>(reduce ? target : 0)

  useEffect(() => {
    if (reduce) {
      setVal(target)
      valRef.current = target
      return
    }
    let raf = 0
    let start = 0
    const from = valRef.current
    const delta = target - from
    const durationMs = durationSeconds * 1000

    const tick = (now: number) => {
      if (start === 0) start = now
      const progress = Math.min((now - start) / durationMs, 1)
      const next = from + delta * easeOutExpo(progress)
      valRef.current = next
      setVal(next)
      if (progress < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, durationSeconds, reduce])

  return val
}
