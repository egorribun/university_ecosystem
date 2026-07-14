import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test("mock API supports credentialed service-host requests", async ({ page }) => {
  await useMockApi(page)
  await page.goto("/login")

  const result = await page.evaluate(async () => {
    const response = await fetch("http://api/v1/news?limit=1", { credentials: "include" })
    return { ok: response.ok, status: response.status, body: await response.json() }
  })

  expect(result.ok).toBe(true)
  expect(result.status).toBe(200)
  expect(result.body).toHaveProperty("items")
})
