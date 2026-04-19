import { expect, test } from "@playwright/test"

/**
 * CDN-injected `axe-core` regression test — Wave 115 SW3.
 *
 * `@axe-core/playwright@4.11.2` bundles `axe-core@4.11.3` internally (see
 * `node_modules/@axe-core/playwright/dist/index.mjs` — it imports the
 * transitive `axe-core` peer). During Wave 114 polish-v2, a full-WCAG
 * audit via `axe.min.js@4.11.2` loaded directly in a running dev preview
 * consistently reported a WCAG 2.5.8 `target-size` violation on
 * `<a href="/forgot-password">` in the `LoginCredentialForm`. Three
 * consecutive runs at Playwright's 1280×720 viewport all surfaced it
 * (19 × 105 px inline link < 24 × 24 px minimum). The same tag-set through
 * `@axe-core/playwright`'s bundled scanner on the same e2e harness did
 * NOT catch it — rule-engine delta between 4.11.2 and 4.11.3 or a
 * Playwright-specific rendering quirk, not instrumented further.
 *
 * This spec loads `axe-core@4.11.2` from the jsdelivr CDN via
 * `page.addScriptTag` and runs `axe.run(document, ...)` directly. That
 * reproduces the Wave 114 polish-v2 finding inside the e2e harness and
 * creates a CI regression guard that fires if the forgot-password link (or
 * any other WCAG 2.2 AA surface on /login) regresses to a sub-24 px hit
 * box. Chromium-only — WebKit projects already have memory-envelope
 * constraints from SW1, and the CDN inject adds payload that would
 * exacerbate them.
 */

type AxeNode = { target: string[]; html: string; failureSummary?: string }
type AxeViolation = { id: string; impact: string; nodes: AxeNode[]; help: string }
type AxeResult = { violations: AxeViolation[] }

test.describe("@a11y CDN-injected axe-core regression", () => {
  test("/login — no WCAG 2.2 AA target-size violations", async ({ page }, testInfo) => {
    // Wave 115 polish — standardised on `testInfo.project.name` across both
    // `a11y-public.spec.ts` and this spec so skip conditions stay consistent
    // (per Wave 113 convention: `browserName` returns "webkit" for both the
    // `webkit` and `mobile-webkit` Playwright projects because they share
    // the same browser binary — only `project.name` distinguishes them).
    test.skip(
      testInfo.project.name !== "chromium",
      "CDN axe injection compounds WebKit memory pressure — Chromium only (Wave 115 SW1 gates WebKit via legacy mode)",
    )

    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/login", { waitUntil: "domcontentloaded" })
    await page.waitForLoadState("networkidle").catch(() => {})
    // Same settle buffer as a11y-public.spec.ts — let React Query observers
    // flush and MotionConfig snap Framer Motion to resting state.
    await page.waitForTimeout(300)

    await page.addScriptTag({
      url: "https://cdn.jsdelivr.net/npm/axe-core@4.11.2/axe.min.js",
    })

    const results = await page.evaluate<AxeResult>(async () => {
      type AxeWindow = {
        axe: {
          run: (
            context: Document,
            options: { runOnly: { type: string; values: string[] } },
          ) => Promise<AxeResult>
        }
      }
      const { axe } = window as unknown as AxeWindow
      return axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
        },
      })
    })

    const targetSize = results.violations.filter((v) => v.id === "target-size")
    // `toEqual([])` surfaces the node[] array in the test failure message for
    // fast triage of which specific link regressed.
    expect(targetSize, JSON.stringify(targetSize, null, 2)).toEqual([])
  })
})
