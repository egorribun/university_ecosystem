import type { Page, Route } from "@playwright/test"
import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

// R49 (ТЗ §10): empty dashboard blocks must not reserve extra vertical space.
// The schedule, news and events cards are mocked with empty payloads. The
// gap between consecutive cards must not exceed the grid gap (plus 1 px):
// stacked cards are measured on the vertical axis, side-by-side cards on the
// horizontal axis.

const EMPTY_LIST_PATH = /\/api\/(?:v1\/)?(schedule|news|events)\/?$/u

const DASHBOARD_CARD_SELECTORS = [".vt-dash-schedule", ".vt-dash-news", ".vt-dash-events"] as const

async function mockEmptyDashboardLists(page: Page): Promise<void> {
  // Registered after useMockApi, so this handler runs first and falls back
  // to the shared mock for every other request.
  await page.route("**/*", async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() !== "GET" || !EMPTY_LIST_PATH.test(url.pathname)) {
      await route.fallback()
      return
    }
    const isEvents = /\/events\/?$/u.test(url.pathname)
    const body = /\/news\/?$/u.test(url.pathname)
      ? { items: [], has_more: false, next_cursor: null }
      : isEvents
        ? {
            items: [],
            total: 0,
            limit: 12,
            cursor: null,
            next_cursor: null,
            has_more: false,
          }
        : []
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    })
  })
}

async function waitForEmptyCardsLoaded(page: Page): Promise<void> {
  for (const selector of DASHBOARD_CARD_SELECTORS) {
    await expect(page.locator(selector)).toHaveAttribute("aria-busy", "false", { timeout: 30_000 })
  }
}

type CardGap = {
  pair: string
  axis: "horizontal" | "vertical"
  gap: number
  allowed: number
}

async function measureCardGaps(page: Page): Promise<CardGap[]> {
  return page.evaluate(
    (selectors) => {
      const cards = selectors.map((selector) => {
        const element = document.querySelector<HTMLElement>(selector)
        if (!element) throw new Error(`Missing dashboard card ${selector}`)
        // Each card sits in a grid cell wrapper; measure that cell.
        const cell = element.parentElement ?? element
        return { selector, cell, box: cell.getBoundingClientRect() }
      })
      const grid = cards[0]?.cell.parentElement
      if (!grid) throw new Error("Dashboard card grid not found")
      const style = getComputedStyle(grid)
      const rowGap = parseFloat(style.rowGap) || 0
      const columnGap = parseFloat(style.columnGap) || 0

      const gaps: CardGap[] = []
      for (let index = 0; index < cards.length - 1; index += 1) {
        const current = cards[index]
        const next = cards[index + 1]
        if (!current || !next) continue
        const pair = `${current.selector} -> ${next.selector}`
        const a = current.box
        const b = next.box
        if (b.top >= a.bottom - 1) {
          gaps.push({ pair, axis: "vertical", gap: b.top - a.bottom, allowed: rowGap + 1 })
        } else if (b.left >= a.right - 1) {
          gaps.push({ pair, axis: "horizontal", gap: b.left - a.right, allowed: columnGap + 1 })
        } else {
          gaps.push({ pair, axis: "vertical", gap: Number.NaN, allowed: rowGap + 1 })
        }
      }
      return gaps
    },
    [...DASHBOARD_CARD_SELECTORS]
  )
}

const VIEWPORTS = [
  { width: 390, height: 844, label: "390" },
  { width: 768, height: 1024, label: "768" },
  { width: 1440, height: 900, label: "1440" },
] as const

test.describe("Dashboard empty card spacing", () => {
  for (const viewport of VIEWPORTS) {
    test(`empty schedule, news and events do not reserve extra space at ${viewport.label}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
      await useMockApi(page, { authenticated: true })
      await mockEmptyDashboardLists(page)

      await page.goto("/dashboard", { waitUntil: "domcontentloaded" })
      await page.waitForFunction(() => window.__APP_HYDRATED === true, null, { timeout: 15_000 })
      await page.waitForURL(/\/dashboard$/u)
      await waitForEmptyCardsLoaded(page)

      // Layout can settle after the cascade; poll until the measured gaps are stable.
      await expect(async () => {
        const gaps = await measureCardGaps(page)
        expect(gaps).toHaveLength(DASHBOARD_CARD_SELECTORS.length - 1)
        for (const gap of gaps) {
          expect(Number.isNaN(gap.gap), `${gap.pair} must not overlap`).toBe(false)
          expect(gap.gap, `${gap.pair} ${gap.axis} gap`).toBeLessThanOrEqual(gap.allowed)
        }
      }).toPass({ timeout: 15_000 })
    })
  }
})
