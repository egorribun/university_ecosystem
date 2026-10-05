import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./admin-notifications-rbac.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const pageErrorDiagnosticUrl = new URL("./page-error-diagnostic.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const adminRouteUrl = new URL("../../src/routes/_admin/admin.notifications.tsx", import.meta.url)
const adminLayoutUrl = new URL("../../src/routes/_admin.tsx", import.meta.url)
const featureUrl = new URL(
  "../../src/features/admin/AdminNotificationsFeature.tsx",
  import.meta.url
)
const queryUrl = new URL("../../src/api/hooks/adminNotifications.ts", import.meta.url)
const apiUrl = new URL("../../src/api/notifications.ts", import.meta.url)
const sdkUrl = new URL("../../src/api/generated/sdk.gen.ts", import.meta.url)
const versionUrl = new URL("../../../app/core/versioning.py", import.meta.url)
const publicApiUrl = new URL("../../../app/api/public/__init__.py", import.meta.url)
const backendRouteUrl = new URL("../../../app/api/notification_dead_letters.py", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_admin_data.py", import.meta.url)
const standUrl = new URL("../../../scripts/live_stand.py", import.meta.url)

const [
  spec,
  fixtures,
  pageErrorDiagnostic,
  config,
  adminRoute,
  adminLayout,
  feature,
  query,
  api,
  sdk,
  version,
  publicApi,
  backendRoute,
  seed,
  stand,
] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(fixtureUrl, "utf8"),
  readFile(pageErrorDiagnosticUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(adminRouteUrl, "utf8"),
  readFile(adminLayoutUrl, "utf8"),
  readFile(featureUrl, "utf8"),
  readFile(queryUrl, "utf8"),
  readFile(apiUrl, "utf8"),
  readFile(sdkUrl, "utf8"),
  readFile(versionUrl, "utf8"),
  readFile(publicApiUrl, "utf8"),
  readFile(backendRouteUrl, "utf8"),
  readFile(seedUrl, "utf8"),
  readFile(standUrl, "utf8"),
])

function requireMatch(source, pattern, message) {
  assert.ok(pattern.test(source), message)
}

test("live notification queue RBAC exercises the seeded admin and both non-admin roles", () => {
  requireMatch(spec, /await loginAs\(page, "admin"\)/u, "admin uses the seeded live session")
  requireMatch(spec, /page\.goto\("\/admin\/notifications"\)/u, "admin page is opened directly")
  requireMatch(
    spec,
    /Notification queue|Очередь уведомлений/u,
    "the visible admin page heading is asserted in both shipped locales"
  )
  const adminStart = spec.indexOf('test("admin can read the seeded notification queue')
  const nonAdminStart = spec.indexOf(
    '\nfor (const role of ["student", "teacher"] as const)',
    adminStart
  )
  assert.ok(
    adminStart >= 0 && nonAdminStart > adminStart,
    "admin and denial scenarios are distinct"
  )
  const adminScenario = spec.slice(adminStart, nonAdminStart)
  requireMatch(
    adminScenario,
    /const expectedOrigin = new URL\(page\.url\(\)\)\.origin[\s\S]*?const browserQueueResponsePromise = page\.waitForResponse\([\s\S]*?response\.request\(\)\.method\(\) === "GET"[\s\S]*?url\.origin === expectedOrigin[\s\S]*?url\.pathname === DEAD_LETTER_PATH/u,
    "the admin acceptance observes the actual same-origin browser GET"
  )
  const responseListener = adminScenario.indexOf("page.waitForResponse")
  const pageNavigation = adminScenario.indexOf('await page.goto("/admin/notifications")')
  const tableAssertion = adminScenario.indexOf("await expect(queueTable).toBeVisible()")
  assert.ok(
    responseListener >= 0 && pageNavigation > responseListener && tableAssertion > pageNavigation,
    "the browser response listener is installed before navigation and UI assertions"
  )
  requireMatch(
    adminScenario,
    /const payload: unknown = await response\.json\(\)[\s\S]*?Array\.isArray\(items\)[\s\S]*?Number\.isInteger\(total\) && total >= 0/u,
    "the actual response envelope is validated in memory without persisting its body"
  )
  requireMatch(
    adminScenario,
    /No dead-lettered jobs at the moment/u,
    "the English empty state copy is explicit"
  )
  requireMatch(
    adminScenario,
    /В отложенной очереди нет задач/u,
    "the Russian empty state copy is explicit"
  )
  requireMatch(
    adminScenario,
    /if \(itemCount === 0\)[\s\S]*?totalCount[\s\S]*?toBe\(0\)[\s\S]*?emptyStateAlert\)\.toBeVisible\(\)[\s\S]*?queueTable\)\.toHaveCount\(0\)/u,
    "an empty response requires the supported empty UI and no table"
  )
  requireMatch(
    adminScenario,
    /else \{[\s\S]*?queueTable\)\.toBeVisible\(\)[\s\S]*?getByRole\("row"\)\)\.toHaveCount\(itemCount \+ 1\)/u,
    "a nonempty response requires all returned rows in the table"
  )
  requireMatch(
    adminScenario,
    /fetchErrorAlert[\s\S]*?toHaveCount\(0\)/u,
    "both supported success states exclude the queue fetch error copy"
  )
  assert.doesNotMatch(
    adminScenario,
    /page\.request\.get\(/u,
    "the admin branch does not substitute an independent API request for browser evidence"
  )
  requireMatch(
    spec,
    /reportLiveAdminQueueState\([\s\S]*?tableVisible,[\s\S]*?progressbarVisible,[\s\S]*?alertVisible,[\s\S]*?rowCount[\s\S]*?\)\s*throw error/u,
    "the failing UI assertion retains only fixed API and rendered-state diagnostics"
  )
  requireMatch(
    spec,
    /for \(const role of \["student", "teacher"\] as const\)/u,
    "both non-admin roles are checked"
  )
  requireMatch(spec, /await loginAs\(page, role\)/u, "denial uses real seeded role sessions")
  requireMatch(
    spec,
    /redirected from \/admin\/notifications[\s\S]*?\/dashboard/u,
    "direct route access is denied"
  )
  const reloadDenialStart = spec.indexOf("await page.reload()")
  const retriedAdminUrl = spec.indexOf('await page.goto("/admin/notifications")', reloadDenialStart)
  assert.ok(reloadDenialStart >= 0, "the authenticated non-admin page is reloaded")
  assert.ok(
    retriedAdminUrl > reloadDenialStart,
    "the direct admin URL is retried after the session reload"
  )
  requireMatch(
    spec,
    /expect\(\s*page,[\s\S]*?remains denied after reload[\s\S]*?toHaveURL/u,
    "the repeated direct navigation asserts that denial still redirects after reload"
  )
  requireMatch(
    spec,
    /GET \/api\/v1\/notifications\/admin\/dead-letter status[\s\S]*?\.toBe\(\s*403\s*\)/u,
    "the non-admin API response denies queue data"
  )
  requireMatch(spec, /const syntheticJobId = randomUUID\(\)/u, "action checks use a synthetic id")
  requireMatch(
    spec,
    /for \(const action of \["retry", "purge"\] as const\)/u,
    "both admin-only mutation endpoints are checked"
  )
  requireMatch(
    spec,
    /page\.request\.post\(actionPath,\s*\{\s*data:\s*\{\s*job_ids:\s*\[syntheticJobId\]\s*\},\s*headers:\s*\{\s*["']X-CSRF-Token["']:\s*csrfToken\s*\}/u,
    "denial requests include valid CSRF and a nonexistent synthetic target"
  )
  requireMatch(
    spec,
    /POST \$\{actionPath\} must be forbidden[\s\S]*?\.toBe\(403\)/u,
    "non-admins receive forbidden for retry and purge"
  )
  assert.doesNotMatch(
    spec,
    /page\.request\.(?:put|patch|delete)\(|\.click\(\)|page\.route\(|routeWebSocket\(/u,
    "the acceptance uses no browser action, data mutation, or authorization mock"
  )
  assert.equal(
    [...spec.matchAll(/page\.request\.post\(/gu)].length,
    1,
    "the only POSTs are the synthetic unauthorized retry/purge checks above"
  )
})

test("admin page-error diagnostics are scoped to these exact scenarios and preserve hard failures", () => {
  assert.ok(
    fixtures.includes("isLiveAdminNotificationsScenario("),
    "fixture scopes the diagnostic to the selected scenario"
  )
  assert.ok(
    pageErrorDiagnostic.includes(
      "admin can read the seeded notification queue without changing it"
    ),
    "admin read title is an explicit allowed case"
  )
  assert.ok(
    pageErrorDiagnostic.includes("student cannot view or mutate notification queue data"),
    "student denial title is an explicit allowed case"
  )
  assert.ok(
    pageErrorDiagnostic.includes("teacher cannot view or mutate notification queue data"),
    "teacher denial title is an explicit allowed case"
  )
  assert.ok(
    pageErrorDiagnostic.includes('type DiagnosticCheck = "password-reset" | "admin-notifications"'),
    "the emitted check label is a finite union"
  )
  assert.ok(
    pageErrorDiagnostic.includes('case "/admin/notifications":'),
    "the admin page is classified by its exact pathname"
  )
  assert.ok(
    pageErrorDiagnostic.includes('return "react-418"'),
    "React hydration 418 is classified as a fixed label"
  )
  assert.ok(
    fixtures.includes("const diagnosticCheck = isResetScenario") &&
      fixtures.includes("pageErrorDiagnostics.report(testInfo.project.name, diagnosticCheck)"),
    "only the whitelisted admin cases emit the fixed check label"
  )
  assert.ok(
    fixtures.includes(
      'expect(errors, errors.map((error) => error.message).join("\\n")).toEqual([])'
    ),
    "diagnostics leave the original hard page-error assertion intact"
  )
})

test("notification queue contracts lead from the admin route to a server-protected read endpoint", () => {
  requireMatch(
    adminRoute,
    /createFileRoute\("\/_admin\/admin\/notifications"\)/u,
    "route is under the admin layout"
  )
  requireMatch(
    adminLayout,
    /beforeLoad: \(\{ context \}\) =>\s*evaluateAdminGuard\(\s*import\.meta\.env\.SSR\s*\?\s*\{\s*user: context\.auth\.isAuth \? context\.auth\.user : null,\s*loading: context\.auth\.loading,\s*\}\s*:\s*useAuthStore\.getState\(\)\s*\)/u,
    "SSR request context and client auth state both enforce the admin role"
  )
  requireMatch(feature, /adminDeadLetterQueueQueryOptions\(\)/u, "page fetches the live queue")
  requireMatch(feature, /admin:notifications\.title/u, "page renders the localized admin title")
  requireMatch(
    query,
    /return fetchDeadLetterQueue\(undefined, signal\)/u,
    "query uses the production API helper"
  )
  requireMatch(
    api,
    /GET \/api\/v1\/notifications\/admin\/dead-letter/u,
    "API helper identifies the GET contract"
  )
  requireMatch(
    sdk,
    /"\/api\/v1\/notifications\/admin\/dead-letter"/u,
    "generated client uses the versioned endpoint"
  )
  requireMatch(version, /API_V1_PREFIX[^=\n]*=\s*["']\/api\/v1["']/u, "API prefix is canonical")
  requireMatch(
    publicApi,
    /router\.include_router\(notification_dead_letters_router\)/u,
    "the route is mounted"
  )
  requireMatch(
    backendRoute,
    /prefix="\/notifications\/admin\/dead-letter"/u,
    "backend route matches the client"
  )
  requireMatch(
    backendRoute,
    /@router\.get\([\s\S]*?async def list_notification_dead_letters/u,
    "queue access is a GET"
  )
  requireMatch(
    backendRoute,
    /Depends\(get_current_admin_user_from_dishka\)/u,
    "server authorization requires admin"
  )
  assert.equal(
    [...backendRoute.matchAll(/Depends\(get_current_admin_user_from_dishka\)/gu)].length,
    3,
    "list, retry and purge endpoints all require the server admin dependency"
  )
  requireMatch(
    backendRoute,
    /list_dead_lettered_jobs\(db, limit=limit, offset=offset\)/u,
    "list handler is read-only"
  )
  requireMatch(
    config,
    /testDir: "\.\/tests\/e2e-live"/u,
    "live spec is in the acceptance test directory"
  )
  requireMatch(
    config,
    /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u,
    "Playwright discovers live specs"
  )
})

test("the live queue records are seeded idempotently by the owned demo-seed command", () => {
  requireMatch(
    fixtures,
    /admin:\s*\{[\s\S]*?password: requireLiveAdminPassword\(\)/u,
    "admin password is injected from the owned stand"
  )
  requireMatch(seed, /DEAD_LETTER_JOBS = \[/u, "demo admin seed defines queue records")
  const jobsStart = seed.indexOf("DEAD_LETTER_JOBS = [")
  const helpersStart = seed.indexOf("# Helpers", jobsStart)
  const jobDefinitions = seed.slice(jobsStart, helpersStart)
  assert.equal([...jobDefinitions.matchAll(/"job_type":/gmu)].length, 4)
  requireMatch(seed, /async def seed_dead_letter_jobs\(db\)/u, "seed provides queue fixtures")
  requireMatch(
    seed,
    /DeadLetterJob\.job_hash == job_hash[\s\S]*?if existing:[\s\S]*?continue/u,
    "seed reruns do not duplicate queue rows"
  )
  requireMatch(
    stand,
    /SEED_SCRIPTS = \([\s\S]*?"scripts\/seed_admin_data\.py"/u,
    "owner-checked live seed invokes admin fixtures"
  )
  requireMatch(
    stand,
    /seed_parser\.add_argument\("--demo", action="store_true", required=True\)/u,
    "live seeding requires explicit demo mode"
  )
})
