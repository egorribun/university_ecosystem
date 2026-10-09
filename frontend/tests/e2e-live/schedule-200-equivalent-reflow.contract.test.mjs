import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./schedule-200-equivalent-reflow.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const routeUrl = new URL("../../src/routes/_auth/schedule.tsx", import.meta.url)
const schedulePageUrl = new URL("../../src/pages/Schedule.tsx", import.meta.url)
const scheduleHeaderUrl = new URL(
  "../../src/components/schedule/ScheduleHeader.tsx",
  import.meta.url
)
const settingsPanelUrl = new URL(
  "../../src/components/schedule/ScheduleSettingsPanel.tsx",
  import.meta.url
)

const [spec, fixtures, config, route, schedulePage, scheduleHeader, settingsPanel] =
  await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(routeUrl, "utf8"),
    readFile(schedulePageUrl, "utf8"),
    readFile(scheduleHeaderUrl, "utf8"),
    readFile(settingsPanelUrl, "utf8"),
  ])

test("schedule reflow runs as a real desktop 200%-equivalent viewport scenario", () => {
  assert.match(spec, /testInfo\.project\.name\s*!==\s*["']desktop["']/u)
  assert.match(spec, /width:\s*720,\s*height:\s*450/u)
  assert.match(spec, /200%-equivalent CSS viewport/u)
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/schedule["']\)/u)
  assert.ok(spec.includes('new URL(page.url()).pathname).toBe("/schedule")'))
  assert.doesNotMatch(spec, /page\.route\(|routeFromHAR|useMockApi|mock(?:ed)?Api/u)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)\(/u)

  assert.match(
    fixtures,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*ROLES\[role\]\.password,\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
  assert.match(route, /createFileRoute\(["']\/_auth\/schedule["']\)/u)
  assert.match(route, /scheduleGroupsQueryOptions/u)
  assert.match(route, /pageScheduleQueryOptions/u)
})

test("reflow contract checks key content, horizontal overflow, and keyboard dialog flow", () => {
  assert.match(spec, /getByRole\(["']heading["'],\s*\{\s*level:\s*1\s*\}\)/u)
  assert.match(spec, /getByRole\(["']tablist["']\)/u)
  assert.match(spec, /aria-selected[\s\S]{0,80}visible|selected:\s*true/u)
  assert.match(spec, /width:\s*window\.innerWidth/u)
  assert.match(
    spec,
    /scrollWidth:\s*Math\.max\(document\.documentElement\.scrollWidth,\s*document\.body\.scrollWidth\)/u
  )
  assert.match(
    spec,
    /expect\(viewport\.scrollWidth\)\.toBeLessThanOrEqual\(viewport\.width\s*\+\s*1\)/u
  )
  assert.match(spec, /getByRole\(["']button["'],\s*\{\s*name:[\s\S]{0,80}settings|настройки/iu)
  assert.match(spec, /\.focus\(\)[\s\S]{0,120}press\(["']Enter["']\)/u)
  assert.match(spec, /getByRole\(["']dialog["']\)/u)
  assert.match(spec, /press\(["']Escape["']\)[\s\S]{0,160}toBeFocused\(\)/u)

  assert.match(schedulePage, /isMobile\s*\?\s*\(/u)
  assert.match(schedulePage, /<ScheduleMobileView/u)
  assert.match(scheduleHeader, /aria-label=\{t\(["']schedule:toolbar\.settings["']\)\}/u)
  assert.match(settingsPanel, /role="dialog"[\s\S]{0,100}aria-modal="true"/u)
  assert.match(settingsPanel, /useFocusTrap/u)
})

test("the live contract uses protected real-stand projects with diagnostics disabled", () => {
  assert.match(
    spec,
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']\s*\}\)/u
  )
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
})
