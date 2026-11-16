import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import process from "node:process"
import test from "node:test"
import { setImmediate, setTimeout } from "node:timers"
import { fileURLToPath, URL } from "node:url"

const helperUrl = new URL("./http-status-diagnostic.ts", import.meta.url)
const profileHelperUrl = new URL("./profile-save-diagnostic.ts", import.meta.url)

test("MFA operation records keep attempt identity and bounded rate-limit metadata", async () => {
  const module = await import(helperUrl.href + "?mfa-operation-red")
  const output = []
  const scope = module.createLiveOperationScope(
    { project: "mobile", source: "email-otp-mfa-login.live.spec.ts", line: 378, retry: 1 },
    (line) => output.push(line)
  )
  scope.begin("email-mfa-verification-accept", "body").finish(429, 0, 1, 12, {
    retryAfterSeconds: 321,
    limiterSignature: "domain-signature",
  })
  assert.deepEqual(output, [
    "UE_LIVE_HTTP_OPERATION_V3 project=mobile source=email-otp-mfa-login.live.spec.ts line=378 retry=1 ordinal=1 phase=body operation=email-mfa-verification-accept outcome=response status=429 elapsed_ms=12 saturated=0 requests=0 responses=1 retry_after_seconds=321 limiter_signature=domain-signature\n",
  ])
})

test("MFA observation classifies a response without delaying the caller or exposing it", async () => {
  let observer
  try {
    observer = await import(new URL("./email-mfa-operation-observer.ts", import.meta.url).href)
  } catch (error) {
    if (error.code !== "ERR_MODULE_NOT_FOUND") throw error
  }
  assert.equal(typeof observer?.observeEmailMfaOperation, "function")
  const { parseLiveRateLimitRetryAfterForDiagnostic } = await import(helperUrl.href)
  const finished = []
  const operation = { finish: (...args) => finished.push(args) }
  const result = observer.observeEmailMfaOperation(
    operation,
    {
      status: () => 429,
      headers: () => ({ "retry-after": "321", private: "must-not-appear" }),
      json: async () => ({ detail: "MFA verification failed", private: "must-not-appear" }),
    },
    12,
    "email-mfa-verification-accept",
    parseLiveRateLimitRetryAfterForDiagnostic
  )
  assert.equal(result, undefined)
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(finished, [
    [429, 0, 1, 12, { retryAfterSeconds: 321, limiterSignature: "domain-signature" }],
  ])
  assert.doesNotMatch(JSON.stringify(finished), /must-not-appear/u)
})

test("MFA operation serializer rejects an unsupported login provenance claim", async () => {
  const module = await import(helperUrl.href + "?mfa-operation-invalid-login")
  const output = []
  const scope = module.createLiveOperationScope(
    { project: "desktop", source: "email-otp-mfa-login.live.spec.ts", line: 378, retry: 0 },
    (line) => output.push(line)
  )
  scope.begin("email-mfa-enabled-login", "body").finish(429, 0, 1, 1, {
    retryAfterSeconds: 1,
    limiterSignature: "domain-signature",
  })
  assert.deepEqual(output, ["UE_LIVE_HTTP_OPERATION_V2 completeness=unavailable\n"])
})

test("MFA operation serializer accepts only the owned scenario and closed scalar values", async () => {
  const module = await import(helperUrl.href + "?mfa-operation-boundaries")
  const output = []
  const emit = (line) => output.push(line)
  const identity = {
    project: "desktop",
    source: "email-otp-mfa-login.live.spec.ts",
    line: 378,
    retry: 0,
  }
  const scope = module.createLiveOperationScope(identity, emit)
  for (const operation of [
    "email-mfa-verification-start",
    "email-mfa-verification-accept",
    "email-mfa-enable-start",
    "email-mfa-enable-accept",
    "email-mfa-enabled-login",
    "email-mfa-login-accept",
  ]) {
    scope.begin(operation, "body").finish(200, 0, 1, 1)
  }
  scope.begin("email-mfa-login-accept", "body").finish(429, 0, 1, 1, {
    retryAfterSeconds: null,
    limiterSignature: "unavailable",
  })
  scope.begin("email-mfa-login-accept", "body").finish(429, 0, 1, 1, {
    retryAfterSeconds: 601,
    limiterSignature: "private-value",
  })
  scope.begin("email-mfa-login-accept", "setup").finish(200, 0, 1, 1)
  module
    .createLiveOperationScope({ ...identity, source: "auth-roles.live.spec.ts", line: 33 }, emit)
    .begin("email-mfa-login-accept", "body")
    .finish(200, 0, 1, 1)
  const rows = output.filter((line) => line.startsWith("UE_LIVE_HTTP_OPERATION_V3 "))
  assert.equal(rows.length, 7)
  assert.ok(
    rows
      .slice(0, 6)
      .every((line) => line.endsWith("retry_after_seconds=none limiter_signature=not-applicable\n"))
  )
  assert.ok(rows[6].endsWith("retry_after_seconds=invalid limiter_signature=unavailable\n"))
  assert.ok(output.some((line) => line.endsWith("completeness=unavailable\n")))
  assert.ok(output.some((line) => line.endsWith("completeness=invalid-scope\n")))
  assert.ok(output.every((line) => !line.includes("private-value")))
})

