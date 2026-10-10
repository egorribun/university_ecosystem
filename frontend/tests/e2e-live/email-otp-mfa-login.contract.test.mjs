import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./email-otp-mfa-login.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)

test("email OTP MFA login uses a live synthetic account without exposing challenge values", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("a dedicated email-OTP MFA login live scenario must exist")
  }

  const config = await readFile(configUrl, "utf8")
  const requireMatch = (pattern, message, source = spec) => assert.ok(pattern.test(source), message)

  requireMatch(/testDir:\s*["']\.\/tests\/e2e-live["']/u, "the live config owns this spec", config)
  requireMatch(/testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u, "the spec is discoverable", config)
  requireMatch(
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']/u,
    "email codes and MFA challenges are excluded from artifacts"
  )

  requireMatch(/randomUUID\(\)/u, "the test creates a unique synthetic user")
  requireMatch(/freshPassword\(\)/u, "the password is generated in memory")
  requireMatch(/stubBreachedPasswordLookup\(page\)/u, "password checks stay inside the live stand")
  requireMatch(/awaitNewCode\(/u, "verification and login codes come from the actual Mailpit sink")
  requireMatch(/mailFor\(/u, "Mailpit messages are addressed to the synthetic user")
  requireMatch(/mailText\(/u, "the OTP is read in memory from the owned Mailpit message")
  requireMatch(
    /\(\?:Verification code\|Код подтверждения\)/u,
    "only expected six-digit codes are parsed"
  )

  for (const endpoint of [
    "/auth/register",
    "/auth/mfa/email/verification/start",
    "/auth/mfa/email/enable",
    "/auth/mfa/verify",
    "/auth/login",
  ]) {
    requireMatch(
      new RegExp(`isApiResponse\\(["']${endpoint.replaceAll("/", "\\/")}['"]\\)`),
      `the test observes the real ${endpoint} endpoint`
    )
  }
  requireMatch(/\/settings\?tab=2/u, "email MFA is enabled through the real settings UI")
  requireMatch(
    /Verify email first|Сначала подтвердить почту/u,
    "the email is verified through its UI"
  )
  requireMatch(/Enable email codes|Включить коды по почте/u, "email MFA is enabled through its UI")
  requireMatch(/email_verified_at/u, "the verified address is confirmed from the live profile")
  requireMatch(/email_mfa_enabled_at/u, "MFA enablement is confirmed from the live profile")
  requireMatch(/methods\.some\([\s\S]*?email_otp/u, "login must actually require the email factor")
  requireMatch(
    /enterCode\(login\.page/u,
    "the login challenge is completed through the six-digit UI"
  )
  requireMatch(/toHaveURL\(\/\\\/dashboard\$\//u, "successful email-MFA login reaches the app")

  requireMatch(/newContext\(/u, "the MFA login starts in an isolated browser context")
  requireMatch(
    /createdUserId\s*=\s*registrationBody\.id/u,
    "cleanup is bound to the returned account ID"
  )
  requireMatch(/deleteOwnedAccount\(/u, "only this test-created account is deleted")
  requireMatch(/loginAs\(page,\s*["']admin["']\)/u, "cleanup uses the live admin role")
  requireMatch(/X-CSRF-Token/u, "account cleanup is CSRF protected")
  requireMatch(
    /encodeURIComponent\(createdId\)/u,
    "cleanup targets only the exact created identity"
  )
  requireMatch(/method:\s*["']DELETE["']/u, "cleanup uses the account-delete operation")
  requireMatch(/expect\(status\)\.toBe\(200\)/u, "cleanup confirms the owned account was removed")

  assert.equal(
    /console\.(?:log|info|warn|error)\s*\(/u.test(spec),
    false,
    "OTP, passwords, and MFA challenge state must not be logged"
  )
  assert.equal(
    /testInfo\.attach|page\.screenshot|recordHar|video:\s*["']on["']/u.test(spec),
    false,
    "runtime authentication values must not be attached to test artifacts"
  )
  assert.equal(
    /page\.route\(|routeWebSocket\(|\.fulfill\(/u.test(spec),
    false,
    "authentication endpoints and UI remain real"
  )
})
