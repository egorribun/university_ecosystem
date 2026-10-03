import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./profile-csrf.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const profilePageUrl = new URL("../../src/pages/Profile.tsx", import.meta.url)
const apiClientUrl = new URL("../../src/api/client.ts", import.meta.url)
const usersApiUrl = new URL("../../../app/api/users.py", import.meta.url)
const csrfMiddlewareUrl = new URL("../../../app/core/csrf.py", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)

test("live profile mutation proves CSRF rejection and the real UI path", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the live profile CSRF browser scenario must exist")
  }
  const [config, profilePage, apiClient, usersApi, csrfMiddleware, fixtures] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(profilePageUrl, "utf8"),
    readFile(apiClientUrl, "utf8"),
    readFile(usersApiUrl, "utf8"),
    readFile(csrfMiddlewareUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
  ])

  assert.match(usersApi, /@users_router\.put\(\s*["']\/me["']/u)
  assert.match(profilePage, /api\.put<User>\(["']\/users\/me["']/u)
  assert.match(apiClient, /xsrfCookieName:\s*["']csrf_token["']/u)
  assert.match(apiClient, /xsrfHeaderName:\s*["']X-CSRF-Token["']/u)
  assert.match(apiClient, /export const ensureCsrfCookie/u)
  assert.match(apiClient, /fetch\(["']\/api\/v1\/auth\/csrf-cookie["']/u)
  assert.match(apiClient, /await ensureCsrfCookie\(\)/u)
  assert.match(csrfMiddleware, /if not cookie_token or not header_token/u)
  assert.match(csrfMiddleware, /secrets\.compare_digest\(cookie_token, header_token\)/u)
  assert.match(
    csrfMiddleware,
    /if self\._signed:[\s\S]*?if not _verify_signed_token\(cookie_token, session_id, self\._hmac_key\):[\s\S]*?await _reject_csrf/u,
    "matching but forged cookie/header proof still fails the signed-token check"
  )

  assert.match(spec, /authenticated profile update rejects missing and invalid CSRF proof/u)
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /await page\.goto\(["']\/register["']\)/u)
  assert.match(spec, /registrationAttempted = true/u)
  assert.match(spec, /loginWith\(page, email, password\)/u)
  assert.match(spec, /cookieNames\).*toContain\(["']access_token_v2["']\)/u)
  assert.match(spec, /cookieNames\).*toContain\(["']csrf_token["']\)/u)
  const csrfCookieClear = spec.indexOf('await page.context().clearCookies({ name: "csrf_token" })')
  const csrfBootstrapWait = spec.indexOf("waitForCsrfCookieBootstrap(page)", csrfCookieClear)
  const profileSave = spec.indexOf('getByRole("button", { name: "СОХРАНИТЬ"', csrfBootstrapWait)
  assert.ok(csrfCookieClear >= 0, "the browser removes only its CSRF cookie before recovery")
  assert.ok(csrfBootstrapWait > csrfCookieClear, "the UI waits for CSRF cookie bootstrap")
  assert.ok(profileSave > csrfBootstrapWait, "the profile form submits after CSRF bootstrap")
  assert.match(spec, /waitForCsrfCookieBootstrap/u)
  assert.match(spec, /\/api\/v1\/auth\/csrf-cookie/u)
  assert.match(spec, /the UI reacquires the CSRF cookie before saving/u)
  assert.match(spec, /credentials:\s*["']same-origin["']/u)
  assert.match(spec, /missing CSRF header/u)
  assert.match(spec, /invalid signed CSRF proof/u)
  assert.match(spec, /expect\(missingCsrfStatus,[^\n]*\.toBe\(403\)/u)
  assert.match(spec, /expect\(invalidCsrfAttempt\.status,[^\n]*\.toBe\(403\)/u)
  assert.match(spec, /expect\(\s*invalidCsrfAttempt\.proofMatchesCookie,[\s\S]*?\.toBe\(true\)/u)
  assert.match(spec, /const forgedToken = `\$\{csrfToken\}\.invalid`/u)
  assert.match(spec, /"X-CSRF-Token": forgedToken/u)
  assert.match(spec, /document\.cookie = `csrf_token=/u)
  assert.match(spec, /document\.cookie = `csrf_token=; Max-Age=0;/u)
  assert.match(
    spec,
    /const missingCookieResponse = await fetch\([\s\S]*?"X-CSRF-Token": csrfToken/u
  )
  assert.match(spec, /missingCookieStatus: missingCookieResponse\.status/u)
  assert.match(spec, /expect\(\s*invalidCsrfAttempt\.missingCookieStatus,[\s\S]*?\.toBe\(403\)/u)
  assert.match(
    spec,
    /expect\(\s*invalidCsrfAttempt\.cookieClearedAfterRejectedRequest,[\s\S]*?\.toBe\(true\)/u
  )
  const rejectedWrites = [
    ...spec.matchAll(
      /expect\(\(await readOwnerProfile\(page\)\)\.full_name\)\.toBe\(initialName\)/gu
    ),
  ].map(({ index }) => index ?? -1)
  assert.equal(rejectedWrites.length, 2, "each rejected mutation is followed by an owner API read")
  const missingStatusCheck = spec.indexOf(
    'expect(missingCsrfStatus, "missing CSRF header is rejected")'
  )
  const invalidAttemptCheck = spec.indexOf(
    'expect(invalidCsrfAttempt.status, "invalid signed CSRF proof is rejected")'
  )
  const profileEditorEntry = spec.indexOf('await page.goto("/profile?edit=1")')
  assert.ok(
    rejectedWrites[0] > missingStatusCheck && rejectedWrites[0] < invalidAttemptCheck,
    "the owner profile is read after missing-proof rejection"
  )
  assert.ok(
    rejectedWrites[1] > invalidAttemptCheck && rejectedWrites[1] < profileEditorEntry,
    "the owner profile is read after forged-proof rejection and before normal UI recovery"
  )
  assert.match(spec, /getByLabel\(["']Имя["']/u)
  assert.match(spec, /getByRole\(["']button["'],\s*\{\s*name:\s*["']СОХРАНИТЬ["']/u)
  assert.match(spec, /the normal same-origin UI mutation succeeds/u)
  assert.match(spec, /waitForResponse/u)
  assert.match(spec, /page\.request\.get\(["']\/api\/v1\/users\/me["']\)/u)
  assert.match(spec, /loginAs\(adminPage,\s*["']admin["']\)/u)
  assert.match(spec, /entry\.email === email/u)
  assert.ok(
    spec.includes("fetch(`/api/v1/users/${encodeURIComponent(userId)}`"),
    "cleanup must delete only the exact generated account id"
  )
  assert.match(spec, /headers:\s*\{\s*["']X-CSRF-Token["']:\s*csrfToken\s*\}/u)
  assert.doesNotMatch(spec, /routeWebSocket|vi\.mock|page\.route/u)
  assert.match(spec, /stubBreachedPasswordLookup\(page\)/u)
  assert.equal((fixtures.match(/page\.route\(/gu) ?? []).length, 1)
  assert.match(fixtures, /await page\.route\(["']https:\/\/api\.pwnedpasswords\.com\/\*\*["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
})
