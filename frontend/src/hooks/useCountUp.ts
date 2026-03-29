import { useCallback, useEffect, useRef, useState } from "react"
import { useMotionValue, useSpring } from "framer-motion"

interface UseCountUpOptions {
  /** Spring stiffness — lower = slower count (default: 80) */
  stiffness?: number
  /** Spring damping — higher = less bounce (default: 25) */
  damping?: number
  /** Whether to disable animation (e.g. reduced motion) */
  disabled?: boolean
}

/**
 * useCountUp — Animated number counter (Wave 48)
 *
 * Counts from 0 to `target` when the element enters the viewport.
 * Uses Framer Motion spring physics for natural deceleration.
 * Fires once per mount. Respects reduced motion via `disabled`.
 * React Compiler safe — no ref access during render.
 */
export function useCountUp(target: number, options: UseCountUpOptions = {}) {
  const { stiffness = 80, damping = 25, disabled = false } = options

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
        if (entry.isIntersecting) {
          setHasBeenSeen(true)
          observer.disconnect()
        }
      },
      { rootMargin: "0px 0px -40px 0px" }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [hasBeenSeen])

  const motionValue = useMotionValue(0)
  const springValue = useSpring(motionValue, { stiffness, damping })

  const [value, setValue] = useState(disabled ? target : 0)
  useEffect(() => {
    const unsubscribe = springValue.on("change", (v) => setValue(Math.round(v)))
    return unsubscribe
  }, [springValue])

  useEffect(() => {
    if (disabled) {
      motionValue.set(target)
      return
    }
    if (hasBeenSeen) {
      motionValue.set(target)
    }
  }, [hasBeenSeen, target, disabled, motionValue])

  return { ref, value }
}
