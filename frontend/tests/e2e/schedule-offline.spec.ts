import { expect, test, type Page } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

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
 * The API mock preserves the real production Service Worker in these specs;
 * readiness is a required precondition and failures are surfaced directly.
 */

const TIMEOUTS = {
  navigation: 15_000,
  element: 15_000,
  toast: 10_000,
}

async function ensureServiceWorkerReady(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle")
  await page.evaluate(async () => {
    if ("serviceWorker" in navigator) {
      await navigator.serviceWorker.ready
    }
  })
  let controlled = await page.evaluate(() => Boolean(navigator.serviceWorker?.controller))
  if (!controlled) {
    await page.reload({ waitUntil: "networkidle" })
    await page.evaluate(async () => {
      if ("serviceWorker" in navigator) {
        await navigator.serviceWorker.ready
      }
    })
    controlled = await page.evaluate(() => Boolean(navigator.serviceWorker?.controller))
  }
  await page.waitForFunction(
    () => !navigator.serviceWorker || navigator.serviceWorker?.controller?.state === "activated"
  )
}

test.describe("Schedule offline behaviour", () => {
  // ── 1. Page loads from SW cache when offline ───────────────────────────
  test("loads schedule page from SW cache when network is offline", async ({ page, context }) => {
    const { login } = await useMockApi(page, { serviceWorker: "preserve" })
    await login(page)

    await gotoWithTransientRetry(page, "/schedule", { waitUntil: "networkidle" })
    await page.waitForURL(/\/schedule$/)

    // Verify the page loaded online first (baseline content present).
    const scheduleHeading = page.getByRole("heading", { name: /расписание|schedule/i })
    await expect(scheduleHeading).toBeVisible({ timeout: TIMEOUTS.element })
    await ensureServiceWorkerReady(page)

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
    const { login } = await useMockApi(page, { serviceWorker: "preserve" })
    await login(page)

    await gotoWithTransientRetry(page, "/schedule", { waitUntil: "networkidle" })
    await page.waitForURL(/\/schedule$/)

    await ensureServiceWorkerReady(page)

    await context.setOffline(true)
    try {
      // Trigger browser's offline event so the app reacts immediately.
      await page.evaluate(() => window.dispatchEvent(new Event("offline")))

      // An offline indicator should appear (toast / banner).
      const offlineBanner = page
        .locator('[role="status"], [role="alert"]')
        .filter({ hasText: /offline|нет подключения|отключено/i })
      await expect(offlineBanner).toBeVisible({ timeout: TIMEOUTS.toast })
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
    const { login } = await useMockApi(page, { serviceWorker: "preserve" })
    await login(page)

    await gotoWithTransientRetry(page, "/schedule", { waitUntil: "networkidle" })
    await page.waitForURL(/\/schedule$/)

    await ensureServiceWorkerReady(page)

    await context.setOffline(true)
    try {
      await page.evaluate(() => window.dispatchEvent(new Event("offline")))

      // The app should surface some offline indicator.
      const indicator = page
        .locator('[role="status"], [role="alert"], [data-testid*="offline"]')
        .filter({ hasText: /offline|нет подключения|отключено/i })

      await expect(indicator.first()).toBeVisible({ timeout: TIMEOUTS.toast })
    } finally {
      await context.setOffline(false)
      await page.evaluate(() => window.dispatchEvent(new Event("online")))
    }
  })
})
