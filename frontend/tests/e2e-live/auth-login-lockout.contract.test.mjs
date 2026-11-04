import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import process from "node:process"
import { fileURLToPath, URL } from "node:url"
import test from "node:test"
import { runInNewContext, runInThisContext } from "node:vm"
import typescript from "typescript"
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

test("the live acceptance is collected and marked runnable in both Playwright projects", () => {
  const cwd = fileURLToPath(new URL("../../", import.meta.url))
  const cli = fileURLToPath(new URL("../../node_modules/@playwright/test/cli.js", import.meta.url))
  // Listing loads the real fixtures and config without connecting to a live stand.
  const result = spawnSync(
    process.execPath,
    [
      cli,
      "test",
      "--config=playwright.live.config.ts",
      "tests/e2e-live/auth-login-lockout.live.spec.ts",
      "--list",
      "--forbid-only",
      "--reporter=json",
    ],
    {
      cwd,
      env: {
        ...process.env,
        TEST_PASSWORD: "p".repeat(24),
        LIVE_MAILPIT_URL: "http://127.0.0.1:25000",
      },
      encoding: "utf8",
      timeout: 30_000,
    }
  )
  assert.equal(result.error, undefined)
  assert.equal(result.status, 0, result.stderr)
  const report = JSON.parse(result.stdout)
  const tests = []
  const walk = (suite) => {
    for (const spec of suite.specs ?? []) {
      if (spec.file === "auth-login-lockout.live.spec.ts") tests.push(...spec.tests)
    }
    for (const child of suite.suites ?? []) walk(child)
  }
  for (const suite of report.suites) walk(suite)
  assert.deepEqual(tests.map((entry) => entry.projectName).sort(), ["desktop", "mobile"])
  for (const entry of tests) {
    assert.equal(entry.expectedStatus, "passed")
    assert.deepEqual(entry.annotations, [])
  }
})

