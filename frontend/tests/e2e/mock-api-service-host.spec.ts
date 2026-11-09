import { expect, test } from "./test"
import { validateResponseBody } from "../../src/tests/contractValidator"
import { useMockApi } from "./utils/mockApi"

test("mock API answers credentialed requests to the same-origin API base", async ({ page }) => {
  await useMockApi(page, { authenticated: false })
  await page.goto("/login")

  const result = await page.evaluate(async () => {
    const response = await fetch("/api/v1/news?limit=1", { credentials: "include" })
    return { ok: response.ok, status: response.status, body: await response.json() }
  })

  expect(result.ok).toBe(true)
  expect(result.status).toBe(200)
  expect(result.body).toHaveProperty("items")
})

test("the page CSP refuses a cross-origin API host", async ({ page }) => {
  // The app only calls its own origin. A request to another API host must be
  // stopped by connect-src before any mock or network sees it.
  await useMockApi(page, { authenticated: false })
  await page.goto("/login")

  const outcome = await page.evaluate(async () => {
    try {
      await fetch("http://api/v1/news?limit=1", { credentials: "include" }) // intentional cross-origin probe
      return "fetched"
    } catch (error) {
      return error instanceof TypeError ? "blocked" : "other"
    }
  })

  expect(outcome).toBe("blocked")
})

test("mock API provides a stable WebSocket for authenticated pages", async ({ page }) => {
  await useMockApi(page, { authenticated: false })
  await page.goto("/login")

  const opened = await page.evaluate(
    () =>
      new Promise<boolean>((resolve) => {
        const socket = new WebSocket("ws://api/ws/chat?ticket=mock-ws-ticket") // intentional local mock service-host test
        const finish = (value: boolean) => {
          clearTimeout(timeout)
          socket.close()
          resolve(value)
        }
        const timeout = setTimeout(() => finish(false), 1000)

        socket.addEventListener("open", () => finish(true), { once: true })
        socket.addEventListener("error", () => finish(false), { once: true })
      })
  )

  expect(opened).toBe(true)
})

test("mock API notification collections satisfy their declared contracts", async ({ page }) => {
  const mock = await useMockApi(page)
  mock.state.profile.role = "admin"
  await page.goto("/login")

  const responses = await page.evaluate(async () => {
    const notificationsResponse = await fetch("/api/v1/notifications")
    const deadLetterResponse = await fetch("/api/v1/notifications/admin/dead-letter")

    return {
      notifications: {
        status: notificationsResponse.status,
        body: (await notificationsResponse.json()) as unknown,
      },
      deadLetter: {
        status: deadLetterResponse.status,
        body: (await deadLetterResponse.json()) as unknown,
      },
    }
  })

  expect(responses.notifications.status).toBe(200)
  validateResponseBody({
    path: "/api/v1/notifications",
    method: "GET",
    statusCode: responses.notifications.status,
    body: responses.notifications.body,
  })
  expect(responses.notifications.body).toEqual({
    items: [],
    unread_count: 0,
    has_more: false,
    next_cursor: null,
  })

  expect(responses.deadLetter.status).toBe(200)
  expect(responses.deadLetter.body).toMatchObject({
    items: expect.any(Array),
    total: 2,
  })
  expect(Object.keys(responses.deadLetter.body as Record<string, unknown>).sort()).toEqual([
    "items",
    "total",
  ])
  const deadLetterItems = (responses.deadLetter.body as { items: unknown[] }).items
  expect(deadLetterItems).toHaveLength(2)
  for (const item of deadLetterItems) {
    expect(Object.keys(item as Record<string, unknown>).sort()).toEqual([
      "attempts",
      "claimed_at",
      "enqueued_at",
      "id",
      "kind",
      "last_error",
      "locale",
      "next_retry_at",
      "record_id",
    ])
  }
})

test("mock API rejects unauthenticated notification dead-letter access", async ({ page }) => {
  await useMockApi(page, { authenticated: false })
  await page.goto("/login")

  const response = await page.evaluate(async () => {
    const result = await fetch("/api/v1/notifications/admin/dead-letter")
    return { status: result.status, body: await result.json() }
  })

  expect(response).toEqual({ status: 401, body: { detail: "Unauthorized" } })
})
