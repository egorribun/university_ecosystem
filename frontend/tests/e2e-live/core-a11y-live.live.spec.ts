import AxeBuilder from "@axe-core/playwright"
import { expect, loginAs, test } from "./fixtures"
import { reportLiveAxeColorContrast } from "./live-ui-diagnostic"

const CORE_ROUTES = ["/dashboard", "/settings"] as const
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

test.use({ trace: "off", screenshot: "off", video: "off" })

test("real student dashboard and settings have no serious or critical axe findings", async ({
  page,
}, testInfo) => {
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

    let reportedContrastNodes = 0
    for (const violation of blocking) {
      if (violation.id !== "color-contrast") continue
      for (const node of violation.nodes) {
        if (reportedContrastNodes >= 4) break
        const contrastCheck = [...node.any, ...node.all, ...node.none].find(
          (check) => check.id === "color-contrast"
        )
        const data: unknown = contrastCheck?.data
        if (typeof data !== "object" || data === null || Array.isArray(data)) continue
        const contrastData = data as {
          fgColor?: unknown
          bgColor?: unknown
          contrastRatio?: unknown
        }
        reportLiveAxeColorContrast(
          testInfo.project.name,
          route === "/dashboard" ? "dashboard" : "settings",
          contrastData.fgColor,
          contrastData.bgColor,
          contrastData.contrastRatio
        )
        reportedContrastNodes += 1
      }
    }

    // Keep assertion diagnostics to rule identifiers; do not serialize axe nodes.
    expect(
      blocking.map(({ impact, id }) => `${impact}:${id}`),
      `${route} axe rules`
    ).toEqual([])
  }
})
