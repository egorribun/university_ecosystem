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

// The production build calls `/api/v1/news`; the Vite dev server calls bare `/news`.
const NEWS_COLLECTION_PREFIXES = ["", "/api", "/api/v1", "/v1"]
const isNewsCollection = (url: URL) =>
  NEWS_COLLECTION_PREFIXES.some((prefix) =>
    [`${prefix}/news`, `${prefix}/news/`].includes(url.pathname)
  )
// Only the page's script-initiated list fetch is limited; the document load is not.
const isNewsPageRequest = (route: Route) =>
  route.request().method() === "GET" &&
  ["fetch", "xhr"].includes(route.request().resourceType()) &&
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

    // Measure in the browser: delays in the Playwright route handler must not
    // make a prematurely dispatched retry look as though it respected the limit.
    await page.addInitScript(() => {
      const urls = new WeakMap<XMLHttpRequest, string>()
      const timings: {
        url: string
        sentAt: number
        sentWallAt: number
        responseAt: number
        responseWallAt: number
        status: number
      }[] = []
      Object.defineProperty(window, "__audit321XhrTimings", { value: timings })

      XMLHttpRequest.prototype.open = new Proxy(XMLHttpRequest.prototype.open, {
        apply(target, xhr: XMLHttpRequest, args: unknown[]) {
          if (typeof args[0] === "string" && args[0].toUpperCase() === "GET") {
            if (typeof args[1] === "string") urls.set(xhr, args[1])
          }
          return Reflect.apply(target, xhr, args)
        },
      })
      XMLHttpRequest.prototype.send = new Proxy(XMLHttpRequest.prototype.send, {
        apply(target, xhr: XMLHttpRequest, args: unknown[]) {
          const url = urls.get(xhr)
          if (url) {
            const entry = {
              url,
              sentAt: performance.now(),
              sentWallAt: Date.now(),
              responseAt: -1,
              responseWallAt: 0,
              status: 0,
            }
            timings.push(entry)
            xhr.addEventListener(
              "load",
              () => {
                entry.responseAt = performance.now()
                entry.responseWallAt = Date.now()
                entry.status = xhr.status
              },
              { once: true }
            )
          }
          return Reflect.apply(target, xhr, args)
        },
      })
    })

    const requests: string[] = []
    await page.route(isNewsCollection, async (route) => {
      if (!isNewsPageRequest(route)) return route.fallback()
      const url = new URL(route.request().url())
      requests.push(url.pathname + url.search)
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
    expect(requests).toHaveLength(2)
    expect(requests[1]).toBe(requests[0])
    const observed = await page.evaluate(
      () =>
        (
          window as typeof window & {
            __audit321XhrTimings: {
              url: string
              sentAt: number
              sentWallAt: number
              responseAt: number
              responseWallAt: number
              status: number
            }[]
          }
        ).__audit321XhrTimings
    )
    const newsRequests = observed.filter((entry) =>
      isNewsCollection(new URL(entry.url, page.url()))
    )
    expect(newsRequests).toHaveLength(2)
    expect(newsRequests.map((entry) => entry.status)).toEqual([429, 200])
    expect(newsRequests[0]!.responseAt).toBeGreaterThanOrEqual(0)
    expect(newsRequests[0]!.responseWallAt).toBeGreaterThan(0)
    const monotonicRetryDelayMs = newsRequests[1]!.sentAt - newsRequests[0]!.responseAt
    const wallClockRetryDelayMs = newsRequests[1]!.sentWallAt - newsRequests[0]!.responseWallAt
    await test.info().attach("retry-after-timing", {
      body: JSON.stringify({
        retryAfterSeconds: 3,
        monotonicRetryDelayMs,
        wallClockRetryDelayMs,
        statuses: newsRequests.map((entry) => entry.status),
      }),
      contentType: "application/json",
    })
    // The limiter computes its deadline from Date.now(), so compare the
    // timestamps in that same (possibly quantized) clock. The independent
    // monotonic check bounds a wall-clock jump and allows 100 ms of precision.
    expect(wallClockRetryDelayMs).toBeGreaterThanOrEqual(3_000)
    expect(monotonicRetryDelayMs).toBeGreaterThanOrEqual(2_900)
  })
})
