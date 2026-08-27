import { expect, test } from "./test"
import { promises as fs } from "node:fs"

import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

test.describe("Schedule export", () => {
  test("downloads the rendered schedule as a PNG file", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/schedule")
    await expect(page).toHaveURL(/\/schedule$/)
    await page.getByRole("tab", { name: /Сб|Sat/i }).click()
    await expect(page.getByText(/Математика|Mathematics/i).first()).toBeVisible()

    // The navbar has a separate Settings button. Scope to the schedule main
    // landmark to select the schedule toolbar control unambiguously.
    await page
      .locator("#main-content")
      .getByRole("button", { name: /Настройки|Settings/i })
      .click()
    await page.getByRole("button", { name: /Экспорт|Export/i }).click()
    const downloadPromise = page.waitForEvent("download")
    await page.getByRole("menuitem", { name: /Изображение \(PNG\)|Image \(PNG\)/i }).click()
    const download = await downloadPromise

    expect(download.suggestedFilename()).toBe("schedule.png")
    const filePath = await download.path()
    expect(filePath).toBeTruthy()
    if (filePath) {
      const content = await fs.readFile(filePath)
      expect(content.subarray(0, 8)).toEqual(
        Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
      )
    }
  })
})
