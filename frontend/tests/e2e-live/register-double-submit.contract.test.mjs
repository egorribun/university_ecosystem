import assert from "node:assert/strict"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./register-double-submit.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const registerUrl = new URL("../../src/pages/Register.tsx", import.meta.url)

test("live registration double-submit acceptance uses one real owned account", async () => {
  assert.equal(
    existsSync(specUrl),
    true,
    "the mobile double-submit registration acceptance must exist"
  )

  const [spec, config, register] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(registerUrl, "utf8"),
  ])

  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(register, /api\.post\(["']\/auth\/register["']/u)
  assert.match(register, /navigate\(\{\s*to:\s*["']\/login["']\s*\}\)/u)
  assert.match(register, /disabled=\{isSubmitting\}/u)

  assert.match(spec, /page\.setViewportSize\(\{\s*width:\s*360/u)
  assert.match(spec, /stubBreachedPasswordLookup\(page\)/u)
  const registrationNavigation = spec.indexOf(
    'await page.goto("/register", { waitUntil: "domcontentloaded" })'
  )
  const hydrationWait = spec.indexOf(
    "await page.waitForFunction(() => window.__APP_HYDRATED === true)",
    registrationNavigation
  )
  const firstFormInteraction = spec.indexOf('await page.locator("#full_name").fill')
  assert.ok(
    registrationNavigation >= 0 &&
      hydrationWait > registrationNavigation &&
      firstFormInteraction > hydrationWait,
    "registration controls must not be interacted with before React hydration"
  )
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /touchscreen\.tap\(x,\s*y\)/u)
  assert.match(spec, /dblclick\(/u)
  assert.match(spec, /registerPostCount/u)
  assert.match(spec, /expect\(registerPostCount\)\.toBe\(1\)/u)
  assert.match(spec, /registrationBody\?\.id/u)
  assert.match(spec, /deleteOwnedAccount\(/u)
  assert.match(spec, /method:\s*["']DELETE["']/u)
  assert.match(spec, /const createdUserIds = new Set<string>\(\)/u)
  assert.match(spec, /request\s*\.response\(\)/u)
  assert.match(spec, /createdUserIds\.add\(/u)
  assert.match(
    spec,
    /finally \{[\s\S]*?await Promise\.all\(registrationResponseCaptures\)[\s\S]*?for \(const userId of createdUserIds\)[\s\S]*?deleteOwnedAccount\(browser, userId\)/u,
    "cleanup must await every registration response and delete every exact successful account ID"
  )
  assert.doesNotMatch(spec, /let createdUserId: string \| null/u)
  assert.match(spec, /\/login\$/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|page\.request|fulfill\(/u)
  assert.doesNotMatch(spec, /password\s*[:=]\s*["'][^"']+/iu)
})
