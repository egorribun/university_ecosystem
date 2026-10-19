import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
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
