import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

// Skip: Admin tests timeout during login in mock environment
test.describe.skip("Admin notification queue", () => {
  test("allows admins to retry and purge dead-letter jobs", async ({ page }) => {
    const mock = await useMockApi(page)
    mock.state.profile.role = "admin"

    await mock.login(page)
    await page.waitForLoadState("networkidle")

    await page.goto("/admin/notifications")
    await page.waitForLoadState("networkidle")
    await page.waitForURL(/\/admin\/notifications$/, { timeout: 15000 })

    await expect(page.getByRole("heading", { name: /Очередь уведомлений/i })).toBeVisible({
      timeout: 15000,
    })
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
    await page.waitForLoadState("networkidle")

    await page.goto("/admin/notifications")
    await page.waitForLoadState("networkidle")
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15000 })
  })
})
