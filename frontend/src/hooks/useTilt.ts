import { useCallback, useEffect, useRef, type CSSProperties, type RefCallback } from "react"

interface UseTiltOptions {
  /** Maximum tilt angle in degrees (default: 6) */
  max?: number
  /** Scale on hover (default: 1.02) */
  scale?: number
  /** Whether tilt is disabled (e.g. reduced motion) */
  disabled?: boolean
}

interface UseTiltReturn {
  ref: RefCallback<HTMLElement>
  style: CSSProperties
  onMouseMove: (e: React.MouseEvent) => void
  onMouseLeave: () => void
}

/**
 * useTilt — 3D perspective tilt effect on hover (Wave 46)
 *
 * Tracks mouse position relative to element center and outputs
 * rotateX/Y values. GPU-composited via will-change: transform.
 * Respects prefers-reduced-motion when disabled=true.
 */
export function useTilt(options: UseTiltOptions = {}): UseTiltReturn {
  const { max = 6, scale = 1.02, disabled = false } = options
  const elRef = useRef<HTMLElement | null>(null)
  const rafRef = useRef<number>(0)

  const ref: RefCallback<HTMLElement> = useCallback((node) => {
    elRef.current = node
  }, [])

  // Cleanup pending rAF on unmount
  useEffect(() => {
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (disabled || !elRef.current) return

      // Extract coords before rAF — synthetic event may be recycled (H-1 fix)
      const { clientX, clientY } = e

      cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(() => {
        const el = elRef.current
        if (!el) return

        const rect = el.getBoundingClientRect()
        const centerX = rect.left + rect.width / 2
        const centerY = rect.top + rect.height / 2

        // Normalize to [-1, 1]
        const normX = (clientX - centerX) / (rect.width / 2)
        const normY = (clientY - centerY) / (rect.height / 2)

        // Clamp
        const clampedX = Math.max(-1, Math.min(1, normX))
        const clampedY = Math.max(-1, Math.min(1, normY))

        // rotateY = horizontal movement, rotateX = vertical (inverted)
        const rotateY = clampedX * max
        const rotateX = -clampedY * max

        el.style.transform = `perspective(800px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) scale3d(${scale}, ${scale}, 1)`
      })
    },
    [disabled, max, scale]
  )

  const onMouseLeave = useCallback(() => {
    if (disabled || !elRef.current) return
    cancelAnimationFrame(rafRef.current)
    elRef.current.style.transform = ""
  }, [disabled])

  const style: CSSProperties = disabled
    ? {}
    : {
        willChange: "transform",
        transition: "transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
      }

  return { ref, style, onMouseMove, onMouseLeave }
}
