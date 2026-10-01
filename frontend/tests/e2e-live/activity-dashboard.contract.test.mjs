import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./activity-dashboard.live.spec.ts", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)
const analyticsUrl = new URL("../../../app/services/user/analytics_service.py", import.meta.url)
const featureUrl = new URL("../../src/features/activity/ActivityFeature.tsx", import.meta.url)
const hookUrl = new URL("../../src/hooks/useActivityData.ts", import.meta.url)

test("Activity empty-baseline acceptance uses only seeded records and the real read-only API", async () => {
  const [spec, seed, analytics, feature, hook] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(seedUrl, "utf8"),
    readFile(analyticsUrl, "utf8"),
    readFile(featureUrl, "utf8"),
    readFile(hookUrl, "utf8"),
  ])

  assert.match(seed, /async def seed_events\(db, user: User\)/u)
  assert.doesNotMatch(seed, /EventAttendance\s*\(|Notification\s*\(/u)
  assert.match(analytics, /models\.EventAttendance\.user_id\s*==\s*user_id/u)
  assert.match(analytics, /models\.Notification\.type\s*==\s*["']grade["']/u)
  assert.match(hook, /attendance\.recent\.length\s*>\s*0/u)
  assert.match(hook, /grades\.recent\.length\s*>\s*0/u)
  assert.match(hook, /participation\.events\s*>\s*0/u)
  assert.match(feature, /hasInitiallyLoaded\s*&&\s*!hasAnyData\s*&&\s*!isPartial/u)

  assert.match(spec, /seeded student sees the supported empty Activity baseline/u)
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/activity\?p=90d["']\)/u)
  assert.match(spec, /stats\/summary/u)
  assert.match(
    spec,
    /summary\.attendance\)\.toMatchObject\(\{ percent: 0, present: 0, total: 0, recent: \[\] \}\)/u
  )
  assert.match(
    spec,
    /summary\.grades\)\.toMatchObject\(\{ average: 0, total_grades: 0, recent: \[\] \}\)/u
  )
  assert.match(spec, /summary\.participation\)\.toMatchObject\(\{ events: 0, recent: \[\] \}\)/u)

  const emptyStateAbsenceChecks = [
    ["analytics charts", "name: /^(?:Аналитика|Analytics)$/u"],
    [
      "attendance trend chart",
      "name: /^(?:Линейный график тренда посещаемости|Line chart showing attendance percentage over time)$/u",
    ],
    [
      "grades by subject chart",
      "name: /^(?:Столбчатая диаграмма оценок по предметам|Bar chart showing grades by subject)$/u",
    ],
    [
      "heatmap",
      "name: /^(?:Тепловая карта активности по дням|Activity heatmap calendar showing daily contributions)$/u",
    ],
    ["period comparison", "name: /^(?:Сравнение периодов|Period Comparison)$/u"],
    ["activity timeline", "name: /^(?:Лента активности|Activity timeline)$/u"],
  ]
  for (const [artifact, locatorName] of emptyStateAbsenceChecks) {
    assert.ok(spec.includes(locatorName), `empty Activity acceptance must identify the ${artifact}`)
  }
  assert.match(
    spec,
    /for\s*\(const artifact of emptyStateArtifacts\)\s*\{\s*await expect\(artifact\)\.toHaveCount\(0\)\s*\}/u
  )

  assert.match(spec, /Активности пока нет\|No activity yet/u)
  assert.doesNotMatch(
    spec,
    /page\.route|route\.fulfill|request\.(?:post|put|patch|delete)|\.fill\(/u
  )
})

test("the selected Activity period agrees with the period used by the summary API", async () => {
  const spec = await readFile(specUrl, "utf8")

  assert.match(spec, /url\.searchParams\.get\("period"\) === "90d"/u)
  assert.match(
    spec,
    /getByRole\("radiogroup",\s*\{\s*name:\s*\/Выберите период для статистики активности\|Select time period for activity statistics\/u,?\s*\}\)/u
  )
  assert.match(spec, /getByRole\("radio",\s*\{\s*name:\s*\/\^90\/u\s*\}\)/u)
  assert.match(spec, /toHaveAttribute\(\s*"aria-checked",\s*"true"\s*\)/u)
})