test("MFA response observation handles success, alternate details, and unavailable values", async () => {
  const { observeEmailMfaOperation } = await import(
    new URL("./email-mfa-operation-observer.ts", import.meta.url).href
  )
  const { parseLiveRateLimitRetryAfterForDiagnostic } = await import(helperUrl.href)
  const results = []
  const operation = { finish: (...values) => results.push(values) }
  const observe = (kind, observed) =>
    observeEmailMfaOperation(
      operation,
      observed,
      10,
      kind,
      parseLiveRateLimitRetryAfterForDiagnostic
    )
  observe("email-mfa-verification-start", {
    status: () => 200,
    headers: () => {
      throw new Error("private-value")
    },
    json: () => {
      throw new Error("private-value")
    },
  })
  observe("email-mfa-enable-start", {
    status: () => 429,
    headers: () => ({ "retry-after": "600" }),
    json: async () => ({ detail: "MFA request rejected", private: "private-value" }),
  })
  observe("email-mfa-enable-accept", {
    status: () => 429,
    headers: () => ({ "retry-after": "601" }),
    json: async () => ({ detail: "different", private: "private-value" }),
  })
  observe("email-mfa-login-accept", {
    status: () => 429,
    headers: () => {
      throw new Error("private-value")
    },
    json: async () => {
      throw new Error("private-value")
    },
  })
  observe("email-mfa-enabled-login", {
    status: () => 429,
    headers: () => ({ "retry-after": "1" }),
    json: () => {
      throw new Error("must not read login body")
    },
  })
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(results, [
    [200, 0, 1, 10],
    [429, 0, 1, 10, { retryAfterSeconds: 1, limiterSignature: "unavailable" }],
    [429, 0, 1, 10, { retryAfterSeconds: 600, limiterSignature: "domain-signature" }],
    [429, 0, 1, 10, { retryAfterSeconds: null, limiterSignature: "other" }],
    [429, 0, 1, 10, { retryAfterSeconds: null, limiterSignature: "unavailable" }],
  ])
  assert.doesNotMatch(JSON.stringify(results), /private-value/u)
  assert.doesNotThrow(() =>
    observeEmailMfaOperation(
      {
        finish: () => {
          throw new Error("private-value")
        },
      },
      { status: () => 200 },
      10,
      "email-mfa-login-accept",
      parseLiveRateLimitRetryAfterForDiagnostic
    )
  )
})

test("MFA response observation times out without delaying or later revising the result", async () => {
  const { observeEmailMfaOperation } = await import(
    new URL("./email-mfa-operation-observer.ts", import.meta.url).href
  )
  const { parseLiveRateLimitRetryAfterForDiagnostic } = await import(helperUrl.href)
  let resolveBody
  const body = new Promise((resolve) => {
    resolveBody = resolve
  })
  const results = []
  observeEmailMfaOperation(
    { finish: (...values) => results.push(values) },
    { status: () => 429, headers: () => ({ "retry-after": "5" }), json: () => body },
    10,
    "email-mfa-login-accept",
    parseLiveRateLimitRetryAfterForDiagnostic
  )
  assert.deepEqual(results, [])
  await new Promise((resolve) => setTimeout(resolve, 600))
  assert.deepEqual(results, [
    [429, 0, 1, 10, { retryAfterSeconds: 5, limiterSignature: "unavailable" }],
  ])
  resolveBody({ detail: "MFA verification failed" })
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(results.length, 1)
})

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { parseLiveRateLimitHeader, parseLiveRateLimitRetryAfterForDiagnostic, reportLiveHttpStatus, reportLiveRateLimitRetry } from ${JSON.stringify(helperUrl.href)};\nimport { reportLiveProfileSaveFailure } from ${JSON.stringify(profileHelperUrl.href)};\n${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0, "the diagnostic helper must not throw")
  assert.equal(result.stderr, "", "the helper writes only its bounded stdout protocol")
  return result.stdout
}

test("HTTP diagnostics emit only fixed project/check labels and integer status boundaries", () => {
  for (const status of [100, 200, 401, 403, 429, 500, 599]) {
    const calls = []
    const expected = []
    for (const project of ["desktop", "mobile"]) {
      for (const check of [
        "student-users-denied",
        "teacher-users-denied",
        "student-feature-flags-denied",
        "teacher-feature-flags-denied",
        "admin-users",
        "admin-feature-flags",
        "admin-feature-flags-ui",
        "password-reset-replay",
        "auth-login",
        "auth-logout",
        "auth-session-preflight",
        "messenger-message-send",
        "chat-attachment-create",
        "email-otp-register",
        "email-otp-verification-start",
        "email-otp-verification-wrong-code",
        "email-otp-verification-resend",
        "email-otp-verification-stale-code",
        "email-otp-verification-accept",
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
      ]) {
        calls.push(
          `reportLiveHttpStatus(${JSON.stringify(project)}, ${JSON.stringify(check)}, ${status})`
        )
        expected.push(`UE_LIVE_HTTP_STATUS_V1 project=${project} check=${check} status=${status}\n`)
      }
    }
    assert.equal(reportInChild(calls.join("\n")), expected.join(""))
  }
})

