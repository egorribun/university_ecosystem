import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { useMockApi } from "./utils/mockApi"

test.describe("Accessibility smoke", () => {
  test("dashboard has no critical axe violations and supports keyboard skip", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/dashboard", { waitUntil: "networkidle" })
    const skipLink = page.getByRole("link", { name: /content/i })
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("main")).toBeFocused()

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()

    expect(results.violations).toEqual([])
  })
})
