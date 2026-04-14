import { useState, useCallback, useRef } from "react"

interface SwipeGestureOptions {
  /** Direction that triggers close */
  direction: "left" | "right"
  /** Minimum distance in px to trigger close (default: 80) */
  threshold?: number
  /** Callback when swipe exceeds threshold */
  onSwipeClose: () => void
  /** Whether gesture is active */
  enabled: boolean
}

interface SwipeGestureResult {
  /** Current drag offset in px (0 when not dragging) */
  dragOffset: number
  /** Whether currently dragging */
  isDragging: boolean
  /** Event handlers to spread on the swipeable element */
  handlers: {
    onTouchStart: (e: React.TouchEvent) => void
    onTouchMove: (e: React.TouchEvent) => void
    onTouchEnd: () => void
  }
}

/**
 * Lightweight touch-based swipe gesture hook.
 * Uses raw touch events for drawer close gesture.
 */
export function useSwipeGesture({
  direction,
  threshold = 80,
  onSwipeClose,
  enabled,
}: SwipeGestureOptions): SwipeGestureResult {
  const [dragOffset, setDragOffset] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef(0)

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (!enabled) return
      startX.current = e.touches[0].clientX
      setIsDragging(true)
    },
    [enabled]
  )

  const onTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!enabled || !isDragging) return
      const delta = e.touches[0].clientX - startX.current
      // Only allow movement in the close direction
      if (direction === "right" && delta > 0) {
        setDragOffset(delta)
      } else if (direction === "left" && delta < 0) {
        setDragOffset(delta)
      }
    },
    [enabled, isDragging, direction]
  )

  const onTouchEnd = useCallback(() => {
    if (!enabled) return
    const absOffset = Math.abs(dragOffset)
    if (absOffset > threshold) {
      onSwipeClose()
    }
    setDragOffset(0)
    setIsDragging(false)
  }, [enabled, dragOffset, threshold, onSwipeClose])

  return {
    dragOffset,
    isDragging,
    handlers: { onTouchStart, onTouchMove, onTouchEnd },
  }
}