test("HTTP diagnostics silently reject out-of-domain runtime values without coercion", () => {
  assert.equal(
    reportInChild(`
      const privateValue = { toString() { throw new Error("private-value") } };
      for (const project of ["", "Desktop", "private-project", "desktop\\n", "desktop\\r", "desktop\\u202e", null, undefined, 1, privateValue]) {
        reportLiveHttpStatus(project, "admin-users", 200);
      }
      for (const check of ["", "admin", "private-check", "admin-users\\n", "admin-users status=401", "messenger-message-send url=https://private.invalid/path", null, undefined, 1, privateValue]) {
        reportLiveHttpStatus("desktop", check, 200);
      }
      for (const status of [99, 600, -1, 200.5, NaN, Infinity, -Infinity, "200", "200\\nprivate", null, undefined, true, 200n, privateValue]) {
        reportLiveHttpStatus("desktop", "admin-users", status);
      }
    `),
    ""
  )
})

test("HTTP diagnostics deduplicate records and stop at the derived bound per worker process", async () => {
  // The bound is projects x checks x attempts, derived from the closed check set in source.
  const source = await readFile(helperUrl, "utf8")
  const checkSet = source.match(
    /const LIVE_HTTP_STATUS_CHECKS: ReadonlySet<LiveHttpStatusCheck> = new Set\(\[([\s\S]*?)\]\)/u
  )
  assert.ok(checkSet, "the closed check set must be declared in the helper")
  const checkCount = [...checkSet[1].matchAll(/"[a-z0-9-]+"/gu)].length
  assert.ok(checkCount > 0)
  assert.match(
    source,
    /MAX_RECORDS =\s*LIVE_HTTP_STATUS_PROJECTS \* LIVE_HTTP_STATUS_CHECKS\.size \* LIVE_HTTP_STATUS_ATTEMPTS/u
  )
  const bound = 2 * checkCount * 2
  const output = reportInChild(`
    for (let status = 100; status < 600; status += 1) {
      for (let duplicate = 0; duplicate < 10; duplicate += 1) {
        reportLiveHttpStatus("desktop", "admin-users", status);
      }
    }
  `)
  assert.equal(
    output,
    Array.from(
      { length: bound },
      (_, index) =>
        `UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=${100 + index}\n`
    ).join("")
  )
})

test("session-cap diagnostics accept only the forbidden status", () => {
  const calls = []
  for (const project of ["desktop", "mobile"]) {
    for (const status of [100, 200, 401, 403, 429, 500, 599]) {
      calls.push(`reportLiveHttpStatus(${JSON.stringify(project)}, "auth-session-cap", ${status})`)
    }
  }
  assert.equal(
    reportInChild(calls.join("\n")),
    ["desktop", "mobile"]
      .map(
        (project) => `UE_LIVE_HTTP_STATUS_V1 project=${project} check=auth-session-cap status=403\n`
      )
      .join("")
  )
})

test("retry decisions retain the original V1 five-field protocol", () => {
  const calls = [
    'reportLiveRateLimitRetry("desktop", "auth-logout", 40, "retry", 60000)',
    'reportLiveRateLimitRetry("mobile", "email-otp-verification-wrong-code", 5, "retry", 50000)',
    'reportLiveRateLimitRetry("mobile", "email-otp-verification-wrong-code", 5, "retry", 50000)',
    'reportLiveRateLimitRetry("mobile", "password-reset-replay", 60, "declined-deadline", 12345)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", null, "declined-header", 0)',
  ].join("\n")
  assert.equal(
    reportInChild(calls),
    [
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=40 decision=retry remaining_ms=60000\n",
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=invalid x_ratelimit_remaining=invalid\n",
      "UE_LIVE_RETRY_V1 project=mobile check=email-otp-verification-wrong-code retry_after_seconds=5 decision=retry remaining_ms=50000\n",
      "UE_LIVE_RETRY_V1 project=mobile check=password-reset-replay retry_after_seconds=60 decision=declined-deadline remaining_ms=12345\n",
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=invalid decision=declined-header remaining_ms=0\n",
    ].join("")
  )
})

test("MFA login retry diagnostics accept only bounded decisions", () => {
  const output = reportInChild(`
    reportLiveRateLimitRetry("mobile", "email-mfa-enabled-login", 17, "retry", 60000);
    reportLiveRateLimitRetry("desktop", "email-mfa-enabled-login", null, "declined-header", 0);
    reportLiveRateLimitRetry("mobile", "email-mfa-enabled-login", 17, "declined-deadline", 1);
    reportLiveRateLimitRetry("desktop", "email-mfa-enabled-login", 17, "not-retried", 1);
    reportLiveRateLimitRetry("desktop", "email-mfa-enabled-login-private", 17, "retry", 1);
    reportLiveRateLimitRetry("desktop", "email-mfa-enabled-login", 61, "retry", 1);
  `)
  assert.equal(
    output,
    [
      "UE_LIVE_RETRY_V1 project=mobile check=email-mfa-enabled-login retry_after_seconds=17 decision=retry remaining_ms=60000\n",
      "UE_LIVE_RETRY_V1 project=desktop check=email-mfa-enabled-login retry_after_seconds=invalid decision=declined-header remaining_ms=0\n",
      "UE_LIVE_RETRY_V1 project=mobile check=email-mfa-enabled-login retry_after_seconds=17 decision=declined-deadline remaining_ms=1\n",
    ].join("")
  )
})

