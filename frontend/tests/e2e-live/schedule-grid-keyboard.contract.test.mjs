import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const read = (path) => readFile(new URL(path, import.meta.url), "utf8")

const [spec, fixtures, config, schedulePage, keyboardHook, scheduleRoute] = await Promise.all([
  read("./schedule-grid-keyboard.live.spec.ts"),
  read("./fixtures.ts"),
  read("../../playwright.live.config.ts"),
  read("../../src/pages/Schedule.tsx"),
  read("../../src/hooks/useScheduleKeyboardNav.ts"),
  read("../../src/routes/_auth/schedule.tsx"),
])

test("schedule grid keyboard acceptance uses the real seeded desktop route", () => {
  assert.match(spec, /testInfo\.project\.name\s*!==\s*["']desktop["']/u)
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/schedule["']\)/u)
  assert.match(spec, /getByRole\(["']grid["']\)/u)
  assert.match(spec, /locator\('\[id\^="lesson-card-"\]'\)/u)
  assert.match(spec, /press\(["']ArrowLeft["']\)[\s\S]*press\(["']Enter["']\)/u)
  assert.match(spec, /await expect\(cell\)\.toBeFocused\(\)[\s\S]*press\(["']Enter["']\)/u)
  assert.match(spec, /getByRole\(["']dialog["']\)/u)
  assert.match(
    spec,
    /detailsDialog\.evaluate\(\(dialog\)\s*=>\s*dialog\.contains\(document\.activeElement\)\)/u
  )
  assert.match(
    spec,
    /page\.keyboard\.press\(["']Escape["']\)[\s\S]*?detailsDialog\)\.toBeHidden\(\)[\s\S]*?expect\(cell\)\.toBeFocused\(\)/u
  )
  assert.doesNotMatch(spec, /page\.route\(|routeFromHAR|mock(?:ed)?Api/u)

  assert.match(fixtures, /export async function loginAs\(page: Page, role: Role\)/u)
  assert.match(scheduleRoute, /createFileRoute\(["']\/_auth\/schedule["']\)/u)
  assert.match(scheduleRoute, /scheduleGroupsQueryOptions/u)
  assert.match(scheduleRoute, /pageScheduleQueryOptions/u)
})

test("Enter resolves the visible keyboard-grid coordinates to the lesson details dialog", () => {
  const enterBranch = keyboardHook.match(/case ["']Enter["']:[\s\S]*?(?=case ["']e["']:)/u)?.[0]
  assert.ok(enterBranch, "the keyboard hook must handle Enter")
  assert.match(keyboardHook, /const pos = activeCell \?\? \{ row: 0, col: 0 \}/u)
  assert.match(
    enterBranch,
    /if \(target instanceof Element && target\.closest\(["']button, a\[href\]["']\)\) return\s*e\.preventDefault\(\)/u
  )
  assert.match(enterBranch, /const row = Math\.max\(0, Math\.min\(pos\.row, rowCount - 1\)\)/u)
  assert.match(enterBranch, /const col = Math\.max\(0, Math\.min\(pos\.col, colCount - 1\)\)/u)
  assert.match(
    enterBranch,
    /if \(row !== pos\.row \|\| col !== pos\.col\) moveTo\(row, col\)\s*onOpen\?\.\(row, col\)/u
  )
  assert.match(schedulePage, /visibleWeekdayBackend\s*=\s*useMemo/u)
  assert.match(schedulePage, /buildTable\(displaySchedule,\s*visibleWeekdayBackend\)/u)
  assert.match(schedulePage, /onOpen:\s*handleKbOpen/u)
  assert.match(
    schedulePage,
    /keyboardRows\[row\]\?\.\[col\][\s\S]{0,100}openDialog\(["']details["']/u
  )
  assert.match(spec, /expect\(detailsDialog\)\.toBeVisible\(\)/u)
})

test("keyboard live acceptance keeps diagnostics and retained artifacts disabled", () => {
  assert.match(
    spec,
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']\s*\}\)/u
  )
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
})
