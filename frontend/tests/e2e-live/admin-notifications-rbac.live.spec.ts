import { randomUUID } from "node:crypto"
import { expect, loginAs, test } from "./fixtures"

const DEAD_LETTER_ENDPOINT = "/api/v1/notifications/admin/dead-letter?limit=20&offset=0"

test("admin can read the seeded notification queue without changing it", async ({ page }) => {
  await loginAs(page, "admin")

  await page.goto("/admin/notifications")
  await expect(page).toHaveURL(/\/admin\/notifications$/u)
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: /Notification queue|Очередь уведомлений/u,
    })
  ).toBeVisible()
  await expect(
    page.getByRole("table", { name: /Dead-letter queue|Отложенные уведомления/u })
  ).toBeVisible()

  const response = await page.request.get(DEAD_LETTER_ENDPOINT)
  expect(
    response.status(),
    "admin GET /api/v1/notifications/admin/dead-letter should be allowed"
  ).toBe(200)
  const body = (await response.json()) as { items: unknown[]; total: number }
  expect(Array.isArray(body.items), "queue response includes items").toBe(true)
  expect(body.items.length, "the seeded read-only queue has visible records").toBeGreaterThan(0)
  expect(Number.isInteger(body.total), "queue response includes a total").toBe(true)
  expect(body.items.length).toBeLessThanOrEqual(body.total)
})

for (const role of ["student", "teacher"] as const) {
  test(`${role} cannot view or mutate notification queue data`, async ({ page }) => {
    await loginAs(page, role)

    const identity = await page.request.get("/api/v1/users/me")
    expect(identity.status(), `${role} fixture is authenticated`).toBe(200)
    expect((await identity.json()).role, `${role} fixture has the expected role`).toBe(role)

    await page.goto("/admin/notifications")
    await expect(
      page,
      `${role} should be redirected from /admin/notifications to /dashboard`
    ).toHaveURL(/\/dashboard$/u)
    await expect(
      page.getByRole("heading", { name: /Notification queue|Очередь уведомлений/u })
    ).toHaveCount(0)

    await page.reload()
    await page.goto("/admin/notifications")
    await expect(
      page,
      `${role} remains denied after reload and a direct admin URL retry`
    ).toHaveURL(/\/dashboard$/u)

    const response = await page.request.get(DEAD_LETTER_ENDPOINT)
    expect(response.status(), `${role} GET /api/v1/notifications/admin/dead-letter status`).toBe(
      403
    )

    const csrfToken = await page.evaluate(() => {
      const prefix = "csrf_token="
      const cookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith(prefix))
      return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : ""
    })
    expect(csrfToken, `${role} session has a CSRF token for safe authorization checks`).not.toBe("")

    const syntheticJobId = randomUUID()
    for (const action of ["retry", "purge"] as const) {
      const actionPath = `/api/v1/notifications/admin/dead-letter/${action}`
      const actionResponse = await page.request.post(actionPath, {
        data: { job_ids: [syntheticJobId] },
        headers: { "X-CSRF-Token": csrfToken },
      })
      expect(actionResponse.status(), `POST ${actionPath} must be forbidden`).toBe(403)
    }
  })
}
