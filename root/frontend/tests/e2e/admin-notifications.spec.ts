import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("Admin notification queue", () => {
  test("allows admins to retry and purge dead-letter jobs", async ({ page }) => {
    const mock = await useMockApi(page)
    mock.state.profile.role = "admin"

    await mock.login(page)

    await page.getByRole("link", { name: "Очередь уведомлений" }).click()
    await page.waitForURL(/\/admin\/notifications$/)

    await expect(page.getByRole("heading", { name: /Очередь уведомлений/i })).toBeVisible()
    const firstCheckbox = page.getByRole("checkbox", { name: "Выбрать задачу 1" })
    await firstCheckbox.check()

    await page.getByRole("button", { name: "Повторить выбранные" }).click()
    await expect(page.getByText("Timeout")).not.toBeVisible()
    await expect(page.getByText("Всего задач: 1")).toBeVisible()

    const secondCheckbox = page.getByRole("checkbox", { name: "Выбрать задачу 2" })
    await secondCheckbox.check()
    await page.getByRole("button", { name: "Удалить выбранные" }).click()

    await expect(page.getByText("В отложенной очереди нет задач.")).toBeVisible()
  })

  test("redirects non-admin users away from the queue", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/admin/notifications")
    await expect(page).toHaveURL(/\/dashboard$/)
  })
})
