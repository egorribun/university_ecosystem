import { expect, test } from "./test"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"

/**
 * Messenger-page accessibility scan — Wave 182 SW5 / closes W181 gap item #8.
 *
 * Adapts the W147 SW2 axe-on-chromium-headless structural pattern from
 * `a11y-public.spec.ts` (page.addInitScript pre-injection + page.route abort
 * post-goto + Promise.race timeout wrapper) to authenticated /messenger.
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

type AxeNode = { target: string[]; html: string; failureSummary?: string }
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

  test.beforeEach(async ({ page }) => {
    await page.addInitScript({ content: AXE_SOURCE })
  })

  for (const theme of THEMES) {
    test(`messenger — ${theme.name} theme has no critical/serious axe violations`, async ({
      page,
      browserName,
    }) => {
      // Restrict to chromium per W115 SW1 + W116 SW1 a11y-public.spec.ts
      // baseline (WebKit + Firefox renderer OOM on axe-core injection +
      // heavy DOM).
      test.skip(
        browserName !== "chromium",
        "Messenger axe scan chromium-only — WebKit + Firefox memory pressure per W115/W116 baseline."
      )

      await page.emulateMedia({ colorScheme: theme.scheme, reducedMotion: "reduce" })
      await page.goto("/messenger", { waitUntil: "domcontentloaded", timeout: 30_000 })

      // W148 SW3 pattern — block ALL subsequent network so React Query
      // retries / dynamic chunks / SW workbox don't starve the event loop
      // and prevent axe.run from scheduling. The DOM tree axe scans is
      // already rendered post-goto.
      await page.route("**/*", (r) => r.abort())

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
})
