import { expect, loginAs, test } from "./fixtures"

type ActivitySummary = {
  attendance: {
    percent: number
    present: number
    total: number
    recent: unknown[]
  }
  grades: {
    average: number
    scale: string
    total_grades: number
    recent: unknown[]
  }
  participation: {
    events: number
    recent: unknown[]
  }
}

test("seeded student sees the supported empty Activity baseline", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "student")

  const summaryResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return (
      response.request().method() === "GET" &&
      url.pathname.endsWith("/api/v1/stats/summary") &&
      url.searchParams.get("period") === "90d"
    )
  })
  await page.goto("/activity?p=90d")

  const summaryResponse = await summaryResponsePromise
  expect(summaryResponse.ok()).toBe(true)
  const summary = (await summaryResponse.json()) as ActivitySummary

  const periodSelector = page.getByRole("radiogroup", {
    name: /Выберите период для статистики активности|Select time period for activity statistics/u,
  })
  await expect(periodSelector.getByRole("radio", { name: /^90/u })).toHaveAttribute(
    "aria-checked",
    "true"
  )

  // The disposable seed creates event listings, but no attendance or grade
  // records. Activity must show this real empty source state without inventing
  // grades or participation records for the demo account.
  expect(summary.attendance).toMatchObject({ percent: 0, present: 0, total: 0, recent: [] })
  expect(summary.grades).toMatchObject({ average: 0, total_grades: 0, recent: [] })
  expect(summary.participation).toMatchObject({ events: 0, recent: [] })

  await expect(
    page.getByRole("heading", { name: /Активности пока нет|No activity yet/u })
  ).toBeVisible()
  await expect(
    page.getByText(
      /Ваша активность появится здесь по мере посещения занятий и участия в мероприятиях|Your activity will appear here as you attend classes and participate in events/u
    )
  ).toBeVisible()

  const attendanceCard = page.getByRole("group", {
    name: /Статистика посещаемости|Attendance statistics/u,
  })
  await expect(attendanceCard.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")

  const gradesCard = page.getByRole("group", {
    name: /Статистика оценок|Grade statistics/u,
  })
  await expect(gradesCard.getByRole("img")).toHaveAttribute(
    "aria-label",
    /(?:0\.0 из 5|0\.0 out of 5)/u
  )

  const participationCard = page.getByRole("group", {
    name: /Статистика участия|Participation statistics/u,
  })
  await expect(participationCard.getByRole("img")).toHaveAttribute(
    "aria-label",
    /(?:0 событий|0 события|0 событие|0 events)/u
  )

  const emptyStateArtifacts = [
    page.getByRole("region", { name: /^(?:Аналитика|Analytics)$/u }),
    page.getByRole("img", {
      name: /^(?:Линейный график тренда посещаемости|Line chart showing attendance percentage over time)$/u,
    }),
    page.getByRole("img", {
      name: /^(?:Столбчатая диаграмма оценок по предметам|Bar chart showing grades by subject)$/u,
    }),
    page.getByRole("group", {
      name: /^(?:Тепловая карта активности по дням|Activity heatmap calendar showing daily contributions)$/u,
    }),
    page.getByRole("region", { name: /^(?:Сравнение периодов|Period Comparison)$/u }),
    page.getByRole("region", { name: /^(?:Лента активности|Activity timeline)$/u }),
  ]
  for (const artifact of emptyStateArtifacts) {
    await expect(artifact).toHaveCount(0)
  }
})
