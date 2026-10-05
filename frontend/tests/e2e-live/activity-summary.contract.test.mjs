import assert from "node:assert/strict"
import { createRequire } from "node:module"
import { readFile } from "node:fs/promises"
import process from "node:process"
import { join } from "node:path"
import { URL } from "node:url"
import test from "node:test"

const requireFromFrontend = createRequire(join(process.cwd(), "package.json"))
const typescript = requireFromFrontend("typescript")
const specUrl = new URL("./activity-summary.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const masterPlanUrl = new URL("../../../docs/superpowers/plans/MVP_MASTER_PLAN.md", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)
const featureUrl = new URL("../../src/features/activity/ActivityFeature.tsx", import.meta.url)
const queryUrl = new URL("../../src/api/hooks/activity.ts", import.meta.url)
const analyticsUrl = new URL("../../../app/services/user/analytics_service.py", import.meta.url)
const statsApiUrl = new URL("../../../app/api/stats.py", import.meta.url)
const enActivityUrl = new URL("../../src/i18n/locales/en/activity.json", import.meta.url)
const ruActivityUrl = new URL("../../src/i18n/locales/ru/activity.json", import.meta.url)

function loadAcceptanceHelpers(spec) {
  const source = typescript.createSourceFile(
    "activity-summary.live.spec.ts",
    spec,
    typescript.ScriptTarget.Latest,
    true,
    typescript.ScriptKind.TS
  )
  const names = [
    "isRecord",
    "readRequiredMetric",
    "readActivitySummaryMetrics",
    "ringLabelsMatchSummary",
  ]
  const declarations = source.statements.filter(
    (statement) =>
      typescript.isFunctionDeclaration(statement) &&
      statement.name &&
      names.includes(statement.name.text)
  )
  assert.deepEqual(
    declarations.map((declaration) => declaration.name.text),
    names,
    "the tested acceptance helpers must be the live spec implementations"
  )
  const helperModule = `${declarations.map((declaration) => declaration.getText(source)).join("\n")}\nmodule.exports = { readActivitySummaryMetrics, ringLabelsMatchSummary }`
  const compiled = typescript.transpileModule(helperModule, {
    compilerOptions: {
      module: typescript.ModuleKind.CommonJS,
      target: typescript.ScriptTarget.ES2022,
    },
  }).outputText
  const module = { exports: {} }
  new Function("module", "exports", compiled)(module, module.exports)
  return module.exports
}

function renderLabel(template, values) {
  return template.replace(/\{\{(\w+)\}\}/gu, (_match, key) => String(values[key]))
}

test("Activity live acceptance uses the seeded student and actual summary payload contract", async () => {
  const [
    spec,
    config,
    masterPlan,
    seed,
    feature,
    query,
    analytics,
    statsApi,
    enActivity,
    ruActivity,
  ] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(masterPlanUrl, "utf8"),
    readFile(seedUrl, "utf8"),
    readFile(featureUrl, "utf8"),
    readFile(queryUrl, "utf8"),
    readFile(analyticsUrl, "utf8"),
    readFile(statsApiUrl, "utf8"),
    readFile(enActivityUrl, "utf8"),
    readFile(ruActivityUrl, "utf8"),
  ])
  const enLabels = JSON.parse(enActivity).a11y
  const ruLabels = JSON.parse(ruActivity).a11y

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(seed, /DEMO_PRIMARY_USER_EMAIL\s*=\s*["']test@university\.dev["']/u)
  assert.match(seed, /role=UserRole\.STUDENT/u)
  assert.match(seed, /async def seed_user\([\s\S]*?return user/u)

  assert.match(feature, /role=["']radiogroup["']/u)
  assert.match(feature, /aria-label=\{t\(["']activity:a11y\.periodSelector["']\)\}/u)
  assert.match(feature, /AttendanceCard/u)
  assert.match(feature, /GradesCard/u)
  assert.match(feature, /ParticipationCard/u)
  assert.match(query, /api\.get<ActivitySummaryEnvelope>\(["']\/stats\/summary["']/u)
  assert.match(
    statsApi,
    /"attendance": attendance_r\.payload[\s\S]*?"grades": grades_r\.payload[\s\S]*?"participation": participation_r\.payload/u
  )
  assert.match(analytics, /percent = attended \/ total \* 100 if total else 0\.0/u)
  assert.match(analytics, /"percent":\s*round\(percent, 2\)/u)
  assert.match(analytics, /"average":\s*round\(current_average, 2\)/u)
  assert.match(analytics, /"scale":\s*scale/u)
  assert.match(analytics, /"events":\s*len\(rows\)/u)
  assert.match(
    analytics,
    /sum\(float\(g\.score\) for g in grades\) \/ len\(grades\) if grades else 0\.0/u
  )

  assert.match(
    spec,
    /seeded student can view Activity summaries, change the period, and restore it after reload/u
  )
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/activity["']\)/u)
  assert.match(spec, /getByRole\(["']radiogroup["']/u)
  assert.match(spec, /getByRole\(["']group["']/u)
  assert.match(spec, /page\.waitForResponse/u)
  assert.match(spec, /response\.request\(\)\.method\(\) === ["']GET["']/u)
  assert.match(spec, /const expectedOrigin = new URL\(page\.url\(\)\)\.origin/u)
  assert.match(spec, /url\.origin === expectedOrigin/u)
  assert.match(spec, /url\.pathname === ["']\/api\/v1\/stats\/summary["']/u)
  assert.match(spec, /stats\/summary/u)
  assert.match(spec, /p=30d/u)
  assert.match(spec, /const summaryPayload: unknown = await summaryResponse\.json\(\)/u)
  assert.match(spec, /readActivitySummaryMetrics\(summaryPayload\)/u)
  assert.match(spec, /Object\.prototype\.hasOwnProperty\.call\(payload, "attendance"\)/u)
  assert.match(spec, /Object\.prototype\.hasOwnProperty\.call\(payload, "grades"\)/u)
  assert.match(spec, /Object\.prototype\.hasOwnProperty\.call\(payload, "participation"\)/u)
  assert.match(spec, /readRequiredMetric\(attendance, "percent"\)/u)
  assert.match(spec, /readRequiredMetric\(grades, "average"\)/u)
  assert.match(spec, /readRequiredMetric\(participation, "events"\)/u)
  assert.match(spec, /gradeScale !== "5" && gradeScale !== "100"/u)
  assert.match(
    spec,
    /labels\.every\(\(label, index\) => typeof label === "string" && expected\[index\]\?\.includes\(label\)\)/u
  )
  assert.match(spec, /const labelsBeforeReload = await readActivityRingLabels\(page\)/u)
  assert.match(spec, /ringLabelsMatchSummary\(labelsAfterReload, summaryMetrics\)/u)
  assert.match(spec, /label === labelsBeforeReload\[index\]/u)
  assert.match(
    masterPlan,
    /индикатор периода\s+Activity совпадает с выбранной radio-кнопкой по геометрии bounding box \(x, y,\s*width и height с допуском 1 px\)/u
  )
  assert.match(spec, /async function expectPeriodIndicatorToMatchRadio\(/u)
  assert.match(spec, /indicator\.boundingBox\(\)/u)
  assert.match(spec, /selectedRadio\.boundingBox\(\)/u)
  assert.match(spec, /Math\.abs\(indicatorBox\.x - radioBox\.x\) <= 1/u)
  assert.match(
    spec,
    /catch \(error\) \{[\s\S]*?reportLiveActivityGeometry\([\s\S]*?periodLabel,[\s\S]*?throw error/u
  )
  assert.match(spec, /expectPeriodIndicatorToMatchRadio\(\s*periodIndicator,\s*period90Days/u)
  assert.match(spec, /expectPeriodIndicatorToMatchRadio\(\s*periodIndicator,\s*period30Days/u)
  assert.doesNotMatch(
    spec,
    /reloadSummaryResponsePromise|reloadSummaryResponse/u,
    "a fresh persisted cache may satisfy reload without a second network request"
  )
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /period30Days\)\.toHaveAttribute\(["']aria-checked["'], ["']true["']\)/u)
  assert.match(
    spec,
    /await expect\(\s*reloadedPeriodSelector\.getByRole\("radio",\s*\{\s*name:\s*\/30 дней\|30 days\/u\s*\}\)\s*\)\.toHaveAttribute\("aria-checked", "true"\)/u
  )
  assert.doesNotMatch(
    spec,
    /page\.route|route\.fulfill|randomUUID|freshPassword|request\.(?:post|put|patch|delete)|\.fill\(/u
  )

  const helpers = loadAcceptanceHelpers(spec)
  const summary = {
    attendance: { percent: 0 },
    grades: { average: 3, scale: "5" },
    participation: { events: 1 },
  }
  const metrics = helpers.readActivitySummaryMetrics(summary)
  assert.deepEqual(metrics, {
    attendancePercent: 0,
    gradeAverage: 3,
    gradeScale: "5",
    participationEvents: 1,
  })

  const format = (translations) => [
    renderLabel(translations.ringAttendance, { value: Math.round(metrics.attendancePercent) }),
    renderLabel(translations.ringGrades, {
      value: metrics.gradeAverage.toFixed(1),
      max: metrics.gradeScale === "100" ? 100 : 5,
    }),
    renderLabel(translations.ringParticipation, { value: metrics.participationEvents }),
  ]
  assert.equal(helpers.ringLabelsMatchSummary(format(enLabels), metrics), true)
  assert.equal(helpers.ringLabelsMatchSummary(format(ruLabels), metrics), true)

  const wrongAttendance = format(enLabels)
  wrongAttendance[0] = renderLabel(enLabels.ringAttendance, { value: 100 })
  assert.equal(helpers.ringLabelsMatchSummary(wrongAttendance, metrics), false)
  const wrongGradeMax = format(enLabels)
  wrongGradeMax[1] = renderLabel(enLabels.ringGrades, { value: "3.0", max: 100 })
  assert.equal(helpers.ringLabelsMatchSummary(wrongGradeMax, metrics), false)
  const wrongParticipation = format(enLabels)
  wrongParticipation[2] = renderLabel(enLabels.ringParticipation, { value: 10 })
  assert.equal(helpers.ringLabelsMatchSummary(wrongParticipation, metrics), false)

  const invalidPayloads = [
    undefined,
    null,
    [],
    {},
    { ...summary, attendance: null },
    { ...summary, attendance: [] },
    { ...summary, attendance: {} },
    { ...summary, grades: { average: 3 } },
    { ...summary, grades: { average: 3, scale: "gpa" } },
    { ...summary, participation: { events: 1.5 } },
    { ...summary, participation: { events: "1" } },
  ]
  for (const payload of invalidPayloads) {
    assert.equal(helpers.readActivitySummaryMetrics(payload), undefined)
  }
})
