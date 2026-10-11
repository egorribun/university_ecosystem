import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./email-otp-mfa-login.live.spec.ts", import.meta.url)
const verificationSpecUrl = new URL("./email-otp-verification.live.spec.ts", import.meta.url)
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

  const expectedMfaChecks = [
    "email-mfa-register",
    "email-mfa-initial-login",
    "email-mfa-sibling-login",
    "email-mfa-verification-start",
    "email-mfa-verification-accept",
    "email-mfa-enable-start",
    "email-mfa-enable-accept",
    "email-mfa-enabled-login",
    "email-mfa-login-resend-early",
    "email-mfa-login-accept",
  ]
  requireMatch(
    /import \{ reportLiveHttpStatus \} from ["']\.\/http-status-diagnostic/u,
    "MFA HTTP status observations use the bounded diagnostic helper"
  )
  assert.deepEqual(
    [
      ...spec.matchAll(
        /reportLiveHttpStatus\(\s*testInfo\.project\.name\s*,\s*["']([^"']+)["']\s*,\s*[A-Za-z]\w*\.status\(\)\s*\)/gu
      ),
    ].map((match) => match[1]),
    expectedMfaChecks,
    "each MFA stage reports only its real response status under a closed check label"
  )

  const verificationSpec = await readFile(verificationSpecUrl, "utf8")
  const expectedVerificationChecks = [
    "email-otp-register",
    "email-otp-verification-start",
    "email-otp-verification-wrong-code",
    "email-otp-verification-wrong-code",
    "email-otp-verification-resend",
    "email-otp-verification-stale-code",
    "email-otp-verification-accept",
  ]
  requireMatch(
    /import\s*\{[^}]*\breportLiveHttpStatus\b[^}]*\}\s*from\s*["']\.\/http-status-diagnostic["']/u,
    "verification HTTP status observations use the bounded diagnostic helper",
    verificationSpec
  )
  assert.deepEqual(
    [
      ...verificationSpec.matchAll(
        /reportLiveHttpStatus\(\s*testInfo\.project\.name\s*,\s*["']([^"']+)["']\s*,\s*[A-Za-z]\w*\.status\(\)\s*\)/gu
      ),
    ].map((match) => match[1]),
    expectedVerificationChecks,
    "each verification stage reports only its real response status under a closed check label"
  )

  requireMatch(
    /test\.setTimeout\(150_000\)/u,
    "the OTP retry preserves the existing 150 second deadline",
    verificationSpec
  )
  requireMatch(
    /if \(rejected\.status\(\) === 429\)[\s\S]*?parseLiveRateLimitRetryAfter\(rejected\.headers\(\)\["retry-after"\]\)/u,
    "wrong-code retries are gated by the actual bounded Retry-After header",
    verificationSpec
  )
  requireMatch(
    /await waitForLiveRateLimitRetry\(retryAfter\)[\s\S]*?const afterWait = assessLiveRateLimitRetry/u,
    "the remaining slot budget is rechecked after waiting",
    verificationSpec
  )
  requireMatch(
    /const retryResponse = page\.waitForResponse\(verifyResponse,\s*\{\s*timeout: responseTimeoutMs,?\s*\}\)[\s\S]*?const retryAction = \(async \(\) => \{\s*await enterCode\(inputs, wrongCode, retryActionDeadlineAtMs\)[\s\S]*?await expect\(verifyButton\)\.toBeEnabled\(\{\s*timeout: retryActionTimeout\(retryActionDeadlineAtMs\),?\s*\}\)[\s\S]*?await verifyButton\.click\(\{\s*timeout: retryActionTimeout\(retryActionDeadlineAtMs\),?\s*\}\)[\s\S]*?Promise\.allSettled\(\[\s*retryResponse,\s*retryAction,?\s*\]\)/u,
    "the bounded retry shares one action deadline across input, enablement, and submission while awaiting its response",
    verificationSpec
  )
  requireMatch(
    /expect\(rejected\.status\(\)\)\.toBe\(400\)/u,
    "the retry remains required to be rejected as an invalid code",
    verificationSpec
  )
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
  const acceptedVerificationIndex = spec.indexOf("expect(emailVerification.status()).toBe(200)")
  const freshProfileReadIndex = spec.indexOf(
    'const verifiedProfileResponse = await page.request.get("/api/v1/users/me")'
  )
  assert.ok(
    acceptedVerificationIndex >= 0 && freshProfileReadIndex > acceptedVerificationIndex,
    "the fresh profile read follows the accepted email OTP response"
  )
  requireMatch(
    /expect\(verifiedProfileResponse\.status\(\)\)\.toBe\(200\)/u,
    "the fresh profile read must return HTTP 200"
  )
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
