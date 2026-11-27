import { useState, useCallback, useEffect, useRef } from "react"

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
    onTouchEnd: (e: React.TouchEvent) => void
    onTouchCancel: () => void
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

  const onTouchCancel = useCallback(() => {
    setDragOffset(0)
    setIsDragging(false)
  }, [])

  // A drawer may close from Escape or its close button before touchend arrives.
  // Clear the transient gesture so reopening cannot reuse the old drag offset.
  useEffect(() => {
    if (!enabled) {
      onTouchCancel()
    }
  }, [enabled, onTouchCancel])

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (!enabled) return
      if (e.touches.length > 1) {
        onTouchCancel()
        return
      }
      const touch = e.touches[0]
      if (!touch) return
      startX.current = touch.clientX
      setIsDragging(true)
    },
    [enabled, onTouchCancel]
  )

  const onTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!enabled || !isDragging) return
      if (e.touches.length > 1) {
        onTouchCancel()
        return
      }
      const touch = e.touches[0]
      if (!touch) return
      const delta = touch.clientX - startX.current
      // Only allow movement in the close direction
      if (direction === "right" && delta > 0) {
        setDragOffset(delta)
      } else if (direction === "left" && delta < 0) {
        setDragOffset(delta)
      } else {
        // Returning to the start or reversing direction cancels the swipe.
        setDragOffset(0)
      }
    },
    [enabled, isDragging, direction, onTouchCancel]
  )

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const absOffset = Math.abs(dragOffset)
      if (enabled && e.touches.length === 0 && absOffset > threshold) {
        onSwipeClose()
      }
      onTouchCancel()
    },
    [enabled, dragOffset, threshold, onSwipeClose, onTouchCancel]
  )

  return {
    dragOffset,
    isDragging,
    handlers: { onTouchStart, onTouchMove, onTouchEnd, onTouchCancel },
  }
}
