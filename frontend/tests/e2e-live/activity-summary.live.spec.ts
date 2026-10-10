import type { Locator, Page } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"
import { reportLiveActivityGeometry } from "./live-ui-diagnostic"

async function expectPeriodIndicatorToMatchRadio(
  indicator: Locator,
  selectedRadio: Locator,
  periodLabel: "30-day" | "90-day",
  project: string
) {
  try {
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
  } catch (error) {
    const [indicatorBox, radioBox] = await Promise.all([
      indicator.boundingBox().catch(() => null),
      selectedRadio.boundingBox().catch(() => null),
    ])
    const deltaMilliPixels = (
      indicatorValue: number | undefined,
      radioValue: number | undefined
    ) =>
      indicatorValue === undefined || radioValue === undefined
        ? 0
        : Math.round((indicatorValue - radioValue) * 1000)

    reportLiveActivityGeometry(
      project,
      periodLabel,
      indicatorBox !== null,
      radioBox !== null,
      deltaMilliPixels(indicatorBox?.x, radioBox?.x),
      deltaMilliPixels(indicatorBox?.y, radioBox?.y),
      deltaMilliPixels(indicatorBox?.width, radioBox?.width),
      deltaMilliPixels(indicatorBox?.height, radioBox?.height)
    )
    throw error
  }
}

type ActivitySummaryMetrics = {
  attendancePercent: number
  gradeAverage: number
  gradeScale: "5" | "100"
  participationEvents: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function readRequiredMetric(section: unknown, metricName: string): number | undefined {
  if (!isRecord(section) || !Object.prototype.hasOwnProperty.call(section, metricName)) {
    return undefined
  }

  const value = section[metricName]
  return typeof value === "number" && Number.isFinite(value) ? value : undefined
}

function readActivitySummaryMetrics(payload: unknown): ActivitySummaryMetrics | undefined {
  if (!isRecord(payload)) return undefined
  if (
    !Object.prototype.hasOwnProperty.call(payload, "attendance") ||
    !Object.prototype.hasOwnProperty.call(payload, "grades") ||
    !Object.prototype.hasOwnProperty.call(payload, "participation")
  ) {
    return undefined
  }

  const attendance = payload.attendance
  const grades = payload.grades
  const participation = payload.participation
  if (!isRecord(attendance) || !isRecord(grades) || !isRecord(participation)) return undefined

  const attendancePercent = readRequiredMetric(attendance, "percent")
  const gradeAverage = readRequiredMetric(grades, "average")
  const participationEvents = readRequiredMetric(participation, "events")
  const gradeScale = grades.scale
  if (
    attendancePercent === undefined ||
    gradeAverage === undefined ||
    participationEvents === undefined ||
    !Number.isInteger(participationEvents) ||
    participationEvents < 0 ||
    (gradeScale !== "5" && gradeScale !== "100")
  ) {
    return undefined
  }

  return { attendancePercent, gradeAverage, gradeScale, participationEvents }
}

async function readActivityRingLabels(page: Page): Promise<Array<string | null>> {
  const cards = [
    page.getByRole("group", { name: /Статистика посещаемости|Attendance statistics/u }),
    page.getByRole("group", { name: /Статистика оценок|Grade statistics/u }),
    page.getByRole("group", { name: /Статистика участия|Participation statistics/u }),
  ]
  return Promise.all(cards.map((card) => card.getByRole("img").getAttribute("aria-label")))
}

function ringLabelsMatchSummary(
  labels: Array<string | null>,
  metrics: ActivitySummaryMetrics
): boolean {
  const gradeMax = metrics.gradeScale === "100" ? 100 : 5
  const attendanceValue = Math.round(metrics.attendancePercent)
  const gradeValue = metrics.gradeAverage.toFixed(1)
  const participationValue = String(metrics.participationEvents)
  const expected = [
    [`Attendance ring showing ${attendanceValue}%`, `Кольцо посещаемости: ${attendanceValue}%`],
    [
      `Grade gauge showing ${gradeValue} out of ${gradeMax}`,
      `Шкала оценок: ${gradeValue} из ${gradeMax}`,
    ],
    [
      `Participation count showing ${participationValue} events`,
      `Счётчик участия: ${participationValue} событий`,
    ],
  ]

  return (
    labels.length === expected.length &&
    labels.every((label, index) => typeof label === "string" && expected[index]?.includes(label))
  )
}

test("seeded student can view Activity summaries, change the period, and restore it after reload", async ({
  page,
}, testInfo) => {
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
  await expectPeriodIndicatorToMatchRadio(
    periodIndicator,
    period90Days,
    "90-day",
    testInfo.project.name
  )

  const expectedOrigin = new URL(page.url()).origin
  const summaryResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      response.request().method() === "GET" &&
      url.origin === expectedOrigin &&
      url.pathname === "/api/v1/stats/summary" &&
      url.searchParams.get("period") === "30d"
    )
  })
  await period30Days.click()

  await expect(period30Days).toHaveAttribute("aria-checked", "true")
  await expect(page).toHaveURL(/(?:\?|&)p=30d(?:&|$)/u)
  await expectPeriodIndicatorToMatchRadio(
    periodIndicator,
    period30Days,
    "30-day",
    testInfo.project.name
  )
  const summaryResponse = await summaryResponsePromise
  expect(summaryResponse.ok()).toBe(true)
  const summaryPayload: unknown = await summaryResponse.json()
  const summaryMetrics = readActivitySummaryMetrics(summaryPayload)
  expect(
    summaryMetrics,
    "successful summary response must include every backend metric"
  ).toBeDefined()
  if (!summaryMetrics) throw new Error("successful summary response is missing backend metrics")

  await expect
    .poll(async () => ringLabelsMatchSummary(await readActivityRingLabels(page), summaryMetrics))
    .toBe(true)
  const labelsBeforeReload = await readActivityRingLabels(page)

  await page.reload()

  await expect(page).toHaveURL(/(?:\?|&)p=30d(?:&|$)/u)
  const reloadedPeriodSelector = page.getByRole("radiogroup", {
    name: /Выберите период для статистики активности|Select time period for activity statistics/u,
  })
  await expect(
    reloadedPeriodSelector.getByRole("radio", { name: /30 дней|30 days/u })
  ).toHaveAttribute("aria-checked", "true")
  await expect
    .poll(async () => {
      const labelsAfterReload = await readActivityRingLabels(page)
      return (
        ringLabelsMatchSummary(labelsAfterReload, summaryMetrics) &&
        labelsAfterReload.every(
          (label, index) => label !== null && label === labelsBeforeReload[index]
        )
      )
    })
    .toBe(true)
})
