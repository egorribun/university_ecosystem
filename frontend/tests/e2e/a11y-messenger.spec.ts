import { blockBackgroundNetwork, expect, test } from "./test"
import type { Locator, Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"

import { useMockApi } from "./utils/mockApi"

/**
 * Messenger-page accessibility scan — Wave 182 SW5 / closes W181 gap item #8.
 *
 * Adapts the W147 SW2 axe-on-chromium-headless structural pattern from
 * `a11y-public.spec.ts` (page.addInitScript pre-injection + background
 * traffic quiescing post-goto + Promise.race timeout wrapper) to
 * authenticated /messenger.
 *
 * **Required environment**: `URL_STATE_E2E=true` (Wave 121 SW3 / Wave 122 SW3
 * pattern). Sets `cross-env VITE_LHCI=true npm run build` for the auto-managed
 * webServer dist, which activates the W126 SW4 auth-at-edge bypass for the
 * LHCI mock user. Without this flag, /messenger redirects to /login at the
 * route guard (W128 SW2 `_auth.tsx` beforeLoad) and the test fails before
 * axe sees the messenger DOM. Single command:
 *
 *     URL_STATE_E2E=true npx playwright test --project=chromium \
 *       tests/e2e/a11y-messenger.spec.ts
 *
 * Coverage: /messenger (list view) under light + dark theme × chromium only.
 * WebKit + Firefox + mobile-webkit skipped per W115 SW1 + W116 SW1 baseline
 * (axe-core injection memory pressure on those projects).
 *
 * The mock user has 0 contacts / 0 chats / 0 messages so the empty-state +
 * MessengerBackdrop + i18n hero-text are what axe scans. ContactList +
 * ChatWindow + TypingIndicator render paths are NOT exercised here (Docker
 * chain scope per W181 NEW caveat #2 carry-forward).
 *
 * Closes: W181 honest gap list item #8 (axe-core a11y scan on /messenger).
 */

type AxeNode = {
  target: string[]
  html: string
  failureSummary?: string
  any?: {
    data?: {
      contrastRatio?: number
      expectedContrastRatio?: number | string
      fgColor?: string
      bgColor?: string
    }
  }[]
  semantic?: { tag: string | null; role: string | null }
}
type AxeImpact = "minor" | "moderate" | "serious" | "critical"
type AxeViolation = { id: string; impact: AxeImpact; nodes: AxeNode[]; help: string }
type AxeResult = { violations: AxeViolation[] }

// Mirror axe-core source resolution from a11y-public.spec.ts.
const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../../node_modules/axe-core/axe.min.js"
)
const AXE_SOURCE = readFileSync(AXE_SOURCE_PATH, "utf-8")

const THEMES = [
  { scheme: "light" as const, name: "light" },
  { scheme: "dark" as const, name: "dark" },
] as const

const AXE_RUN_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] as const
const AXE_RUN_TIMEOUT_MS = 60_000

const R32_VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
] as const
const R32_INTERACTIVE =
  'button, input, textarea, select, a[href], [role="button"], [role="link"], [role="tab"], [role="option"]'

async function assertR32NoOverflow(page: Page, region: string) {
  const geometry = await page.evaluate(() => ({
    viewport: innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }))
  expect(geometry.document, `${region}: document width`).toBeLessThanOrEqual(geometry.viewport)
  expect(geometry.body, `${region}: body width`).toBeLessThanOrEqual(geometry.viewport)
}

async function assertR32Targets(targets: Locator, region: string) {
  const geometry = await targets.evaluateAll((elements) =>
    elements.flatMap((element) => {
      const style = getComputedStyle(element)
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        element.getClientRects().length === 0
      ) {
        return []
      }
      const rect = element.getBoundingClientRect()
      return [
        {
          tag: element.tagName.toLowerCase(),
          role: element.getAttribute("role"),
          width: rect.width,
          height: rect.height,
        },
      ]
    })
  )
  expect(geometry.length, `${region}: visible targets`).toBeGreaterThan(0)
  expect(
    geometry.filter(({ width, height }) => width < 44 || height < 44),
    `${region}: targets must be at least 44x44 CSS pixels`
  ).toEqual([])
}

function safeR32Color(value: unknown) {
  if (typeof value !== "string" || value.length > 40) return null
  return /^#[a-f0-9]{3,8}$/i.test(value) || /^rgba?\([0-9., %]+\)$/i.test(value) ? value : null
}

