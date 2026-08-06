import { expect, test } from "./test"

/**
 * Wave 179 SW9 login-flow regression e2e (closes W174 §Honesty #4-playwright).
 *
 * Three regression scenarios from W177 SW1 + W178 SW1 + W179 SW4 verified
 * empirically via chrome-devtools-mcp during their respective waves but
 * lacked Playwright regression coverage. This spec restores that.
 *
 * ## Scenarios
 *
 *   1. Authed user on /login → redirects to /dashboard (W177 SW1 useEffect)
 *   2. Authed user on /forgot-password → redirects to /dashboard via
 *      PublicLayout useEffect (W178 SW1 layout-level reactive redirect
 *      covering all 5 /_public/ routes via single mechanism)
 *   3. state.from preservation: /login?redirect=/events lands on /events
 *      (W179 SW4 closes W177 §Honesty #3 race — useEffects honor TanStack
 *      canonical search.redirect via resolveRedirectPath helper)
 *
 * ## Gated to opt-in invocation (URL_STATE_E2E=true)
 *
 * Reuses the same URL_STATE_E2E auto-managed mode as url-state-persistence
 * spec — needs VITE_LHCI=true build for auth bypass (useProfileSync injects
 * mock user → useAuthStore.user is set on mount → Login.tsx + PublicLayout
 * useEffects observe transition and fire navigate).
 *
 * Single command (per W121 SW3 + W148 SW3 invariants):
 *   `URL_STATE_E2E=true npx playwright test --project=chromium wave179-login-flow.spec.ts`
 *
 * Without URL_STATE_E2E=true, every test in this file `test.skip()`s.
 *
 * ## Implementation pattern
 *
 * Same fast-fail mechanism as url-state-persistence.spec.ts:
 *   - `page.route("**\/api\/v1\/**", abort)` BEFORE goto (W148 SW3 pattern
 *     — prevents React Query retry storm from starving event loop)
 *   - URL-only assertions via `toHaveURL` (W149 SW1 finding — CDP-based
 *     frame-navigation events immune to event-loop starvation)
 *   - chromium-only (TanStack Router behavior identical across engines)
 *
 * ## CI integration
 *
 * Runs in the URL_STATE_E2E job step at `.github/workflows/reusable-e2e-
 * tests.yml`. Single shared step that runs both url-state-persistence +
 * wave179-login-flow specs under the same VITE_LHCI=true preview.
 */

const ENABLED = process.env.URL_STATE_E2E === "true"
const BASE = process.env.URL_STATE_E2E_BASE ?? "http://127.0.0.1:4175"

test.describe("Login flow redirect guards (Wave 177 SW1 + W178 SW1 + W179 SW4)", () => {
  test.skip(!ENABLED, "set URL_STATE_E2E=true + run a VITE_LHCI=true preview to enable")
  test.skip(({ browserName }) => browserName !== "chromium", "chromium-only by design")

  test.use({ baseURL: BASE, serviceWorkers: "block" })

  test("authed user on /login redirects to /dashboard (W177 SW1)", async ({ page }) => {
    // VITE_LHCI mock user → useAuthStore.user populated on mount → Login.tsx
    // W177 SW1 useEffect observes user !== null → fires navigate({to:
    // "/dashboard", replace:true}). page.route abort prevents React Query
    // retry storms (W148 SW3 + W149 SW3 pattern).
    await page.route("**/api/v1/**", (route) => route.abort("internetdisconnected"))
    await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 30_000 })
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15_000 })
  })

  test("authed user on /forgot-password redirects via PublicLayout useEffect (W178 SW1)", async ({
    page,
  }) => {
    // W178 SW1 added layout-level reactive useEffect in _public.tsx
    // PublicLayout covering all 5 /_public/ routes (/login, /forgot-password,
    // /register, /reset-password, /reset-password/$token) via single
    // mechanism, parallel to Login.tsx's W177 SW1 useEffect. This test
    // verifies the layout-level path specifically — /forgot-password has
    // NO route-specific useEffect (unlike /login), so the redirect MUST
    // come from PublicLayout.
    await page.route("**/api/v1/**", (route) => route.abort("internetdisconnected"))
    await page.goto("/forgot-password", { waitUntil: "domcontentloaded", timeout: 30_000 })
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15_000 })
  })

  test("state.from preservation: /login?redirect=/events lands on /events (W179 SW4)", async ({
    page,
  }) => {
    // W179 SW4 closes W177 §Honesty #3 race condition. Pre-W179: Login.tsx +
    // _public.tsx useEffects hardcoded /dashboard, ignoring TanStack canonical
    // search.redirect written by _auth.tsx:47 beforeLoad. User intent (e.g.,
    // deep-link to /events) was lost on re-auth → always landed on /dashboard.
    // W179 SW4 fix: both useEffects read search.redirect + resolveRedirectPath
    // → navigate to redirect target. resolveRedirectPath includes same-origin
    // check (cross-origin redirect rejected as security measure).
    await page.route("**/api/v1/**", (route) => route.abort("internetdisconnected"))
    await page.goto("/login?redirect=" + encodeURIComponent("/events"), {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    })
    await expect(page).toHaveURL(/\/events/, { timeout: 15_000 })
    // Negative assertion: should NOT have landed on /dashboard (would happen pre-W179)
    expect(page.url()).not.toMatch(/\/dashboard/)
  })
})
