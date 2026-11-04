import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import process from "node:process"
import { fileURLToPath, URL } from "node:url"
import test from "node:test"
import { runInNewContext, runInThisContext } from "node:vm"
import typescript from "typescript"
import {
  REGISTRATION_STEP_ORDER,
  registrationTraceViolations,
} from "./register-double-submit.decisions.mjs"
import {
  isOpaqueRegistrationReceipt,
  waitForRegistrationCompletion,
  withRegistrationDetach,
} from "./register-double-submit-lifecycle.mjs"

const specUrl = new URL("./register-double-submit.live.spec.ts", import.meta.url)

test("Playwright collects registration and SSR acceptance in both live projects without skips", () => {
  const cwd = fileURLToPath(new URL("../../", import.meta.url))
  const cli = fileURLToPath(new URL("../../node_modules/@playwright/test/cli.js", import.meta.url))
  // --list only loads the fixtures; the placeholders never connect to a stand.
  const result = spawnSync(
    process.execPath,
    [
      cli,
      "test",
      "--config=playwright.live.config.ts",
      "tests/e2e-live/register-double-submit.live.spec.ts",
      "tests/e2e-live/ssr-hydration-i18n.live.spec.ts",
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
  assert.equal(result.status, 0)
  const report = JSON.parse(result.stdout)
  const collected = []
  const walk = (suite, file) => {
    for (const spec of suite.specs ?? []) {
      for (const entry of spec.tests) {
        collected.push({
          file,
          project: entry.projectName,
          status: entry.expectedStatus,
          annotations: entry.annotations,
        })
      }
    }
    for (const child of suite.suites ?? []) walk(child, file)
  }
  for (const suite of report.suites) walk(suite, suite.file)
  for (const [file, minimum] of [
    ["register-double-submit.live.spec.ts", 1],
    ["ssr-hydration-i18n.live.spec.ts", 3],
  ]) {
    for (const project of ["desktop", "mobile"]) {
      const tests = collected.filter((entry) => entry.file === file && entry.project === project)
      assert.ok(tests.length >= minimum, `${file} must collect in ${project}`)
      for (const entry of tests) {
        assert.equal(entry.status, "passed")
        assert.deepEqual(entry.annotations, [])
      }
    }
  }
})

test("live registration acceptance keeps its artifact and real-stack policy", async () => {
  assert.equal(
    existsSync(specUrl),
    true,
    "the mobile double-submit registration acceptance must exist"
  )

  // Behaviour: evaluate the live Playwright config and read the effective project settings.
  const { default: liveConfig } = await import("../../playwright.live.config.ts")
  const projects = Object.fromEntries(liveConfig.projects.map((project) => [project.name, project]))
  assert.ok(projects.desktop, "the desktop acceptance project must exist")
  assert.ok(projects.mobile, "the mobile acceptance project must exist")
  for (const name of ["desktop", "mobile"]) {
    const use = { ...liveConfig.use, ...projects[name].use }
    assert.equal(use.trace, "off", `${name} must not record traces`)
    assert.equal(use.screenshot, "off", `${name} must not capture screenshots`)
    assert.equal(use.video, "off", `${name} must not record video`)
  }

  const spec = await readFile(specUrl, "utf8")
  // Static policy guards kept deliberately: the acceptance must reach the real registration
  // API (no route mocking or direct API posts) and must not embed a literal password. Only a
  // live run can exercise the behaviour itself.
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|page\.request\.(?:post|put|patch|delete)\(|fulfill\(/u
  )
  assert.doesNotMatch(spec, /password\s*[:=]\s*["'][^"']+/iu)
})

// Execute the actual Playwright callback against a controlled browser adapter. This
// checks the scenario's wiring and failure decisions; only a live run can establish
// what the real application or backend does in response to the two inputs.
async function registrationScenario(options = {}) {
  const source = await readFile(specUrl, "utf8")
  const compiled = typescript.transpileModule(source, {
    compilerOptions: {
      module: typescript.ModuleKind.CommonJS,
      target: typescript.ScriptTarget.ES2022,
    },
  }).outputText
  const events = []
  const deletionRequests = []
  const decisions = []
  const fields = new Map()
  const origin = "https://owned.example.invalid"
  const password = "p".repeat(24)
  const account = { email: "owned@example.invalid", fullName: "Owned Test" }
  let callback
  let cleanup
  let listener
  let responsePredicate
  let resolveResponse
  let responseSent = false
  let interactions = 0
  let postCount = 0
  let finishResponse
  const completion = options.pendingCompletion
    ? new Promise((resolve) => {
        finishResponse = resolve
      })
    : undefined

  function fakeExpect(actual, message) {
    return {
      toBe(expected) {
        assert.equal(actual, expected, message)
      },
      toEqual(expected) {
        assert.deepEqual(actual, expected, message)
      },
      async toBeVisible() {
        assert.equal(actual.visible, true, message)
      },
      async toBeEnabled() {
        assert.equal(actual.enabled, true, message)
      },
      async toHaveURL(expected) {
        assert.match(actual.url, expected, message)
      },
    }
  }

  function emitRequest(method, url) {
    const request = {
      method: () => method,
      url: () => url,
      response: async () => response,
    }
    const response = {
      request: () => request,
      status: () => options.status ?? 200,
      json: async () => (Object.hasOwn(options, "receipt") ? options.receipt : { status: "ok" }),
      finished: async () => completion ?? (options.incomplete ? new Error("unfinished") : null),
    }
    if (method === "POST" && url === `${origin}/api/v1/auth/register`) postCount += 1
    listener?.(request)
    if (!responseSent && responsePredicate?.(response)) {
      responseSent = true
      page.url = `${origin}/login`
      resolveResponse(response)
    }
  }

  function sendInput() {
    events.push("input")
    interactions += 1
    assert.equal(typeof cleanup, "function", "cleanup must be registered before input")
    // Unrelated requests must not contribute to the registration count.
    emitRequest("GET", `${origin}/api/v1/auth/register`)
    emitRequest("POST", `${origin}/api/v1/other`)
    emitRequest("POST", "https://other.example.invalid/api/v1/auth/register")
    if (!options.missing && (interactions === 1 || options.duplicate === "input")) {
      emitRequest("POST", `${origin}/api/v1/auth/register`)
    }
  }

  const submitButton = {
    visible: true,
    enabled: true,
    async scrollIntoViewIfNeeded() {},
    async boundingBox() {
      return { x: 0, y: 0, width: 100, height: 44 }
    },
    async dblclick(options) {
      assert.equal(options.delay, 0)
      events.push("double-click")
      sendInput()
      sendInput()
    },
  }
  const page = {
    url: "",
    request: {},
    touchscreen: {
      async tap(x, y) {
        events.push(["tap", x, y])
        sendInput()
      },
    },
    async setViewportSize(size) {
      events.push(["viewport", size.width, size.height])
    },
    async addInitScript() {},
    async goto(path) {
      events.push("navigated")
      this.url = `${origin}${path}`
    },
    async waitForFunction(predicate) {
      const expression = `(${predicate.toString()})()`
      assert.equal(runInNewContext(expression, { window: { __APP_HYDRATED: false } }), false)
      assert.equal(runInNewContext(expression, { window: { __APP_HYDRATED: true } }), true)
      events.push("hydrated")
    },
    locator(selector) {
      if (selector === "#register-submit") return submitButton
      if (selector === "section.auth-shell--login") return { visible: true }
      return {
        async fill(value) {
          fields.set(selector, value)
        },
      }
    },
    on(name, fn) {
      assert.equal(name, "request")
      listener = fn
      events.push("listener-attached")
    },
    off(name, fn) {
      assert.equal(name, "request")
      assert.equal(fn, listener)
      listener = undefined
      events.push("listener-detached")
    },
    waitForResponse(predicate) {
      if (options.missing) return Promise.reject(new Error("request timed out"))
      responsePredicate = predicate
      return new Promise((resolve) => {
        resolveResponse = resolve
      })
    },
    async close() {
      if (options.duplicate === "close") emitRequest("POST", `${origin}/api/v1/auth/register`)
      events.push("page-closed")
      if (options.closeFails) throw new Error("page close failed")
    },
  }
  const context = {
    async addCookies() {},
    async newCDPSession() {
      return {
        async send(method, parameters) {
          if (method === "Network.emulateNetworkConditions")
            events.push(["network", parameters.latency])
        },
        async detach() {
          events.push("cdp-detached")
        },
      }
    },
  }
  const adminPage = {
    request: {},
    async evaluate(fn, args) {
      const fetch = async (url, init) => {
        deletionRequests.push({
          url,
          method: init.method,
          csrf: init.headers["X-CSRF-Token"],
          credentials: init.credentials,
          redirect: init.redirect,
        })
        return { status: 200, json: async () => ({ deleted: true }) }
      }
      return runInNewContext(`(${fn.toString()})(args)`, {
        args,
        document: { cookie: "csrf_token=owned%20csrf" },
        window: { setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout },
        AbortController: globalThis.AbortController,
        fetch,
        encodeURIComponent,
        decodeURIComponent,
      })
    },
  }
  const cleanupBrowser = {
    async newContext() {
      return {
        async newPage() {
          return adminPage
        },
        async close() {
          events.push("cleanup-context-closed")
        },
      }
    },
  }
  const fixtures = {
    test(_name, fn) {
      assert.equal(callback, undefined, "expected one registration scenario")
      callback = fn
    },
    expect: fakeExpect,
    freshPassword: () => password,
    ownedSessionOrigin: () => origin,
    liveDeadlineBoundedTimeoutMs: () => 500,
    liveTestSlotDeadlineAtMs: () => Date.now() + 1000,
    registerOwnedSessionCleanup(fn) {
      cleanup = fn
      events.push("cleanup-registered")
    },
    async stubBreachedPasswordLookup() {},
    async withLiveRegistrationAdmission(_page, count, fn) {
      assert.equal(count, 2)
      return fn()
    },
    async loginWith(_page, email, suppliedPassword) {
      assert.equal(email, account.email)
      assert.equal(suppliedPassword, password)
      events.push("login")
      if (options.duplicate === "login") emitRequest("POST", `${origin}/api/v1/auth/register`)
    },
    async loginAs(_page, role) {
      assert.equal(role, "admin")
      events.push("cleanup-admin-login")
    },
  }
  const modules = {
    "./fixtures": fixtures,
    "./password-reset-account-identity": {
      createOwnedResetAccount: () => account,
      async readOwnedResetUserId() {
        if (options.failIdentity) throw new Error("identity lookup failed")
        return "owned-user"
      },
      async findOwnedResetUserId() {
        events.push("cleanup-identity-lookup")
        return "owned-user"
      },
    },
    "./register-double-submit-lifecycle.mjs": {
      isOpaqueRegistrationReceipt,
      waitForRegistrationCompletion,
      withRegistrationDetach,
    },
    "./register-double-submit.decisions.mjs": {
      registrationTraceViolations(trace, count) {
        decisions.push({ trace: [...trace], count })
        return options.forceTraceViolation
          ? ["injected violation"]
          : registrationTraceViolations(trace, count)
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
    { env: { LIVE_BASE_URL: origin } }
  )
  assert.equal(typeof callback, "function")
  return {
    events,
    deletionRequests,
    decisions,
    fields,
    get postCount() {
      return postCount
    },
    run: () =>
      callback(
        { page, context },
        { project: { name: options.project ?? "mobile" }, annotations: [] }
      ),
    cleanup: async () => {
      assert.equal(typeof cleanup, "function")
      return cleanup(cleanupBrowser, Date.now() + 1000)
    },
    finishResponse: () => {
      assert.equal(typeof finishResponse, "function")
      finishResponse(null)
    },
  }
}

test("the real registration scenario drives two inputs and validates its recorded trace", async () => {
  for (const project of ["desktop", "mobile"]) {
    const scenario = await registrationScenario({ project })
    await scenario.run()
    assert.deepEqual(scenario.events[0], ["viewport", 360, 800])
    assert.equal(scenario.events.filter((event) => event === "input").length, 2)
    const taps = scenario.events.filter((event) => Array.isArray(event) && event[0] === "tap")
    if (project === "mobile") {
      assert.deepEqual(taps, [
        ["tap", 50, 22],
        ["tap", 50, 22],
      ])
      assert.equal(scenario.events.includes("double-click"), false)
    } else {
      assert.deepEqual(taps, [])
      assert.equal(scenario.events.filter((event) => event === "double-click").length, 1)
    }
    assert.equal(scenario.postCount, 1)
    assert.equal(scenario.fields.get("#email"), "owned@example.invalid")
    assert.deepEqual(scenario.decisions, [{ trace: [...REGISTRATION_STEP_ORDER], count: 1 }])
    assert.ok(scenario.events.indexOf("cleanup-registered") < scenario.events.indexOf("input"))
    assert.ok(scenario.events.indexOf("listener-attached") < scenario.events.indexOf("input"))
    assert.ok(scenario.events.indexOf("page-closed") < scenario.events.indexOf("listener-detached"))
    const slowNetwork = scenario.events.findIndex(
      (event) => Array.isArray(event) && event[0] === "network" && event[1] > 0
    )
    const restoredNetwork = scenario.events.findIndex(
      (event) => Array.isArray(event) && event[0] === "network" && event[1] === 0
    )
    assert.ok(slowNetwork >= 0 && slowNetwork < scenario.events.indexOf("input"))
    assert.ok(restoredNetwork > scenario.events.lastIndexOf("input"))
    await scenario.cleanup()
    assert.deepEqual(scenario.deletionRequests, [
      {
        url: "/api/v1/users/owned-user",
        method: "DELETE",
        csrf: "owned csrf",
        credentials: "same-origin",
        redirect: "error",
      },
    ])
    assert.ok(scenario.events.includes("cleanup-context-closed"))
  }
})

test("the real registration scenario rejects missing, duplicate and invalid responses", async () => {
  for (const [options, failure] of [
    [{ missing: true }, /Registration request did not receive a response/u],
    [{ duplicate: "input" }, /2 !== 1/u],
    [{ duplicate: "login" }, /no extra registration request during navigation/u],
    [{ duplicate: "close" }, /no extra registration request before the page closed/u],
    [{ status: 500 }, /500 !== 200/u],
    [{ receipt: null }, /false !== true/u],
    [{ receipt: { status: "ok", id: "unexpected-public-identifier" } }, /false !== true/u],
    [{ forceTraceViolation: true }, /registration steps ran out of order or more than once/u],
  ]) {
    const scenario = await registrationScenario(options)
    await assert.rejects(scenario.run(), failure, JSON.stringify(options))
    assert.ok(scenario.events.includes("cdp-detached"))
    assert.ok(scenario.events.includes("page-closed"))
  }
})

test("registration cleanup finds the account after identity failure and rejects incomplete requests", async () => {
  const failedIdentity = await registrationScenario({ failIdentity: true })
  await assert.rejects(failedIdentity.run(), /identity lookup failed/u)
  await failedIdentity.cleanup()
  assert.ok(failedIdentity.events.includes("cleanup-identity-lookup"))
  assert.equal(failedIdentity.deletionRequests.length, 1)

  const incomplete = await registrationScenario({ incomplete: true })
  await incomplete.run()
  await assert.rejects(incomplete.cleanup(), /request completion could not be verified/u)
  assert.equal(incomplete.deletionRequests.length, 1)
  assert.ok(incomplete.events.includes("cleanup-context-closed"))

  const closeFails = await registrationScenario({ closeFails: true })
  await assert.rejects(closeFails.run(), /Registration browser cleanup failed/u)
  await assert.rejects(closeFails.cleanup(), /request completion could not be verified/u)
  assert.equal(closeFails.deletionRequests.length, 1)
  assert.ok(closeFails.events.includes("cleanup-context-closed"))
})

test("the live scenario waits for the observed request before deleting its account", async () => {
  const scenario = await registrationScenario({ pendingCompletion: true })
  await scenario.run()
  let completed = false
  const cleanup = scenario.cleanup().then(() => {
    completed = true
  })
  await new Promise((resolve) => globalThis.setImmediate(resolve))
  assert.equal(completed, false)
  assert.equal(scenario.deletionRequests.length, 0)
  scenario.finishResponse()
  await cleanup
  assert.equal(completed, true)
  assert.equal(scenario.deletionRequests.length, 1)
})

test("the ordering decision accepts the legal sequence with exactly one registration POST", () => {
  assert.deepEqual(registrationTraceViolations([...REGISTRATION_STEP_ORDER], 1), [])
})

test("the ordering decision rejects a registration that is not single or not ordered", () => {
  const legal = [...REGISTRATION_STEP_ORDER]
  const swap = (a, b) => legal.map((step) => (step === a ? b : step === b ? a : step))

  assert.ok(
    registrationTraceViolations(legal, 2).includes("expected exactly one registration POST, saw 2")
  )
  assert.ok(registrationTraceViolations(legal, 0).length > 0)
  assert.ok(
    registrationTraceViolations(swap("hydrated", "filled"), 1).includes("filled before hydrated")
  )
  assert.ok(
    registrationTraceViolations(swap("cleanup-registered", "submitted"), 1).includes(
      "submitted before cleanup-registered"
    )
  )
  assert.ok(
    registrationTraceViolations(swap("listener-attached", "submitted"), 1).includes(
      "submitted before listener-attached"
    )
  )
  assert.ok(registrationTraceViolations([...legal, "submitted"], 1).includes("duplicate submitted"))
  assert.ok(
    registrationTraceViolations(
      legal.filter((step) => step !== "page-closed"),
      1
    ).includes("missing page-closed")
  )
  assert.ok(
    registrationTraceViolations(
      legal.filter((step) => step !== "hydrated"),
      1
    ).length > 0
  )
})

test("registration accepts only the generic success receipt", () => {
  assert.equal(isOpaqueRegistrationReceipt({ status: "ok" }), true)
  for (const invalid of [
    null,
    undefined,
    [],
    "ok",
    {},
    { status: "error" },
    { status: "ok", id: "unexpected-public-identifier" },
  ]) {
    assert.equal(isOpaqueRegistrationReceipt(invalid), false)
  }
})

test("registration detaches after success and preserves the result", async () => {
  let detached = 0
  let reported = 0
  const result = await withRegistrationDetach(
    async () => "result",
    async () => {
      detached += 1
    },
    () => {
      reported += 1
    }
  )
  assert.equal(result, "result")
  assert.equal(detached, 1)
  assert.equal(reported, 0)
})

test("a detach failure does not mask a registration failure", async () => {
  const primary = new Error("registration failed")
  let reported = 0
  await assert.rejects(
    withRegistrationDetach(
      async () => {
        throw primary
      },
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        reported += 1
      }
    ),
    (error) => error === primary
  )
  assert.equal(reported, 1)
})

test("a detach failure after success remains a failure without exposing CDP details", async () => {
  await assert.rejects(
    withRegistrationDetach(
      async () => "result",
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        throw new Error("unused")
      }
    ),
    (error) =>
      error instanceof Error &&
      error.message === "Registration browser cleanup failed" &&
      !String(error).includes("private CDP details")
  )
})

test("a broken detach diagnostic cannot replace the registration failure", async () => {
  const primary = new Error("registration failed")
  let diagnostics = 0
  await assert.rejects(
    withRegistrationDetach(
      async () => {
        throw primary
      },
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        diagnostics += 1
        throw new Error("diagnostic failed")
      }
    ),
    (error) => error === primary
  )
  assert.equal(diagnostics, 1)
})

test("registration cleanup waits for all observed request completions", async () => {
  let finish
  const pending = new Promise((resolve) => {
    finish = resolve
  })
  let settled = false
  const result = waitForRegistrationCompletion([Promise.resolve(true), pending], 500).then(
    (value) => {
      settled = true
      return value
    }
  )
  await new Promise((resolve) => globalThis.setImmediate(resolve))
  assert.equal(settled, false)
  finish(true)
  assert.equal(await result, true)
})

test("failed or missing request completion remains unverified", async () => {
  assert.equal(await waitForRegistrationCompletion([], 100), false)
  assert.equal(await waitForRegistrationCompletion([Promise.resolve(true)], 0), false)
  assert.equal(await waitForRegistrationCompletion([Promise.resolve(false)], 100), false)
  const failedRequest = Promise.reject(new Error("private transport"))
  void failedRequest.catch(() => undefined)
  assert.equal(await waitForRegistrationCompletion([failedRequest], 100), false)
  assert.equal(await waitForRegistrationCompletion([new Promise(() => {})], 10), false)
})

test("every required registration step is mandatory and unique", () => {
  for (const step of REGISTRATION_STEP_ORDER) {
    const missing = REGISTRATION_STEP_ORDER.filter((entry) => entry !== step)
    assert.ok(registrationTraceViolations(missing, 1).includes(`missing ${step}`))
    assert.ok(
      registrationTraceViolations([...REGISTRATION_STEP_ORDER, step], 1).includes(
        `duplicate ${step}`
      )
    )
  }
})

test("every inverted registration step pair is rejected", () => {
  for (let left = 0; left < REGISTRATION_STEP_ORDER.length; left += 1) {
    for (let right = left + 1; right < REGISTRATION_STEP_ORDER.length; right += 1) {
      const trace = [...REGISTRATION_STEP_ORDER]
      ;[trace[left], trace[right]] = [trace[right], trace[left]]
      assert.ok(
        registrationTraceViolations(trace, 1).includes(
          `${REGISTRATION_STEP_ORDER[right]} before ${REGISTRATION_STEP_ORDER[left]}`
        )
      )
    }
  }
})

test("registration count accepts only the integer one", () => {
  for (const count of [-1, 0, 2, 1.5, Number.NaN, Infinity, "1", null, undefined]) {
    assert.ok(registrationTraceViolations([...REGISTRATION_STEP_ORDER], count).length > 0)
  }
})
