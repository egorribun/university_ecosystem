import { useCallback, useEffect, useRef, useState } from "react"

interface UseCountUpOptions {
  /** Animation duration in ms (default: 1400 — matches prior spring overdamp) */
  durationMs?: number
  /** Whether to disable animation (e.g. reduced motion) */
  disabled?: boolean
}

/**
 * useCountUp — Animated number counter (Wave 48, refactored Wave 124 SW1)
 *
 * Counts from 0 to `target` when the element enters the viewport.
 * Uses requestAnimationFrame with easeOutCubic for natural deceleration —
 * matches the prior overdamped spring (stiffness 80 / damping 25) UX.
 * Fires once per mount. Respects reduced motion via `disabled`.
 * React Compiler safe — no ref access during render.
 *
 * Wave 124 SW1: removed framer-motion useMotionValue/useSpring deps so
 * this hook works under LazyMotion+domAnimation strict mode (those hooks
 * require domMax). Pure rAF + cubic-bezier easing.
 */
export function useCountUp(target: number, options: UseCountUpOptions = {}) {
  const { durationMs = 1400, disabled = false } = options

  const elRef = useRef<HTMLElement | null>(null)
  const [hasBeenSeen, setHasBeenSeen] = useState(false)

  // Ref callback — React Compiler safe (no .current access during render)
  const ref = useCallback((node: HTMLElement | null) => {
    elRef.current = node
  }, [])

  // IntersectionObserver instead of useInView (avoids ref.current read during render)
  useEffect(() => {
    const el = elRef.current
    if (!el || hasBeenSeen) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setHasBeenSeen(true)
          observer.disconnect()
        }
      },
      { rootMargin: "0px 0px -40px 0px" }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [hasBeenSeen])

  const [value, setValue] = useState(disabled ? target : 0)

  useEffect(() => {
    if (disabled) {
      setValue(target)
      return
    }
    if (!hasBeenSeen) return

    let raf = 0
    let start = 0
    const from = 0
    const delta = target - from

    const tick = (now: number) => {
      if (start === 0) start = now
      const elapsed = now - start
      const progress = Math.min(elapsed / durationMs, 1)
      // easeOutCubic — matches prior overdamped spring perception
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(from + delta * eased))
      if (progress < 1) raf = requestAnimationFrame(tick)
    }

    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [hasBeenSeen, target, disabled, durationMs])

  return { ref, value }
}
