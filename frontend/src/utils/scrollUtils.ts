/**
 * Global Scroll Utilities
 * Decouples DOM manipulation from UI components.
 */

export function getScrollRoot(): HTMLElement {
  // Use explicit scroll root if defined, otherwise fallback to document defaults
  const root = document.querySelector<HTMLElement>("[data-scroll-root]")
  if (root) return root

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
    const oy = getComputedStyle(e).overflowY
    const scrollable = (oy === "auto" || oy === "scroll") && e.scrollHeight > e.clientHeight
    if (scrollable) return e
  }

  return (document.scrollingElement || document.documentElement) as HTMLElement
}

export function smoothToTop(target: HTMLElement) {
  try {
    target.scrollTo({ top: 0, behavior: "smooth" })
  } catch {
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
