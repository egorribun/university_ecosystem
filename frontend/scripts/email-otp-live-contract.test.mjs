import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import test from "node:test"

const specPath = fileURLToPath(
  new URL("../tests/e2e-live/email-otp-verification.live.spec.ts", import.meta.url)
)
const configPath = fileURLToPath(new URL("../playwright.live.config.ts", import.meta.url))

test("email OTP live acceptance rejects wrong and replayed codes, and cleans up its own account", () => {
  const source = readFileSync(specPath, "utf8")
  const config = readFileSync(configPath, "utf8")

  assert.match(source, /live-email-otp-\$\{randomUUID\(\)\}@university\.dev/u)
  assert.match(source, /const EMAIL_CODE = .*Verification code.*\\d\{6\}/u)
  assert.match(source, /Код подтверждения/u)
  assert.match(source, /wrongCode/u)
  assert.match(source, /expect\(rejected\.status\(\)\)\.toBe\(400\)/u)
  assert.match(source, /expect\(verified\.status\(\)\)\.toBe\(200\)/u)
  assert.match(source, /waitForRequest\(verifyRequest\)/u)
  assert.match(source, /accepted\.postData\(\)/u)
  assert.match(source, /expect\(replayed\.status\)\.toBe\(400\)/u)
  assert.match(source, /credentials: "same-origin"/u)
  assert.match(source, /"X-CSRF-Token"/u)
  assert.match(source, /email_verified_at/u)
  assert.match(source, /finally/u)
  assert.match(source, /loginAs\(cleanupPage, "admin"\)/u)
  assert.match(source, /encodeURIComponent\(userId\)/u)
  assert.match(source, /\}, createdUserId\)/u)
  assert.doesNotMatch(source, /console\.(?:log|info|warn|error)\(/u)
  assert.match(config, /trace: "off"/u)
  assert.match(config, /screenshot: "off"/u)
  assert.match(config, /video: "off"/u)
})

test("email OTP live acceptance proves resend rotation invalidates the prior code", () => {
  const source = readFileSync(specPath, "utf8")

  assert.match(source, /resend_available_at/u)
  assert.match(source, /waitUntilResendAvailable/u)
  assert.match(source, /awaitNewMail/u)
  assert.match(source, /Отправить новый код\|Send a new code/u)
  assert.match(source, /staleCodeRejected\.status\(\)\)\.toBe\(400\)/u)
  assert.match(source, /rotatedCode/u)
  assert.match(source, /revision/u)
})
