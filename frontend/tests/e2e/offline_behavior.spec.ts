import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

test.describe("SPA Offline Banner & IndexedDB Queueing", () => {
  test("shows reconnect banner and queues likes in IndexedDB offline store", async ({ page }) => {
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

    // Click the like button on the first news card while navigator is still online
    // to bypass TanStack Query mutation pausing and trigger handleMutationError
    await likeBtn.click()

    interface QueuedItem {
      url: string
      method: string
    }

    // Retrieve pending items from IndexedDB with retry/polling to prevent race conditions
    let queuedItems: QueuedItem[] = []
    const startTime = Date.now()
    while (queuedItems.length === 0 && Date.now() - startTime < 5000) {
      queuedItems = await page.evaluate(async () => {
        return new Promise<QueuedItem[]>((resolve) => {
          const request = indexedDB.open("notification-interactions", 3)
          request.onupgradeneeded = () => {
            const db = request.result
            if (!db.objectStoreNames.contains("pending-navigations")) {
              db.createObjectStore("pending-navigations", { keyPath: "id", autoIncrement: true })
            }
            if (!db.objectStoreNames.contains("pending-reports")) {
              db.createObjectStore("pending-reports", { keyPath: "id", autoIncrement: true })
            }
            if (!db.objectStoreNames.contains("pending-news-interactions")) {
              db.createObjectStore("pending-news-interactions", {
                keyPath: "id",
                autoIncrement: true,
              })
            }
          }
          request.onsuccess = () => {
            const db = request.result
            if (!db.objectStoreNames.contains("pending-news-interactions")) {
              resolve([])
              return
            }
            try {
              const tx = db.transaction("pending-news-interactions", "readonly")
              const store = tx.objectStore("pending-news-interactions")
              const getAll = store.getAll()
              getAll.onsuccess = () => resolve(getAll.result)
              getAll.onerror = () => resolve([])
            } catch {
              resolve([])
            }
          }
          request.onerror = () => resolve([])
        })
      })
      if (queuedItems.length === 0) {
        await page.waitForTimeout(100)
      }
    }

    // Assert that the news like event is successfully queued
    expect(queuedItems.length).toBeGreaterThan(0)
    const item = queuedItems[0]!
    expect(item.url).toContain("/news/")
    expect(item.method).toBe("POST")

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
