/**
 * Global Scroll Utilities
 * Decouples DOM manipulation from UI components.
 */

export function getScrollRoot(): HTMLElement {
  const isScrollable = (element: HTMLElement) => {
    const overflowY = getComputedStyle(element).overflowY
    return (
      (overflowY === "auto" || overflowY === "scroll") &&
      element.scrollHeight > element.clientHeight
    )
  }

  // A layout marker is only an owner when it actually owns scrolling.
  const root = document.querySelector<HTMLElement>("[data-scroll-root]")
  if (root && isScrollable(root)) return root

  // Legacy/Safety fallback search
  const candidates = [
    document.querySelector("main"),
    document.scrollingElement,
    document.documentElement,
    document.body,
  ]

  for (const el of candidates) {
    if (!el) continue
    const e = el as HTMLElement
    if (isScrollable(e)) return e
  }

  return (document.scrollingElement || document.documentElement) as HTMLElement
}

export function smoothToTop(target: HTMLElement, behavior: ScrollBehavior = "smooth") {
  try {
    target.scrollTo({ top: 0, behavior })
  } catch {
    if (behavior === "auto") {
      target.scrollTop = 0
      return
    }
    const start = target.scrollTop
    const duration = 420
    let t0 = 0
    const step = (ts: number) => {
      if (!t0) t0 = ts
      const p = Math.min(1, (ts - t0) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      target.scrollTop = Math.round(start * (1 - eased))
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }
}

export function markIfFromBottom() {
  const el = getScrollRoot()
  const threshold = 24
  const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - threshold
  if (nearBottom) sessionStorage.setItem("__scrollTopNext", "1")
}