test("stale-code throttling records bounded Retry-After without retrying", () => {
  const output = reportInChild(`
    const shortWindow = parseLiveRateLimitRetryAfterForDiagnostic("61");
    const serviceWindow = parseLiveRateLimitRetryAfterForDiagnostic("600");
    const missingWindow = parseLiveRateLimitRetryAfterForDiagnostic("601");
    reportLiveRateLimitRetry("desktop", "email-otp-verification-stale-code", shortWindow, "not-retried", 12345);
    reportLiveRateLimitRetry("mobile", "email-otp-verification-stale-code", serviceWindow, "not-retried", 0);
    reportLiveRateLimitRetry("desktop", "email-otp-verification-stale-code", missingWindow, "not-retried", 0);
    reportLiveRateLimitRetry("desktop", "auth-logout", serviceWindow, "not-retried", 12345);
    reportLiveRateLimitRetry("desktop", "email-otp-verification-stale-code", serviceWindow, "retry", 12345);
  `)
  assert.equal(
    output,
    [
      "UE_LIVE_RETRY_V1 project=desktop check=email-otp-verification-stale-code retry_after_seconds=61 decision=not-retried remaining_ms=12345\n",
      "UE_LIVE_RETRY_V1 project=mobile check=email-otp-verification-stale-code retry_after_seconds=600 decision=not-retried remaining_ms=0\n",
      "UE_LIVE_RETRY_V1 project=desktop check=email-otp-verification-stale-code retry_after_seconds=invalid decision=not-retried remaining_ms=0\n",
    ].join("")
  )
})

test("logout header metadata uses a separate bounded protocol", () => {
  const calls = [
    'const privateValue = { toString() { throw new Error("private-value") } }',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 40, "retry", 60000, parseLiveRateLimitHeader("5", "limit"), parseLiveRateLimitHeader("0", "remaining"))',
    'reportLiveRateLimitRetry("mobile", "auth-logout", 33, "declined-deadline", 26463, parseLiveRateLimitHeader("05", "limit"), parseLiveRateLimitHeader("2", "remaining"))',
    'reportLiveRateLimitRetry("mobile", "auth-logout", 33, "declined-deadline", 26463, parseLiveRateLimitHeader("5", "limit"), parseLiveRateLimitHeader("2", "remaining"))',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 1, "retry", 1000, parseLiveRateLimitHeader("100000", "limit"), parseLiveRateLimitHeader("100001", "remaining"))',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 2, "retry", 1002, parseLiveRateLimitHeader("0", "limit"), parseLiveRateLimitHeader("0", "remaining"))',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 2, "retry", 1003, parseLiveRateLimitHeader("100001", "limit"), parseLiveRateLimitHeader("1", "remaining"))',
    'reportLiveRateLimitRetry("mobile", "auth-logout", 1, "retry", 1002, 5, privateValue)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 1, "retry", 1001, "private-limit", 2)',
    'reportLiveRateLimitRetry("desktop", "password-reset-replay", 1, "retry", 1000, 5, 0)',
  ].join("\n")
  const output = reportInChild(calls)
  assert.equal(
    output,
    [
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=40 decision=retry remaining_ms=60000\n",
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=0\n",
      "UE_LIVE_RETRY_V1 project=mobile check=auth-logout retry_after_seconds=33 decision=declined-deadline remaining_ms=26463\n",
      "UE_LIVE_RATE_LIMIT_V1 project=mobile check=auth-logout x_ratelimit_limit=invalid x_ratelimit_remaining=2\n",
      "UE_LIVE_RATE_LIMIT_V1 project=mobile check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=2\n",
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=1000\n",
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=100000 x_ratelimit_remaining=invalid\n",
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=2 decision=retry remaining_ms=1002\n",
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=invalid x_ratelimit_remaining=0\n",
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=2 decision=retry remaining_ms=1003\n",
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=invalid x_ratelimit_remaining=1\n",
      "UE_LIVE_RETRY_V1 project=mobile check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=1002\n",
      "UE_LIVE_RATE_LIMIT_V1 project=mobile check=auth-logout x_ratelimit_limit=5 x_ratelimit_remaining=invalid\n",
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=1001\n",
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=invalid x_ratelimit_remaining=2\n",
      "UE_LIVE_RETRY_V1 project=desktop check=password-reset-replay retry_after_seconds=1 decision=retry remaining_ms=1000\n",
    ].join("")
  )
  assert.doesNotMatch(output, /private-limit|private-value/u)
})

test("retry decision diagnostics reject unbounded and inconsistent runtime values", () => {
  const calls = [
    'const privateValue = { toString() { throw new Error("private-value") } }',
    'reportLiveRateLimitRetry("private-project", "auth-logout", 1, "retry", 1000)',
    'reportLiveRateLimitRetry("desktop", "private-check", 1, "retry", 1000)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 0, "retry", 1000)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 61, "retry", 1000)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 1.5, "retry", 1000)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", "private-header", "retry", 1000)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 1, "declined-header", 1000)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", null, "declined-deadline", 1000)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 1, "retry", 0)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", 1, "retry", 60001)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", privateValue, "retry", 1000)',
  ].join("\n")
  assert.equal(reportInChild(calls), "")
})

test("retry diagnostics deduplicate and cap at thirty-two records", () => {
  const output = reportInChild(
    Array.from(
      { length: 40 },
      (_, remaining) =>
        `reportLiveRateLimitRetry("desktop", "auth-logout", 1, "retry", ${remaining})`
    ).join("\n")
  )
  const retryRecords = Array.from(
    { length: 32 },
    (_, index) =>
      `UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=1 decision=retry remaining_ms=${index + 1}\n`
  )
  assert.equal(
    output,
    retryRecords[0] +
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=invalid x_ratelimit_remaining=invalid\n" +
      retryRecords.slice(1).join("")
  )
})

