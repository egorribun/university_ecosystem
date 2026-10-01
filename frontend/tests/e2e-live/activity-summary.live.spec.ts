import type { Locator } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"

async function expectPeriodIndicatorToMatchRadio(
  indicator: Locator,
  selectedRadio: Locator,
  periodLabel: string
) {
  await expect
    .poll(
      async () => {
        const [indicatorBox, radioBox] = await Promise.all([
          indicator.boundingBox(),
          selectedRadio.boundingBox(),
        ])
        if (!indicatorBox || !radioBox) return false

        return (
          Math.abs(indicatorBox.x - radioBox.x) <= 1 &&
          Math.abs(indicatorBox.y - radioBox.y) <= 1 &&
          Math.abs(indicatorBox.width - radioBox.width) <= 1 &&
          Math.abs(indicatorBox.height - radioBox.height) <= 1
        )
      },
      { message: `${periodLabel} indicator should match the selected period control bounds` }
    )
    .toBe(true)
}

test("seeded student can view Activity summaries, change the period, and restore it after reload", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/activity")

  await expect(page.getByRole("heading", { name: /Активность|Activity/u })).toBeVisible()

  const periodSelector = page.getByRole("radiogroup", {
    name: /Выберите период для статистики активности|Select time period for activity statistics/u,
  })
  const period90Days = periodSelector.getByRole("radio", { name: /90 дней|90 days/u })
  const period30Days = periodSelector.getByRole("radio", { name: /30 дней|30 days/u })
  const periodIndicator = periodSelector.locator(":scope > span[aria-hidden='true']")

  await expect(
    page.getByRole("group", { name: /Статистика посещаемости|Attendance statistics/u })
  ).toBeVisible()
  await expect(
    page.getByRole("group", { name: /Статистика оценок|Grade statistics/u })
  ).toBeVisible()
  await expect(
    page.getByRole("group", { name: /Статистика участия|Participation statistics/u })
  ).toBeVisible()
  await expect(period90Days).toHaveAttribute("aria-checked", "true")
  await expectPeriodIndicatorToMatchRadio(periodIndicator, period90Days, "90-day")

  const summaryResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      response.request().method() === "GET" &&
      url.pathname.endsWith("/api/v1/stats/summary") &&
      url.searchParams.get("period") === "30d"
    )
  })
  await period30Days.click()

  await expect(period30Days).toHaveAttribute("aria-checked", "true")
  await expect(page).toHaveURL(/(?:\?|&)p=30d(?:&|$)/u)
  await expectPeriodIndicatorToMatchRadio(periodIndicator, period30Days, "30-day")
  const summaryResponse = await summaryResponsePromise
  expect(summaryResponse.ok()).toBe(true)

  const reloadSummaryResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      response.request().method() === "GET" &&
      url.pathname.endsWith("/api/v1/stats/summary") &&
      url.searchParams.get("period") === "30d"
    )
  })
  await page.reload()

  await expect(page).toHaveURL(/(?:\?|&)p=30d(?:&|$)/u)
  const reloadedPeriodSelector = page.getByRole("radiogroup", {
    name: /Выберите период для статистики активности|Select time period for activity statistics/u,
  })
  await expect(
    reloadedPeriodSelector.getByRole("radio", { name: /30 дней|30 days/u })
  ).toHaveAttribute("aria-checked", "true")

  const reloadSummaryResponse = await reloadSummaryResponsePromise
  expect(reloadSummaryResponse.ok()).toBe(true)
})
