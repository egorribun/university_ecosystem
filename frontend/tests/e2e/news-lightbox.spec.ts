import { expect, test } from "./test"
import { MOCK_NEWS_ID, useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

for (const viewport of [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
]) {
  test(`closes the news image above the navbar at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const mock = await useMockApi(page)
    await mock.login(page)
    await gotoWithTransientRetry(page, `/news/${MOCK_NEWS_ID}`)

    const zoomName = /Открыть изображение|View full image/i
    await page.getByRole("button", { name: zoomName }).click()
    const dialog = page.getByRole("dialog", { name: zoomName })
    await dialog.getByRole("button", { name: /^(Закрыть|Close)$/i }).click()
    await expect(dialog).not.toBeVisible()
  })
}
