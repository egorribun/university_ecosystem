import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

test("mock API supports credentialed service-host requests", async ({ page }) => {
  await useMockApi(page)
  await page.goto("/login")

  const result = await page.evaluate(async () => {
    const response = await fetch("http://api/v1/news?limit=1", { credentials: "include" }) // nosemgrep: typescript.react.security.react-insecure-request.react-insecure-request -- intentional local mock service-host test
    return { ok: response.ok, status: response.status, body: await response.json() }
  })

  expect(result.ok).toBe(true)
  expect(result.status).toBe(200)
  expect(result.body).toHaveProperty("items")
})

test("mock API provides a stable WebSocket for authenticated pages", async ({ page }) => {
  await useMockApi(page)
  await page.goto("/login")

  const opened = await page.evaluate(
    () =>
      new Promise<boolean>((resolve) => {
        const socket = new WebSocket("ws://api/ws/chat?ticket=mock-ws-ticket") // nosemgrep: javascript.lang.security.detect-insecure-websocket.detect-insecure-websocket -- intentional local mock service-host test
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