async function assertR32Axe(page: Page, region: string) {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const result = await Promise.race<AxeResult>([
      page.evaluate<AxeResult, { tags: readonly string[] }>(
        async ({ tags }) => {
          const { axe } = window as unknown as {
            axe: {
              run: (
                context: Document,
                options: {
                  runOnly: { type: string; values: readonly string[] }
                  resultTypes: string[]
                }
              ) => Promise<AxeResult>
            }
          }
          const result = await axe.run(document, {
            runOnly: { type: "tag", values: tags },
            resultTypes: ["violations"],
          })
          for (const violation of result.violations) {
            for (const node of violation.nodes) {
              try {
                const selector = node.target[0]
                const element =
                  typeof selector === "string" ? document.querySelector(selector) : null
                const tag = element?.tagName.toLowerCase() ?? null
                const role = element?.getAttribute("role") ?? null
                node.semantic = {
                  tag:
                    tag && ["button", "span", "p", "input", "a", "div"].includes(tag) ? tag : null,
                  role:
                    role && ["button", "tab", "status", "option", "dialog"].includes(role)
                      ? role
                      : null,
                }
              } catch {
                node.semantic = { tag: null, role: null }
              }
            }
          }
          return result
        },
        { tags: AXE_RUN_TAGS }
      ),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("R32 axe scan timed out")), AXE_RUN_TIMEOUT_MS)
      }),
    ])
    const blocking = result.violations
      .filter((violation) => violation.impact === "critical" || violation.impact === "serious")
      .map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        nodes: violation.nodes.map((node) => ({
          semantic: node.semantic ?? null,
          target: node.target.map((selector) => {
            const allowed =
              "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:# >+~(),-[]\\/"
            return selector.length > 0 &&
              selector.length <= 256 &&
              !selector.includes("://") &&
              [...selector].every((character) => allowed.includes(character))
              ? selector
              : "[redacted]"
          }),
          contrast: (node.any ?? []).flatMap(({ data }) => {
            const ratio = data?.contrastRatio
            const expected = data?.expectedContrastRatio
            if (typeof ratio !== "number" || !Number.isFinite(ratio)) return []
            return [
              {
                ratio,
                fg: safeR32Color(data?.fgColor),
                bg: safeR32Color(data?.bgColor),
                expected:
                  typeof expected === "number" && Number.isFinite(expected)
                    ? expected
                    : typeof expected === "string" &&
                        expected.length <= 16 &&
                        expected.endsWith(":1") &&
                        Number.isFinite(Number(expected.slice(0, -2))) &&
                        Number(expected.slice(0, -2)) > 0
                      ? expected
                      : null,
              },
            ]
          }),
        })),
      }))
    expect(blocking, `${region}: serious and critical axe violations`).toEqual([])
  } finally {
    if (timer) clearTimeout(timer)
  }
}

// Skip outside URL_STATE_E2E mode — /messenger requires auth + the default
// non-LHCI Playwright webServer (5173) renders /login redirect, not the
// messenger DOM we want axe to scan. The CI workflow + local invocation
// both set URL_STATE_E2E=true; this guard prevents accidental green runs
// under the default config that don't actually exercise the route.
const URL_STATE_E2E_ACTIVE = process.env.URL_STATE_E2E === "true"

