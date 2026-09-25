import { useEffect, type RefObject } from "react"

/** Keep a sticky control below mobile browser chrome as the visual viewport moves. */
export function useVisualViewportStickyOffset(ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const element = ref.current
    const viewport = window.visualViewport
    if (!element || !viewport) return

    let frame = 0
    let previousOffset = -1
    const update = () => {
      frame = 0
      const offset = Math.max(0, Math.round(viewport.offsetTop))
      if (offset === previousOffset) return
      previousOffset = offset
      element.style.setProperty("--visual-viewport-offset-top", `${offset}px`)
    }
    const scheduleUpdate = () => {
      if (!frame) frame = window.requestAnimationFrame(update)
    }

    update()
    viewport.addEventListener("scroll", scheduleUpdate, { passive: true })
    viewport.addEventListener("resize", scheduleUpdate, { passive: true })
    window.addEventListener("scroll", scheduleUpdate, { passive: true })

    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      viewport.removeEventListener("scroll", scheduleUpdate)
      viewport.removeEventListener("resize", scheduleUpdate)
      window.removeEventListener("scroll", scheduleUpdate)
      element.style.removeProperty("--visual-viewport-offset-top")
    }
  }, [ref])
}
