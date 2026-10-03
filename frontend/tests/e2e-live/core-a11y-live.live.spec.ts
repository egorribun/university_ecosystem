import AxeBuilder from "@axe-core/playwright"
import { expect, loginAs, test } from "./fixtures"

const CORE_ROUTES = ["/dashboard", "/settings"] as const
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

test.use({ trace: "off", screenshot: "off", video: "off" })

test("real student dashboard and settings have no serious or critical axe findings", async ({
  page,
}) => {
  await loginAs(page, "student")

  for (const route of CORE_ROUTES) {
    await page.goto(route)
    await expect(page.getByRole("main")).toBeVisible()
    await expect(page.locator("#main-content")).toBeVisible()
    if (route === "/settings") {
      await expect(page.getByRole("tablist")).toBeVisible()
    }

    const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
    const blocking = violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious"
    )

    // Report rule identifiers only; violation nodes may contain user-visible content.
    expect(
      blocking.map(({ impact, id }) => `${impact}:${id}`),
      `${route} axe rules`
    ).toEqual([])
  }
})
