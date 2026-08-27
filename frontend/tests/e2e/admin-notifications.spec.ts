import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

test.describe("Admin notification queue", () => {
  test("allows admins to retry and purge dead-letter jobs", async ({ page }) => {
    const mock = await useMockApi(page)
    mock.state.profile.role = "admin"

    await mock.login(page)
    await page.waitForLoadState("networkidle")

    // The explicit E2E SSR marker intentionally models a student. Enter the
    // admin route through the hydrated router so this scenario exercises the
    // admin profile returned by the hermetic API fixture.
    await page
      .getByRole("button", {
        name: /Дополнительная навигация|Открыть меню|Additional navigation|Open menu/i,
      })
      .click()
    await page.getByRole("menuitem", { name: /Очередь уведомлений|Notification queue/i }).click()
    await page.waitForURL(/\/admin\/notifications$/)

    await expect(
      page.getByRole("heading", { name: /Очередь уведомлений|Notification queue/i })
    ).toBeVisible({
      timeout: 15000,
    })
    const firstCheckbox = page.getByRole("checkbox", {
      name: /Выбрать задачу 33333333-3333-4333-8333-333333333331|Select job 33333333-3333-4333-8333-333333333331/i,
    })
    await firstCheckbox.check()

    await page.getByRole("button", { name: /Повторить выбранные|Retry selected/i }).click()
    await expect(page.getByText("Timeout")).not.toBeVisible()
    await expect(page.getByText(/Всего задач: 1|Total jobs: 1/i)).toBeVisible()

    const secondCheckbox = page.getByRole("checkbox", {
      name: /Выбрать задачу 33333333-3333-4333-8333-333333333332|Select job 33333333-3333-4333-8333-333333333332/i,
    })
    await secondCheckbox.check()
    await page.getByRole("button", { name: /Удалить выбранные|Delete selected/i }).click()

    await expect(
      page.getByText(/В отложенной очереди нет задач|No dead-lettered jobs/i)
    ).toBeVisible()
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
