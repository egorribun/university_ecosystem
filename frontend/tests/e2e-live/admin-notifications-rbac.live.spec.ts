import { randomUUID } from "node:crypto"
import { expect, loginAs, test } from "./fixtures"
import { reportLiveAdminQueueState } from "./live-ui-diagnostic"

const DEAD_LETTER_ENDPOINT = "/api/v1/notifications/admin/dead-letter?limit=20&offset=0"

test("admin can read the seeded notification queue without changing it", async ({
  page,
}, testInfo) => {
  await loginAs(page, "admin")

  await page.goto("/admin/notifications")
  await expect(page).toHaveURL(/\/admin\/notifications$/u)
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: /Notification queue|Очередь уведомлений/u,
    })
  ).toBeVisible()

  const queueTable = page.getByRole("table", { name: /Dead-letter queue|Отложенные уведомления/u })
  let status = 0
  let itemsAreArray = false
  let itemCount = 0
  let totalIsInteger = false
  try {
    const response = await page.request.get(DEAD_LETTER_ENDPOINT)
    status = response.status()
    const body = (await response.json()) as { items: unknown[]; total: number }
    itemsAreArray = Array.isArray(body.items)
    itemCount = itemsAreArray ? body.items.length : 0
    totalIsInteger = Number.isInteger(body.total)

    expect(status, "admin GET /api/v1/notifications/admin/dead-letter should be allowed").toBe(200)
    expect(itemsAreArray, "queue response includes items").toBe(true)
    expect(itemCount, "the seeded read-only queue has visible records").toBeGreaterThan(0)
    expect(totalIsInteger, "queue response includes a total").toBe(true)
    expect(itemCount).toBeLessThanOrEqual(body.total)
    await expect(queueTable).toBeVisible()
  } catch (error) {
    const [tableVisible, progressbarVisible, alertVisible, rowCount] = await Promise.all([
      queueTable.isVisible().catch(() => false),
      page
        .getByRole("progressbar")
        .isVisible()
        .catch(() => false),
      page
        .getByRole("alert")
        .first()
        .isVisible()
        .catch(() => false),
      queueTable
        .getByRole("row")
        .count()
        .catch(() => 0),
    ])
    reportLiveAdminQueueState(
      testInfo.project.name,
      status,
      itemsAreArray,
      itemCount,
      totalIsInteger,
      tableVisible,
      progressbarVisible,
      alertVisible,
      rowCount
    )
    throw error
  }
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
