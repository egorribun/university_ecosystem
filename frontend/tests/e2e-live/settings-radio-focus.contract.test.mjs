import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

test("radio focus acceptance uses native keyboard and actual computed styles", async () => {
  const spec = await readFile(
    new URL("./settings-radio-focus.live.spec.ts", import.meta.url),
    "utf8"
  )
  const config = await readFile(new URL("../../playwright.live.config.ts", import.meta.url), "utf8")
  const radio = await readFile(
    new URL("../../src/components/ui/RadioGroup.tsx", import.meta.url),
    "utf8"
  )
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(spec, /from\s*["']\.\/fixtures["']/u)
  assert.match(spec, /loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/settings["']\)/u)
  assert.match(spec, /Тема\|Theme/u)
  assert.match(spec, /Система\|System/u)
  assert.match(spec, /expect\(accordion\)\.toBeFocused\(\)/u)
  assert.match(spec, /ancestor::label/u)
  assert.match(spec, /peer-focus-visible:shadow-focus/u)
  assert.match(spec, /getComputedStyle\(element\)\.boxShadow/u)
  assert.match(
    spec,
    /keyboard\.press\(["']Tab["']\)[\s\S]*expect\(systemRadio\)\.toBeFocused\(\)/u
  )
  assert.match(spec, /matches\(["']:focus-visible["']\)/u)
  assert.match(spec, /expect\.poll\(boxShadow\)\.not\.toBe\(unfocusedShadow\)/u)
  assert.match(
    spec,
    /keyboard\.press\(["']Shift\+Tab["']\)[\s\S]*expect\(accordion\)\.toBeFocused\(\)/u
  )
  assert.match(spec, /expect\.poll\(boxShadow\)\.toBe\(unfocusedShadow\)/u)
  assert.match(spec, /expect\(systemRadio\)\.toBeChecked\(\)/u)
  assert.match(radio, /peer sr-only/u)
  assert.match(radio, /peer-focus-visible:shadow-focus/u)
  assert.match(spec, /trace:\s*["']off["']/u)
  assert.match(spec, /screenshot:\s*["']off["']/u)
  assert.match(spec, /video:\s*["']off["']/u)
  assert.doesNotMatch(
    spec,
    /systemRadio\.click|\.focus\(|chooseTheme|localStorage|addInitScript|\.route\(|routeWebSocket|test\.skip|waitForTimeout/u
  )
})

test("semantic tokens use production CSS without changing saved theme", async () => {
  const spec = await readFile(
    new URL("./settings-radio-focus.live.spec.ts", import.meta.url),
    "utf8"
  )
  assert.match(spec, /Semantic tokens preserve percentage alpha in both themes/u)
  assert.match(spec, /\["light", "dark"\] as const/u)
  assert.match(spec, /colorScheme:\s*scheme/u)
  assert.match(spec, /page\.locator\("html"\).*toHaveAttribute\("data-color-scheme", scheme\)/u)
  assert.match(spec, /page\.locator\("body"\).*toHaveAttribute\("data-color-scheme", scheme\)/u)
  assert.match(spec, /expect\(systemRadio\)\.toBeChecked\(\)/u)
  for (const token of [
    "--bg-panel",
    "--raw-shadow-glass",
    "--shadow-glow-primary",
    "--opacity-dim",
    "--raw-shadow-focus",
  ]) {
    assert.ok(spec.includes(`var(${token})`), `Actual token ${token} must be observed`)
  }
  assert.match(spec, /70%, transparent/u)
  assert.match(spec, /black 20%, transparent/u)
  assert.match(spec, /var\(--primary-main\) 20%, transparent/u)
  assert.match(spec, /getComputedStyle\(probe\)\.getPropertyValue\(property\)/u)
  assert.match(spec, /expect\(tokens\.opacity\)\.toBe\("0\.2"\)/u)
  assert.match(spec, /expect\(tokens\.focus\)\.toBe\(tokens\.focusExpected\)/u)
  assert.match(spec, /expect\.soft\(tokens\.panel,[^\n]+\.toBe\(tokens\.panelExpected\)/u)
  assert.match(spec, /expect\.soft\(tokens\.glass,[^\n]+\.toBe\(tokens\.glassExpected\)/u)
  assert.match(spec, /expect\.soft\(tokens\.glow,[^\n]+\.toBe\(tokens\.glowExpected\)/u)
  for (const token of [
    "glass-bg-high",
    "grad-nav-light",
    "grad-nav-dark",
    "bg-footer-light",
    "bg-footer-dark",
  ]) {
    assert.ok(spec.includes(`name: "${token}"`), `Remaining token ${token} must be compared`)
  }
  assert.match(spec, /expected: mix\("white", 20\)/u)
  assert.match(spec, /radial\("var\(--color-blue-400\)", 50, 58\)/u)
  assert.match(spec, /radial\("var\(--color-sky-400\)", 20, 58\)/u)
  assert.match(spec, /radial\("var\(--color-blue-400\)", 15, 60\)/u)
  assert.match(spec, /const dashboard = document\.querySelector\("\.dashboard-theme"\)/u)
  assert.match(spec, /const scope = dashboard \?\? document\.body/u)
  assert.match(spec, /scope\.append\(host\)/u)
  assert.match(spec, /await page\.goto\("\/dashboard"\)/u)
  assert.match(spec, /page\.locator\("\.dashboard-theme"\)\)\.toBeVisible\(\)/u)
  assert.match(spec, /read\("background-color", "var\(--dash-hero-orb\)"\)/u)
  assert.match(spec, /mix\("var\(--color-sky-400\)", dark \? 18 : 15\)/u)
  assert.match(
    spec,
    /expect\.soft\(tokens\.dashboardOrb, label\)\.toBe\(tokens\.dashboardOrbExpected\)/u
  )
  // Finite AUD-072 references: property, theme scope, and literal expectation.
  // This guards the reviewed map, not merely the number of browser probes.
  const casesStart = spec.indexOf("const cases = [")
  const dashboardStart = spec.indexOf("const dashboardCases = [")
  const returnStart = spec.indexOf("return {", dashboardStart)
  assert.ok(casesStart >= 0 && dashboardStart > casesStart && returnStart > dashboardStart)
  const globalSource = spec.slice(casesStart, dashboardStart)
  const darkOnly = globalSource.match(/\.\.\.\(dark\s*\?\s*\[([\s\S]*?)\]\s*:\s*\[\]\)/u)
  assert.ok(darkOnly, "The two dark-only declarations must remain inside the dark guard")
  const scopes = {
    global: globalSource.slice(0, globalSource.indexOf("...(dark")),
    dark: darkOnly[1],
    dashboard: spec.slice(dashboardStart, returnStart),
  }
  const compact = (source) => source.replace(/\s+/gu, "").replace(/,([)\]}])/gu, "$1")
  const references = [
    ["global", "raw-shadow-xs", "box-shadow", `shadow("0 1px 2px", "black", 5)`],
    [
      "global",
      "raw-shadow-md",
      "box-shadow",
      `[shadow("0 4px 12px", "black", 10), shadow("0 2px 4px", "black", 5)].join(", ")`,
    ],
    [
      "global",
      "raw-shadow-premium",
      "box-shadow",
      `[shadow("0 20px 50px", "black", 10), shadow("0 8px 16px", "black", 5)].join(", ")`,
    ],
    [
      "global",
      "raw-shadow-premium-lift",
      "box-shadow",
      `shadow("0 20px 40px -12px", "var(--primary-main)", 20)`,
    ],
    ["global", "raw-shadow-glass-strong", "box-shadow", `shadow("0 45px 90px", "black", 50)`],
    ["global", "raw-shadow-up", "box-shadow", `shadow("0 -4px 12px", "black", 5)`],
    ["global", "shadow-glow-error", "box-shadow", `shadow("0 0 12px", "var(--error-text)", 20)`],
    [
      "global",
      "shadow-glow-warning",
      "box-shadow",
      `shadow("0 0 12px", "var(--warning-text)", 20)`,
    ],
    [
      "global",
      "shadow-glow-success",
      "box-shadow",
      `shadow("0 0 12px", "var(--success-text)", 20)`,
    ],
    ["global", "bg-nav-light", "background-color", `mix("var(--color-white)", 90)`],
    ["global", "bg-nav-dark", "background-color", `mix("var(--color-slate-950)", 90)`],
    [
      "global",
      "msg-online-pulse",
      "background-color",
      `mix(dark ? "var(--color-emerald-400)" : "var(--success-text)", 30)`,
    ],
    [
      "global",
      "glass-bg",
      "background-color",
      `mix(dark ? "var(--color-slate-900)" : "white", 10)`,
    ],
    [
      "global",
      "shadow-glass",
      "box-shadow",
      `shadow("0 8px 32px 0", dark ? "var(--color-black)" : "var(--color-slate-900)", dark ? 30 : 10)`,
    ],
    [
      "global",
      "glass-tint1",
      "background-color",
      `mix(dark ? "var(--color-sky-400)" : "white", dark ? 5 : 10)`,
    ],
    [
      "global",
      "glass-tint2",
      "background-color",
      `mix(dark ? "var(--color-indigo-400)" : "white", 5)`,
    ],
    [
      "global",
      "primary-subtle",
      "background-color",
      `dark ? mix("var(--color-sky-400)", 10) : "var(--color-blue-50)"`,
    ],
    [
      "global",
      "success-bg",
      "background-color",
      `dark ? mix("var(--color-emerald-500)", 20) : "var(--color-green-100)"`,
    ],
    [
      "global",
      "warning-bg",
      "background-color",
      `dark ? mix("var(--color-amber-500)", 20) : "var(--color-amber-100)"`,
    ],
    [
      "global",
      "msg-sidebar-active",
      "background-color",
      `dark ? mix("var(--primary-main)", 10) : "var(--color-blue-50)"`,
    ],
    ["dark", "overlay-bg", "background-color", `mix("black", 80)`],
    [
      "dark",
      "shadow-glass-strong",
      "box-shadow",
      `shadow("0 12px 48px 0", "var(--color-black)", 50)`,
    ],
    [
      "dashboard",
      "dash-hero-radial-top",
      "background-color",
      `mix("var(--color-sky-400)", dark ? 15 : 20)`,
    ],
    [
      "dashboard",
      "dash-hero-highlight",
      "background-color",
      `mix(dark ? "var(--color-indigo-400)" : "var(--color-indigo-500)", 10)`,
    ],
    [
      "dashboard",
      "dash-hero-highlight-soft",
      "background-color",
      `mix(dark ? "var(--color-sky-400)" : "var(--primary-main)", dark ? 6 : 5)`,
    ],
  ]
  for (const [scope, name, property, expected] of references) {
    const declaration = `{name:"${name}",property:"${property}",expected:${expected}}`
    assert.ok(
      compact(scopes[scope]).includes(compact(declaration)),
      `Token ${name} must retain its ${scope} property and independent reference`
    )
  }
  assert.match(spec, /expect\(tokens\.cohort\)\.toHaveLength\(scheme === "dark" \? 39 : 37\)/u)
  assert.match(spec, /dashboardCohort:\s*dashboard\s*\?\s*dashboardCases\.map/u)
  assert.match(spec, /expect\(tokens\.dashboardCohort\)\.toHaveLength\(3\)/u)
  assert.match(spec, /for \(const probe of tokens\.dashboardCohort\)/u)
  assert.match(spec, /expect\.soft\(probe\.actual, probeLabel\)\.toBe\(probe\.expected\)/u)
  assert.match(spec, /finally\s*\{\s*probe\.remove\(\)/u)
  assert.match(spec, /finally\s*\{\s*host\.remove\(\)/u)
  assert.doesNotMatch(
    spec,
    /addStyleTag|createElement\(["']style["']\)|setProperty\(["']--|classList\.|chooseTheme|localStorage|addInitScript|\.route\(|routeWebSocket|test\.skip|waitForTimeout/u
  )
})