test("HTTP diagnostics retain a differing replay status after eight initial records", () => {
  const initial = ["desktop", "mobile"].flatMap((project) =>
    ["admin-users", "admin-feature-flags", "admin-feature-flags-ui", "password-reset-replay"].map(
      (check) => [project, check, check === "password-reset-replay" ? 400 : 200]
    )
  )
  // Synthetic retry status exercises retention; it is not a claim about live output.
  const retry = ["mobile", "password-reset-replay", 429]
  const calls = [...initial, retry, retry].map(
    (record) => `reportLiveHttpStatus(${record.map((value) => JSON.stringify(value)).join(", ")})`
  )
  assert.equal(
    reportInChild(calls.join("\n")),
    [...initial, retry]
      .map(
        ([project, check, status]) =>
          `UE_LIVE_HTTP_STATUS_V1 project=${project} check=${check} status=${status}\n`
      )
      .join("")
  )
})

test("logout fixture reads only Retry-After and the two rate-limit headers", async () => {
  const source = await readFile(new URL("./fixtures.ts", import.meta.url), "utf8")
  const headerReads = [...source.matchAll(/\bheaders\["([^"]+)"\]/gu)].map((match) => match[1])
  assert.deepEqual(headerReads.sort(), [
    "retry-after",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
  ])
})

test("HTTP diagnostic helper has no browser, response, environment, or artifact access", async () => {
  const source = (await readFile(helperUrl, "utf8")).split("// Stage A:")[0]
  assert.doesNotMatch(
    source,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\b(?:page|browser|context|response|request|URL)\b|\.(?:json|text|screenshot|storageState|attach)\s*\(/u
  )
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 4)
  const loginReporter = source.slice(source.indexOf("export function reportLiveLoginFailure("))
  assert.match(loginReporter, /UE_LIVE_LOGIN_FAILURE_V1/u)
  assert.equal((loginReporter.match(/process\.stdout\.write\(/gu) ?? []).length, 1)
})

test("the real Playwright list reporter preserves stdout protocol without browser fixtures", async (t) => {
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), "ue-http-diagnostic-"))
  t.after(() => rm(temporaryRoot, { recursive: true, force: true }))
  const playwrightUrl = new URL("../../node_modules/@playwright/test/index.mjs", import.meta.url)
  const cliPath = fileURLToPath(
    new URL("../../node_modules/@playwright/test/cli.js", import.meta.url)
  )
  const configPath = path.join(temporaryRoot, "playwright.config.mjs")
  const outputPath = path.join(temporaryRoot, "output")
  await writeFile(
    configPath,
    `export default {
      testDir: ${JSON.stringify(temporaryRoot)}, testMatch: "diagnostic.spec.mjs",
      reporter: "list", workers: 1, retries: 0, preserveOutput: "never",
      outputDir: ${JSON.stringify(outputPath)},
      use: { trace: "off", screenshot: "off", video: "off" },
      projects: [{ name: "desktop" }, { name: "mobile" }]
    }`
  )
  await writeFile(
    path.join(temporaryRoot, "diagnostic.spec.mjs"),
    `import { test } from ${JSON.stringify(playwrightUrl.href)};
    import { reportLiveHttpStatus } from ${JSON.stringify(helperUrl.href)};
    test("private-title", async ({}, testInfo) => {
      process.stdout.write("private-body https://private.invalid/?token=private-token\\n");
      process.stderr.write("private-credential private-browser-state\\n");
      reportLiveHttpStatus(testInfo.project.name, "admin-users", 403);
      reportLiveHttpStatus(testInfo.project.name, "admin-feature-flags", 503);
      reportLiveHttpStatus(testInfo.project.name, "admin-feature-flags-ui", 502);
      throw new Error("private-error");
    });`
  )
  const result = spawnSync(process.execPath, [cliPath, "test", "--config", configPath], {
    encoding: "utf8",
    timeout: 30_000,
    env: { ...process.env, FORCE_COLOR: "0" },
  })
  assert.equal(result.status, 1, "the fixture must execute and fail its intentional assertion")
  const records = result.stdout
    .split("\n")
    .filter((line) => line.startsWith("UE_LIVE_HTTP_STATUS_V1 "))
  assert.deepEqual(records, [
    "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=403",
    "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-feature-flags status=503",
    "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-feature-flags-ui status=502",
    "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-users status=403",
    "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-feature-flags status=503",
    "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-feature-flags-ui status=502",
  ])
  assert.match(result.stdout, /private-title|private-body/u)
  assert.match(result.stderr, /private-credential/u)
  assert.doesNotMatch(result.stderr, /UE_LIVE_HTTP_STATUS_V1/u)
  assert.deepEqual(await readdir(outputPath), [".last-run.json"])
})

test("profile-save diagnostics expose only closed validation and UI fields", () => {
  const output = reportInChild(`
    reportLiveProfileSaveFailure({
      project: "desktop",
      status: 422,
      body: { detail: [{ loc: ["body", "profile_detail", "about"], msg: "private-validation-message", type: "too_long", input: "private-user-input", ctx: { limit: 4096 } }] },
      alertCount: 0,
      saveDisabled: false,
      pathname: "/profile",
      pageErrors: [new TypeError("private-stack-message")],
    });
  `)
  assert.equal(
    output,
    "UE_LIVE_PROFILE_SAVE_V1 project=desktop status=422 detail=array detail_count=1 detail_msg=true alert_count=0 save_disabled=false route=profile page_error_count=1 page_error=type-error\n"
  )
  assert.doesNotMatch(
    output,
    /private-validation-message|private-user-input|private-stack-message|profile_detail|4096/u
  )
})

