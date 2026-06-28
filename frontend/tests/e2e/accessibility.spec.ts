import { expect, test, type BrowserContext, type Page } from "@playwright/test"
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
  { path: "/events", name: "events" },
  { path: "/activity", name: "activity" },
  { path: "/news", name: "news" },
  { path: "/schedule", name: "schedule" },
  { path: "/profile", name: "profile" },
  { path: "/settings", name: "settings" },
  { path: "/dashboard", name: "dashboard" },
  { path: "/map", name: "map" },
] as const

const AXE_RUN_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] as const
const ENABLED = process.env.URL_STATE_E2E === "true"

const gotoAppRoute = async (page: Page, route: string) => {
  await page.goto(route, { waitUntil: "commit", timeout: 60_000 })
  await page.locator("#main-content").waitFor({ state: "attached", timeout: 60_000 })
}

test.describe("Authenticated routes accessibility scan", () => {
  test.describe.configure({ mode: "serial" })
  test.skip(!ENABLED, "Requires URL_STATE_E2E=true build with VITE_LHCI=true auth bypass")
  test.use({ serviceWorkers: "block" })

  test.beforeEach(async ({ page }) => {
    await page.addInitScript({ content: AXE_SOURCE })
  })

  test("authenticated routes have no critical or serious axe violations", async ({
    browser,
    browserName,
  }) => {
    test.skip(browserName !== "chromium", "Axe scans chromium-only to prevent memory pressure")
    test.setTimeout(240_000)

    const openContexts: BrowserContext[] = []

    try {
      for (const route of AUTH_ROUTES) {
        const context = await browser.newContext({ serviceWorkers: "block" })
        openContexts.push(context)
        await context.addInitScript({ content: AXE_SOURCE })
        const routePage = await context.newPage()
        await routePage.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" })
        await gotoAppRoute(routePage, route.path)

        if (route.path === "/dashboard") {
          const skipLink = routePage.locator(".skip-link")
          await expect(skipLink).toBeAttached()
          await skipLink.focus()
          await expect(skipLink).toBeFocused()
          await routePage.keyboard.press("Enter")
          await expect(routePage.locator("#main-content")).toBeFocused()

          const cardLink = routePage.locator(".vt-dash-news a, .vt-dash-schedule a").first()
          await expect(cardLink).toBeAttached()
          await cardLink.focus()
          await expect(cardLink).toBeFocused()

          await routePage.waitForTimeout(100)

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

          const politeRegion = routePage.locator('[role="status"][aria-live="polite"].sr-only')
          await expect(politeRegion).toBeAttached()
          const assertiveRegion = routePage.locator('[role="alert"][aria-live="assertive"].sr-only')
          await expect(assertiveRegion).toBeAttached()
        }

        await routePage.waitForTimeout(1500)
        const AXE_RUN_TIMEOUT_MS = 60_000
        const disabledRules: Record<string, { enabled: boolean }> = {
          "color-contrast": { enabled: false },
          "color-contrast-enhanced": { enabled: false },
        }
        if (route.path === "/map") {
          // Dense geospatial pins can overlap at the current zoom; map keyboard access is tested
          // separately while this route still runs the rest of the axe WCAG rules.
          disabledRules["target-size"] = { enabled: false }
        }

        const results = await Promise.race<AxeResult>([
          routePage.evaluate<
            AxeResult,
            { tags: readonly string[]; rules: Record<string, { enabled: boolean }> }
          >(
            async ({ tags, rules }) => {
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
                rules,
                resultTypes: ["violations"],
              })
            },
            { tags: AXE_RUN_TAGS, rules: disabledRules }
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
        expect(blocking, `${route.path}: ${JSON.stringify(blocking, null, 2)}`).toEqual([])

        await context.close()
        openContexts.pop()
        await new Promise((resolve) => setTimeout(resolve, 3_000))
      }
    } finally {
      await Promise.all(openContexts.map((context) => context.close()))
    }
  })
})
