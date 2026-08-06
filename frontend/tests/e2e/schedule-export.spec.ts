import { expect, test } from "./test"
import { promises as fs } from "fs"

import { useMockApi } from "./utils/mockApi"

test.describe("Schedule export", () => {
  test.skip("allows downloading the schedule as an iCal file", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/schedule")
    await expect(page).toHaveURL(/\/schedule$/)

    const downloadPromise = page.waitForEvent("download")
    await page.getByRole("link", { name: "Экспорт в календарь" }).click()
    const download = await downloadPromise

    expect(download.suggestedFilename()).toMatch(/schedule-iu-21\.ics$/)
    const filePath = await download.path()
    expect(filePath).toBeTruthy()
    if (filePath) {
      const content = await fs.readFile(filePath, "utf-8")
      expect(content).toContain("BEGIN:VCALENDAR")
      expect(content).toContain("SUMMARY:Математика")
    }
  })
})