test("profile-save diagnostics reject invalid domains and do not coerce private values", () => {
  const output = reportInChild(`
    const privateValue = { toString() { throw new Error("private-value") } };
    reportLiveProfileSaveFailure({
      project: "mobile", status: 422, body: { detail: [{ msg: "secret" }] },
      alertCount: privateValue, saveDisabled: "false",
      pathname: "/profile?token=private", pageErrors: [],
    });
    reportLiveProfileSaveFailure({ project: "private-project", status: 422 });
    reportLiveProfileSaveFailure({ project: "desktop", status: "422" });
  `)
  assert.equal(
    output,
    "UE_LIVE_PROFILE_SAVE_V1 project=mobile status=422 detail=array detail_count=1 detail_msg=true alert_count=unknown save_disabled=unknown route=other page_error_count=0 page_error=none\n"
  )
  assert.doesNotMatch(output, /secret|private|token/u)
})

test("profile-save diagnostics deduplicate and stop after four records", () => {
  const output = reportInChild(`
    for (let status = 400; status < 410; status += 1) {
      reportLiveProfileSaveFailure({ project: "desktop", status, body: { detail: [] }, alertCount: 0, saveDisabled: false, pathname: "/profile", pageErrors: [] });
    }
    reportLiveProfileSaveFailure({ project: "desktop", status: 400, body: { detail: [] }, alertCount: 0, saveDisabled: false, pathname: "/profile", pageErrors: [] });
  `)
  assert.equal(
    output,
    Array.from(
      { length: 4 },
      (_, index) =>
        `UE_LIVE_PROFILE_SAVE_V1 project=desktop status=${400 + index} detail=array detail_count=0 detail_msg=false alert_count=0 save_disabled=false route=profile page_error_count=0 page_error=none\n`
    ).join("")
  )
})

test("profile-save diagnostic helper has no browser, response, environment, or artifact access", async () => {
  const source = await readFile(profileHelperUrl, "utf8")
  assert.doesNotMatch(
    source,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\b(?:page|browser|context|response|request|URL)\b|\.(?:json|text|screenshot|storageState|attach)\s*\(/u
  )
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 1)
})

test("HTTP diagnostics cannot replace an assertion when stdout writing fails", () => {
  assert.equal(
    reportInChild(`
    process.stdout.write = () => { throw new Error("synthetic-write-failure") };
    reportLiveHttpStatus("desktop", "password-reset-replay", 429);
  `),
    ""
  )
})

async function reportLoginInChild(calls) {
  const helper = await import(helperUrl.href)
  assert.equal(typeof helper.reportLiveLoginFailure, "function")
  return reportInChild(
    `const { reportLiveLoginFailure } = await import(${JSON.stringify(helperUrl.href)});\n${calls}`
  )
}

test("login failure diagnostics expose only closed scalar observations", async () => {
  assert.equal(
    await reportLoginInChild(`
      reportLiveLoginFailure("desktop", "submit", "0", "0", null, "login");
      reportLiveLoginFailure("mobile", "navigation", "1", "1", 200, "other");
      reportLiveLoginFailure("desktop", "navigation", "many", "many", 599, "unavailable");
    `),
    [
      "UE_LIVE_LOGIN_FAILURE_V1 project=desktop stage=submit requests=0 responses=0 status=none route=login\n",
      "UE_LIVE_LOGIN_FAILURE_V1 project=mobile stage=navigation requests=1 responses=1 status=200 route=other\n",
      "UE_LIVE_LOGIN_FAILURE_V1 project=desktop stage=navigation requests=many responses=many status=599 route=unavailable\n",
    ].join("")
  )
})

test("login failure diagnostics reject malformed values without coercing private data", async () => {
  assert.equal(
    await reportLoginInChild(`
      const privateValue = { toString() { throw new Error("private-value") } };
      const valid = ["desktop", "navigation", "1", "1", 200, "login"];
      const invalid = [
        ["Desktop", "desktop\\n", privateValue, null],
        ["response", "navigation\\r", privateValue, null],
        [0, "2", "01", "many\\n", privateValue, null],
        [1, "2", "many\\r", privateValue, null],
        [99, 600, 200.5, "200", "none", NaN, Infinity, undefined, true, privateValue],
        ["/login", "https://private.invalid/login?token=x", "login#token=x", privateValue, null],
      ];
      for (let index = 0; index < invalid.length; index += 1) {
        for (const value of invalid[index]) {
          const args = [...valid];
          args[index] = value;
          reportLiveLoginFailure(...args);
        }
      }
    `),
    ""
  )
})

test("login failure diagnostics deduplicate and cap output at sixteen records", async () => {
  const output = await reportLoginInChild(`
    for (let status = 100; status < 600; status += 1) {
      reportLiveLoginFailure("desktop", "navigation", "1", "1", status, "login");
      reportLiveLoginFailure("desktop", "navigation", "1", "1", status, "login");
    }
  `)
  assert.equal(
    output,
    Array.from(
      { length: 16 },
      (_, index) =>
        `UE_LIVE_LOGIN_FAILURE_V1 project=desktop stage=navigation requests=1 responses=1 status=${100 + index} route=login\n`
    ).join("")
  )
})

