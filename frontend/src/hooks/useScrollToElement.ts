/**
 * useScrollToElement — Scroll to an element once when its ID becomes available.
 * Extracted from Schedule.tsx scroll-to-current-lesson pattern (FIX-68-06).
 *
 * Fires once per mount (or when elementId changes from null → valid).
 * Uses requestAnimationFrame for layout stability.
 */
import { useRef, useEffect } from "react"

export function useScrollToElement(
  elementId: string | null,
  { behavior = "smooth", block = "center" }: ScrollIntoViewOptions = {},
) {
  const scrolledRef = useRef(false)

  // Reset when elementId changes to a new target
  useEffect(() => {
    scrolledRef.current = false
  }, [elementId])

  useEffect(() => {
    if (!elementId || scrolledRef.current) return
    scrolledRef.current = true
    requestAnimationFrame(() => {
      document.getElementById(elementId)?.scrollIntoView({ behavior, block })
    })
  }, [elementId, behavior, block])
}
