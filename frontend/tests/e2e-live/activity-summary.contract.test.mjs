import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./activity-summary.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const approvedPlanUrl = new URL(
  "../../../docs/superpowers/plans/MVP_APPROVED_PLAN.md",
  import.meta.url
)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)
const featureUrl = new URL("../../src/features/activity/ActivityFeature.tsx", import.meta.url)
const queryUrl = new URL("../../src/api/hooks/activity.ts", import.meta.url)
const analyticsUrl = new URL("../../../app/services/user/analytics_service.py", import.meta.url)

test("Activity live acceptance uses the seeded student and real read-only summaries", async () => {
  const [spec, config, approvedPlan, seed, feature, query, analytics] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(approvedPlanUrl, "utf8"),
    readFile(seedUrl, "utf8"),
    readFile(featureUrl, "utf8"),
    readFile(queryUrl, "utf8"),
    readFile(analyticsUrl, "utf8"),
  ])

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
  assert.match(analytics, /"percent":\s*round\(percent, 2\)/u)
  assert.match(analytics, /"average":\s*average/u)
  assert.match(analytics, /"events":\s*events/u)

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
  assert.match(spec, /stats\/summary/u)
  assert.match(spec, /p=30d/u)
  assert.match(
    approvedPlan,
    /центрирование ползунков Events-табов и Activity-периодов \(геометрия bbox\)/u
  )
  assert.match(spec, /async function expectPeriodIndicatorToMatchRadio\(/u)
  assert.match(spec, /indicator\.boundingBox\(\)/u)
  assert.match(spec, /selectedRadio\.boundingBox\(\)/u)
  assert.match(spec, /expectPeriodIndicatorToMatchRadio\(periodIndicator,\s*period90Days/u)
  assert.match(spec, /expectPeriodIndicatorToMatchRadio\(periodIndicator,\s*period30Days/u)
  assert.match(spec, /const reloadSummaryResponsePromise = page\.waitForResponse/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /const reloadSummaryResponse = await reloadSummaryResponsePromise/u)
  assert.match(spec, /period30Days\)\.toHaveAttribute\(["']aria-checked["'], ["']true["']\)/u)
  assert.match(
    spec,
    /await expect\(\s*reloadedPeriodSelector\.getByRole\("radio",\s*\{\s*name:\s*\/30 дней\|30 days\/u\s*\}\)\s*\)\.toHaveAttribute\("aria-checked", "true"\)/u
  )
  assert.doesNotMatch(
    spec,
    /page\.route|route\.fulfill|randomUUID|freshPassword|request\.(?:post|put|patch|delete)|\.fill\(/u
  )
})
