import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./settings-theme-roundtrip.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const [spec, config] = await Promise.all([readFile(specUrl, "utf8"), readFile(configUrl, "utf8")])

test("live theme round-trip uses the Settings UI and verifies browser-persisted state", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /await page\.goto\(["']\/settings["']/u)
  assert.match(spec, /page\.getByRole\("radio", \{ name \}\)/u)
  assert.match(spec, /option\.locator\("xpath=ancestor::label"\)\.click\(\)/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /page\.locator\("html"\)[\s\S]*?toHaveClass/u)
  assert.match(spec, /localStorage\.getItem\(key\)/u)
  assert.match(spec, /page\.evaluate\(\(\) => document\.cookie\)/u)

  const afterReload = spec.slice(spec.indexOf("await page.reload()"))
  assert.match(
    afterReload,
    /getByRole\("radio", \{ name: \/Тёмная\|Dark\/i \}\)\)\.toBeChecked\(\)/u
  )
  assert.match(afterReload, /localStorage\.getItem\(key\)[\s\S]*?\.toBe\("dark"\)/u)
  assert.match(afterReload, /document\.cookie\)\)\.toContain\("ue-mode=dark"\)/u)
  assert.match(afterReload, /locator\("html"\)\)\.toHaveClass\(\/\\bdark\\b\/u\)/u)

  assert.match(spec, /const LANGUAGE_KEY = "ue:language"/u)
  assert.match(spec, /async function openLanguageOptions\(page: Page\)/u)
  assert.match(spec, /async function chooseLanguage\(page: Page, name: RegExp\)/u)
  assert.match(spec, /async function verifyReloadedAppearance/u)
  const englishReloadCheck = spec.indexOf('await verifyReloadedAppearance(page, "en"')
  const englishLightReloadCheck = spec.indexOf(
    'await verifyReloadedAppearance(page, "en", /Settings/u, /English/u, "light", /Light/u)'
  )
  const russianReloadCheck = spec.indexOf(
    'await verifyReloadedAppearance(page, "ru", /Настройки/u, /Русский/u, "light", /Светлая/u)'
  )
  assert.ok(
    englishReloadCheck >= 0 &&
      englishLightReloadCheck > englishReloadCheck &&
      russianReloadCheck > englishReloadCheck &&
      spec.lastIndexOf("await page.reload()", englishReloadCheck) >= 0 &&
      spec.lastIndexOf("await page.reload()", englishLightReloadCheck) > englishReloadCheck &&
      spec.lastIndexOf("await page.reload()", russianReloadCheck) > englishReloadCheck,
    "English and Russian settings plus light and dark theme modes must be reloaded and verified through the UI"
  )
  const reloadAppearanceHelper = spec.slice(
    spec.indexOf("async function verifyReloadedAppearance"),
    spec.indexOf("test(", spec.indexOf("async function verifyReloadedAppearance"))
  )
  assert.match(reloadAppearanceHelper, /toHaveAttribute\("lang", language\)/u)
  assert.match(reloadAppearanceHelper, /getByRole\("heading",\s*\{\s*name: settingsHeading/u)
  assert.match(reloadAppearanceHelper, /localStorage\.getItem\(key\)[\s\S]*?\.toBe\(language\)/u)
  assert.match(
    reloadAppearanceHelper,
    /document\.cookie[\s\S]*?toContain\(`ue:language=\$\{language\}`\)/u
  )
  assert.match(reloadAppearanceHelper, /toHaveClass\(\/\\bdark\\b\/u\)/u)
  assert.match(reloadAppearanceHelper, /not\.toHaveClass\(\/\\bdark\\b\/u\)/u)
  assert.match(reloadAppearanceHelper, /localStorage\.getItem\(key\)[\s\S]*?\.toBe\(theme\)/u)
  assert.match(
    reloadAppearanceHelper,
    /document\.cookie[\s\S]*?toContain\(`ue-mode=\$\{theme\}`\)/u
  )

  const systemSelection = spec.indexOf("await chooseTheme(page, /Система|System/i)")
  const explicitDarkSelection = spec.indexOf(
    "await chooseTheme(page, /Тёмная|Dark/i)",
    systemSelection
  )
  const systemOsDark = spec.indexOf(
    'await page.emulateMedia({ colorScheme: "dark"',
    systemSelection
  )
  const systemOsLight = spec.indexOf('await page.emulateMedia({ colorScheme: "light"', systemOsDark)
  assert.ok(
    systemSelection >= 0 &&
      systemOsDark > systemSelection &&
      systemOsLight > systemOsDark &&
      explicitDarkSelection > systemOsLight,
    "the live acceptance must change OS color scheme both ways while System remains selected"
  )
  const systemOsDarkTransition = spec.slice(systemOsDark, systemOsLight)
  const systemOsLightTransition = spec.slice(systemOsLight, explicitDarkSelection)
  assert.match(systemOsDarkTransition, /locator\("html"\)\)\.toHaveClass\(\/\\bdark\\b\/u\)/u)
  assert.match(systemOsDarkTransition, /localStorage\.getItem\(key\)[\s\S]*?\.toBe\("system"\)/u)
  assert.match(systemOsDarkTransition, /document\.cookie\)\)\.toContain\("ue-mode=system"\)/u)
  assert.match(systemOsLightTransition, /locator\("html"\)\)\.not\.toHaveClass\(\/\\bdark\\b\/u\)/u)
  assert.match(systemOsLightTransition, /localStorage\.getItem\(key\)[\s\S]*?\.toBe\("system"\)/u)
  assert.match(systemOsLightTransition, /document\.cookie\)\)\.toContain\("ue-mode=system"\)/u)

  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|useMockApi|vi\.mock|page\.request/u,
    "the live theme acceptance must use the actual app without API mocks"
  )
  assert.doesNotMatch(
    spec,
    /page\.addInitScript|localStorage\.setItem|sessionStorage\.(?:getItem|setItem)|document\.cookie\s*=/u,
    "the live preference must be changed and restored through UI controls, not storage injection"
  )
})
