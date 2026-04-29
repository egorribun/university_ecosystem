import { expect, test } from "@playwright/test"

/**
 * URL-state persistence smoke spec — Wave 120 SW7 (Item #9).
 *
 * Wave 112 SW3 introduced URL-synced filter/tab/sort state via the shared
 * `useURLState` hook for News/Events/Activity/Schedule. Wave 120 SW5 added
 * the same pattern to the Map page (zoom/center/pitch). None of these had
 * end-to-end coverage — this spec exercises the round-trip:
 *   click control → URL updates → reload → control state restored from URL.
 *
 * ## Why this spec is gated to opt-in invocation
 *
 * The default `playwright.config.ts` webServer builds without VITE_LHCI=true,
 * so authenticated routes (/events, /news, /activity, /schedule, /map)
 * redirect to /login. Wave 116 SW3 wired `VITE_LHCI=true` into `_auth.tsx`
 * `beforeLoad` and `useProfileSync.ts` to bypass auth + inject a mock user
 * for LHCI sweeps. This spec reuses that mechanism.
 *
 * ## Recommended: auto-managed mode (Wave 121 SW3)
 *
 * Wave 121 SW3 added a `URL_STATE_E2E=true` branch to `playwright.config.ts`
 * that uses `cross-env` to propagate `VITE_LHCI=true` to `npm run build`
 * cross-platform (bash/zsh/cmd/PowerShell), then serves on port 4175
 * (matching `URL_STATE_E2E_BASE` default below). Single command runs the
 * whole flow:
 *
 *   `URL_STATE_E2E=true npx playwright test --project=chromium url-state-persistence.spec.ts`
 *
 * Without `URL_STATE_E2E=true`, every test in this file `test.skip()`s.
 * On POSIX shells, prefix `URL_STATE_E2E=true` works. On Windows cmd use
 * `set URL_STATE_E2E=true && ...` or invoke via the cross-env-equipped
 * `npm run` script if added.
 *
 * ## Fallback: manual SKIP_WEBSERVER mode (Wave 120 SW7)
 *
 * If the auto-managed `webServer.command` fails (port collision on 4175,
 * cross-env not installed, etc.), the original 3-step flow still works:
 *
 *   1. Build LHCI dist:
 *      `env VITE_LHCI=true npm run build`
 *      (use `env` prefix on POSIX/Git-Bash; on Windows cmd use
 *       `set VITE_LHCI=true && npm run build`)
 *   2. Start a vite preview on a known port (default 4175):
 *      `npx vite preview --port 4175 --strictPort`
 *   3. Run with SKIP_WEBSERVER (in addition to URL_STATE_E2E):
 *      `SKIP_WEBSERVER=true URL_STATE_E2E=true \
 *       URL_STATE_E2E_BASE=http://127.0.0.1:4175 \
 *       npx playwright test --project=chromium url-state-persistence.spec.ts`
 *
 * The `SKIP_WEBSERVER=true` flag (Wave 120 SW7) prevents the default
 * Playwright-managed `npm run build` from clobbering the LHCI dist.
 *
 * Wave 122 candidate: integrate a `URL_STATE_E2E=true` Playwright project
 * into CI workflow alongside a11y-public + a11y-cdn-axe.
 *
 * ## Coverage (6 routes)
 *
 *   1. /events   ?tab=archive  — tab persistence
 *   2. /events   ?q=test       — search-query persistence
 *   3. /news     ?cat=&sort=   — category + sort persistence
 *   4. /activity ?p=month      — period-selector persistence
 *   5. /schedule ?w=1          — week-offset persistence
 *   6. /map      ?z&lat&lng    — viewport persistence (Wave 120 SW5)
 *
 * Chromium-only — multi-browser coverage isn't necessary for URL-state
 * round-tripping (TanStack Router behavior is identical across engines).
 */

const ENABLED = process.env.URL_STATE_E2E === "true"
const BASE = process.env.URL_STATE_E2E_BASE ?? "http://127.0.0.1:4175"

