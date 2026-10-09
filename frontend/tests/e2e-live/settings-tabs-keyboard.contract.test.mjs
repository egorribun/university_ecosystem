import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const read = (path) => readFile(new URL(path, import.meta.url), "utf8")

const [
  spec,
  fixtures,
  config,
  settingsPage,
  settingsTabs,
  settingsRoute,
  russianSettings,
  englishSettings,
] = await Promise.all([
  read("./settings-tabs-keyboard.live.spec.ts"),
  read("./fixtures.ts"),
  read("../../playwright.live.config.ts"),
  read("../../src/pages/Settings.tsx"),
  read("../../src/components/settings/ui/Layout.tsx"),
  read("../../src/routes/_auth/settings.tsx"),
  read("../../src/i18n/locales/ru/settings.json"),
  read("../../src/i18n/locales/en/settings.json"),
])

test("Settings tab keyboard acceptance uses the live authenticated route without API mocks", () => {
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/settings["']\)/u)
  assert.match(
    spec,
    /getByRole\(["']tablist["'],\s*\{\s*name:\s*\/Разделы настроек\|Settings sections\/u\s*\}\)/u
  )
  assert.match(spec, /getByRole\(["']tab["']\)/u)
  for (const key of ["ArrowRight", "ArrowLeft", "Home", "End"]) {
    assert.match(spec, new RegExp(`keyboard\\.press\\(["']${key}["']\\)`, "u"))
  }
  assert.match(spec, /keyboard\.press\(["']Tab["']\)/u)
  assert.match(spec, /keyboard\.press\(["']Shift\+Tab["']\)/u)
  assert.match(spec, /toBeFocused\(\)/u)
  assert.match(spec, /toBeVisible\(\)/u)
  assert.match(spec, /toHaveAttribute\(["']aria-selected["'],\s*["']true["']\)/u)
  assert.match(spec, /toHaveAttribute\(["']aria-selected["'],\s*["']false["']\)/u)
  assert.match(spec, /toHaveAttribute\(["']tabindex["'],\s*["']0["']\)/u)
  assert.match(spec, /toHaveAttribute\(["']tabindex["'],\s*["']-1["']\)/u)
  assert.match(spec, /toHaveAttribute\(["']aria-controls["']/u)
  assert.match(spec, /toHaveAttribute\(["']aria-controls["'],\s*panelId/u)
  assert.match(spec, /new Set\(tabIds\)\.size\).*toBe\(6\)/u)
  assert.match(spec, /toHaveAttribute\(["']aria-labelledby["']/u)
  assert.match(spec, /toHaveURL\(url\)/u)
  assert.match(spec, /expectSelection\(1,\s*\/[^\n]*tab=1/u)
  assert.match(spec, /expectSelection\(5,\s*\/[^\n]*tab=5/u)
  assert.match(spec, /getByRole\(["']tabpanel["']\)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeFromHAR|page\.request\.|useMockApi|vi\.mock/u)

  assert.match(
    fixtures,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*ROLES\[role\]\.password,\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
  assert.match(settingsRoute, /createFileRoute\(["']\/_auth\/settings["']\)/u)
  assert.match(settingsPage, /ariaLabel=\{t\(["']settings:tabs\.ariaLabel["']\)\}/u)
  assert.match(russianSettings, /"ariaLabel":\s*"Разделы настроек"/u)
  assert.match(englishSettings, /"ariaLabel":\s*"Settings sections"/u)
})

test("the real Settings tabs retain APG keyboard focus and URL-linked panel semantics", () => {
  assert.match(
    settingsTabs,
    /case ["']ArrowRight["']:[\s\S]{0,100}nextIndex\s*=\s*\(value\s*\+\s*1\)\s*%\s*tabCount/u
  )
  assert.match(
    settingsTabs,
    /case ["']ArrowLeft["']:[\s\S]{0,120}nextIndex\s*=\s*\(value\s*-\s*1\s*\+\s*tabCount\)\s*%\s*tabCount/u
  )
  assert.match(settingsTabs, /case ["']Home["']:[\s\S]{0,80}nextIndex\s*=\s*0/u)
  assert.match(settingsTabs, /case ["']End["']:[\s\S]{0,100}nextIndex\s*=\s*tabCount\s*-\s*1/u)
  assert.match(settingsTabs, /queueMicrotask\(\(\)\s*=>\s*focusTab\(nextIndex/u)
  assert.match(settingsTabs, /aria-orientation="horizontal"/u)
  assert.match(settingsTabs, /aria-label=\{ariaLabel\}/u)
  assert.match(settingsTabs, /tabIndex=\{selected\s*\?\s*0\s*:\s*-1\}/u)
  assert.match(settingsTabs, /aria-controls=\{panelId\}/u)
  assert.match(settingsPage, /<Tabs[\s\S]{0,240}panelId=\{settingsPanelId\}/u)
  assert.match(settingsPage, /role="tabpanel"[\s\S]{0,100}aria-labelledby=\{activeTabId\}/u)
  assert.match(settingsPage, /tabIndex=\{0\}/u)
  assert.match(settingsPage, /out\.tab\s*=\s*next/u)
})

test("the live scenario uses the configured desktop/mobile Chromium projects without artifacts", () => {
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
