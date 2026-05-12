import { expect, test } from "@playwright/test"
import { readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import path from "node:path"

/**
 * Local-injected `axe-core` regression test — Wave 115 SW3 / Wave 146 SW1.
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
 * Originally this spec loaded `axe-core@4.11.2` from the jsdelivr CDN via
 * `page.addScriptTag`. Wave 146 SW1 replaces that with the npm-bundled
 * version injected via `page.evaluate(eval(src))` — production CSP
 * `script-src 'self' 'strict-dynamic'` (see `app/core/policies/csp.py:39`)
 * silently blocks CDN script-tag loads in `npm run preview` (the same
 * VITE_LHCI build that auto-bypasses auth via `_auth.tsx` `beforeLoad`),
 * making the `page.addScriptTag` `load` event never fire and the test
 * hit its 90 s timeout. The same fix is documented at
 * `frontend/scripts/wave138-visual-audit.mjs:401-433` (Wave 144 SW1 iter 2
 * + Wave 145 SW1 Promise.race(30s) ceiling — the latter resolves W144
 * NEW (z) #21 24-min unbounded hang).
 *
 * Chromium-only — WebKit projects already have memory-envelope
 * constraints from SW1, and the eval inject is structurally identical
 * to the CDN script-tag path from a renderer-memory standpoint (the
 * 550 KB source still has to land in the page's JS context).
 */

type AxeNode = { target: string[]; html: string; failureSummary?: string }
type AxeViolation = { id: string; impact: string; nodes: AxeNode[]; help: string }
type AxeResult = { violations: AxeViolation[] }

// W146 SW1 — Path resolution from `frontend/tests/e2e/a11y-cdn-axe.spec.ts`
// up to `frontend/node_modules/axe-core/axe.min.js`. Three levels up
// (file → e2e → tests → frontend) then descend. Mirrors
// `wave138-visual-audit.mjs:87-91` resolution pattern (which goes two
// levels because that script is in `frontend/scripts/`).
const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../../node_modules/axe-core/axe.min.js"
)

test.describe("@a11y local-injected axe-core regression", () => {
  test("/login — no WCAG 2.2 AA target-size violations", async ({ page }, testInfo) => {
    // Wave 115 polish — standardised on `testInfo.project.name` across both
    // `a11y-public.spec.ts` and this spec so skip conditions stay consistent
    // (per Wave 113 convention: `browserName` returns "webkit" for both the
    // `webkit` and `mobile-webkit` Playwright projects because they share
    // the same browser binary — only `project.name` distinguishes them).
    test.skip(
      testInfo.project.name !== "chromium",
      "axe-core eval inject compounds WebKit memory pressure — Chromium only (Wave 115 SW1 gates WebKit via legacy mode)"
    )

    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 30_000 })
    // Wave 146 polish-v2 — removed `page.waitForLoadState("networkidle")` which
    // hung the test under W146 SW1 CSP-block elimination. Pre-W146 the test
    // never reached `waitForLoadState` because `addScriptTag(CDN)` hit its 90s
    // timeout first; post-W146 SW1, the test reaches the next step and the
    // `networkidle` wait hangs indefinitely when /login has pending API
    // requests (backend unavailable in CI E2E env → 404s + retries keep the
    // network active). Default Playwright `waitForLoadState` ignores the
    // `.catch(() => {})` because it uses an internal navigation timeout that
    // doesn't fire promptly. Pattern verified working in
    // `frontend/scripts/wave138-visual-audit.mjs:355-366` (W145 SW1 baseline):
    // skip networkidle entirely + use a fixed 1500ms settle for Framer Motion
    // + React Query observers + MotionConfig `reducedMotion="user"` to snap.
    await page.waitForTimeout(1500)

    // Wave 146 SW1 — npm-bundled axe-core injected via eval (CSP-agnostic).
    //
    // Why this replaced the pre-W146 `page.addScriptTag({ url: CDN })`:
    //
    // Production CSP `script-src 'self' 'strict-dynamic'` (see
    // `app/core/policies/csp.py:39` + per-request nonce at
    // `app/core/security_headers.py:76`) blocks the jsdelivr CDN URL
    // because Playwright's `addScriptTag` can't attach a per-request
    // nonce → browser silently blocks → `load` event never fires →
    // indefinite wait → 90 s test timeout. Identical CSP-block pattern
    // resolved by W144 SW1 iter 2 (`wave138-visual-audit.mjs` A2 pivot)
    // and bounded by W145 SW1 30 s Promise.race ceiling.
    //
    // eval inside `page.evaluate` is CSP-agnostic: no `<script>` tag is
    // created → `script-src` is not evaluated against this code path.
    // Source is the npm-pinned `axe-core@4.11.2` minified bundle
    // (~270 KB after compression, ~550 KB raw — `node_modules/axe-core/
    // axe.min.js`). Read once per test (single test, single worker
    // — no warm-cache savings to be had vs module-scope load).
    //
    // Promise.race(30 s) provides defensive ceiling — mirrors
    // `wave138-visual-audit.mjs:418-432` pattern that resolved W144 NEW
    // (z) #21 24-min unbounded hang on the visual-audit script. If the
    // 30 s ceiling fires here, the failure is in `page.evaluate` IPC
    // serialization of the 550 KB source OR eval() under Chromium memory
    // pressure — same diagnostic dichotomy.
    const AXE_SOURCE = await readFile(AXE_SOURCE_PATH, "utf-8")
    const INJECT_TIMEOUT_MS = 30_000
    await Promise.race([
      page.evaluate((src) => {
        // npm-pinned axe-core@4.11.2 .min.js, intentional + audited;
        // eval inside browser-context page.evaluate is CSP-agnostic +
        // no user input flows here (source is from node_modules pin).
        // eslint-disable-next-line security/detect-eval-with-expression
        eval(src)
      }, AXE_SOURCE),
      new Promise<never>((_, reject) =>
        setTimeout(
          () => reject(new Error(`axe-inject-timeout-${INJECT_TIMEOUT_MS / 1000}s`)),
          INJECT_TIMEOUT_MS
        )
      ),
    ])

    const results = await page.evaluate<AxeResult>(async () => {
      type AxeWindow = {
        axe: {
          run: (
            context: Document,
            options: { runOnly: { type: string; values: string[] } }
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
