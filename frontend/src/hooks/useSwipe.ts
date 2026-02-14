import { useRef, useCallback, type PointerEvent } from "react"

interface UseSwipeOptions {
  onSwipeLeft?: () => void
  onSwipeRight?: () => void
  threshold?: number
  timeout?: number
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

      const touchEnd = {
        x: e.clientX,
        y: e.clientY,
        time: Date.now(),
      }

      const dx = touchEnd.x - touchStart.current.x
      const dy = touchEnd.y - touchStart.current.y
      const dt = touchEnd.time - touchStart.current.time

      if (dt < timeout) {
        if (Math.abs(dx) > threshold && Math.abs(dx) > Math.abs(dy)) {
          if (dx > 0) {
            onSwipeRight?.()
          } else {
            onSwipeLeft?.()
          }
        }
      }

      touchStart.current = null
    },
    [onSwipeLeft, onSwipeRight, threshold, timeout]
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
