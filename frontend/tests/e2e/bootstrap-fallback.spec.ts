import { test, expect } from "@playwright/test"

test.describe("bootstrap fallback", () => {
  test("shows fallback UI when bootstrap fails", async ({ page }) => {
    await page.addInitScript(() => {
      ;(
        window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean }
      ).__APP_BOOTSTRAP_FORCE_ERROR__ = true
      window.localStorage.setItem("ue:language", "ru")
    })

    await page.goto("/")

    await expect(
      page.getByRole("heading", { name: "Что-то пошло не так" })
    ).toBeVisible()
    await expect(
      page.getByText("Мы уже работаем над проблемой", {
        exact: false,
      })
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Перезагрузить страницу" })).toBeVisible()
    await expect(page.getByRole("button", { name: "Очистить кэш и перезагрузить" })).toBeVisible()
  })
})
