import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

test.describe("SPA offline banner and unqueued ambiguous likes", () => {
  test("shows the offline banner and never queues an ambiguous like", async ({ page }) => {
    const mock = await useMockApi(page)

    // Purge any stale service workers and caches to prevent 404 module imports from previous test runs
    await page.goto("/")
    await page.evaluate(async () => {
      if ("serviceWorker" in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations()
        for (const reg of regs) {
          try {
            await reg.unregister()
          } catch {
            // ignore
          }
        }
      }
      if (window.caches) {
        try {
          const keys = await caches.keys()
          for (const key of keys) {
            await caches.delete(key)
          }
        } catch {
          // ignore
        }
      }
    })

    await mock.login(page)

    // Go to news section
    await page.goto("/news")
    await page.waitForURL(/\/news$/)

    // Wait for search input to be visible to guarantee hydration
    await expect(page.getByPlaceholder(/Search news|Поиск новостей/i)).toBeVisible()

    // Initially online: banner is hidden
    await expect(page.getByText(/Нет подключения к сети|You're offline/i).first()).not.toBeVisible()

    await page.waitForLoadState("networkidle")

    // Initially online: make sure the like button is visible first
    const likeBtn = page.getByRole("button", { name: /Like|Лайк|Нравится/i }).first()
    await expect(likeBtn).toBeVisible()

    // Trigger offline API state so the like request fails with a network error
    await mock.setApiOffline(true)

    // A like whose request fails with a network error is ambiguous: the server
    // may have applied it. Without durable idempotency the app must not queue it
    // for replay, so it rolls back instead (useNewsInteraction).
    const likeRequest = page.waitForRequest(
      (request) => request.method() === "POST" && /\/news\/[^/]+\/like$/u.test(request.url())
    )
    await likeBtn.click()
    await likeRequest

    const queuedNewsInteractions = () =>
      page.evaluate(
        () =>
          new Promise<number>((resolve) => {
            const request = indexedDB.open("notification-interactions")
            request.onsuccess = () => {
              const db = request.result
              if (!db.objectStoreNames.contains("pending-news-interactions")) {
                db.close()
                resolve(0)
                return
              }
              const count = db
                .transaction("pending-news-interactions", "readonly")
                .objectStore("pending-news-interactions")
                .count()
              count.onsuccess = () => {
                db.close()
                resolve(count.result)
              }
              count.onerror = () => resolve(-1)
            }
            request.onerror = () => resolve(-1)
          })
      )
    // Give any queueing path time to write before asserting it did not.
    await page.waitForTimeout(1500)
    expect(await queuedNewsInteractions()).toBe(0)

    // Now trigger UI offline mode by emulating navigator.onLine and offline event
    await page.evaluate(() => {
      Object.defineProperty(navigator, "onLine", { value: false, configurable: true })
      window.dispatchEvent(new Event("offline"))
    })

    // Assert that the offline banner is visible
    await expect(page.getByText(/Нет подключения к сети|You're offline/i).first()).toBeVisible({
      timeout: 10000,
    })

    // Restore online state
    await mock.setApiOffline(false)
    await page.evaluate(() => {
      Object.defineProperty(navigator, "onLine", { value: true, configurable: true })
      window.dispatchEvent(new Event("online"))
    })

    // Assert that the offline banner disappears
    await expect(page.getByText(/Нет подключения к сети|You're offline/i).first()).not.toBeVisible({
      timeout: 10000,
    })
  })
})
