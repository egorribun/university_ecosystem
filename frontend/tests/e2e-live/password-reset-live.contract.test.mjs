import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { URL, fileURLToPath } from "node:url"
import test from "node:test"

const specPath = fileURLToPath(new URL("./password-reset.live.spec.ts", import.meta.url))
const configPath = fileURLToPath(new URL("../../playwright.live.config.ts", import.meta.url))
const fixturePath = fileURLToPath(new URL("./fixtures.ts", import.meta.url))

test("password reset rejects redirect abuse, reuse, and cleanup outside its own user", () => {
  const source = readFileSync(specPath, "utf8")
  const config = readFileSync(configPath, "utf8")

  assert.match(source, /live-reset-\$\{testInfo\.project\.name\}-\$\{randomUUID\(\)\}/u)
  assert.match(source, /waitForResponse\([\s\S]*?\/auth\/register/u)
  assert.match(source, /createdUserId = registrationBody\.id/u)
  assert.match(source, /awaitMail\(email, RESET_LINK\)/u)
  assert.match(source, /new URL\(resetMatch\[0\], page\.url\(\)\)/u)
  assert.match(source, /redirect-target\.invalid/u)
  assert.match(source, /searchParams\.set\("redirect"/u)
  assert.match(source, /openResetLink\(page, resetUrl\.href\)/u)
  assert.match(source, /searchParams\.has\("token"\)/u)
  assert.match(source, /await page\.goBack\(\)/u)
  assert.match(source, /toHaveURL\(new URL\("\/login", resetOrigin\)\.href\)/u)
  assert.match(source, /new URL\(page\.url\(\)\)\.search === ""/u)
  assert.match(source, /expect\(replayFeedback\.containsResetToken\)\.toBe\(false\)/u)
  assert.match(source, /const replayResponse = page\.waitForResponse\(/u)
  assert.match(source, /replayResponse[\s\S]*?status\(\)[\s\S]*?\.toBe\(400\)/u)
  for (const submitId of ["login-submit", "reset-submit-btn"]) {
    assert.match(
      source,
      new RegExp(
        `page\\s*\\.locator\\("form"\\)\\s*\\.filter\\(\\{ has: page\\.locator\\("#${submitId}"\\) \\}\\)\\s*\\.getByRole\\("alert"\\)`,
        "u"
      )
    )
  }
  assert.doesNotMatch(source, /page\.getByRole\("alert"\)|\.first\(\)/u)
  assert.match(source, /encodeURIComponent\(userId\)/u)
  assert.match(source, /"X-CSRF-Token"/u)
  assert.match(source, /finally/u)
  assert.doesNotMatch(source, /console\.(?:log|info|warn|error)\(/u)
  assert.match(config, /trace: "off"/u)
  assert.match(config, /screenshot: "off"/u)
  assert.match(config, /video: "off"/u)
})

test("password reset uses live auth APIs and confines its password-check stub to HIBP", () => {
  const source = readFileSync(specPath, "utf8")
  const fixtures = readFileSync(fixturePath, "utf8")
  const lookupStub = fixtures.match(
    /export async function stubBreachedPasswordLookup\(page: Page\): Promise<void> \{[\s\S]*?\n\}/u
  )?.[0]

  assert.ok(lookupStub, "the external password-breach lookup helper exists")
  assert.equal(
    [...lookupStub.matchAll(/page\.route\(/gu)].length,
    1,
    "the fixture has only one route interception in the permitted helper"
  )
  assert.match(lookupStub, /page\.route\(["']https:\/\/api\.pwnedpasswords\.com\/\*\*["']/u)
  assert.match(
    lookupStub,
    /route\.fulfill\(\{\s*status:\s*200,\s*contentType:\s*["']text\/plain["']/u
  )
  assert.doesNotMatch(lookupStub, /\/api\/v1\/|\/auth\/|localhost|LIVE_BASE_URL/u)
  assert.doesNotMatch(source, /page\.route\(|routeWebSocket\(|\.fulfill\(|useMockApi/u)
  assert.match(source, /waitForResponse\([\s\S]*?\/auth\/register/u)
  assert.match(source, /await submitLogin\(page, email, firstPassword\)/u)
  assert.match(source, /await loginWith\(page, email, newPassword\)/u)
})
