import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"

type AxeNode = { target: string[]; html: string; failureSummary?: string }
type AxeViolation = { id: string; impact: string; nodes: AxeNode[]; help: string }
type AxeResult = { violations: AxeViolation[] }

const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../../node_modules/axe-core/axe.min.js"
)
const AXE_SOURCE = readFileSync(AXE_SOURCE_PATH, "utf-8")

const AUTH_ROUTES = [
  { path: "/dashboard", name: "dashboard" },
  { path: "/news", name: "news" },
  { path: "/schedule", name: "schedule" },
  { path: "/events", name: "events" },
  { path: "/profile", name: "profile" },
  { path: "/settings", name: "settings" },
  { path: "/activity", name: "activity" },
  { path: "/map", name: "map" },
] as const

const AXE_RUN_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] as const
const ENABLED = process.env.URL_STATE_E2E === "true"

test.describe("Authenticated routes accessibility scan", () => {
  test.skip(!ENABLED, "Requires URL_STATE_E2E=true build with VITE_LHCI=true auth bypass")

  test.beforeEach(async ({ page }) => {
    await page.addInitScript({ content: AXE_SOURCE })
  })

  // Keyboard skip-link functional test on /dashboard
  test("dashboard supports keyboard skip-link", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "skip-link test chromium-only")
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/dashboard", { waitUntil: "domcontentloaded", timeout: 30_000 })

    const skipLink = page.locator(".skip-link")
    await expect(skipLink).toBeAttached()
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.locator("#main-content")).toBeFocused()
  })

  // Keyboard focus functional test on /dashboard
  test("interactive elements have visible focus indicators", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "focus indicator test chromium-only")
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/dashboard", { waitUntil: "domcontentloaded", timeout: 30_000 })

    // Find first interactive element (a link in schedule or news card)
    const cardLink = page.locator(".vt-dash-news a, .vt-dash-schedule a").first()
    await expect(cardLink).toBeAttached()
    await cardLink.focus()
    await expect(cardLink).toBeFocused()

    await page.waitForTimeout(100)

    const focusStyles = await cardLink.evaluate((el) => {
      const style = window.getComputedStyle(el)
      return {
        boxShadow: style.boxShadow,
        outlineStyle: style.outlineStyle,
      }
    })

    const hasVisibleFocus =
      (focusStyles.boxShadow &&
        focusStyles.boxShadow !== "none" &&
        focusStyles.boxShadow !== "transparent") ||
      (focusStyles.outlineStyle &&
        focusStyles.outlineStyle !== "none" &&
        focusStyles.outlineStyle !== "transparent")

    expect(hasVisibleFocus).toBe(true)
  })

  // ARIA live regions test on /dashboard
  test("dashboard has ARIA live regions for announcements", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "live regions test chromium-only")
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/dashboard", { waitUntil: "domcontentloaded", timeout: 30_000 })

    const politeRegion = page.locator('[role="status"][aria-live="polite"].sr-only')
    await expect(politeRegion).toBeAttached()
    const assertiveRegion = page.locator('[role="alert"][aria-live="assertive"].sr-only')
    await expect(assertiveRegion).toBeAttached()
  })

  // Axe accessibility scan for each route
  for (const route of AUTH_ROUTES) {
    test(`route ${route.path} has no critical or serious axe violations`, async ({
      page,
      browserName,
    }) => {
      test.skip(
        browserName !== "chromium",
        "Axe scans chromium-only to prevent WebKit memory pressure"
      )

      await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" })
      await page.goto(route.path, { waitUntil: "domcontentloaded", timeout: 30_000 })

      await page.route("**/*", (r) => r.abort())
      await page.waitForTimeout(1500)

      const AXE_RUN_TIMEOUT_MS = 60_000
      const results = await Promise.race<AxeResult>([
        page.evaluate<AxeResult, { tags: readonly string[] }>(
          async ({ tags }) => {
            type AxeWindow = {
              axe: {
                run: (
                  context: Document,
                  options: {
                    runOnly: { type: string; values: readonly string[] }
                    rules?: Record<string, { enabled: boolean }>
                    resultTypes?: string[]
                  }
                ) => Promise<AxeResult>
              }
            }
            const { axe } = window as unknown as AxeWindow
            return axe.run(document, {
              runOnly: { type: "tag", values: tags },
              rules: {
                "color-contrast": { enabled: false },
                "color-contrast-enhanced": { enabled: false },
              },
              resultTypes: ["violations"],
            })
          },
          { tags: AXE_RUN_TAGS }
        ),
        new Promise<never>((_, reject) =>
          setTimeout(
            () => reject(new Error(`axe-run-timeout-${AXE_RUN_TIMEOUT_MS / 1000}s`)),
            AXE_RUN_TIMEOUT_MS
          )
        ),
      ])

      const blocking = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious"
      )
      expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([])
    })
  }
})
