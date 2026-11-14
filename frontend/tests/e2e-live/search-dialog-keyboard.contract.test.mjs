import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

test("SearchDialog focus regression uses the real seeded browser and keyboard", async () => {
  const spec = await readFile(
    new URL("./search-dialog-keyboard.live.spec.ts", import.meta.url),
    "utf8"
  )
  const config = await readFile(new URL("../../playwright.live.config.ts", import.meta.url), "utf8")
  const dialog = await readFile(
    new URL("../../src/components/search/SearchDialog.tsx", import.meta.url),
    "utf8"
  )
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(dialog, /enabled:\s*open\s*&&\s*debouncedQuery\.length\s*>=\s*2/u)
  assert.match(dialog, /active:\s*open,\s*returnFocus:\s*true/u)
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /addInitScript[\s\S]*ue:deferred-global-overlays-ready/u)
  assert.match(spec, /waitForFunction/u)
  assert.match(spec, /#navbar-logo-link/u)
  assert.match(spec, /keyboard\.press\(["']Control\+k["']\)/u)
  assert.match(spec, /keyboard\.type\(["']x["']\)/u)
  assert.match(spec, /keyboard\.press\(["']Tab["']\)[\s\S]*expect\(clear\)\.toBeFocused\(\)/u)
  assert.match(
    spec,
    /keyboard\.press\(["']Shift\+Tab["']\)[\s\S]*expect\(clear\)\.toBeFocused\(\)/u
  )
  assert.match(
    spec,
    /keyboard\.press\(["']Escape["']\)[\s\S]*toHaveCount\(0\)[\s\S]*expect\(originalFocus\)\.toBeFocused\(\)/u
  )
  assert.doesNotMatch(
    spec,
    /fireEvent|\.route\(|route\.fulfill|test\.skip|waitForTimeout|focus-trap/u
  )
})

test("compact profile keyboard acceptance covers both available-width branches", async () => {
  const spec = await readFile(
    new URL("./search-dialog-keyboard.live.spec.ts", import.meta.url),
    "utf8"
  )
  const menu = await readFile(
    new URL("../../src/components/navbar/UserMenu.tsx", import.meta.url),
    "utf8"
  )
  const pill = await readFile(
    new URL("../../src/components/navbar/NavbarPill.tsx", import.meta.url),
    "utf8"
  )
  const seed = await readFile(
    new URL("../../../scripts/seed_demo_data.py", import.meta.url),
    "utf8"
  )
  const compact = spec.slice(
    spec.indexOf('test("compact navbar preserves native profile keyboard access"'),
    spec.indexOf('test.describe("controlled full-text search"')
  )
  assert.ok(compact.length > 0)
  assert.equal((spec.match(/\btest\("/gu) ?? []).length, 5, "retain the same five live cases")
  assert.match(pill, /"h-full max-w-none rounded-none"/u)
  assert.match(pill, /isCompact && isPhone \? "w-\[calc\(100%-1rem\)\]" : "w-full"/u)
  assert.match(menu, /@container\/profile-actions/u)
  assert.match(menu, /hidden @min-\[18rem\]\/profile-actions:block/u)
  assert.match(seed, /full_name="Тест Студентов"/u)
  assert.match(compact, /setViewportSize\(\{ width: 1920, height: 900 \}\)/u)
  assert.match(compact, /await page\.evaluate\(\(\) => document\.fonts\.ready\)/u)
  assert.match(compact, /toHaveAttribute\("lang", "ru"\)/u)
  assert.match(
    compact,
    /await page\s*\.context\(\)\s*\.addCookies\(\[\s*\{ name: "ue:language", value: "ru", url: new URL\(page\.url\(\)\)\.origin \},?\s*\]\)/u
  )
  assert.match(
    compact,
    /await page\.addInitScript\(\(\) => window\.localStorage\.setItem\("ue:language", "ru"\)\)/u
  )
  assert.equal((compact.match(/addCookies\(/gu) ?? []).length, 1)
  assert.equal((compact.match(/localStorage\.setItem\(/gu) ?? []).length, 1)
  assert.equal(
    (compact.match(/waitForFunction\(\(\) => window\.__APP_HYDRATED === true\)/gu) ?? []).length,
    4
  )
  assert.equal((compact.match(/toHaveAttribute\("lang", "ru"\)/gu) ?? []).length, 4)
  assert.match(
    compact,
    /getBoundingClientRect\(\)\.width \/\s*Number\.parseFloat\(getComputedStyle\(document\.documentElement\)\.fontSize\)/u
  )
  assert.equal(
    (
      compact.match(/expect\.poll\(readProfileActionsWidthRem\)\.toBeGreaterThanOrEqual\(18\)/gu) ??
      []
    ).length,
    2,
    "both expanded keyboard entries require the real 18rem container precondition"
  )
  assert.equal((compact.match(/await expect\(name\)\.toBeVisible\(\)/gu) ?? []).length, 2)
  assert.match(
    compact,
    /await avatar\.focus\(\)[\s\S]*?keyboard\.press\("Tab"\)[\s\S]*?expect\(name\)\.toBeFocused\(\)[\s\S]*?window\.scrollTo\(0, 180\)[\s\S]*?expect\(name\)\.toBeDisabled\(\)[\s\S]*?toHaveAttribute\("aria-hidden", "true"\)[\s\S]*?expect\(name\)\.not\.toBeFocused\(\)/u
  )
  assert.match(compact, /expect\.soft\(afterAvatar\.scrollY\)\.toBeGreaterThan\(24\)/u)
  for (const field of ["disabled", "hidden"]) {
    assert.ok(compact.includes(`expect.soft(afterAvatar.${field}).toBe(true)`))
  }
  assert.match(compact, /expect\.soft\(afterAvatar\.focus\)\.toBe\("avatar"\)/u)
  assert.match(
    compact,
    /keyboard\.press\("Tab"\)[\s\S]*?expect\(settings\)\.toBeFocused\(\)[\s\S]*?window\.scrollTo\(0, 180\)[\s\S]*?expect\(name\)\.toBeDisabled\(\)[\s\S]*?expect\(settings\)\.toBeFocused\(\)[\s\S]*?keyboard\.press\("Shift\+Tab"\)[\s\S]*?expect\(avatar\)\.toBeFocused\(\)/u
  )
  const narrow = compact.slice(compact.indexOf("await page.setViewportSize({ width: 1440"))
  assert.match(narrow, /expect\.poll\(readProfileActionsWidthRem\)\.toBeLessThan\(18\)/u)
  assert.match(narrow, /expect\(name\.locator\("\.\."\)\)\.toHaveCSS\("display", "none"\)/u)
  assert.match(narrow, /expect\(name\)\.toBeHidden\(\)/u)
  assert.match(narrow, /expect\(name\)\.toBeEnabled\(\)/u)
  assert.match(narrow, /expect\(name\)\.toHaveAttribute\("aria-hidden", "false"\)/u)
  assert.match(narrow, /expect\(name\)\.toHaveText\("Тест Студентов"\)/u)
  assert.match(narrow, /expect\(avatar\)\.toHaveAccessibleName\("Открыть профиль"\)/u)
  assert.match(
    narrow,
    /expect\(avatar\)\.toHaveAccessibleDescription\("Открыть профиль: Тест Студентов"\)/u
  )
  assert.match(
    narrow,
    /await avatar\.focus\(\)[\s\S]*?keyboard\.press\("Tab"\)[\s\S]*?expect\(settings\)\.toBeFocused\(\)[\s\S]*?keyboard\.press\("Shift\+Tab"\)[\s\S]*?expect\(avatar\)\.toBeFocused\(\)[\s\S]*?keyboard\.press\("Enter"\)[\s\S]*?toBe\("\/profile"\)/u
  )
  assert.equal(
    (compact.match(/toBe\("\/profile"\)/gu) ?? []).length,
    2,
    "retain name Enter and add avatar Enter"
  )
  assert.doesNotMatch(
    compact,
    /if\s*\(|\.isVisible\(|\.blur\(|preventScroll|name\.focus\(|settings\.focus\(|test\.skip|test\.slow|setTimeout|waitForTimeout|\.route\(|page\.request\.(?:post|put|patch|delete)|\.style\s*=/u
  )
})