test("login failure diagnostics cannot replace the original failure if stdout throws", async () => {
  assert.equal(
    await reportLoginInChild(`
      process.stdout.write = () => { throw new Error("closed output"); };
      reportLiveLoginFailure("desktop", "navigation", "1", "1", 200, "login");
    `),
    ""
  )
})

test("role-denial probes report status before preserving the strict forbidden assertions", async () => {
  const source = await readFile(new URL("./auth-roles.live.spec.ts", import.meta.url), "utf8")
  const denial = source.slice(source.indexOf('for (const role of ["student", "teacher"] as const)'))
  for (const [variable, check] of [
    ["users", "users"],
    ["featureFlags", "feature-flags"],
  ]) {
    const diagnostic = denial.indexOf("`${role}-" + check + "-denied`")
    const assertion = denial.indexOf("expect(" + variable + ".status(),")
    assert.ok(diagnostic >= 0 && diagnostic < assertion)
    assert.match(denial.slice(assertion).split("\n")[0], /\.toBe\(403\)/u)
  }
  assert.doesNotMatch(denial, /Retry|retry|waitForTimeout|expect\.poll/u)
})

// Pure Stage A tests: no reporter, browser, subprocess, environment or network.
// Catch lost immutable scope, unsafe scalar serialization and exhausted bounds.
test("Stage A operation identity stays immutable across overlapping scopes", async () => {
  const module = await import(helperUrl.href + "?stage-a-scopes")
  assert.equal(typeof module.createLiveOperationScope, "function")
  const output = []
  const emit = (line) => output.push(line)
  const input = {
    project: "desktop",
    source: "chat-attachment-isolation.live.spec.ts",
    line: 229,
    retry: 0,
  }
  const first = module.createLiveOperationScope(input, emit)
  const second = module.createLiveOperationScope({ ...input, project: "mobile", retry: 1 }, emit)
  const a = first.begin("auth-login", "setup")
  const b = second.begin("chat-attachment-create", "body")
  input.project = "private-value"
  b.finish(502, 1, 1, 120001)
  a.finish(null, 0, 0, 17)
  a.finish(503, 1, 1, 20)
  assert.deepEqual(output, [
    "UE_LIVE_HTTP_OPERATION_V2 project=mobile source=chat-attachment-isolation.live.spec.ts line=229 retry=1 ordinal=1 phase=body operation=chat-attachment-create outcome=response status=502 elapsed_ms=120000 saturated=1 requests=1 responses=1\n",
    "UE_LIVE_HTTP_OPERATION_V2 project=desktop source=chat-attachment-isolation.live.spec.ts line=229 retry=0 ordinal=1 phase=setup operation=auth-login outcome=no-response status=none elapsed_ms=17 saturated=0 requests=0 responses=0\n",
  ])
})

test("Stage A rejects unsafe values and contains synchronous sink exceptions", async () => {
  const module = await import(helperUrl.href + "?stage-a-invalid")
  assert.equal(typeof module.createLiveOperationScope, "function")
  const output = []
  const emit = (line) => output.push(line)
  for (const change of [
    { source: "private-value" },
    { line: 223 },
    { retry: 2 },
    { project: "desktop\n" },
  ]) {
    module
      .createLiveOperationScope(
        {
          project: "desktop",
          source: "chat-attachment-isolation.live.spec.ts",
          line: 229,
          retry: 0,
          ...change,
        },
        emit
      )
      .begin("auth-login", "setup")
      .finish(502, 1, 1, 1)
  }
  assert.ok(
    output.every((line) => line === "UE_LIVE_HTTP_OPERATION_V2 completeness=invalid-scope\n")
  )
  const scope = module.createLiveOperationScope(
    { project: "desktop", source: "chat-attachment-isolation.live.spec.ts", line: 229, retry: 0 },
    emit
  )
  for (const value of [NaN, Infinity, -1, "502", {}, 99, 600])
    scope.begin("auth-login", "setup").finish(value, 1, 1, 1)
  assert.ok(output.every((line) => !line.includes("status=")))
  const primary = new Error("private-value")
  const failing = module.createLiveOperationScope(
    { project: "mobile", source: "chat-attachment-isolation.live.spec.ts", line: 229, retry: 1 },
    () => {
      throw primary
    }
  )
  assert.doesNotThrow(() => failing.begin("auth-login", "cleanup").finish(502, 1, 1, 1))
})

test("Stage A separately bounds case attempts and worker emission", async () => {
  const module = await import(helperUrl.href + "?stage-a-budget")
  assert.equal(typeof module.createLiveOperationScope, "function")
  const output = []
  const emit = (line) => output.push(line)
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const scope = module.createLiveOperationScope(
      { project: "desktop", source: "chat-attachment-isolation.live.spec.ts", line: 229, retry: 0 },
      emit
    )
    for (let index = 0; index < 20; index += 1)
      scope.begin("auth-login", "setup").finish(502, 2, 2, 1)
  }
  const rows = output.filter((line) => line.includes("status="))
  assert.equal(rows.length, 104)
  assert.equal(output.filter((line) => line.includes("completeness=truncated")).length, 1)
  assert.ok(rows.every((line) => line.length <= 512 && !/ordinal=(17|18|19|20) /.test(line)))
  assert.ok(rows.every((line) => line.endsWith("requests=many responses=many\n")))
})

