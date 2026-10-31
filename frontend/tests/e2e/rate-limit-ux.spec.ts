import { expect, test, type Route } from "./test"
import { useMockApi } from "./utils/mockApi"

const RETRIED_TITLE = "News after rate limit"
const NEWS_PAYLOAD = {
  items: [
    {
      id: "3e5a32b2-5f6c-48d9-a78b-d7be62512345",
      title: RETRIED_TITLE,
      content: "The news request succeeded after the limit was lifted.",
      created_at: "2026-06-27T10:00:00Z",
      image_url_optimized: null,
    },
  ],
  has_more: false,
  next_cursor: null,
}

const isNewsCollection = (url: URL) => /^\/(?:api\/(?:v1\/)?|v1\/)news\/?$/u.test(url.pathname)
const isNewsPageRequest = (route: Route) =>
  route.request().method() === "GET" &&
  /^\/news\/?$/u.test(new URL(route.request().frame().url()).pathname)

const corsHeaders = (route: Route): Record<string, string> => {
  const origin = route.request().headers()["origin"]
  return origin
    ? {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Expose-Headers": "Retry-After",
      }
    : {}
}

// The news UI has a generic load error and manual retry, not a 429 countdown.
// The API client automatically retries a 429 after the server's Retry-After.
test.describe("Rate limit UX", () => {
  test("a persistent 429 shows a load error and manual retry recovers", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    let allowSuccess = false
    let rejectedRequests = 0
    let successfulRequests = 0
    await page.route(isNewsCollection, async (route) => {
      if (!isNewsPageRequest(route)) return route.fallback()
      if (!allowSuccess) {
        rejectedRequests += 1
        return route.fulfill({
          status: 429,
          headers: { ...corsHeaders(route), "Retry-After": "0" },
          json: { detail: "Too Many Requests" },
        })
      }
      successfulRequests += 1
      return route.fulfill({ status: 200, headers: corsHeaders(route), json: NEWS_PAYLOAD })
    })

    await page.goto("/news", { waitUntil: "domcontentloaded" })
    const loadError = page
      .getByRole("alert")
      .filter({ hasText: /не удалось загрузить|failed to load/i })
    await expect(loadError).toBeVisible({ timeout: 30_000 })
    expect(rejectedRequests).toBeGreaterThanOrEqual(3)

    allowSuccess = true
    await loadError.getByRole("button", { name: /попробовать снова|try again/i }).click()
    await expect.poll(() => successfulRequests).toBeGreaterThan(0)
    await expect(page.getByText(RETRIED_TITLE, { exact: true })).toBeVisible()
  })

  test("retries a 429 after Retry-After and renders the successful response", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    const requests: { url: string; at: number }[] = []
    await page.route(isNewsCollection, async (route) => {
      if (!isNewsPageRequest(route)) return route.fallback()
      const url = new URL(route.request().url())
      requests.push({ url: url.pathname + url.search, at: Date.now() })
      if (requests.length === 1) {
        return route.fulfill({
          status: 429,
          headers: { ...corsHeaders(route), "Retry-After": "3" },
          json: { detail: "Too Many Requests" },
        })
      }
      return route.fulfill({ status: 200, headers: corsHeaders(route), json: NEWS_PAYLOAD })
    })

    await page.goto("/news", { waitUntil: "domcontentloaded" })
    await expect.poll(() => requests.length, { timeout: 15_000 }).toBeGreaterThanOrEqual(2)
    await expect(page.getByText(RETRIED_TITLE, { exact: true })).toBeVisible({ timeout: 20_000 })
    expect(requests[1]!.url).toBe(requests[0]!.url)
    expect(requests[1]!.at - requests[0]!.at).toBeGreaterThanOrEqual(2_700)
  })
})
