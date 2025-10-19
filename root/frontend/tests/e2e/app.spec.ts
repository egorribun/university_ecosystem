import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("University ecosystem app", () => {
  test("allows a student to login and reach the dashboard", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await expect(page.getByText(/Иван!/)).toBeVisible()
    const newsLink = page.getByRole("link", { name: "Новости" }).first()
    await expect(newsLink).toBeVisible()
  })

  test("supports navigation between main sections", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.getByRole("link", { name: "Смотреть все новости" }).click()
    await expect(page).toHaveURL(/\/news$/)
    await expect(page.getByText("Новости Университета")).toBeVisible()

    await page.getByRole("link", { name: "На главную" }).first().click()
    await expect(page).toHaveURL(/\/dashboard$/)

    await page.getByRole("link", { name: "Перейти к полному расписанию" }).click()
    await expect(page).toHaveURL(/\/schedule$/)
    await expect(page.getByText("Расписание моей группы")).toBeVisible()
  })

  test("caches news responses using ETag", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.getByRole("link", { name: "Смотреть все новости" }).click()
    await expect(page.getByText("Новость дня")).toBeVisible()

    const cached = await page.evaluate(() => localStorage.getItem("news:list:ru"))
    expect(cached).not.toBeNull()

    await page.reload()
    await expect(page.getByText("Новость дня")).toBeVisible()

    expect(mock.state.newsLog.some((entry) => entry.status === 304)).toBeTruthy()
    expect(mock.state.newsLog.filter((entry) => entry.status === 200).length).toBeGreaterThan(0)
  })

  test("reuses cached news data when the API is offline", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.getByRole("link", { name: "Смотреть все новости" }).click()
    await expect(page.getByText("Новость дня")).toBeVisible()

    mock.goOffline(true)
    await page.reload()

    await expect(page.getByText("Новость дня")).toBeVisible()
    expect(mock.state.newsLog.some((entry) => entry.status === 503)).toBeTruthy()
  })

  test("allows revoking secondary sessions from settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings")
    await page.waitForURL(/\/settings$/)

    await page.getByRole("tab", { name: "Аккаунт" }).click()

    await expect(page.getByText("Устройства и сессии")).toBeVisible()
    const revokeButton = await page.getByRole("button", { name: "Завершить" })
    await revokeButton.click()

    await expect(page.getByText("Сессия завершена")).toBeVisible()
    await expect(page.getByText("Завершена")).toBeVisible()
  })
})
