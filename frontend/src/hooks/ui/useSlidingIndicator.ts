import { useEffect, useState, type RefObject } from "react"

export interface IndicatorRect {
  left: number
  top: number
  width: number
  height: number
}

// Wave 124 SW1 — domAnimation-compatible replacement for framer-motion
// `layoutId` shared-element transitions. Computes the bounding rect of the
// active item (relative to its container) so an absolutely-positioned
// indicator can slide between items via CSS `transition: transform`.
//
// Usage: place an indicator div with `position: absolute` inside the
// container. Apply `transform: translate(left, top) + width/height` from
// the rect, plus a CSS transition. Mark each tab/item with `data-tab-key={key}`.
//
// Re-measures on:
//   - activeKey change
//   - window resize
//   - any item resizing (ResizeObserver per-item)
export function useSlidingIndicator(
  containerRef: RefObject<HTMLElement | null>,
  activeKey: string | null,
  attributeName = "data-tab-key"
): IndicatorRect | null {
  const [rect, setRect] = useState<IndicatorRect | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || !activeKey) {
      setRect(null)
      return
    }

    const update = () => {
      const target = container.querySelector<HTMLElement>(`[${attributeName}="${activeKey}"]`)
      if (!target) {
        setRect(null)
        return
      }
      const containerBox = container.getBoundingClientRect()
      const targetBox = target.getBoundingClientRect()
      setRect({
        left: targetBox.left - containerBox.left,
        top: targetBox.top - containerBox.top,
        width: targetBox.width,
        height: targetBox.height,
      })
    }

    update()

    // Observe each item for size changes (i18n switch, content reflow)
    const observer = new ResizeObserver(update)
    const items = container.querySelectorAll<HTMLElement>(`[${attributeName}]`)
    items.forEach((item) => observer.observe(item))
    observer.observe(container)

    window.addEventListener("resize", update)
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", update)
    }
  }, [containerRef, activeKey, attributeName])

  return rect
}
