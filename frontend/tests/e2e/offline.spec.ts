import { expect, test, type Page } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const ensureServiceWorkerIsReady = async (page: Page) => {
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

  expect(controlled).toBeTruthy()
}

const OFFLINE_TEST_TIMEOUTS = {
  elementVisible: 15_000,
  toastVisible: 10_000,
}

test.describe("PWA offline support", () => {
  test("shows offline fallback page when network is unavailable", async ({ page, context }) => {
    const mock = await useMockApi(page, { serviceWorker: "preserve" })
    await mock.login(page)

    await ensureServiceWorkerIsReady(page)

    await page.goto("/offline.html", { waitUntil: "domcontentloaded" })
    await expect(page.locator("h1")).toBeVisible({ timeout: OFFLINE_TEST_TIMEOUTS.elementVisible })
    await expect(
      page.getByRole("heading", { name: /No network connection|Нет подключения к сети/i })
    ).toBeVisible()

    await gotoWithTransientRetry(page, "/dashboard", { waitUntil: "networkidle" })

    await context.setOffline(true)
    try {
      // For SPA, navigation to a cached route should still work but show offline indicator
      await page.goto("/news", { waitUntil: "domcontentloaded" })
      const offlineIndicator = page
        .locator('[role="status"]')
        .filter({ hasText: /offline|подключения/i })
      await expect(offlineIndicator).toBeVisible({ timeout: OFFLINE_TEST_TIMEOUTS.elementVisible })

      // Explicitly check the fallback page too
      await page.goto("/offline.html", { waitUntil: "domcontentloaded" })
      await expect(page.locator("h1")).toBeVisible()
      await expect(
        page.getByRole("heading", { name: /No network connection|Нет подключения к сети/i })
      ).toBeVisible()
    } finally {
      await context.setOffline(false)
    }
  })

  test("profile data stays available offline after it was cached", async ({ page, context }) => {
    const mock = await useMockApi(page, { serviceWorker: "preserve" })
    await mock.login(page)

    await ensureServiceWorkerIsReady(page)

    await gotoWithTransientRetry(page, "/profile", { waitUntil: "networkidle" })
    await expect(page).toHaveURL(/\/profile/)
    await expect(page.getByText(/Иван Иванов|Ivan Ivanov/i)).toBeVisible()

    await context.setOffline(true)
    try {
      await page.reload({ waitUntil: "domcontentloaded" })
      await expect(page).toHaveURL(/\/profile/)
      await expect(page.getByText(/Иван Иванов|Ivan Ivanov/i)).toBeVisible()
    } finally {
      await context.setOffline(false)
    }
  })

  test("news, schedule, and events stay cached for offline navigation", async ({
    page,
    context,
  }) => {
    const mock = await useMockApi(page, { serviceWorker: "preserve" })
    await mock.login(page)
    await ensureServiceWorkerIsReady(page)

    await gotoWithTransientRetry(page, "/news", { waitUntil: "networkidle" })
    await expect(page.getByText(/Новость дня|News of the day/i)).toBeVisible()

    await gotoWithTransientRetry(page, "/schedule", { waitUntil: "networkidle" })
    await expect(page.getByText(/Математика|Mathematics/i).first()).toBeVisible()

    const initialStatuses = await page.evaluate(async () => {
      const [newsResp, scheduleResp, eventsResp] = await Promise.all([
        fetch("/api/v1/news"),
        fetch("/api/v1/schedule/1"),
        fetch("/api/v1/events"),
      ])

      return {
        newsStatus: newsResp.status,
        scheduleStatus: scheduleResp.status,
        eventsStatus: eventsResp.status,
      }
    })

    expect(initialStatuses.newsStatus).toBe(200)
    expect(initialStatuses.scheduleStatus).toBe(200)
    expect(initialStatuses.eventsStatus).toBe(200)

    await context.setOffline(true)
    try {
      await page.goto("/news", { waitUntil: "domcontentloaded" })
      await expect(page.getByText(/Новость дня|News of the day/i)).toBeVisible()

      const offlineData = await page.evaluate(async () => {
        const [newsResp, scheduleResp, eventsResp] = await Promise.all([
          fetch("/api/v1/news"),
          fetch("/api/v1/schedule/1"),
          fetch("/api/v1/events"),
        ])

        const news = await newsResp.clone().json()
        const schedule = await scheduleResp.clone().json()
        const eventsPayload = await eventsResp.clone().json()

        return {
          newsStatus: newsResp.status,
          scheduleStatus: scheduleResp.status,
          eventsStatus: eventsResp.status,
          newsLength: Array.isArray(news) ? news.length : 0,
          scheduleLength: Array.isArray(schedule) ? schedule.length : 0,
          eventsCount: Array.isArray(eventsPayload?.items) ? eventsPayload.items.length : 0,
        }
      })

      expect(offlineData.newsStatus).toBe(200)
      expect(offlineData.scheduleStatus).toBe(200)
      expect(offlineData.eventsStatus).toBe(200)
      expect(offlineData.newsLength).toBeGreaterThan(0)
      expect(offlineData.scheduleLength).toBeGreaterThan(0)
      expect(offlineData.eventsCount).toBeGreaterThan(0)
    } finally {
      await context.setOffline(false)
    }
  })

  test("shows offline indicator toast when connection is lost", async ({ page, context }) => {
    const mock = await useMockApi(page, { serviceWorker: "preserve" })
    await mock.login(page)

    await ensureServiceWorkerIsReady(page)

    await gotoWithTransientRetry(page, "/dashboard", { waitUntil: "networkidle" })

    // Go offline and check for indicator
    await context.setOffline(true)
    try {
      // Trigger the online/offline event
      await page.evaluate(() => {
        window.dispatchEvent(new Event("offline"))
      })

      // Wait for offline indicator to appear
      const offlineToast = page.locator('[role="status"]').filter({
        hasText: /offline|подключения/i,
      })
      await expect(offlineToast).toBeVisible({ timeout: OFFLINE_TEST_TIMEOUTS.toastVisible })

      // Go back online
      await context.setOffline(false)
      await page.evaluate(() => {
        window.dispatchEvent(new Event("online"))
      })

      // Check for "Back online" message
      const onlineToast = page.locator('[role="status"]').filter({
        hasText: /online|восстановлено/i,
      })
      await expect(onlineToast).toBeVisible({ timeout: OFFLINE_TEST_TIMEOUTS.toastVisible })

      // Toast should auto-hide after a few seconds
      await expect(onlineToast).not.toBeVisible({ timeout: OFFLINE_TEST_TIMEOUTS.toastVisible })
    } finally {
      await context.setOffline(false)
    }
  })
})
