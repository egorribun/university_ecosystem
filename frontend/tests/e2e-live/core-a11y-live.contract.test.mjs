import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./core-a11y-live.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const planUrl = new URL("../../../docs/superpowers/plans/MVP_MASTER_PLAN.md", import.meta.url)

test("real authenticated core-route axe acceptance checks serious and critical findings", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the authenticated core-route accessibility live scenario must exist")
  }

  const [fixtures, config, plan] = await Promise.all([
    readFile(fixtureUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(planUrl, "utf8"),
  ])

  assert.match(plan, /отсутствие serious\/critical axe\s+findings/u)
  assert.match(spec, /import AxeBuilder from ["']@axe-core\/playwright["']/u)
  assert.match(spec, /loginAs\(page, ["']student["']\)/u)
  assert.match(spec, /CORE_ROUTES\s*=\s*\[[\s\S]*?["']\/dashboard["'][\s\S]*?["']\/settings["']/u)
  assert.match(spec, /for\s*\(const route of CORE_ROUTES\)[\s\S]*?page\.goto\(route\)/u)
  assert.match(spec, /WCAG_TAGS\s*=\s*\[[\s\S]*?["']wcag22aa["']/u)
  assert.match(spec, /new AxeBuilder\(\{\s*page\s*\}\)\.withTags\(WCAG_TAGS\)\.analyze\(\)/u)
  assert.match(spec, /impact === ["']critical["'][\s\S]*?impact === ["']serious["']/u)
  assert.match(spec, /blocking\.map\(\s*\(\{\s*impact,\s*id\s*\}/u)
  assert.doesNotMatch(spec, /page\.route\(|routeFromHAR|useMockApi/u)
  assert.doesNotMatch(spec, /JSON\.stringify\(blocking[\s\S]{0,100}(?:html|nodes|failureSummary)/u)
  assert.match(
    fixtures,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*ROLES\[role\]\.password,\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
})
