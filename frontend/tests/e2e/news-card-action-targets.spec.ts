import { expect, test } from "./test"

import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"
import { assertControlTarget } from "./utils/targetSize"

test.use({ reducedMotion: "reduce", serviceWorkers: "block" })

for (const width of [360, 390, 768, 1440]) {
  for (const action of [
    { label: "like", name: /^Like \d+$/u },
    { label: "bookmark", name: "Bookmark" },
  ]) {
    test(`news card ${action.label} has a reachable 44px target at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 844 })
      await useMockApi(page, { language: "en" })
      await gotoWithTransientRetry(page, "/news")

      const card = page.getByTestId("news-card").filter({ hasText: "News of the day" })
      const button = card.getByRole("button", { name: action.name, exact: true })
      await assertControlTarget(button, `${width}px news card ${action.label}`)
      await button.click({ trial: true })

      const overflow = await page.evaluate(() => {
        const root = document.documentElement
        return root.scrollWidth - root.clientWidth
      })
      expect(overflow).toBeLessThanOrEqual(0)
    })
  }
}
