/**
 * Wave 11 — E2E: Error recovery & offline resilience.
 *
 * WHY: Network failure is the most common real-world error scenario. These
 * tests verify the app degrades gracefully (no white screen, no frozen UI)
 * when connectivity is lost and restored. This complements the existing
 * offline.spec.ts by specifically testing recovery transitions.
 */
import { test, expect, type Route } from "./test"
import type { Request } from "@playwright/test"
import { MOCK_NEWS_ID, useMockApi } from "./utils/mockApi"

test.describe("Error Recovery — Wave 11", () => {
  test("app remains visible when going offline", async ({ page, context }) => {
    await page.goto("/")
    await page.waitForLoadState("domcontentloaded")

    // Simulate network loss
    await context.setOffline(true)
    await page.evaluate(() => window.dispatchEvent(new Event("offline")))

    // The previously-rendered DOM must still be visible
    await expect(page.locator("body")).toBeVisible()

    await context.setOffline(false)
  })

  test("app recovers and remains functional after network restore", async ({ page, context }) => {
    const mock = await useMockApi(page)
    await mock.login(page)
    await page.goto("/news", { waitUntil: "domcontentloaded" })
    const articles = [
      { id: MOCK_NEWS_ID, title: "Новость дня" },
      { id: "22222222-2222-4222-8222-222222222222", title: "Библиотека открыта" },
    ]
    const firstArticle = page.getByRole("link", { name: articles[0]!.title, exact: true })
    await expect(firstArticle).toBeVisible()

    await context.setOffline(true)
    await page.evaluate(() => window.dispatchEvent(new Event("offline")))

    await context.setOffline(false)
    await page.evaluate(() => window.dispatchEvent(new Event("online")))

    await expect(firstArticle).toBeVisible()

    // Browser-intercepted API failures only: this does not exercise backend
    // fault injection, an SSR HTTP 500 document, or production CSP/axe acceptance.
    // Keep this inside the existing test and its existing timeout/retry budget.
    let phase: "fail" | "hold" | "success" = "fail"
    const requests: string[] = []
    const heldRoutes: Route[] = []
    await page.route(
      (url) =>
        ["", "/api", "/api/v1", "/v1"].some((prefix) =>
          articles.some(({ id }) => url.pathname === `${prefix}/news/${id}`)
        ),
      async (route) => {
        const request = route.request()
        // Never replace the document or TanStack route-data responses with JSON.
        if (
          request.method() !== "GET" ||
          !["fetch", "xhr"].includes(request.resourceType()) ||
          !(request.headers()["accept"] ?? "").includes("application/json")
        ) {
          return route.fallback()
        }
        requests.push(new URL(request.url()).pathname.split("/").at(-1)!)
        if (phase === "fail") {
          const origin = request.headers()["origin"]
          return route.fulfill({
            status: 500,
            headers: origin
              ? {
                  "Access-Control-Allow-Origin": origin,
                  "Access-Control-Allow-Credentials": "true",
                }
              : {},
            json: { detail: "SYNTHETIC_SERVER_DETAIL_MUST_NOT_RENDER" },
          })
        }
        if (phase === "hold") {
          heldRoutes.push(route)
          return
        }
        return route.fallback()
      }
    )

    const loadError = page.getByText("Не удалось загрузить новость.", { exact: true })
    const retry = page.getByRole("button", { name: "Попробовать снова", exact: true })
    const back = page.getByRole("button", { name: "Назад", exact: true })
    for (const [index, article] of articles.entries()) {
      phase = "fail"
      await page.getByRole("link", { name: article.title, exact: true }).click()
      await expect(page).toHaveURL((url) => url.pathname === `/news/${article.id}`)
      await expect(loadError).toBeVisible()
      await expect(page.getByText("SYNTHETIC_SERVER_DETAIL_MUST_NOT_RENDER")).toHaveCount(0)
      await expect(retry).toBeEnabled()
      await expect(back).toBeEnabled()
      for (const button of [retry, back]) {
        const bounds = await button.boundingBox()
        expect(bounds?.width).toBeGreaterThanOrEqual(44)
        expect(bounds?.height).toBeGreaterThanOrEqual(44)
      }
      await retry.focus()
      await page.keyboard.press("Tab")
      await expect(back).toBeFocused()
      await page.keyboard.press("Shift+Tab")
      await expect(retry).toBeFocused()

      // The loader and query retain their automatic retry policy. Count the
      // explicit retry separately after the terminal failure is visible.
      const countRequests = () => requests.filter((id) => id === article.id).length
      const failedRequests = countRequests()
      expect(failedRequests).toBeGreaterThanOrEqual(2)
      const heldBefore = heldRoutes.length
      phase = "hold"
      await page.keyboard.press("Enter")
      await expect.poll(() => heldRoutes.length).toBe(heldBefore + 1)
      await expect(retry).toHaveCount(0)
      await expect(page.locator('.news-theme [aria-busy="true"]').first()).toBeVisible()
      // A repeated keyboard activation while the request is pending must not
      // launch a second fetch or restore the terminal failure controls.
      await page.keyboard.press("Enter")
      expect(countRequests()).toBe(failedRequests + 1)
      const heldRoute = heldRoutes[heldBefore]!
      const heldRequest = heldRoute.request()
      const terminal: { state: "pending" | "finished" | "failed" } = { state: "pending" }
      const recordFinished = (request: Request) => {
        if (request === heldRequest) terminal.state = "finished"
      }
      const recordFailed = (request: Request) => {
        if (request === heldRequest) terminal.state = "failed"
      }
      // Register before Back can cancel this exact request. fallback() only
      // hands it to the next route handler; it is not a completion barrier.
      page.on("requestfinished", recordFinished)
      page.on("requestfailed", recordFailed)
      try {
        if (index === 1) {
          // Supersede the retry through real browser history before releasing it.
          // Cancellation is allowed; Forward must recover with fresh data.
          await page.goBack()
          await expect(page).toHaveURL(/\/news\/?$/u)
          await expect(firstArticle).toBeVisible()
        }
        phase = "success"
        await heldRoute.fallback()
        await expect.poll(() => terminal.state).not.toBe("pending")
        if (terminal.state === "failed") {
          expect(index).toBe(1)
          expect(heldRequest.failure()?.errorText).toMatch(
            /^(?:net::ERR_ABORTED|NS_BINDING_ABORTED)$|\bcancelled\b/iu
          )
        } else {
          expect((await heldRequest.response())?.status()).toBe(200)
        }
        if (index === 1) {
          // Let the completed XHR/query notification reach a rendering turn
          // before inspecting the superseding page, without a timed sleep.
          await page.evaluate(
            () =>
              new Promise<void>((resolve) => {
                requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
              })
          )
          await expect(page).toHaveURL(/\/news\/?$/u)
          await expect(firstArticle).toBeVisible()
          await expect(page.getByRole("heading", { level: 1, name: article.title })).toHaveCount(0)
          await expect(loadError).toHaveCount(0)
          await expect(retry).toHaveCount(0)
          await page.goForward()
        }
      } finally {
        page.off("requestfinished", recordFinished)
        page.off("requestfailed", recordFailed)
      }
      await expect(page).toHaveURL((url) => url.pathname === `/news/${article.id}`)
      await expect(page.getByRole("heading", { level: 1, name: article.title })).toBeVisible()
      await expect(loadError).toHaveCount(0)
      await expect(retry).toHaveCount(0)
      if (index === 0) expect(countRequests()).toBe(failedRequests + 1)
      await page.goBack()
      await expect(page).toHaveURL(/\/news\/?$/u)
      await expect(firstArticle).toBeVisible()
    }
  })

  test("no uncaught JS errors during offline→online transition", async ({ page, context }) => {
    const errors: string[] = []
    page.on("pageerror", (err) => {
      if (
        !err.message.includes("ResizeObserver") &&
        !err.message.includes("NetworkError") &&
        !err.message.includes("AbortError")
      ) {
        errors.push(err.message)
      }
    })

    await page.goto("/")
    await context.setOffline(true)
    await context.setOffline(false)

    expect(errors).toHaveLength(0)
  })

  test("404 route shows a non-blank page (not a crash)", async ({ page }) => {
    // WHY: Unmatched routes must render a 404 component, not a white screen or
    // an unhandled error boundary fallback that swallows the error silently.
    const errors: string[] = []
    page.on("pageerror", (err) => {
      if (!err.message.includes("ResizeObserver")) errors.push(err.message)
    })

    await page.goto("/definitely-does-not-exist-42xyz")
    await page.waitForLoadState("domcontentloaded")

    await expect(page.locator("body")).toBeVisible()
    const text = await page.locator("body").innerText()
    expect(text.trim().length).toBeGreaterThan(0)
    expect(errors).toHaveLength(0)
  })
})