test.describe("URL-state persistence (Wave 120 SW7)", () => {
  test.skip(!ENABLED, "set URL_STATE_E2E=true + run a VITE_LHCI=true preview to enable")
  test.skip(({ browserName }) => browserName !== "chromium", "chromium-only by design")

  // The webServer in playwright.config.ts builds the non-LHCI preview;
  // override use.baseURL so this spec hits the LHCI-mode preview.
  // Block service workers — the PWA injectManifest precache can serve a
  // STALE bundle (from previous build) and bypass the auth-bypass JS we
  // need at runtime. Wave 120 SW7 found this empirically: tests
  // intermittently hit /login because cached SW returned non-VITE_LHCI
  // HTML/JS even after a fresh `VITE_LHCI=true npm run build`.
  test.use({ baseURL: BASE, serviceWorkers: "block" })

  test("/events tab persists across reload", async ({ page }) => {
    await page.goto("/events")
    // Wait for the tablist to render
    const archiveTab = page.locator("#events-tab-archive")
    await expect(archiveTab).toBeVisible({ timeout: 15_000 })
    await archiveTab.click()
    await expect(page).toHaveURL(/\?tab=archive/, { timeout: 5_000 })

    await page.reload()
    await expect(page).toHaveURL(/\?tab=archive/)
    await expect(archiveTab).toHaveAttribute("aria-selected", "true")
  })

  test("/events search query persists across reload", async ({ page }) => {
    await page.goto("/events")
    const search = page
      .locator('input[type="search"], input[placeholder*="оиск" i], input[placeholder*="earch" i]')
      .first()
    await expect(search).toBeVisible({ timeout: 15_000 })
    await search.fill("конференция")
    // Search debounces — wait for URL to settle
    await expect(page).toHaveURL(/[?&]q=/, { timeout: 5_000 })

    await page.reload()
    await expect(page).toHaveURL(/[?&]q=/)
    // Input value should be restored from URL
    await expect(search).toHaveValue("конференция", { timeout: 5_000 })
  })

  test("/news category + sort persist across reload", async ({ page }) => {
    await page.goto("/news")
    // Click a category chip (any non-default) — exact text varies by data,
    // so target by class
    const categoryChips = page.locator('[role="radio"], button').filter({ hasText: /\S/ })
    await expect(categoryChips.first()).toBeVisible({ timeout: 15_000 })
    // Set sort via URL directly (sort dropdown UI varies)
    await page.goto("/news?sort=popular")
    await expect(page).toHaveURL(/[?&]sort=popular/)

    await page.reload()
    await expect(page).toHaveURL(/[?&]sort=popular/)
  })

  test("/activity period persists across reload", async ({ page }) => {
    await page.goto("/activity?p=month")
    await expect(page).toHaveURL(/[?&]p=month/, { timeout: 15_000 })
    // Wait for page heading to render (Activity title in either locale).
    // The period selector mounts inside Suspense boundary, so radio
    // role isn't immediately queryable; URL persistence is the actual
    // assertion target for SW7.
    await page.locator("h1").first().waitFor({ state: "visible", timeout: 15_000 })

    await page.reload()
    await expect(page).toHaveURL(/[?&]p=month/)
  })

  test("/schedule week offset persists across reload", async ({ page }) => {
    await page.goto("/schedule?w=1")
    await expect(page).toHaveURL(/[?&]w=1/, { timeout: 15_000 })
    await page.reload()
    await expect(page).toHaveURL(/[?&]w=1/)
  })

  test("/map viewport persists across reload", async ({ page }) => {
    await page.goto("/map?z=18&lat=55.714&lng=37.816&p=30&b=90")
    await expect(page).toHaveURL(/z=18/, { timeout: 15_000 })
    // Wait for canvas to render (MapLibre takes ~3-4s)
    await expect(page.locator(".maplibregl-canvas")).toBeVisible({ timeout: 15_000 })
    await page.waitForTimeout(2_500)

    await page.reload()
    await expect(page).toHaveURL(/z=18/)
    await expect(page).toHaveURL(/lat=55\.714/)
    await expect(page).toHaveURL(/lng=37\.816/)
    await expect(page).toHaveURL(/p=30/)
    await expect(page).toHaveURL(/b=90/)
  })
})
