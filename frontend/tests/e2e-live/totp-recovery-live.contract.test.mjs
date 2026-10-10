import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./totp-recovery.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const russianSettingsUrl = new URL("../../src/i18n/locales/ru/settings.json", import.meta.url)
const englishSettingsUrl = new URL("../../src/i18n/locales/en/settings.json", import.meta.url)

test("live TOTP enrollment, login, recovery use, and replay rejection stay secret-safe", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("a dedicated live TOTP/recovery acceptance scenario must exist")
  }

  const config = await readFile(configUrl, "utf8")
  const russianSettings = JSON.parse(await readFile(russianSettingsUrl, "utf8"))
  const englishSettings = JSON.parse(await readFile(englishSettingsUrl, "utf8"))
  const requireMatch = (pattern, message, source = spec) => assert.ok(pattern.test(source), message)

  requireMatch(/testDir:\s*["']\.\/tests\/e2e-live["']/u, "the live config owns this spec", config)
  requireMatch(/testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u, "the spec is discoverable", config)
  requireMatch(
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']/u,
    "live MFA values are excluded from traces, screenshots, and video"
  )

  requireMatch(/randomUUID\(\)/u, "the test account identity is unique")
  requireMatch(/freshPassword\(\)/u, "the account password is generated in memory")
  requireMatch(/isApiResponse\(["']\/auth\/register["']\)/u, "registration uses the live endpoint")
  requireMatch(/#totp-manual-code/u, "the TOTP seed is read from the enrollment UI only in memory")

  requireMatch(
    /name:\s*\/\^\(\?:Приложение-аутентификатор\|Authenticator app\)\/iu/u,
    "the live locator matches the localized Russian and English accordion titles"
  )
  const accordionNamePattern = /^(?:Приложение-аутентификатор|Authenticator app)/iu
  assert.match(russianSettings.security.method.totp, accordionNamePattern)
  assert.match(englishSettings.security.method.totp, accordionNamePattern)
  requireMatch(
    /createHmac\(["']sha1["']/u,
    "RFC 6238 codes use Node's built-in HMAC without an added dependency"
  )
  requireMatch(/Buffer\.alloc\(8\)/u, "the TOTP helper encodes its time counter")
  requireMatch(
    /isApiResponse\(["']\/auth\/mfa\/totp\/confirm["']\)/u,
    "the UI confirms the actual TOTP enrollment"
  )

  requireMatch(
    /\/api\/v1\/auth\/mfa\/recovery-codes/u,
    "recovery codes are issued through the supported same-origin API"
  )
  requireMatch(/X-CSRF-Token/u, "recovery-code issuance and account cleanup are CSRF protected")
  requireMatch(/codes\[0\]/u, "only one recovery code is retained by the test")
  requireMatch(/isApiResponse\(["']\/auth\/login["']\)/u, "login uses the live endpoint")
  requireMatch(
    /isApiResponse\(["']\/auth\/mfa\/verify["']\)/u,
    "factor challenges use the real MFA verification endpoint"
  )
  requireMatch(/request\(\)\.method\(\)\s*===\s*["']POST["']/u, "observed auth calls are POSTs")
  requireMatch(
    /new URL\(response\.url\(\)\)\.pathname\.endsWith\(suffix\)/u,
    "response matching uses the exact API path suffix"
  )
  requireMatch(/use-recovery-code-toggle/u, "recovery-code logins use the actual challenge UI")
  requireMatch(/recoveryCode/u, "the same in-memory recovery code is tested for use and replay")
  requireMatch(
    /toHaveURL\(\/\\\/dashboard\$\//u,
    "successful MFA logins reach the authenticated app"
  )
  requireMatch(
    /verifyRecoveryCodeOnLogin\(replayLogin\.page,\s*recoveryCode,\s*400\)/u,
    "a consumed recovery code is rejected on a fresh challenge"
  )
  requireMatch(
    /verifyRecoveryCodeOnLogin\(replayLogin\.page,\s*recoveryCode,\s*400\)[\s\S]*?const postReplayTotpLogin = await createIsolatedPage[\s\S]*?loginToMfaChallenge\([\s\S]*?waitForTotpCode\(authenticatorSecret,\s*loginTotp\.step\)[\s\S]*?verifyTotpOnLogin\(postReplayTotpLogin\.page/u,
    "replay rejection must leave the enrolled TOTP factor usable in a fresh session"
  )

  requireMatch(/newContext\(/u, "login and replay attempts use isolated browser contexts")
  requireMatch(/deleteOwnedAccount\(/u, "cleanup deletes only the account created by this test")
  requireMatch(/createdUserId/u, "cleanup is bound to the ID returned by this registration")
  requireMatch(/stubBreachedPasswordLookup/u, "password checks stay inside the live stand")
  assert.equal(
    /console\.(?:log|info|warn|error)\s*\(/u.test(spec),
    false,
    "runtime MFA values must not be logged"
  )
  assert.equal(
    /testInfo\.attach|page\.screenshot|recordHar|video:\s*["']on["']/u.test(spec),
    false,
    "runtime MFA values must not be attached to test artifacts"
  )
  assert.equal(
    /\b(?:authenticatorSecret|secret|seed)\s*=\s*["'][A-Z2-7]{16,}["']/u.test(spec),
    false,
    "the source must not contain a reusable TOTP seed"
  )
  assert.equal(
    /page\.route\(|routeWebSocket\(|\.fulfill\(/u.test(spec),
    false,
    "authentication APIs and pages are not mocked"
  )
})
