import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import process from "node:process"
import test from "node:test"
import { fileURLToPath, URL } from "node:url"

const helperUrl = new URL("./http-status-diagnostic.ts", import.meta.url)
const profileHelperUrl = new URL("./profile-save-diagnostic.ts", import.meta.url)

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { parseLiveRateLimitHeader, reportLiveHttpStatus, reportLiveRateLimitRetry } from ${JSON.stringify(helperUrl.href)};\nimport { reportLiveProfileSaveFailure } from ${JSON.stringify(profileHelperUrl.href)};\n${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0, "the diagnostic helper must not throw")
  assert.equal(result.stderr, "", "the helper writes only its bounded stdout protocol")
  return result.stdout
}

test("HTTP diagnostics emit only fixed project/check labels and integer status boundaries", () => {
  for (const status of [100, 599]) {
    const calls = []
    const expected = []
    for (const project of ["desktop", "mobile"]) {
      for (const check of [
        "admin-users",
        "admin-feature-flags",
        "admin-feature-flags-ui",
        "password-reset-replay",
        "auth-login",
        "auth-logout",
        "auth-session-preflight",
        "messenger-message-send",
        "chat-attachment-create",
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

test("HTTP diagnostics deduplicate records and stop at forty records per worker process", () => {
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
      { length: 40 },
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
    'reportLiveRateLimitRetry("mobile", "password-reset-replay", 60, "declined-deadline", 12345)',
    'reportLiveRateLimitRetry("desktop", "auth-logout", null, "declined-header", 0)',
  ].join("\n")
  assert.equal(
    reportInChild(calls),
    [
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=40 decision=retry remaining_ms=60000\n",
      "UE_LIVE_RATE_LIMIT_V1 project=desktop check=auth-logout x_ratelimit_limit=invalid x_ratelimit_remaining=invalid\n",
      "UE_LIVE_RETRY_V1 project=mobile check=password-reset-replay retry_after_seconds=60 decision=declined-deadline remaining_ms=12345\n",
      "UE_LIVE_RETRY_V1 project=desktop check=auth-logout retry_after_seconds=invalid decision=declined-header remaining_ms=0\n",
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
  const source = await readFile(helperUrl, "utf8")
  assert.doesNotMatch(
    source,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\b(?:page|browser|context|response|request|URL)\b|\.(?:json|text|screenshot|storageState|attach)\s*\(/u
  )
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 3)
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
