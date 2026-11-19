/** Numeric-only snapshot, evaluated inside the Events page. */
export function collectEventsGeometry(link: Element) {
  const selected = link.closest('[data-testid="event-card"]')
  const grid = selected?.closest("#events-tabpanel > .grid")
  const view = link.ownerDocument.defaultView
  if (!selected || !grid || !view) return null
  const cards = Array.from(grid.querySelectorAll('[data-testid="event-card"]'))
  const selectedIndex = cards.indexOf(selected)
  if (selectedIndex < 0 || selectedIndex >= 100 || cards.length > 100) return null
  return {
    viewportWidth: Math.round(view.innerWidth),
    viewportHeight: Math.round(view.innerHeight),
    documentHeight: Math.round(link.ownerDocument.documentElement.scrollHeight),
    scrollY: Math.round(view.scrollY),
    gridTop: Math.round(grid.getBoundingClientRect().top),
    linkTop: Math.round(link.getBoundingClientRect().top),
    linkHeight: Math.round(link.getBoundingClientRect().height),
    selectedIndex,
    cardCount: cards.length,
    heights: cards.slice(0, 12).map((card) => Math.round(card.getBoundingClientRect().height)),
  }
}
import type { Locator } from "@playwright/test"

export async function sampleEventsGeometry(
  eventLink: Pick<Locator, "evaluate">,
  timeoutMs: number
) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 500) return null
  const deadlineAtMs = performance.now() + timeoutMs
  let timer: ReturnType<typeof setTimeout> | undefined
  // As with the password-forgot diagnostic, timeout ends our wait only. The
  // read-only evaluation keeps a rejection handler and cannot emit a late record.
  const pending = Promise.resolve()
    .then(() => {
      if (performance.now() >= deadlineAtMs) return null
      return eventLink.evaluate(collectEventsGeometry, undefined, { timeout: 500 })
    })
    .catch(() => null)
  try {
    return await Promise.race([
      pending,
      new Promise<null>((resolve) => {
        timer = setTimeout(() => resolve(null), timeoutMs)
      }),
    ])
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}
