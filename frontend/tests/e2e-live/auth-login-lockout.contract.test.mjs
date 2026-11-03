import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"
import {
  DEFAULT_AUTH_LOCKOUT_THRESHOLDS,
  expectedFailedAttemptStatus,
  firstLockoutRule,
  isAccountLockedStatus,
  lockoutRetryAfterWithinRule,
  parseLockoutThresholds,
} from "./auth-login-lockout.decisions.mjs"

const specUrl = new URL("./auth-login-lockout.live.spec.ts", import.meta.url)

// AUD-432: the lockout acceptance is checked by executing the same decision functions the
// live spec applies to real responses, not by matching the spec's text.

test("the default backend lockout rules parse into strictly increasing attempt/cooldown pairs", () => {
  assert.deepEqual(parseLockoutThresholds(DEFAULT_AUTH_LOCKOUT_THRESHOLDS), [
    { attempts: 5, seconds: 30 },
    { attempts: 8, seconds: 300 },
    { attempts: 10, seconds: 3600 },
  ])
  assert.deepEqual(firstLockoutRule(), { attempts: 5, seconds: 30 })
})

test("malformed, empty, zero and non-increasing lockout rule lists are rejected", () => {
  for (const value of [
    "",
    "   ",
    "5",
    "x:30",
    "5:0",
    "0:30",
    "5:30,5:300",
    "8:300,5:3600",
    "5:30,8:20",
  ]) {
    assert.throws(
      () => parseLockoutThresholds(value),
      TypeError,
      `accepted ${JSON.stringify(value)}`
    )
  }
  assert.throws(() => parseLockoutThresholds(undefined), TypeError)
})

test("the live scenario expects 401 before the first lockout and 423 on the lockout attempt", () => {
  const rule = firstLockoutRule()
  for (let attempt = 1; attempt < rule.attempts; attempt += 1) {
    assert.equal(expectedFailedAttemptStatus(attempt, rule), 401)
  }
  assert.equal(expectedFailedAttemptStatus(rule.attempts, rule), 423)
  assert.throws(() => expectedFailedAttemptStatus(0, rule), RangeError)
  assert.throws(() => expectedFailedAttemptStatus(1.5, rule), RangeError)
})

test("only HTTP 423 is treated as the account-lockout response", () => {
  assert.equal(isAccountLockedStatus(423), true)
  for (const status of [200, 401, 403, 429, 500]) {
    assert.equal(isAccountLockedStatus(status), false, `status ${status} read as lockout`)
  }
})

test("the lockout cooldown must be a positive integer no longer than the first rule", () => {
  const rule = firstLockoutRule()
  for (const header of ["1", "15", "30"]) {
    assert.equal(lockoutRetryAfterWithinRule(header, rule), true, `rejected ${header}`)
  }
  for (const header of [undefined, "", "0", "31", "-1", "1.5", "abc", " 5", "3600"]) {
    assert.equal(lockoutRetryAfterWithinRule(header, rule), false, `accepted ${String(header)}`)
  }
})

test("the live spec applies these decisions instead of restating its own constants", async () => {
  const spec = await readFile(specUrl, "utf8")
  assert.match(spec, /from "\.\/auth-login-lockout\.decisions\.mjs"/u)
  assert.doesNotMatch(spec, /const LOCKOUT_ATTEMPTS = \d/u)
  // Static policy guards retained from the original contract: registration must not consume
  // the shared rate-limited path, and the live auth endpoints must not be mocked.
  assert.doesNotMatch(spec, /\/auth\/register/u)
  assert.doesNotMatch(spec, /page\.route\(|route\.fulfill\(/u)
})
