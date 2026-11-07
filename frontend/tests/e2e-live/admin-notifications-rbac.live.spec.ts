import { randomUUID } from "node:crypto"
import { expect, loginAs, test } from "./fixtures"
import { reportLiveAdminQueueState } from "./live-ui-diagnostic"

const DEAD_LETTER_PATH = "/api/v1/notifications/admin/dead-letter"
const DEAD_LETTER_ENDPOINT = "/api/v1/notifications/admin/dead-letter?limit=20&offset=0"

const queueRecordIds = (items: unknown): string[] => {
  if (!Array.isArray(items) || items.length > 20) {
    throw new Error("Invalid bounded notification queue page")
  }
  return items.map((item: unknown) => {
    const recordId =
      typeof item === "object" && item !== null && !Array.isArray(item)
        ? (item as Record<string, unknown>).record_id
        : undefined
    if (
      typeof recordId !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu.test(recordId)
    ) {
      throw new Error("Invalid notification queue record identity")
    }
    return recordId
  })
}

test("admin can read the seeded notification queue without changing it", async ({
  page,
}, testInfo) => {
  await loginAs(page, "admin")
  const expectedOrigin = new URL(page.url()).origin

  const browserQueueResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      response.request().method() === "GET" &&
      url.origin === expectedOrigin &&
      url.pathname === DEAD_LETTER_PATH &&
      url.searchParams.get("limit") === "20" &&
      url.searchParams.get("offset") === "0"
    )
  })

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
    const response = await browserQueueResponsePromise
    status = response.status()
    const payload: unknown = await response.json()
    const body =
      typeof payload === "object" && payload !== null && !Array.isArray(payload)
        ? (payload as Record<string, unknown>)
        : undefined
    const items = body?.items
    const total = body?.total
    if (Array.isArray(items)) {
      itemsAreArray = true
      itemCount = items.length
    }
    totalIsInteger = typeof total === "number" && Number.isInteger(total) && total >= 0

    expect(status, "browser GET /api/v1/notifications/admin/dead-letter should be allowed").toBe(
      200
    )
    expect(itemsAreArray, "queue response includes items").toBe(true)
    expect(totalIsInteger, "queue response includes a non-negative integer total").toBe(true)
    const totalCount = typeof total === "number" ? total : 0
    expect(itemCount).toBeLessThanOrEqual(totalCount)

    const emptyStateAlert = page.getByRole("alert").filter({
      hasText: /No dead-lettered jobs at the moment\.|В отложенной очереди нет задач\./u,
    })
    const fetchErrorAlert = page
      .getByRole("alert")
      .filter({ hasText: /Failed to load the dead-letter queue\.|Не удалось загрузить очередь\./u })
    await expect(fetchErrorAlert).toHaveCount(0)

    if (itemCount === 0) {
      expect(totalCount, "an empty queue has a zero total").toBe(0)
      await expect(emptyStateAlert).toBeVisible()
      await expect(queueTable).toHaveCount(0)
    } else {
      await expect(emptyStateAlert).toHaveCount(0)
      await expect(queueTable).toBeVisible()
      await expect(queueTable.getByRole("row")).toHaveCount(itemCount + 1)
    }

    expect(totalCount, "owned queue pagination fixture includes a second page").toBeGreaterThan(20)
    expect(itemCount).toBe(20)
    const firstRecordIds = queueRecordIds(items)
    expect(new Set(firstRecordIds).size).toBe(20)
    for (const recordId of firstRecordIds) {
      await expect(queueTable.getByRole("cell", { name: recordId, exact: true })).toBeVisible()
    }
    const previousPage = page.getByRole("button", { name: /^(Go to previous page|Назад)$/u })
    const nextPage = page.getByRole("button", { name: /^(Go to next page|Вперед)$/u })
    await expect(previousPage).toBeDisabled()
    await expect(nextPage).toBeEnabled()
    const [secondResponse] = await Promise.all([
      page.waitForResponse((response) => {
        const url = new URL(response.url())
        return (
          response.request().method() === "GET" &&
          url.origin === expectedOrigin &&
          url.pathname === DEAD_LETTER_PATH &&
          url.searchParams.get("limit") === "20" &&
          url.searchParams.get("offset") === "20"
        )
      }),
      nextPage.click(),
    ])
    expect(secondResponse.status()).toBe(200)
    const secondPayload: unknown = await secondResponse.json()
    const secondBody =
      typeof secondPayload === "object" && secondPayload !== null && !Array.isArray(secondPayload)
        ? (secondPayload as Record<string, unknown>)
        : undefined
    expect(secondBody?.total).toBe(totalCount)
    const secondRecordIds = queueRecordIds(secondBody?.items)
    expect(secondRecordIds.length).toBe(Math.min(20, totalCount - 20))
    expect(new Set(secondRecordIds).size).toBe(secondRecordIds.length)
    const firstPageIds = new Set(firstRecordIds)
    expect(secondRecordIds.every((id) => !firstPageIds.has(id))).toBe(true)
    await expect(queueTable.getByRole("row")).toHaveCount(secondRecordIds.length + 1)
    for (const recordId of secondRecordIds) {
      await expect(queueTable.getByRole("cell", { name: recordId, exact: true })).toBeVisible()
    }
    for (const recordId of firstRecordIds) {
      await expect(queueTable.getByRole("cell", { name: recordId, exact: true })).toHaveCount(0)
    }
    await expect(previousPage).toBeEnabled()
    await previousPage.click()
    // A valid cached first page need not trigger a redundant network request.
    await expect(previousPage).toBeDisabled()
    await expect(queueTable.getByRole("row")).toHaveCount(21)
    for (const recordId of firstRecordIds) {
      await expect(queueTable.getByRole("cell", { name: recordId, exact: true })).toBeVisible()
    }
    for (const recordId of secondRecordIds) {
      await expect(queueTable.getByRole("cell", { name: recordId, exact: true })).toHaveCount(0)
    }
    await expect(fetchErrorAlert).toHaveCount(0)
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
