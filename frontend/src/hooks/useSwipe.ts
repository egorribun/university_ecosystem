import { useRef, useCallback, type PointerEvent } from "react"

interface UseSwipeOptions {
  onSwipeLeft?: () => void
  onSwipeRight?: () => void
  /** Minimum distance (px) for swipe detection */
  threshold?: number
  /** Maximum time (ms) for swipe gesture */
  timeout?: number
  /** Minimum velocity (px/ms) — catches fast short swipes below threshold */
  minVelocity?: number
}

interface SwipeHandlers {
  onPointerDown: (e: PointerEvent) => void
  onPointerUp: (e: PointerEvent) => void
  onPointerCancel: (e: PointerEvent) => void
  onPointerLeave: (e: PointerEvent) => void
}

export function useSwipe({
  onSwipeLeft,
  onSwipeRight,
  threshold = 50,
  timeout = 500,
  minVelocity = 0.3,
}: UseSwipeOptions): SwipeHandlers {
  const touchStart = useRef<{ x: number; y: number; time: number } | null>(null)

  const onPointerDown = useCallback((e: PointerEvent) => {
    touchStart.current = {
      x: e.clientX,
      y: e.clientY,
      time: Date.now(),
    }
  }, [])

  const onPointerUp = useCallback(
    (e: PointerEvent) => {
      if (!touchStart.current) return

      const dx = e.clientX - touchStart.current.x
      const dy = e.clientY - touchStart.current.y
      const dt = Date.now() - touchStart.current.time

      touchStart.current = null

      // Must be primarily horizontal movement
      if (Math.abs(dx) <= Math.abs(dy)) return
      // Must be within time window
      if (dt >= timeout) return

      const velocity = dt > 0 ? Math.abs(dx) / dt : 0
      // Trigger if distance exceeds threshold OR velocity is high enough (fast short swipe)
      if (Math.abs(dx) >= threshold || velocity >= minVelocity) {
        if (dx > 0) {
          onSwipeRight?.()
        } else {
          onSwipeLeft?.()
        }
      }
    },
    [onSwipeLeft, onSwipeRight, threshold, timeout, minVelocity]
  )

  const onPointerCancel = useCallback(() => {
    touchStart.current = null
  }, [])

  const onPointerLeave = useCallback(() => {
    touchStart.current = null
  }, [])

  return {
    onPointerDown,
    onPointerUp,
    onPointerCancel,
    onPointerLeave,
  }
}
