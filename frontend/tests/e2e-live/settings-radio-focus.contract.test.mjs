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
  assert.match(spec, /peer-focus-visible:ring-4/u)
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
  assert.match(radio, /peer-focus-visible:ring-4/u)
  assert.match(spec, /trace:\s*["']off["']/u)
  assert.match(spec, /screenshot:\s*["']off["']/u)
  assert.match(spec, /video:\s*["']off["']/u)
  assert.doesNotMatch(
    spec,
    /systemRadio\.click|\.focus\(|chooseTheme|localStorage|addInitScript|\.route\(|routeWebSocket|test\.skip|waitForTimeout/u
  )
})
