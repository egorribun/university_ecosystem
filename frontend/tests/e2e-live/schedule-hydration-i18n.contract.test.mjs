import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./schedule-hydration-i18n.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const authRouteUrl = new URL("../../src/routes/_auth.tsx", import.meta.url)
const scheduleRouteUrl = new URL("../../src/routes/_auth/schedule.tsx", import.meta.url)
const schedulePageUrl = new URL("../../src/pages/Schedule.tsx", import.meta.url)
const scheduleHeaderUrl = new URL(
  "../../src/components/schedule/ScheduleHeader.tsx",
  import.meta.url
)
const hydrationUrl = new URL("../../src/app/hydration.ts", import.meta.url)
const fixturesUrl = new URL("./fixtures.ts", import.meta.url)

const [spec, config, authRoute, scheduleRoute, schedulePage, scheduleHeader, hydration, fixtures] =
  await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(authRouteUrl, "utf8"),
    readFile(scheduleRouteUrl, "utf8"),
    readFile(schedulePageUrl, "utf8"),
    readFile(scheduleHeaderUrl, "utf8"),
    readFile(hydrationUrl, "utf8"),
    readFile(fixturesUrl, "utf8"),
  ])

test("schedule hydration acceptance exercises real RU and EN document requests", () => {
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/schedule["']/u)
  assert.ok(spec.includes('new URL(page.url()).pathname).toBe("/schedule")'))
  assert.match(spec, /name:\s*["']ue:language["']/u)
  assert.match(spec, /localStorage\.setItem\(["']ue:language["']/u)
  assert.match(spec, /Russian schedule SSR markup hydrates without raw i18n keys/u)
  assert.match(spec, /English schedule SSR markup hydrates without raw i18n keys/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|useMockApi|page\.request/u)
  assert.match(
    fixtures,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*ROLES\[role\]\.password,\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
})

test("schedule assertions cover server markup, hydration, real content, and translation keys", () => {
  assert.match(spec, /response\?\.status\(\)\)\.toBe\(200\)/u)
  assert.match(spec, /response\?\.headers\(\)\[["']content-type["']\]/u)
  assert.match(spec, /serverLanguage\)\.toBe\(language\)/u)
  assert.match(spec, /data-ssr-auth=["']authenticated:student["']/u)
  assert.match(spec, /window\.__APP_HYDRATED\s*===\s*true/u)
  assert.match(spec, /getByRole\(["']heading["'],\s*\{\s*level:\s*1\s*\}\)/u)
  assert.ok(spec.includes('const scheduleViewName = language === "ru" ? "Расписание" : "Schedule"'))
  assert.ok(spec.includes('.getByRole("grid", { name: scheduleViewName, exact: true })'))
  assert.ok(
    spec.includes('.or(page.getByRole("tablist", { name: scheduleViewName, exact: true }))')
  )
  assert.match(spec, /rawTranslationKey/u)
  assert.match(spec, /hydrationDiagnostics/u)
  assert.match(spec, /uncaughtPageErrors/u)
  assert.match(hydration, /window\.__APP_HYDRATED\s*=\s*true/u)
  assert.match(scheduleRoute, /createFileRoute\(["']\/_auth\/schedule["']\)/u)
  assert.match(scheduleRoute, /scheduleGroupsQueryOptions/u)
  assert.match(scheduleRoute, /pageScheduleQueryOptions/u)
  assert.match(authRoute, /ssr:\s*true/u)
  assert.match(schedulePage, /<ScheduleDesktopTable/u)
  assert.match(schedulePage, /<ScheduleMobileView/u)
  assert.match(scheduleHeader, /<h1[\s\S]{0,260}schedule:title\.student/u)
})

test("schedule hydration has matching desktop/mobile projects and disables diagnostics artifacts", () => {
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(
    spec,
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']\s*\}\)/u
  )
})
