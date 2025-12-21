import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("Visual regression tests", () => {
    test("dashboard page matches snapshot", async ({ page }) => {
        const { login } = await useMockApi(page)
        await login(page)

        // Wait for animations to settle
        await page.waitForTimeout(1000)

        await expect(page).toHaveScreenshot("dashboard.png", {
            maxDiffPixelRatio: 0.05,
            animations: "disabled"
        })
    })

    test("news page matches snapshot", async ({ page }) => {
        const { login } = await useMockApi(page)
        await login(page)

        await page.getByRole("link", { name: "Новости" }).first().click()
        await page.waitForURL(/\/news$/)
        await page.waitForTimeout(500)

        await expect(page).toHaveScreenshot("news-list.png", {
            maxDiffPixelRatio: 0.05,
            animations: "disabled"
        })
    })

    test("schedule page matches snapshot", async ({ page }) => {
        const { login } = await useMockApi(page)
        await login(page)

        await page.getByRole("link", { name: "Расписание" }).first().click()
        await page.waitForURL(/\/schedule$/)
        await page.waitForTimeout(500)

        await expect(page).toHaveScreenshot("schedule.png", {
            maxDiffPixelRatio: 0.05,
            animations: "disabled"
        })
    })
})
