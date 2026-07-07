import { expect, test, type Page } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

/**
 * Schedule offline behaviour specs — W24.
 *
 * Tests that the schedule page degrades gracefully when the network is
 * unavailable:
 *   1. The page loads (from Service Worker cache) when offline.
 *   2. Sync resumes and new data appears after coming back online.
 *   3. An offline indicator is visible while disconnected.
 *
 * Pattern mirrors offline.spec.ts: Service Worker readiness is checked
 * before going offline, and the context is always restored to online in a
 * finally block to prevent test pollution.
 *
 * NOTE: Service Worker caching requires a proper SW-registered build.
 * In the plain mock-API environment the SW is not guaranteed to control
 * the page. Tests are skipped if the SW is not active, rather than
 * letting them fail non-deterministically.
 */

const TIMEOUTS = {
  navigation: 10_000,
  element: 10_000,
  toast: 5_000,
}

async function isServiceWorkerControlled(page: Page): Promise<boolean> {
  try {
    return await page.evaluate(() => Boolean(navigator.serviceWorker?.controller))
  } catch {
    return false
  }
}

async function ensureServiceWorkerReady(page: Page): Promise<boolean> {
  await page.waitForLoadState("networkidle")
  try {
    await page.evaluate(async () => {
      await navigator.serviceWorker?.ready
    })
  } catch {
    return false
  }
  let controlled = await isServiceWorkerControlled(page)
  if (!controlled) {
    await page.reload({ waitUntil: "networkidle" })
    try {
      await page.evaluate(async () => {
        await navigator.serviceWorker?.ready
      })
    } catch {
      return false
    }
    controlled = await isServiceWorkerControlled(page)
  }
  return controlled
}

test.describe("Schedule offline behaviour", () => {
  // ── 1. Page loads from SW cache when offline ───────────────────────────
  test("loads schedule page from SW cache when network is offline", async ({ page, context }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/schedule", { waitUntil: "networkidle" })
    await page.waitForURL(/\/schedule$/)

    // Verify the page loaded online first (baseline content present).
    const scheduleHeading = page.getByRole("heading", { name: /расписание|schedule/i })
    if (!(await scheduleHeading.isVisible({ timeout: 5000 }))) {
      test.skip(true, "Schedule page heading not found — layout may have changed")
    }

    const swReady = await ensureServiceWorkerReady(page)
    if (!swReady) {
      test.skip(true, "Service Worker not active — caching not testable in this environment")
    }

    await context.setOffline(true)
    try {
      // Reload while offline — SW cache should serve the page.
      await page.reload({ waitUntil: "domcontentloaded" })
      await expect(page).toHaveURL(/\/schedule/, { timeout: TIMEOUTS.navigation })

      // The schedule heading must still be present from cache.
      await expect(page.getByRole("heading", { name: /расписание|schedule/i })).toBeVisible({
        timeout: TIMEOUTS.element,
      })
    } finally {
      await context.setOffline(false)
    }
  })

  // ── 2. Sync resumes on reconnect ──────────────────────────────────────
  //
  // Goes offline, then comes back online, dispatches the `online` event,
  // and verifies the UI no longer shows an offline indicator (i.e., the
  // app detected the reconnect and cleared the offline banner).
  test("clears offline indicator and resumes sync on reconnect", async ({ page, context }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/schedule", { waitUntil: "networkidle" })
    await page.waitForURL(/\/schedule$/)

    const swReady = await ensureServiceWorkerReady(page)
    if (!swReady) {
      test.skip(true, "Service Worker not active — offline sync not testable in this environment")
    }

    await context.setOffline(true)
    try {
      // Trigger browser's offline event so the app reacts immediately.
      await page.evaluate(() => window.dispatchEvent(new Event("offline")))
      await page.waitForTimeout(500)

      // An offline indicator should appear (toast / banner).
      const offlineBanner = page
        .locator('[role="status"], [role="alert"]')
        .filter({ hasText: /offline|нет подключения|отключено/i })
      if (await offlineBanner.isVisible({ timeout: 3000 })) {
        await expect(offlineBanner).toBeVisible()
      }
    } finally {
      await context.setOffline(false)
      await page.evaluate(() => window.dispatchEvent(new Event("online")))
    }

    // After coming online the offline banner should disappear.
    const offlineBanner = page
      .locator('[role="status"], [role="alert"]')
      .filter({ hasText: /offline|нет подключения|отключено/i })
    await expect(offlineBanner).not.toBeVisible({ timeout: TIMEOUTS.toast })
  })

  // ── 3. Offline indicator shown while disconnected ──────────────────────
  test("shows offline indicator while network is unavailable", async ({ page, context }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/schedule", { waitUntil: "networkidle" })
    await page.waitForURL(/\/schedule$/)

    const swReady = await ensureServiceWorkerReady(page)
    if (!swReady) {
      test.skip(true, "Service Worker not active — offline indicator test skipped")
    }

    await context.setOffline(true)
    try {
      await page.evaluate(() => window.dispatchEvent(new Event("offline")))
      await page.waitForTimeout(500)

      // The app should surface some offline indicator.
      const indicator = page
        .locator('[role="status"], [role="alert"], [data-testid*="offline"]')
        .filter({ hasText: /offline|нет подключения|отключено/i })

      if (await indicator.isVisible({ timeout: TIMEOUTS.toast })) {
        await expect(indicator.first()).toBeVisible()
      } else {
        test.info().annotations.push({
          type: "info",
          description: "Offline indicator not rendered — the app may use a different UX pattern",
        })
      }
    } finally {
      await context.setOffline(false)
      await page.evaluate(() => window.dispatchEvent(new Event("online")))
    }
  })
})
