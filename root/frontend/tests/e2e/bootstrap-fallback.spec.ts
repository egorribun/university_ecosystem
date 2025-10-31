import { test, expect } from "@playwright/test"

test.describe("bootstrap fallback", () => {
  test("shows fallback UI when bootstrap fails", async ({ page }) => {
    await page.addInitScript(() => {
      ;(
        window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean }
      ).__APP_BOOTSTRAP_FORCE_ERROR__ = true
    })

    await page.goto("/")

    await expect(
      page.getByRole("heading", { name: "Не удалось загрузить приложение" })
    ).toBeVisible()
    await expect(
      page.getByText("Попробуйте перезагрузить страницу или очистить кэш браузера", {
        exact: false,
      })
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Перезагрузить страницу" })).toBeVisible()
    await expect(page.getByRole("button", { name: "Очистить кэш и перезагрузить" })).toBeVisible()
  })
})