test("Stage A boundaries retain only closed scalar observations", async () => {
  const module = await import(helperUrl.href + "?stage-a-boundaries")
  const output = []
  const scope = module.createLiveOperationScope(
    { project: "desktop", source: "chat-attachment-isolation.live.spec.ts", line: 229, retry: 0 },
    (line) => output.push(line)
  )
  for (const status of [100, 599]) scope.begin("auth-login", "cleanup").finish(status, 1, 1, 0)
  scope.begin("chat-attachment-create", "body").finish(502, 0, 1, 120000)
  scope.begin("auth-login", "setup").finish(null, 1, 0, 0.9)
  for (const values of [
    [502, -1, 1, 0],
    [502, 1, NaN, 0],
    [502, 1, 0, 0],
    [null, 1, 1, 0],
    [502, 1, 1, Infinity],
  ]) {
    scope.begin("auth-login", "setup").finish(...values)
  }
  for (const [operation, phase] of [
    ["private-value", "setup"],
    ["auth-login", "body"],
    ["chat-attachment-create", "cleanup"],
    ["auth-login", "private-value"],
  ])
    scope.begin(operation, phase).finish(502, 1, 1, 0)
  const rows = output.filter((line) => line.includes("status="))
  assert.equal(rows.length, 4)
  assert.ok(rows[0].includes("status=100 elapsed_ms=0 saturated=0"))
  assert.ok(rows[1].includes("status=599 elapsed_ms=0 saturated=0"))
  assert.ok(rows[2].endsWith("elapsed_ms=120000 saturated=0 requests=0 responses=1\n"))
  assert.ok(rows[3].endsWith("status=none elapsed_ms=0 saturated=0 requests=1 responses=0\n"))
  assert.ok(output.every((line) => !line.includes("private-value")))
})

test("Stage A malformed identity cannot introduce a fixture failure", async () => {
  const module = await import(helperUrl.href + "?stage-a-accessors")
  const output = []
  for (const identity of [
    null,
    undefined,
    {
      get project() {
        throw Error("private-value")
      },
    },
  ]) {
    assert.doesNotThrow(() =>
      module
        .createLiveOperationScope(identity, (line) => output.push(line))
        .begin("auth-login", "setup")
        .finish(502, 1, 1, 0)
    )
  }
  assert.deepEqual(output, ["UE_LIVE_HTTP_OPERATION_V2 completeness=invalid-scope\n"])
})

test("Stage A helper access boundary excludes browser, network and private data APIs", async () => {
  const { default: ts } = await import("typescript")
  const source = "// Stage A:" + (await readFile(helperUrl, "utf8")).split("// Stage A:")[1]
  const deniedNames = new Set([
    "request",
    "response",
    "page",
    "browser",
    "context",
    "fetch",
    "XMLHttpRequest",
    "WebSocket",
    "URL",
    "require",
    "console",
    "globalThis",
    "global",
    "window",
    "document",
  ])
  const deniedMembers = new Set([
    "json",
    "text",
    "screenshot",
    "storageState",
    "attach",
    "body",
    "headers",
  ])
  const violatesBoundary = (input) => {
    const tree = ts.createSourceFile(
      "diagnostic.ts",
      input,
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TS
    )
    let denied = tree.parseDiagnostics.length !== 0
    const visit = (node) => {
      if (
        ts.isImportDeclaration(node) ||
        ts.isImportEqualsDeclaration(node) ||
        node.kind === ts.SyntaxKind.ImportKeyword
      )
        denied = true
      if (ts.isIdentifier(node) && deniedNames.has(node.text)) denied = true
      if (ts.isIdentifier(node) && node.text === "process") {
        const stdout = node.parent
        const write = stdout?.parent
        const call = write?.parent
        if (!(
          ts.isPropertyAccessExpression(stdout) &&
          stdout.expression === node &&
          stdout.name.text === "stdout" &&
          ts.isPropertyAccessExpression(write) &&
          write.expression === stdout &&
          write.name.text === "write" &&
          ts.isCallExpression(call) &&
          call.expression === write
        ))
          denied = true
      }
      if (ts.isPropertyAccessExpression(node) && deniedMembers.has(node.name.text)) denied = true
      if (
        ts.isElementAccessExpression(node) &&
        ts.isStringLiteral(node.argumentExpression) &&
        deniedMembers.has(node.argumentExpression.text)
      )
        denied = true
      ts.forEachChild(node, visit)
    }
    visit(tree)
    return denied
  }
  assert.equal(violatesBoundary(source), false)
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 1)
  // Inspect code identifiers, not protocol literals; aliases cannot hide their source.
  for (const added of [
    "process.env.PRIVATE_VALUE",
    "process['env'].PRIVATE_VALUE",
    "const hidden = process; hidden.env.PRIVATE_VALUE",
    "page.context()",
    "request.get('private-value')",
    "request.post('private-value')",
    "response.body()",
    "response.headers()",
    "response?.headers()",
    "response['body']()",
    "const hidden = response; hidden.body()",
    "const { body: hidden } = response; hidden()",
    "globalThis['request'].get('private-value')",
    "fetch('private-value')",
    "value.json()",
    "value['json']()",
    "import 'private-value'",
    "import('private-value')",
  ])
    assert.equal(violatesBoundary(source + "\n" + added), true)
  assert.equal(violatesBoundary(source + '\nconst safe = "response request process.env"'), false)
})