test("the live acceptance keeps its real-auth policy", async () => {
  const spec = await readFile(specUrl, "utf8")
  // Static policy guards retained from the original contract: registration must not consume
  // the shared rate-limited path, and the live auth endpoints must not be mocked.
  assert.doesNotMatch(spec, /\/auth\/register/u)
  assert.doesNotMatch(spec, /page\.route\(|route\.fulfill\(/u)
})

// Run the actual Playwright callback with a controlled adapter and real decision helpers.
// This tests the scenario's wiring and assertions, not the backend or a real browser.
async function lockoutScenario(options = {}) {
  const source = await readFile(specUrl, "utf8")
  const compiled = typescript.transpileModule(source, {
    compilerOptions: {
      module: typescript.ModuleKind.CommonJS,
      target: typescript.ScriptTarget.ES2022,
    },
  }).outputText
  const events = []
  const adminRequests = []
  const loginRequests = []
  const decisions = { rules: [], attempts: [], locked: [], cooldowns: [] }
  const ownedId = "owned/user ?"
  const email = "live-auth-lockout-uuid-1@university.dev"
  const password = randomUUID()
  const wrongPassword = randomUUID()
  assert.notEqual(password, wrongPassword)
  let callback
  let responsePredicate
  let resolveResponse
  let generatedPasswords = 0
  let generatedUuids = 0

  function fakeExpect(actual, message) {
    return {
      toBe(expected) {
        assert.equal(actual, expected, message)
      },
      not: {
        toBe(expected) {
          assert.notEqual(actual, expected, message)
        },
      },
      async toHaveURL(pattern) {
        assert.match(actual.url, pattern, message)
      },
      async toBeVisible() {
        assert.equal(actual.visible, true, message)
      },
    }
  }

  function response(method, pathname, status = 401) {
    return {
      request: () => ({ method: () => method }),
      url: () => `https://owned.example.invalid${pathname}`,
      status: () => status,
    }
  }

  const adminPage = {
    async evaluate(fn, arg) {
      const fetch = async (url, init) => {
        const entry = {
          url,
          method: init.method,
          credentials: init.credentials,
          csrf: init.headers["X-CSRF-Token"],
          requestedWith: init.headers["X-Requested-With"],
          body: init.body ? JSON.parse(init.body) : undefined,
        }
        adminRequests.push(entry)
        events.push(init.method === "POST" ? "created" : "deleted")
        return init.method === "POST"
          ? {
              status: options.creationStatus ?? 200,
              json: async () => ({
                id: Object.hasOwn(options, "createdId") ? options.createdId : ownedId,
              }),
            }
          : {
              status: options.deletionStatus ?? 200,
              json: async () => ({ deleted: options.deleted ?? true }),
            }
      }
      return runInNewContext(`(${fn.toString()})(arg)`, {
        arg,
        document: { cookie: "other=x; csrf_token=admin%20csrf; last=y" },
        fetch,
        encodeURIComponent,
        decodeURIComponent,
      })
    },
  }
  const adminContext = {
    async newPage() {
      return adminPage
    },
    async close() {
      events.push("admin-context-closed")
    },
  }
  const browser = {
    async newContext(contextOptions) {
      assert.equal(contextOptions.baseURL, "https://owned.example.invalid")
      assert.equal(contextOptions.ignoreHTTPSErrors, true)
      assert.equal(contextOptions.locale, "ru-RU")
      return adminContext
    },
  }
  const page = {
    url: "https://owned.example.invalid/login",
    waitForResponse(predicate) {
      events.push("response-listener")
      responsePredicate = predicate
      return new Promise((resolve) => {
        resolveResponse = resolve
      })
    },
    locator(selector) {
      assert.equal(selector, "form")
      return {
        getByRole(role) {
          assert.equal(role, "alert")
          return {
            filter({ hasText }) {
              assert.equal(hasText.test(" "), false)
              assert.equal(hasText.test("Wrong credentials"), true)
              return { visible: options.errorVisible ?? true }
            },
          }
        },
      }
    },
    context() {
      return {
        async cookies() {
          return options.sessionCookie === false ? [] : [{ name: "access_token_v2" }]
        },
      }
    },
    async evaluate(fn) {
      return runInNewContext(`(${fn.toString()})()`, {
        document: { cookie: options.userCookie ?? "other=x; csrf_token=user%20csrf" },
        decodeURIComponent,
      })
    },
    request: {
      async get(url) {
        assert.equal(url, "/api/v1/users/me")
        events.push("identity-checked")
        return {
          status: () => options.identityStatus ?? 200,
          json: async () => ({ id: options.identityId ?? ownedId }),
        }
      },
      async post(url, init) {
        const attempt = loginRequests.length + 1
        loginRequests.push({ url, form: init.form, csrf: init.headers["X-CSRF-Token"] })
        events.push(`attempt-${attempt}`)
        const status = options.statuses?.[attempt] ?? (attempt < 5 ? 401 : 423)
        return {
          status: () => status,
          headers: () => ({
            "retry-after": Object.hasOwn(options, "retryAfter") ? options.retryAfter : "30",
          }),
        }
      },
    },
  }
  const fixtures = {
    test(_name, fn) {
      assert.equal(callback, undefined, "expected one lockout scenario")
      callback = fn
    },
    expect: fakeExpect,
    freshPassword() {
      generatedPasswords += 1
      return generatedPasswords === 1 ? password : wrongPassword
    },
    async loginAs(actualPage, role) {
      assert.equal(actualPage, adminPage)
      assert.equal(role, "admin")
      events.push("admin-login")
    },
    async submitLogin(actualPage, actualEmail, suppliedPassword) {
      assert.equal(actualPage, page)
      assert.equal(actualEmail, email)
      assert.equal(suppliedPassword, wrongPassword)
      assert.equal(typeof responsePredicate, "function", "listen before submitting the login")
      assert.equal(responsePredicate(response("GET", "/api/v1/auth/login")), false)
      assert.equal(responsePredicate(response("POST", "/api/v1/other")), false)
      const matchingResponse = response("POST", "/api/v1/auth/login", options.uiStatus ?? 401)
      assert.equal(responsePredicate(matchingResponse), true)
      events.push("ui-failure")
      resolveResponse(matchingResponse)
    },
    async loginWith(actualPage, actualEmail, suppliedPassword) {
      assert.equal(actualPage, page)
      assert.equal(actualEmail, email)
      assert.equal(suppliedPassword, password)
      events.push("successful-login")
    },
  }
  fixtures.test.setTimeout = (timeout) => {
    assert.equal(timeout, 90_000)
  }
  const modules = {
    "node:crypto": { randomUUID: () => `uuid-${++generatedUuids}` },
    "./fixtures": fixtures,
    "./auth-login-lockout.decisions.mjs": {
      firstLockoutRule(...args) {
        const rule = firstLockoutRule(...args)
        decisions.rules.push(rule)
        return rule
      },
      expectedFailedAttemptStatus(attempt, rule) {
        decisions.attempts.push({ attempt, rule })
        return options.overrideExpectedStatus ?? expectedFailedAttemptStatus(attempt, rule)
      },
      isAccountLockedStatus(status) {
        decisions.locked.push(status)
        return isAccountLockedStatus(status)
      },
      lockoutRetryAfterWithinRule(header, rule) {
        decisions.cooldowns.push({ header, rule })
        return options.overrideCooldownDecision ?? lockoutRetryAfterWithinRule(header, rule)
      },
    },
  }
  const load = runInThisContext(`(function(exports, require, process) {\n${compiled}\n})`, {
    filename: fileURLToPath(specUrl),
  })
  load(
    {},
    (id) => {
      assert.ok(Object.hasOwn(modules, id), `unexpected scenario dependency: ${id}`)
      return modules[id]
    },
    { env: { LIVE_BASE_URL: "https://owned.example.invalid" } }
  )
  assert.equal(typeof callback, "function")
  return {
    events,
    adminRequests,
    loginRequests,
    decisions,
    password,
    wrongPassword,
    run: () => callback({ browser, page }),
  }
}

test("the Playwright callback drives the owned lockout flow and applies every decision", async () => {
  const scenario = await lockoutScenario()
  await scenario.run()
  const rule = { attempts: 5, seconds: 30 }
  assert.deepEqual(scenario.decisions.rules, [rule])
  assert.deepEqual(
    scenario.decisions.attempts,
    Array.from({ length: 5 }, (_, index) => ({ attempt: index + 1, rule }))
  )
  assert.deepEqual(scenario.decisions.locked, [401, 401, 401, 401, 423])
  assert.deepEqual(scenario.decisions.cooldowns, [{ header: "30", rule }])
  assert.deepEqual(
    scenario.loginRequests,
    Array.from({ length: 5 }, () => ({
      url: "/api/v1/auth/login",
      form: {
        username: "live-auth-lockout-uuid-1@university.dev",
        password: scenario.wrongPassword,
      },
      csrf: "user csrf",
    }))
  )
  assert.deepEqual(scenario.adminRequests, [
    {
      url: "/api/v1/users",
      method: "POST",
      credentials: "same-origin",
      csrf: "admin csrf",
      requestedWith: "XMLHttpRequest",
      body: {
        email: "live-auth-lockout-uuid-1@university.dev",
        full_name: "Live Auth Lockout uuid-2",
        password: scenario.password,
        role: "student",
      },
    },
    {
      url: "/api/v1/users/owned%2Fuser%20%3F",
      method: "DELETE",
      credentials: "same-origin",
      csrf: "admin csrf",
      requestedWith: "XMLHttpRequest",
      body: undefined,
    },
  ])
  assert.deepEqual(scenario.events, [
    "admin-login",
    "created",
    "response-listener",
    "ui-failure",
    "successful-login",
    "identity-checked",
    "attempt-1",
    "attempt-2",
    "attempt-3",
    "attempt-4",
    "attempt-5",
    "deleted",
    "admin-context-closed",
  ])
})

test("the callback rejects wrong statuses, cooldowns, and disconnected decision results", async () => {
  for (const options of [
    { uiStatus: 429 },
    ...[1, 2, 3, 4].flatMap((attempt) => [
      { statuses: { [attempt]: 423 } },
      { statuses: { [attempt]: 429 } },
    ]),
    { statuses: { 5: 401 } },
    { statuses: { 5: 429 } },
    { retryAfter: undefined },
    { retryAfter: "0" },
    { retryAfter: "31" },
    { retryAfter: "1.5" },
    { overrideExpectedStatus: 222 },
    { overrideCooldownDecision: false },
  ]) {
    const scenario = await lockoutScenario(options)
    await assert.rejects(scenario.run(), assert.AssertionError, JSON.stringify(options))
    assert.equal(scenario.adminRequests.at(-1).method, "DELETE")
    assert.equal(scenario.events.at(-1), "admin-context-closed")
  }
})

test("the callback rejects unverified accounts and still closes its admin context", async () => {
  for (const options of [
    { errorVisible: false },
    { identityStatus: 401 },
    { identityId: "another-user" },
    { sessionCookie: false },
    { userCookie: "other=x" },
    { creationStatus: 500 },
  ]) {
    const scenario = await lockoutScenario(options)
    await assert.rejects(scenario.run(), assert.AssertionError, JSON.stringify(options))
    assert.equal(scenario.adminRequests.at(-1).method, "DELETE")
    assert.equal(scenario.events.at(-1), "admin-context-closed")
  }

  const missingId = await lockoutScenario({ createdId: null })
  await assert.rejects(missingId.run(), /returned no account id/u)
  assert.equal(missingId.loginRequests.length, 0)
  assert.equal(missingId.events.at(-1), "admin-context-closed")

  for (const options of [{ deletionStatus: 500 }, { deleted: false }]) {
    const scenario = await lockoutScenario(options)
    await assert.rejects(scenario.run(), assert.AssertionError, JSON.stringify(options))
    assert.equal(scenario.events.at(-1), "admin-context-closed")
  }
})
