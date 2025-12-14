import { expect, test, type Page } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

const ensureServiceWorkerIsReady = async (page: Page) => {
  await page.waitForLoadState("networkidle")
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await page.evaluate(async () => {
        await navigator.serviceWorker?.ready
      })
      break
    } catch (error) {
      if (attempt === 2) throw error
      await page.waitForTimeout(250)
    }
  }

  let controlled = await page.evaluate(() => Boolean(navigator.serviceWorker?.controller))
  if (!controlled) {
    await page.reload({ waitUntil: "networkidle" })
    await page.evaluate(async () => {
      await navigator.serviceWorker?.ready
    })
    controlled = await page.evaluate(() => Boolean(navigator.serviceWorker?.controller))
  }

  await page.waitForFunction(() => navigator.serviceWorker?.controller?.state === "activated")

  expect(controlled).toBeTruthy()
}

test.describe("PWA offline support", () => {
  test("shows offline fallback page when network is unavailable", async ({ page, context }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await ensureServiceWorkerIsReady(page)

    await page.goto("/offline.html", { waitUntil: "domcontentloaded" })
    await expect(page.getByRole("heading", { name: "Нет подключения к сети" })).toBeVisible()

    await page.goto("/dashboard", { waitUntil: "networkidle" })

    await context.setOffline(true)
    try {
      await page.goto("/news", { waitUntil: "domcontentloaded" })
      await expect(page.getByRole("heading", { name: "Нет подключения к сети" })).toBeVisible()
      await expect(
        page.getByText("Расписание и новости, просмотренные ранее, останутся доступными офлайн.")
      ).toBeVisible()
    } finally {
      await context.setOffline(false)
    }
  })

  test("profile data stays available offline after it was cached", async ({ page, context }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await ensureServiceWorkerIsReady(page)

    await page.goto("/profile", { waitUntil: "networkidle" })
    await expect(page).toHaveURL(/\/profile/)
    await expect(page.getByText("Иван Иванов")).toBeVisible()

    await context.setOffline(true)
    try {
      await page.reload({ waitUntil: "domcontentloaded" })
      await expect(page).toHaveURL(/\/profile/)
      await expect(page.getByText("Иван Иванов")).toBeVisible()
    } finally {
      await context.setOffline(false)
    }
  })

  test("news, schedule, and events stay cached for offline navigation", async ({
    page,
    context,
  }) => {
    const mock = await useMockApi(page)
    await mock.login(page)
    await ensureServiceWorkerIsReady(page)

    await page.goto("/news", { waitUntil: "networkidle" })
    await expect(page.getByText("Новость дня")).toBeVisible()

    await page.goto("/schedule", { waitUntil: "networkidle" })
    await expect(page.getByText("Математика")).toBeVisible()

    const initialStatuses = await page.evaluate(async () => {
      const [newsResp, scheduleResp, eventsResp] = await Promise.all([
        fetch("/api/news"),
        fetch("/api/schedule"),
        fetch("/api/events"),
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
      await expect(page.getByText("Новость дня")).toBeVisible()

      const offlineData = await page.evaluate(async () => {
        const [newsResp, scheduleResp, eventsResp] = await Promise.all([
          fetch("/api/news"),
          fetch("/api/schedule"),
          fetch("/api/events"),
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
})