test.describe("@a11y messenger route axe scan", () => {
  test.skip(
    !URL_STATE_E2E_ACTIVE,
    "Requires URL_STATE_E2E=true (W121 SW3 + W122 SW3 mode) to build with VITE_LHCI=true auth bypass — /messenger is auth-gated under default config."
  )
  // Preserve the existing Chromium-only axe boundary for every case in this suite.
  test.skip(
    ({ browserName }) => browserName !== "chromium",
    "Messenger axe scan chromium-only — WebKit + Firefox memory pressure per W115/W116 baseline."
  )

  test.beforeEach(async ({ page }) => {
    await page.addInitScript({ content: AXE_SOURCE })
  })

  for (const theme of THEMES) {
    test(`messenger — ${theme.name} theme has no critical/serious axe violations`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme: theme.scheme, reducedMotion: "reduce" })
      await page.goto("/messenger", { waitUntil: "domcontentloaded", timeout: 30_000 })

      // W148 SW3 pattern — quiesce background API/realtime traffic so React
      // Query retries / SW workbox don't starve the event loop and prevent
      // axe.run from scheduling, without cancelling pending application
      // chunks. The DOM tree axe scans is already rendered post-goto.
      await blockBackgroundNetwork(page)

      // Framer Motion entrance animations + React Query observers settle.
      // Under `reducedMotion: "reduce"` + MotionConfig `reducedMotion="user"`
      // (W127 SW1) animations snap to end-state. Per a11y-public.spec.ts.
      await page.waitForTimeout(1500)

      // Promise.race timeout wrapper per W147 SW2 — `axe.run()` can hang
      // mid-scan on heavy DOM (different from injection hang).
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
              // Disable color-contrast rules (Lighthouse owns those per
              // W116 SW3 + W147 SW2 rationale).
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

  test("@R32-pointer disconnected status does not block the new-chat button", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false })
    })
    await useMockApi(page, { authenticated: true, language: "ru" })
    await page.goto("/messenger", { waitUntil: "domcontentloaded", timeout: 30_000 })

    const status = page.getByRole("status", { name: "Статус соединения", exact: true })
    await expect(status).toBeVisible()
    await expect(status).toHaveAttribute("aria-live", "polite")
    await expect(status.locator(R32_INTERACTIVE)).toHaveCount(0)
    const newChat = page.getByRole("button", { name: "Новый чат", exact: true })
    await expect(newChat).toBeVisible()
    await assertR32NoOverflow(page, "pointer list")
    await assertR32Targets(newChat, "pointer button")
    const statusBox = await status.boundingBox()
    const buttonBox = await newChat.boundingBox()
    if (!statusBox || !buttonBox) throw new Error("Expected visible status and button bounds")
    const center = { x: buttonBox.x + buttonBox.width / 2, y: buttonBox.y + buttonBox.height / 2 }
    expect(center.x).toBeGreaterThanOrEqual(statusBox.x)
    expect(center.x).toBeLessThanOrEqual(statusBox.x + statusBox.width)
    expect(center.y).toBeGreaterThanOrEqual(statusBox.y)
    expect(center.y).toBeLessThanOrEqual(statusBox.y + statusBox.height)
    await newChat.click()
    await expect(page.getByRole("dialog")).toBeVisible()
  })

  for (const viewport of R32_VIEWPORTS) {
    for (const theme of THEMES) {
      test(`@R32 messenger ${viewport.width}px ${theme.name}: list and new-chat dialog`, async ({
        page,
        baseURL,
      }) => {
        if (!baseURL) throw new Error("R32 requires a managed preview origin")
        await page.setViewportSize(viewport)
        await page.emulateMedia({ colorScheme: theme.scheme, reducedMotion: "reduce" })
        await page.context().addCookies([{ name: "ue-mode", value: theme.name, url: baseURL }])
        await page.addInitScript((mode) => localStorage.setItem("ue-mode", mode), theme.name)
        const mock = await useMockApi(page, { authenticated: true, language: "ru" })
        const current = {
          id: mock.state.profile.id,
          email: mock.state.profile.email,
          full_name: mock.state.profile.full_name,
          avatar_url: mock.state.profile.avatar_url ?? null,
          is_active: true,
        }
        const other = {
          id: "00000000-0000-4000-8000-000000000002",
          email: "r32.other@example.test",
          full_name: "R32 Contact",
          avatar_url: null,
          is_active: true,
        }
        const chat = {
          id: "00000000-0000-4000-8000-000000000001",
          chat_type: "dm",
          name: null,
          created_by: null,
          participants: [current, other],
          last_message: null,
          unread_count: 0,
          created_at: "2026-01-01T00:00:00.000Z",
          updated_at: "2026-01-01T00:00:00.000Z",
        }
        await page.route(
          (url) => url.pathname === "/api/chats" || url.pathname === "/api/v1/chats",
          async (route) => {
            if (route.request().method() !== "GET") return route.fallback()
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({ items: [chat], has_more: false, next_cursor: null }),
            })
          }
        )

        await page.goto("/messenger", { waitUntil: "domcontentloaded", timeout: 30_000 })
        await expect(page.locator("html")).toHaveAttribute("lang", "ru")
        await expect(page.locator("html")).toHaveAttribute("data-color-scheme", theme.name)
        const list = page.getByRole("list", { name: "Диалоги", exact: true })
        await expect(list.getByText("R32 Contact", { exact: true })).toBeVisible()
        const newChat = page.getByRole("button", { name: "Новый чат", exact: true })
        await expect(newChat).toBeVisible()
        await assertR32NoOverflow(page, "list")
        await assertR32Targets(
          list.locator(R32_INTERACTIVE).or(newChat).or(page.locator("#messenger-sidebar-search")),
          "list"
        )
        await assertR32Axe(page, "list")

        await newChat.click()
        const dialog = page.getByRole("dialog")
        await expect(dialog).toBeVisible()
        await expect(dialog.locator("xpath=..")).toHaveCSS("opacity", "1")
        await expect(dialog).toHaveAttribute("aria-modal", "true")
        await assertR32NoOverflow(page, "dialog")
        const dialogWidth = await dialog.evaluate((element) => ({
          client: element.clientWidth,
          scroll: element.scrollWidth,
        }))
        expect(dialogWidth.scroll, "dialog content width").toBeLessThanOrEqual(dialogWidth.client)
        await assertR32Targets(dialog.locator(R32_INTERACTIVE), "dialog")
        await assertR32Axe(page, "dialog")
      })
    }
  }
})
