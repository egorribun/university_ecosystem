import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { EventEmitter } from "node:events"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import { performance } from "node:perf_hooks"
import process from "node:process"
import test from "node:test"
import { clearTimeout, setImmediate, setTimeout } from "node:timers"
import { URL } from "node:url"
import { runInNewContext } from "node:vm"
import ts from "typescript"
import { readPlaywrightTestSlotDeadlineAtMs } from "../../scripts/live-registration-admission.mjs"

const helper = new URL("./push-recipient-observation.mjs", import.meta.url)
const owner = "11111111-1111-4111-8111-111111111111"
const other = "22222222-2222-4222-8222-222222222222"
const privateEndpoint = "https://push.example.invalid/private-token"

async function create(options = {}) {
  assert.ok(existsSync(helper), "the bounded push recipient observer exists")
  const { createPushRecipientObservation } = await import(helper.href)
  const context = new EventEmitter()
  const output = []
  const page = {
    context: () => context,
    evaluate: async (fn, value) => {
      options.onEvaluate?.()
      if (options.evaluationFails) throw new Error("private evaluation")
      const prior = Object.getOwnPropertyDescriptor(globalThis, "navigator")
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: {
          serviceWorker: {
            getRegistration: async () => {
              if (options.registrationHangs) return new Promise(() => {})
              if (options.registrationFails) throw new Error("private failure")
              if (options.registrationMissing) return undefined
              return {
                pushManager: {
                  getSubscription: async () =>
                    options.currentEndpoint === null
                      ? null
                      : { endpoint: options.currentEndpoint ?? privateEndpoint },
                },
              }
            },
          },
        },
      })
      try {
        return await fn(value)
      } finally {
        if (prior === undefined) delete globalThis.navigator
        else Object.defineProperty(globalThis, "navigator", prior)
      }
    },
  }
  const observer = createPushRecipientObservation(
    page,
    options.origin ?? "https://owned.example.invalid",
    options.project ?? "mobile",
    options.retry ?? 0,
    options.useDefaultSink ? undefined : (options.emit ?? ((line) => output.push(line)))
  )
  observer.arm("news", owner)
  return { context, observer, output }
}

function request({ url = "https://owned.example.invalid/api/v1/users/me", worker = true } = {}) {
  return { url: () => url, method: () => "GET", serviceWorker: () => (worker ? {} : null) }
}

async function respond(context, requestObject, status, body) {
  context.emit("request", requestObject)
  context.emit("response", {
    request: () => requestObject,
    status: () => status,
    json: async () => body,
  })
  await new Promise((resolve) => setImmediate(resolve))
}

test("observes only service-worker identity checks and emits classes without private data", async () => {
  const { context, observer, output } = await create()
  await respond(context, request({ worker: false }), 200, { id: other })
  await respond(context, request({ url: "https://elsewhere.invalid/api/v1/users/me" }), 200, {
    id: other,
  })
  await respond(context, request(), 200, {
    id: owner,
    email: "private-user",
    token: "private-token",
  })
  await observer.report(privateEndpoint)
  assert.deepEqual(output, [
    "UE_LIVE_PUSH_RECIPIENT_V1 project=mobile retry=0 scenario=news check=session-owner-match subscription=same\n",
  ])
  assert.doesNotMatch(output.join(""), /private|11111111|22222222|example\.invalid/u)
  observer.dispose()
  assert.equal(context.listenerCount("request"), 0)
})

test("distinguishes suppressions, response errors, missing checks, and endpoint rotation", async () => {
  for (const [status, body, expected] of [
    [403, {}, "auth"],
    [200, { id: other }, "session-owner-mismatch"],
    [200, { id: "bad" }, "invalid"],
    [200, null, "invalid"],
    [500, {}, "other"],
  ]) {
    const { context, observer, output } = await create({
      currentEndpoint: "https://push.example.invalid/changed",
    })
    await respond(context, request(), status, body)
    await observer.report(privateEndpoint)
    assert.match(output[0], new RegExp(`check=${expected} subscription=changed\\n$`, "u"))
    observer.dispose()
  }
  const { observer, output } = await create({ currentEndpoint: null })
  await observer.report(privateEndpoint)
  assert.match(output[0], /check=none subscription=missing\n$/u)
  observer.dispose()
})

test("does not attribute a prior scenario's late response to a later scenario", async () => {
  const { context, observer, output } = await create()
  const previous = request()
  context.emit("request", previous)
  observer.arm("events", owner)
  context.emit("response", { request: () => previous, status: () => 403, json: async () => ({}) })
  await observer.report(privateEndpoint)
  assert.match(output[0], /scenario=events check=none subscription=same\n$/u)
  observer.dispose()
})

test("reports ambiguous multiple requests and failed requests without their details", async () => {
  const { context, observer, output } = await create()
  const first = request()
  context.emit("request", first)
  context.emit("request", request())
  context.emit("response", { request: () => first, status: () => 403, json: async () => ({}) })
  await observer.report(privateEndpoint)
  assert.match(output[0], /check=multiple subscription=same\n$/u)
  observer.arm("events", owner)
  const failed = request()
  context.emit("request", failed)
  context.emit("requestfailed", failed)
  await observer.report(privateEndpoint)
  assert.match(output[1], /check=network subscription=same\n$/u)
  observer.dispose()
})

test("waits within the observation budget for an in-flight response body", async () => {
  const { context, observer, output } = await create()
  const pending = request()
  let resolveBody
  const body = new Promise((resolve) => {
    resolveBody = resolve
  })
  context.emit("request", pending)
  context.emit("response", { request: () => pending, status: () => 200, json: () => body })
  const reporting = observer.report(privateEndpoint)
  setImmediate(() => resolveBody({ id: owner }))
  await reporting
  assert.match(output[0], /check=session-owner-match subscription=same\n$/u)
  observer.dispose()
})

test("waits for an already-started identity request to receive headers or fail", async () => {
  for (const [kind, expected] of [
    ["response", "auth"],
    ["failure", "network"],
  ]) {
    const { context, observer, output } = await create()
    const pending = request()
    context.emit("request", pending)
    const reporting = observer.report(privateEndpoint, 200)
    setImmediate(() => {
      if (kind === "response") {
        context.emit("response", { request: () => pending, status: () => 403 })
      } else {
        context.emit("requestfailed", pending)
      }
    })
    await reporting
    assert.match(output[0], new RegExp(`check=${expected} subscription=same\\n$`, "u"))
    observer.dispose()
  }
})

test("the shared test-slot budget preserves cleanup time and fails closed", async () => {
  const [fixture, shared] = await Promise.all([
    readFile(new URL("./native-push-profile-fixtures.ts", import.meta.url), "utf8"),
    readFile(new URL("./fixtures.ts", import.meta.url), "utf8"),
  ])
  const budget = fixture.match(/export function livePushObservationBudgetMs\([\s\S]*?^\}/mu)?.[0]
  const timeout = shared.match(/export function liveDeadlineBoundedTimeoutMs\([\s\S]*?^\}/mu)?.[0]
  assert.ok(budget && timeout)
  const reserve = fixture.match(/const PROFILE_CLEANUP_TIMEOUT_MS = [\d_]+/u)?.[0]
  const margin = shared.match(/const LIVE_OWNED_CLEANUP_OPERATION_MARGIN_MS = [\d_]+/u)?.[0]
  assert.ok(reserve && margin)
  const compiled = ts.transpileModule(`${reserve}\n${margin}\n${timeout}\n${budget}`, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText
  const module = { exports: {} }
  let failAdapter = false
  let adapterCalls = 0
  runInNewContext(compiled, {
    module,
    exports: module.exports,
    performance: { now: () => 1000 },
    readPlaywrightTestSlotDeadlineAtMs: (info) => {
      if (failAdapter) {
        adapterCalls += 1
        throw new Error("private adapter failure")
      }
      return readPlaywrightTestSlotDeadlineAtMs(info, undefined, () => ({
        localBeforeMs: 1000,
        playwrightNowMs: 1000,
        localAfterMs: 1000,
      }))
    },
  })
  const { livePushObservationBudgetMs } = module.exports
  const slot = (timeout, remaining) => ({
    timeout,
    _deadline: () => ({ timeout, deadline: 1000 + remaining }),
  })
  assert.equal(livePushObservationBudgetMs(null), 0)
  assert.equal(livePushObservationBudgetMs(slot(180_000, 30_250)), 0)
  assert.equal(livePushObservationBudgetMs(slot(180_000, 30_751)), 501)
  assert.equal(livePushObservationBudgetMs(slot(180_000, 60_000)), 1200)
  assert.equal(livePushObservationBudgetMs(slot(360_000, 45_250), 45_000), 0)
  assert.equal(livePushObservationBudgetMs(slot(360_000, 60_000), 45_000), 1200)
  assert.equal(livePushObservationBudgetMs(slot(360_001, 60_000)), 0)
  assert.equal(livePushObservationBudgetMs(slot(180_000, 60_000), Number.NaN), 0)

  failAdapter = true
  assert.equal(livePushObservationBudgetMs(slot(180_000, 60_000)), 0)
  assert.equal(adapterCalls, 1)
})

test("a second request during capture resolves as multiple", async () => {
  const { context, observer, output } = await create()
  context.emit("request", request())
  let completed = false
  const reporting = observer.report(privateEndpoint).then(() => {
    completed = true
  })
  setImmediate(() => context.emit("request", request()))
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(completed, true)
  await reporting
  assert.match(output[0], /check=multiple subscription=same\n$/u)
  observer.dispose()
})

test("completed checks and near-expired slots do not spend the observation budget", async () => {
  for (const withResponse of [false, true]) {
    let evaluations = 0
    const { context, observer, output } = await create({
      onEvaluate: () => {
        evaluations += 1
      },
    })
    if (withResponse) await respond(context, request(), 200, { id: owner })
    else context.emit("request", request())
    let completed = false
    const reporting = observer.report(privateEndpoint, withResponse ? 1200 : 0).then(() => {
      completed = true
    })
    await new Promise((resolve) => setImmediate(resolve))
    assert.equal(completed, true)
    await reporting
    assert.match(
      output[0],
      withResponse ? /check=session-owner-match/u : /check=pending subscription=unavailable/u
    )
    assert.equal(evaluations, withResponse ? 1 : 0)
    observer.dispose()
  }
})

test("a body failure after request failure retains the network class", async () => {
  const { context, observer, output } = await create()
  const pending = request()
  let rejectBody
  const body = new Promise((_, reject) => {
    rejectBody = reject
  })
  context.emit("request", pending)
  context.emit("response", { request: () => pending, status: () => 200, json: () => body })
  await Promise.resolve()
  const reporting = observer.report(privateEndpoint)
  context.emit("requestfailed", pending)
  rejectBody(new Error("private response"))
  await reporting
  await new Promise((resolve) => setImmediate(resolve))
  assert.match(output[0], /check=network subscription=same\n$/u)
  assert.doesNotMatch(output[0], /private/u)
  observer.dispose()
})

test("a stalled identity request is bounded and a late body rejection stays private", async () => {
  const { context, observer, output } = await create()
  const pending = request()
  context.emit("request", pending)
  const started = performance.now()
  let guard
  try {
    await Promise.race([
      observer.report(privateEndpoint),
      new Promise((_, reject) => {
        guard = setTimeout(() => reject(new Error("observation exceeded its host budget")), 5000)
      }),
    ])
  } finally {
    clearTimeout(guard)
  }
  assert.ok(performance.now() - started >= 1000)
  assert.match(output[0], /check=pending subscription=same\n$/u)
  context.emit("response", {
    request: () => pending,
    status: () => 200,
    json: async () => {
      throw new Error("private response")
    },
  })
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(output.length, 1)
  assert.doesNotMatch(output[0], /private|example\.invalid/u)
  observer.dispose()
})

test("topic opt-in verifies endpoint equality without printing either endpoint on failure", async () => {
  const spec = await readFile(
    new URL("./notification-topics-delivery.live.spec.ts", import.meta.url),
    "utf8"
  )
  assert.match(spec, /nativeEndpoint\s*===\s*subscriptionReceipt\.endpoint[\s\S]*?toBe\(true\)/u)
  assert.doesNotMatch(spec, /expect\(\s*nativeEndpoint\s*[,)]/u)
})

test("chat failure paths report before disposal without duplicating a captured record", async () => {
  const spec = await readFile(new URL("./push-delivery.live.spec.ts", import.meta.url), "utf8")
  for (const scenario of [
    "chat message reaches Chromium through its real push subscription",
    "quoted group author gets one chat.reply push with group context and no generic duplicate",
  ]) {
    const start = spec.indexOf(`test("${scenario}"`)
    assert.ok(start >= 0)
    const next = spec.indexOf('\ntest("', start + 1)
    const source = spec.slice(start, next < 0 ? undefined : next)
    assert.match(
      source,
      /catch \(error\) \{[\s\S]*?await failureObservation\?\.capture\(\)\s*await recipientObservation\.report\(subscriptionEndpoint, livePushObservationBudgetMs\(testInfo\)\)\s*\}\s*recipientObservation\.dispose\(\)/u
    )
  }

  const { observer, output } = await create()
  observer.arm("chat", owner)
  const beforeCapture = undefined
  await beforeCapture?.capture()
  await observer.report(privateEndpoint)
  assert.equal(output.length, 1)
  assert.match(output[0], /scenario=chat check=none subscription=same\n$/u)

  observer.arm("reply", owner)
  const capture = { capture: () => observer.report(privateEndpoint) }
  await capture.capture()
  await observer.report(privateEndpoint)
  assert.equal(output.length, 2)
  assert.match(output[1], /scenario=reply check=none subscription=same\n$/u)
  observer.dispose()
})

test("both live specs preserve cleanup time while keeping the existing browser diagnostic", async () => {
  const [chat, topics, fixture] = await Promise.all([
    readFile(new URL("./push-delivery.live.spec.ts", import.meta.url), "utf8"),
    readFile(new URL("./notification-topics-delivery.live.spec.ts", import.meta.url), "utf8"),
    readFile(new URL("./native-push-profile-fixtures.ts", import.meta.url), "utf8"),
  ])
  assert.equal(
    chat.match(
      /recipientObservation\.report\(subscriptionEndpoint, livePushObservationBudgetMs\(testInfo\)\)/gu
    )?.length,
    4
  )
  assert.match(
    topics,
    /recipientObservation\.report\(\s*subscriptionEndpoint,\s*livePushObservationBudgetMs\(testInfo, SCHEDULE_CLEANUP_WAIT_TIMEOUT_MS\)\s*\)/u
  )
  assert.match(topics, /nativePushProfiles\.armFailureObservation\(notificationId/u)
  assert.match(topics, /timeout: SCHEDULE_CLEANUP_WAIT_TIMEOUT_MS/u)
  assert.match(
    fixture,
    /createLivePushFailureObservation\(async \(\) => \{[\s\S]*?await Promise\.all\(\[\s*reportLivePushDeliveryObservation[\s\S]*?onCapture\?\.\(\),?\s*\]\)/u
  )
})

test("recipient capture runs alongside the established browser observation", async () => {
  const fixture = await readFile(
    new URL("./native-push-profile-fixtures.ts", import.meta.url),
    "utf8"
  )
  const start = fixture.indexOf("const observation = createLivePushFailureObservation(")
  const end = fixture.indexOf("pendingFailureObservation = observation", start)
  assert.ok(start >= 0 && end > start)
  const compiled = ts.transpileModule(fixture.slice(start, end) + "\nobservation", {
    compilerOptions: { module: ts.ModuleKind.None },
  }).outputText
  const started = []
  let releaseBrowser
  let releaseRecipient
  const observe = runInNewContext(compiled, {
    createLivePushFailureObservation: (fn) => fn,
    reportLivePushDeliveryObservation: () => {
      started.push("browser")
      return new Promise((resolve) => {
        releaseBrowser = resolve
      })
    },
    onCapture: () => {
      started.push("recipient")
      return new Promise((resolve) => {
        releaseRecipient = resolve
      })
    },
    primary: { page: {} },
    testInfo: { project: { name: "mobile" } },
    expectedTag: "private",
  })
  let done = false
  const capture = observe().then(() => {
    done = true
  })
  assert.deepEqual(started, ["browser", "recipient"])
  releaseBrowser()
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(done, false)
  releaseRecipient()
  await capture
  assert.equal(done, true)
})

test("unreadable responses and missing or failing registrations remain bounded", async () => {
  for (const options of [
    { registrationMissing: true },
    { registrationFails: true },
    { evaluationFails: true },
  ]) {
    const { context, observer, output } = await create(options)
    const pending = request()
    context.emit("request", pending)
    context.emit("response", {
      request: () => pending,
      status: () => 200,
      json: async () => {
        throw new Error("private response")
      },
    })
    await observer.report(privateEndpoint)
    assert.match(output[0], /check=unreadable subscription=unavailable\n$/u)
    observer.dispose()
  }
})

test("ignores invalid inputs and contains malformed events and a broken sink", async () => {
  const invalid = await create({ origin: "invalid-origin" })
  invalid.context.emit("request", request())
  await invalid.observer.report(privateEndpoint, Number.NaN)
  assert.match(invalid.output[0], /check=none subscription=unavailable\n$/u)
  invalid.observer.dispose()

  const { context, observer } = await create({
    emit: () => {
      throw new Error("private sink")
    },
  })
  context.emit("request", {
    serviceWorker: () => {
      throw new Error("private request")
    },
  })
  context.emit("response", {
    request: () => {
      throw new Error("private response")
    },
  })
  const tracked = request()
  context.emit("request", tracked)
  context.emit("response", {
    request: () => tracked,
    status: () => {
      throw new Error("private response")
    },
  })
  await observer.report(privateEndpoint)
  await observer.report(privateEndpoint)
  observer.dispose()

  for (const options of [{ project: "private" }, { retry: 2 }]) {
    const attempt = await create(options)
    await attempt.observer.report(privateEndpoint)
    assert.deepEqual(attempt.output, [])
    attempt.observer.dispose()
  }
})

test("rejects invalid scenario and owner values without exposing them", async () => {
  const { context, observer, output } = await create()
  observer.arm("private scenario", owner)
  await observer.report(privateEndpoint)
  assert.deepEqual(output, [])
  observer.arm("reply", "private owner")
  await respond(context, request(), 200, { id: owner })
  await observer.report(privateEndpoint)
  assert.match(output[0], /scenario=reply check=invalid subscription=same\n$/u)
  assert.doesNotMatch(output[0], /private|11111111/u)
  observer.dispose()
})

test("a late response remains ambiguous after a second matching request", async () => {
  const { context, observer, output } = await create()
  const first = request()
  let resolveBody
  const body = new Promise((resolve) => {
    resolveBody = resolve
  })
  context.emit("request", first)
  context.emit("response", { request: () => first, status: () => 200, json: () => body })
  context.emit("request", request())
  resolveBody({ id: owner })
  await observer.report(privateEndpoint)
  assert.match(output[0], /check=multiple subscription=same\n$/u)
  observer.dispose()
})

test("a stalled browser inspection respects a reduced budget without exposing the endpoint", async () => {
  const { observer, output } = await create({ registrationHangs: true })
  const started = performance.now()
  await observer.report(privateEndpoint, 25)
  assert.ok(performance.now() - started >= 10)
  assert.match(output[0], /check=none subscription=unavailable\n$/u)
  assert.doesNotMatch(output[0], /private|example\.invalid/u)
  observer.dispose()
})

test("the default sink writes only the closed observation record", async () => {
  const { observer } = await create({ useDefaultSink: true })
  const write = process.stdout.write
  const records = []
  process.stdout.write = function (chunk, ...args) {
    if (typeof chunk === "string" && chunk.startsWith("UE_LIVE_PUSH_RECIPIENT_V1 ")) {
      records.push(chunk)
      return true
    }
    return write.call(this, chunk, ...args)
  }
  try {
    await observer.report(privateEndpoint)
  } finally {
    process.stdout.write = write
    observer.dispose()
  }
  assert.equal(records.length, 1)
  assert.match(records[0], /^UE_LIVE_PUSH_RECIPIENT_V1 project=mobile .* subscription=same\n$/u)
  assert.doesNotMatch(records[0], /private|\.invalid|11111111/u)
})

test("record output stops at the finite worker cap", async () => {
  const { observer, output } = await create()
  for (let index = 0; index < 40; index += 1) {
    observer.arm("news", owner)
    await observer.report(privateEndpoint)
  }
  assert.ok(output.length > 0 && output.length <= 32)
  const observed = output.length
  observer.arm("news", owner)
  await observer.report(privateEndpoint)
  assert.equal(output.length, observed)
  observer.dispose()
})

const helperUrl = new URL("./push-delivery-observation.ts", import.meta.url)
const specUrl = new URL("./push-delivery.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./native-push-profile-fixtures.ts", import.meta.url)

function runChild(childSource) {
  const result = spawnSync(process.execPath, ["--input-type=module", "--eval", childSource], {
    encoding: "utf8",
  })
  assert.equal(result.status, 0, "the diagnostic must not throw")
  assert.equal(result.stderr, "", "the diagnostic writes no raw errors to stderr")
  return result.stdout
}

function reportInChild(calls) {
  return runChild(
    "import { reportLivePushDeliveryObservation } from " +
      JSON.stringify(helperUrl.href) +
      ";\n" +
      calls
  )
}

const DEFAULT_SUBSCRIBE = "async () => ({ unsubscribe: async () => { log.unsubscribed += 1 } })"

// Builds a child that runs the real helper against a fake browser realm. The probe's
// 15 s budget is shortened to 20 ms inside the realm so timeout cases finish quickly.
function probeChild({
  permission = "granted",
  registered = true,
  subscription = "null",
  subscribe = DEFAULT_SUBSCRIBE,
  phase = "report",
  notifications = "[]",
} = {}) {
  const call =
    phase === "subscribe"
      ? "await awaitPushSubscribeWithObservation(Promise.reject(new Error('save failed')), page, 'desktop').catch(() => {});\n"
      : "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n"
  const registration = registered
    ? "{ active: { state: 'activated' }, getNotifications: async () => " +
      notifications +
      ", pushManager: { " +
      "getSubscription: async () => " +
      subscription +
      ", subscribe: async (options) => { log.subscribeCalls += 1; " +
      "log.userVisibleOnly = options.userVisibleOnly; log.keyLength = options.applicationServerKey.length; " +
      "log.keyFirst = options.applicationServerKey[0]; return subscribeImpl(options); } } }"
    : "undefined"
  return (
    "import { createContext, runInContext } from 'node:vm';\n" +
    "import { awaitPushSubscribeWithObservation, reportLivePushDeliveryObservation } from " +
    JSON.stringify(helperUrl.href) +
    ";\n" +
    "const log = { subscribeCalls: 0, unsubscribed: 0, userVisibleOnly: null, keyLength: 0, keyFirst: -1 };\n" +
    "const subscribeImpl = (" +
    subscribe +
    ");\n" +
    "const registration = " +
    registration +
    ";\n" +
    "const ctx = createContext({ Notification: { permission: " +
    JSON.stringify(permission) +
    " }, atob: (value) => Buffer.from(value, 'base64').toString('binary'), " +
    "window: { setTimeout: (callback, delay, ...args) => setTimeout(callback, delay === 15000 ? 20 : delay, ...args), " +
    "clearTimeout: (timer) => clearTimeout(timer) }, " +
    "navigator: { serviceWorker: { controller: null, ready: Promise.resolve(registration), " +
    "getRegistration: async () => registration } } });\n" +
    "const page = { evaluate: async (fn, options) => runInContext('(' + fn.toString() + ')(' + " +
    "JSON.stringify(options ?? null) + ')', ctx) };\n" +
    call +
    "process.stdout.write('LOG ' + JSON.stringify(log) + '\\n');\n"
  )
}

function runProbeChild(options) {
  const output = runChild(probeChild(options))
  const newline = output.indexOf("\n")
  const record = output.slice(0, newline + 1)
  const log = JSON.parse(
    output
      .slice(newline + 1)
      .replace(/^LOG /u, "")
      .trim()
  )
  return { output, record, log }
}

test("failure observation is captured before cleanup around each unchanged native poll", async () => {
  const [spec, helper, fixture] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(helperUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
  ])
  const scenarios = [
    {
      declaration: 'test("chat message reaches Chromium through its real push subscription"',
      expected: "const expectedNotificationId = notificationId",
    },
    {
      declaration: 'test("quoted group author gets one chat.reply push',
      expected: "const expectedNotificationId = replyNotificationId",
    },
  ]
  for (const { declaration, expected } of scenarios) {
    const start = spec.indexOf(declaration)
    assert.ok(start >= 0)
    const next = spec.indexOf('\ntest("', start + declaration.length)
    const scenario = spec.slice(start, next < 0 ? undefined : next)
    const pollStart = scenario.indexOf(expected)
    const armIndex = scenario.indexOf(
      "failureObservation = nativePushProfiles.armFailureObservation(expectedNotificationId,",
      pollStart
    )
    const timeoutIndex = scenario.indexOf("timeout: 60_000", armIndex)
    const pollSuccess = scenario.indexOf(".toBe(1)", timeoutIndex)
    const disarmIndex = scenario.indexOf("failureObservation.disarm()", pollSuccess)
    const catchIndex = scenario.indexOf("} catch (error) {", disarmIndex)
    const captureIndex = scenario.indexOf("await failureObservation?.capture()", catchIndex)
    const unsubscribeIndex = scenario.indexOf(
      "unsubscribeOnlyNativeSubscription(page, subscriptionEndpoint)",
      captureIndex
    )
    assert.ok(pollStart >= 0 && armIndex > pollStart)
    assert.ok(timeoutIndex > armIndex && pollSuccess > timeoutIndex && disarmIndex > pollSuccess)
    assert.ok(catchIndex > disarmIndex && captureIndex > catchIndex)
    assert.ok(unsubscribeIndex > captureIndex)
    assert.match(scenario.slice(armIndex, disarmIndex), /expect\s*\.\s*poll/u)
    assert.doesNotMatch(scenario.slice(armIndex, disarmIndex), /catch\s*\(/u)
  }
  assert.doesNotMatch(spec, /reportLivePushDeliveryObservation/u)
  assert.match(helper, /normalizeObservation\(\s*await observe/u)

  const teardownCapture = fixture.indexOf(
    "await pendingFailureObservation?.captureIfAborted(testInfo.status)"
  )
  const profileVerification = fixture.indexOf("verifyProfileBeforeRemoval(record)", teardownCapture)
  assert.ok(teardownCapture >= 0 && profileVerification > teardownCapture)
  assert.match(
    fixture,
    /reportLivePushDeliveryObservation\(\s*primary\.page,\s*testInfo\.project\.name,\s*expectedTag\s*\)/u
  )
  assert.match(fixture, /if \(pendingFailureObservation\?\.isArmed\(\)\) \{[\s\S]*already armed/u)
  assert.match(helper, /HOST_CAPTURE_DEADLINE_MS = 1_600/u)
  assert.match(helper, /BROWSER_OBSERVATION_BUDGET_MS = 1_200/u)
  assert.match(helper, /PROBE_BUDGET_MS = 15_000/u)
  assert.match(helper, /HOST_CAPTURE_DEADLINE_MS \+ \(probeSubscribe \? PROBE_BUDGET_MS : 0\)/u)
  assert.match(helper, /navigator\.serviceWorker\.ready/u)
  assert.match(helper, /navigator\.serviceWorker\.getRegistration\(\)/u)
  assert.match(helper, /registration\.getNotifications\(\)/u)
  assert.match(helper, /Notification\.permission/u)
  assert.match(helper, /if \(typeof Notification === "undefined"\) return "unsupported"/u)
  assert.match(helper, /if \(capturedPermission === null\) return null/u)
  assert.match(helper, /navigator\.serviceWorker\.controller !== null/u)
  assert.match(helper, /registration\.pushManager\.getSubscription\(\)/u)
  assert.match(helper, /const notifications = notificationsResult\.value/u)
  assert.match(helper, /matches = notifications\.some[\s\S]*?\? 1\s*:\s*0/u)
  assert.match(helper, /shown = count >= 3 \? 3 : count === 2 \? 2 : count === 1 \? 1 : 0/u)
  assert.match(
    helper,
    /untagged = notifications\.some\(\(notification\) => notification\.tag === ""\) \? 1 : 0/u
  )
  assert.match(helper, /MAX_RECORDS = 4/u)
  assert.match(helper, /notification\.tag === expectedTag/u)
  assert.doesNotMatch(
    helper,
    /\bfetch\s*\(|\brequest\s*\(|\.locator\s*\(|new URL|\.endpoint\b|\.body\b|\.title\b|process\.stderr/u
  )
})

test("concurrent failure and abort captures share a pre-cleanup observation", () => {
  const output = runChild(`
    import assert from "node:assert/strict"
    import { createLivePushFailureObservation } from ${JSON.stringify(helperUrl.href)}
    const events = []
    let release
    const gate = new Promise((resolve) => { release = resolve })
    const handle = createLivePushFailureObservation(async () => {
      events.push("capture-start")
      await gate
      events.push("capture-end")
    })
    assert.equal(handle.isArmed(), true)
    const body = handle.capture()
    const abort = handle.captureIfAborted("timedOut")
    let bodyDone = false
    let abortDone = false
    body.then(() => { bodyDone = true })
    abort.then(() => { abortDone = true })
    await Promise.resolve()
    assert.deepEqual(events, ["capture-start"])
    assert.equal(handle.isArmed(), true)
    assert.equal(bodyDone, false)
    assert.equal(abortDone, false)
    release()
    await Promise.all([body, abort])
    events.push("unsubscribe", "delete")
    assert.deepEqual(events, ["capture-start", "capture-end", "unsubscribe", "delete"])
    assert.equal(handle.isArmed(), false)
    await handle.capture()
    assert.equal(events.length, 4)
  `)
  assert.equal(output, "")
})

test("diagnostic rejection is contained and never replaces the original failure", () => {
  const output = runChild(`
    import assert from "node:assert/strict"
    import { createLivePushFailureObservation } from ${JSON.stringify(helperUrl.href)}
    let calls = 0
    const original = new Error("original-test-failure")
    const handle = createLivePushFailureObservation(async () => {
      calls += 1
      throw new Error("private-diagnostic-error")
    })
    let caught
    try {
      try { throw original } catch (error) { await handle.capture(); throw error }
    } catch (error) { caught = error }
    await handle.capture()
    assert.equal(caught, original)
    assert.equal(calls, 1)
    assert.equal(handle.isArmed(), false)
  `)
  assert.equal(output, "")
})

test("teardown observes only aborted tests and respects a disarmed poll", () => {
  const output = runChild(`
    import assert from "node:assert/strict"
    import { createLivePushFailureObservation } from ${JSON.stringify(helperUrl.href)}
    let calls = 0
    const handle = createLivePushFailureObservation(async () => { calls += 1 })
    for (const status of ["passed", "failed", "skipped", "unknown", null]) {
      await handle.captureIfAborted(status)
    }
    assert.equal(calls, 0)
    assert.equal(handle.isArmed(), true)
    await handle.captureIfAborted("timedOut")
    await handle.captureIfAborted("interrupted")
    assert.equal(calls, 1)
    const interrupted = createLivePushFailureObservation(async () => { calls += 1 })
    await interrupted.captureIfAborted("interrupted")
    assert.equal(calls, 2)
    const disarmed = createLivePushFailureObservation(async () => { calls += 1 })
    disarmed.disarm()
    assert.equal(disarmed.isArmed(), false)
    await disarmed.capture()
    await disarmed.captureIfAborted("timedOut")
    assert.equal(calls, 2)
  `)
  assert.equal(output, "")
})

test("push observation emits only bounded closed browser state and never the notification identity", () => {
  const privateId = "private-notification-identity"
  const output = reportInChild(
    "let evaluations = 0;\n" +
      "const page = { evaluate: async (probe, options) => {\n" +
      "  evaluations += 1;\n" +
      "  if (evaluations === 1) return 'granted';\n" +
      "  if (typeof probe !== 'function' || !options || options.expectedTag !== " +
      JSON.stringify(privateId) +
      " || options.budgetMs !== 1200 || options.permission !== 'granted') " +
      "throw new Error('private-probe-failure');\n" +
      "  return { permission: options.permission, ready: 'resolved', state: 'activated', " +
      "controller: true, subscription: true, matches: 0, shown: 0, untagged: 0, probe: 'skipped' };\n" +
      "} };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', " +
      JSON.stringify(privateId) +
      ");\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V2 project=desktop permission=granted ready=resolved " +
      "state=activated controller=1 subscription=1 matches=0 shown=0 untagged=0 probe=skipped\n"
  )
  assert.doesNotMatch(output, /private-notification-identity|private-probe-failure/u)
})

test("push observation snapshots accessor values once before formatting", () => {
  const output = reportInChild(
    "let permissionReads = 0;\n" +
      "let evaluations = 0;\n" +
      "const changing = { get permission() { permissionReads += 1; " +
      "return permissionReads === 1 ? 'granted' : 'private-value'; }, " +
      "ready: 'resolved', state: 'activated', controller: true, " +
      "subscription: true, matches: 1, shown: 0, untagged: 0, probe: 'skipped' };\n" +
      "const page = { evaluate: async () => { evaluations += 1; " +
      "return evaluations === 1 ? 'granted' : changing; } };\n" +
      "await reportLivePushDeliveryObservation(page, 'mobile', 'private-id');\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V2 project=mobile permission=granted ready=resolved " +
      "state=activated controller=1 subscription=1 matches=1 shown=0 untagged=0 probe=skipped\n"
  )
  assert.doesNotMatch(output, /private-value|private-id/u)
})
test("push observation rejects invalid domains and private values without coercion", () => {
  const output = reportInChild(
    "const page = { evaluate: async () => ({ permission: 'granted', ready: 'resolved', " +
      "state: 'activated', controller: true, subscription: true, matches: 0, shown: 0, untagged: 0, probe: 'skipped' }) };\n" +
      "const privateValue = { toString() { throw new Error('private-value'); } };\n" +
      "await reportLivePushDeliveryObservation(page, 'private-project', 'private-id');\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', privateValue);\n" +
      "let invalidEvaluations = 0;\n" +
      "const invalidPage = { evaluate: async () => { invalidEvaluations += 1; " +
      "return invalidEvaluations === 1 ? 'granted' : ({ permission: privateValue, " +
      "ready: 'resolved', state: 'activated', controller: true, subscription: true, matches: 2, shown: 0, untagged: 0, probe: 'skipped' }); } };\n" +
      "await reportLivePushDeliveryObservation(invalidPage, 'mobile', 'private-id');\n" +
      "let probeEvaluations = 0;\n" +
      "const invalidProbePage = { evaluate: async () => { probeEvaluations += 1; " +
      "return probeEvaluations === 1 ? 'granted' : ({ permission: 'granted', ready: 'resolved', " +
      "state: 'activated', controller: true, subscription: true, matches: 0, shown: 0, untagged: 0, probe: 'private-probe' }); } };\n" +
      "await reportLivePushDeliveryObservation(invalidProbePage, 'desktop', 'private-id');\n"
  )
  assert.equal(output, "")
  assert.doesNotMatch(output, /private-value|private-id|private-probe/u)
})

test("push observation deduplicates and caps output at four records", () => {
  const output = reportInChild(
    "const permissions = ['default', 'granted', 'denied', 'unsupported', 'default'];\n" +
      "let evaluations = 0;\n" +
      "const page = { evaluate: async (_probe, options) => { evaluations += 1; " +
      "if (evaluations % 2 === 1) return permissions[(evaluations - 1) / 2]; " +
      "return { permission: options.permission, ready: 'timeout', state: 'missing', " +
      "controller: false, subscription: false, matches: 0, shown: 0, untagged: 0, probe: 'skipped' }; } };\n" +
      "for (const permission of permissions) await reportLivePushDeliveryObservation(page, 'mobile', permission);\n"
  )
  assert.equal(
    output,
    [
      "UE_LIVE_PUSH_OBS_V2 project=mobile permission=default ready=timeout state=missing controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=skipped\n",
      "UE_LIVE_PUSH_OBS_V2 project=mobile permission=granted ready=timeout state=missing controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=skipped\n",
      "UE_LIVE_PUSH_OBS_V2 project=mobile permission=denied ready=timeout state=missing controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=skipped\n",
      "UE_LIVE_PUSH_OBS_V2 project=mobile permission=unsupported ready=timeout state=missing controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=skipped\n",
    ].join("")
  )
})

test("push observation omits a record when permission cannot be captured", () => {
  const output = reportInChild(
    "const page = { evaluate: async () => { throw new Error('private URL and token'); } };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n"
  )
  assert.equal(output, "")
  assert.doesNotMatch(output, /private|token|unsupported/u)
})

test("push observation reports unsupported when Notification is absent", () => {
  const output = reportInChild(
    "const { runInNewContext } = await import('node:vm');\n" +
      "const page = { evaluate: async (probe, options) => runInNewContext(" +
      "'(' + probe.toString() + ')(' + JSON.stringify(options) + ')', { navigator: {} }) };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V2 project=desktop permission=unsupported ready=error " +
      "state=missing controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=skipped\n"
  )
})

test("push observation preserves captured permission when host capture times out", () => {
  const output = reportInChild(
    "const originalSetTimeout = globalThis.setTimeout;\n" +
      "const originalClearTimeout = globalThis.clearTimeout;\n" +
      "globalThis.setTimeout = (callback, delay, ...args) => {\n" +
      "  if (delay !== 1600) return originalSetTimeout(callback, delay, ...args);\n" +
      "  queueMicrotask(() => queueMicrotask(() => callback(...args)));\n" +
      "  return 601;\n" +
      "};\n" +
      "globalThis.clearTimeout = (timer) => { if (timer !== 601) originalClearTimeout(timer); };\n" +
      "let evaluations = 0;\n" +
      "const page = { evaluate: async () => { evaluations += 1; " +
      "if (evaluations === 1) return 'denied'; return new Promise(() => {}); } };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n" +
      "globalThis.setTimeout = originalSetTimeout; globalThis.clearTimeout = originalClearTimeout;\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V2 project=desktop permission=denied ready=timeout " +
      "state=error controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=skipped\n"
  )
})

test("a stdout write failure is contained after a valid observation", () => {
  const output = reportInChild(
    "let evaluations = 0;\n" +
      "let writeAttempts = 0;\n" +
      "const page = { evaluate: async () => { evaluations += 1; " +
      "if (evaluations === 1) return 'denied'; " +
      "return { permission: 'denied', ready: 'error', state: 'error', " +
      "controller: false, subscription: false, matches: 0, shown: 0, untagged: 0, probe: 'skipped' }; } };\n" +
      "process.stdout.write = () => { writeAttempts += 1; " +
      "throw new Error('private-write-error'); };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n" +
      "if (evaluations !== 2 || writeAttempts !== 1) " +
      "throw new Error('valid observation did not reach the stdout write');\n"
  )
  assert.equal(output, "")
})

test("the subscribe probe runs only for the subscribe-phase helper", () => {
  const plain = runProbeChild({ phase: "report" })
  assert.equal(
    plain.record,
    "UE_LIVE_PUSH_OBS_V2 project=desktop permission=granted ready=resolved " +
      "state=activated controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=skipped\n"
  )
  assert.equal(plain.log.subscribeCalls, 0)

  const subscribePhase = runProbeChild({ phase: "subscribe" })
  assert.equal(
    subscribePhase.record,
    "UE_LIVE_PUSH_OBS_V2 project=desktop permission=granted ready=resolved " +
      "state=activated controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=subscribed\n"
  )
  assert.equal(subscribePhase.log.subscribeCalls, 1)
})

test("a successful probe requests a 65-byte uncompressed key and unsubscribes", () => {
  const { record, log } = runProbeChild({ phase: "subscribe" })
  assert.match(record, / probe=subscribed\n$/u)
  assert.equal(log.userVisibleOnly, true)
  assert.equal(log.keyLength, 65)
  assert.equal(log.keyFirst, 4)
  assert.equal(log.unsubscribed, 1)
})

test("the subscribe probe is skipped when permission, registration or subscription rules out a probe", () => {
  const cases = [
    { permission: "denied" },
    { permission: "default" },
    { registered: false },
    { subscription: "({ endpoint: 'private-endpoint' })" },
  ]
  for (const options of cases) {
    const { output, record, log } = runProbeChild({ phase: "subscribe", ...options })
    assert.match(record, / probe=skipped\n$/u)
    assert.equal(log.subscribeCalls, 0)
    assert.doesNotMatch(output, /private-endpoint/u)
  }
})

test("each subscribe rejection is classified to its closed probe value without echoing the message", () => {
  const cases = [
    ["Error", "Permission denied for private-token-value", "permission-denied"],
    ["Error", "Push service not available", "push-service-unavailable"],
    ["Error", "PUSH SERVICE ERROR secret", "push-service-error"],
    ["NotAllowedError", "blocked", "not-allowed"],
    ["AbortError", "aborted", "abort"],
    ["InvalidStateError", "state", "invalid-state"],
    ["NotSupportedError", "unsupported", "not-supported"],
    ["TypeError", "private-token-value", "other"],
  ]
  for (const [name, message, probe] of cases) {
    const subscribe =
      "async () => { const error = new Error(" +
      JSON.stringify(message) +
      "); error.name = " +
      JSON.stringify(name) +
      "; throw error; }"
    const { output, record, log } = runProbeChild({ phase: "subscribe", subscribe })
    assert.equal(
      record,
      "UE_LIVE_PUSH_OBS_V2 project=desktop permission=granted ready=resolved " +
        "state=activated controller=0 subscription=0 matches=0 shown=0 untagged=0 probe=" +
        probe +
        "\n",
      name
    )
    assert.equal(log.unsubscribed, 0)
    assert.doesNotMatch(output, /private-token-value|secret|aborted|blocked/u)
  }
})

test("a subscribe that outlives the probe budget is reported as timeout", () => {
  const { output, record, log } = runProbeChild({
    phase: "subscribe",
    subscribe: "() => new Promise(() => {})",
  })
  assert.match(record, / probe=timeout\n$/u)
  assert.equal(log.subscribeCalls, 1)
  assert.doesNotMatch(output, /private/u)
})

test("displayed notifications are reported as a capped count and a tag-presence flag only", () => {
  const cases = [
    ["[]", "matches=0 shown=0 untagged=0"],
    ["[{ tag: 'private-id', title: 'private-title' }]", "matches=1 shown=1 untagged=0"],
    ["[{ tag: '', body: 'private-body' }]", "matches=0 shown=1 untagged=1"],
    ["[{ tag: 'private-other' }, { tag: 'private-id' }]", "matches=1 shown=2 untagged=0"],
    [
      "[{ tag: 'private-a' }, { tag: '' }, { tag: 'private-b' }, { tag: 'private-c' }]",
      "matches=0 shown=3 untagged=1",
    ],
  ]
  for (const [notifications, fields] of cases) {
    const { output, record } = runProbeChild({ phase: "report", notifications })
    assert.equal(
      record,
      "UE_LIVE_PUSH_OBS_V2 project=desktop permission=granted ready=resolved " +
        "state=activated controller=0 subscription=0 " +
        fields +
        " probe=skipped\n",
      notifications
    )
    assert.doesNotMatch(output, /private/u)
  }
})

test("an unreadable notification list reports no displayed notifications", () => {
  const { record } = runProbeChild({
    phase: "report",
    notifications: "[{ get tag() { throw new Error('private-tag'); } }]",
  })
  assert.match(record, / matches=0 shown=0 untagged=0 probe=skipped\n$/u)
})

test("push observation rejects out-of-domain notification counts and flags", () => {
  const output = reportInChild(
    "for (const extra of [{ shown: 4, untagged: 0 }, { shown: 1, untagged: 2 }, { shown: '1', untagged: 0 }]) {\n" +
      "  let evaluations = 0;\n" +
      "  const page = { evaluate: async () => { evaluations += 1; " +
      "return evaluations === 1 ? 'granted' : ({ permission: 'granted', ready: 'resolved', " +
      "state: 'activated', controller: true, subscription: true, matches: 0, probe: 'skipped', ...extra }); } };\n" +
      "  await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n" +
      "}\n"
  )
  assert.equal(output, "")
})

test("cleanup observation preserves success and failure while emitting only closed classes", async () => {
  const { observePushCleanup } = await import(`${helper.href}?cleanup-v2`)
  const records = []
  const emit = (line) => records.push(line)
  const context = { project: "desktop", retry: 0, case: "topics", bound: true }
  await observePushCleanup(context, async () => true, emit)
  assert.deepEqual(records, [
    "UE_LIVE_PUSH_CLEANUP_V1 project=desktop retry=0 case=topics current-user-row=removed original-recipient=unknown\n",
  ])
  const failure = new Error("private cleanup error")
  await assert.rejects(
    observePushCleanup(
      { project: "mobile", retry: 1, case: "reply", bound: true },
      async () => {
        throw failure
      },
      emit
    ),
    (error) => error === failure
  )
  assert.match(records[1], /current-user-row=unknown original-recipient=unknown\n$/u)
  await observePushCleanup({ ...context, case: "chat" }, async () => false, emit)
  assert.match(records[2], /current-user-row=not-found original-recipient=unknown\n$/u)
  await observePushCleanup({ ...context, bound: false }, async () => false, emit)
  await observePushCleanup({ ...context, case: "private-token" }, async () => false, emit)
  await assert.doesNotReject(
    observePushCleanup(
      { project: "desktop", retry: 1, case: "reply", bound: true },
      async () => true,
      () => {
        throw new Error("private sink error")
      }
    )
  )
  assert.equal(records.length, 3)
  assert.doesNotMatch(records.join(""), /private|https|endpoint|token/u)
})

const rotationHelper = new URL("./push-rotation-observation.mjs", import.meta.url)

test("rotation capture hashes subscription at opt-in, waits and failure", async () => {
  const { createHash } = await import("node:crypto")
  const { createPushRotationObservation } = await import(rotationHelper.href)
  let endpoint = privateEndpoint
  const page = {
    evaluate: async (fn) => {
      const prior = Object.getOwnPropertyDescriptor(globalThis, "navigator")
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: {
          serviceWorker: {
            getRegistration: async () => ({
              pushManager: {
                getSubscription: async () => (endpoint === null ? null : { endpoint }),
              },
            }),
          },
        },
      })
      try {
        return await fn()
      } finally {
        if (prior === undefined) delete globalThis.navigator
        else Object.defineProperty(globalThis, "navigator", prior)
      }
    },
  }
  const lines = []
  const diagnostic = createPushRotationObservation(page, "mobile", 0, (line) => lines.push(line))
  const prefix = (value) => createHash("sha256").update(value).digest("hex").slice(0, 12)
  await diagnostic.optIn(100)
  diagnostic.arm("news")
  await diagnostic.beforeWait("news", 100)
  assert.deepEqual(lines, [])
  endpoint = "https://push.example.invalid/rotated-private-token"
  await diagnostic.beforeWait("events", 100)
  await diagnostic.reportFailure(100)
  await diagnostic.reportFailure(100)
  const base = "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario="
  assert.deepEqual(lines, [
    base + "setup phase=opt-in ordinal=1 endpoint_sha256=" + prefix(privateEndpoint) + "\n",
    base + "news phase=before-wait ordinal=2 endpoint_sha256=" + prefix(privateEndpoint) + "\n",
    base + "events phase=before-wait ordinal=3 endpoint_sha256=" + prefix(endpoint) + "\n",
    base + "events phase=failure ordinal=4 endpoint_sha256=" + prefix(endpoint) + "\n",
  ])
  assert.doesNotMatch(lines.join(""), /private|example|https/u)
})

test("reply rotation retains its own bounded phases only after a failure", async () => {
  const { createPushRotationObservation } = await import(rotationHelper.href)
  const lines = []
  const page = { evaluate: async () => "0123456789ab" }
  const observation = createPushRotationObservation(
    page,
    "mobile",
    0,
    (line) => lines.push(line),
    "reply"
  )

  await observation.optIn(100)
  observation.arm("reply")
  await observation.beforeWait("reply", 100)
  assert.deepEqual(lines, [])
  await observation.reportFailure(100)
  await observation.reportFailure(100)
  assert.deepEqual(lines, [
    "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario=reply phase=opt-in ordinal=1 endpoint_sha256=0123456789ab\n",
    "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario=reply phase=before-wait ordinal=2 endpoint_sha256=0123456789ab\n",
    "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=0 scenario=reply phase=failure ordinal=3 endpoint_sha256=0123456789ab\n",
  ])
})

test("reply rotation rejects other scenarios and never emits raw observation data", async () => {
  const { createPushRotationObservation } = await import(rotationHelper.href)
  const lines = []
  const page = { evaluate: async () => privateEndpoint }
  const observation = createPushRotationObservation(
    page,
    "mobile",
    1,
    (line) => lines.push(line),
    "reply"
  )

  observation.arm("news")
  await observation.beforeWait("news", 100)
  await observation.reportFailure(100)
  assert.deepEqual(lines, [
    "UE_LIVE_PUSH_ROTATION_V1 project=mobile retry=1 scenario=reply phase=failure ordinal=1 endpoint_sha256=unavailable\n",
  ])
  assert.doesNotMatch(lines.join(""), /private|example|https/u)

  const invalid = createPushRotationObservation(
    page,
    "mobile",
    0,
    (line) => lines.push(line),
    "other"
  )
  await invalid.optIn(100)
  await invalid.reportFailure(100)
  const desktop = createPushRotationObservation(
    page,
    "desktop",
    0,
    (line) => lines.push(line),
    "reply"
  )
  await desktop.optIn(100)
  await desktop.reportFailure(100)
  assert.equal(lines.length, 1)
})

test("rotation capture bounds failures, input classes, output and the failure slot", async () => {
  const { createPushRotationObservation } = await import(rotationHelper.href)
  const lines = []
  const page = { evaluate: async () => "https://private.example/token" }
  const diagnostic = createPushRotationObservation(page, "desktop", 1, (line) => lines.push(line))
  diagnostic.arm("private")
  await diagnostic.optIn(1)
  for (let i = 0; i < 12; i++) await diagnostic.beforeWait("schedule", 1)
  await diagnostic.reportFailure(1)
  assert.equal(lines.length, 8)
  assert.match(
    lines.at(-1),
    /scenario=schedule phase=failure ordinal=8 endpoint_sha256=unavailable\n$/u
  )
  assert.doesNotMatch(lines.join(""), /private|example|https/u)
  const missing = []
  const withoutSubscription = createPushRotationObservation(
    { evaluate: async () => "missing" },
    "mobile",
    1,
    (line) => missing.push(line)
  )
  await withoutSubscription.optIn(1)
  await withoutSubscription.reportFailure(0)
  assert.match(missing[0], /endpoint_sha256=missing\n$/u)
  assert.match(
    missing[1],
    /scenario=unknown phase=failure ordinal=2 endpoint_sha256=unavailable\n$/u
  )
  const timed = []
  const hanging = createPushRotationObservation(
    { evaluate: () => new Promise(() => {}) },
    "mobile",
    0,
    (line) => timed.push(line)
  )
  await hanging.optIn(1)
  await hanging.reportFailure(NaN)
  assert.equal(timed.length, 2)
  assert.ok(timed.every((line) => line.includes("endpoint_sha256=unavailable")))
  const throwing = createPushRotationObservation(
    {
      evaluate: async () => {
        throw new Error("private")
      },
    },
    "desktop",
    0,
    () => {
      throw new Error("private")
    }
  )
  await assert.doesNotReject(throwing.reportFailure(1))
  for (const [project, retry] of [
    ["private", 0],
    ["mobile", 2],
  ]) {
    const invalid = createPushRotationObservation(page, project, retry, () =>
      assert.fail("invalid scope")
    )
    await invalid.optIn(1)
    await invalid.reportFailure(1)
  }
})

test("concurrent abort and test failure share one rotation capture", async () => {
  const { createPushRotationObservation } = await import(rotationHelper.href)
  const lines = []
  let calls = 0
  const diagnostic = createPushRotationObservation(
    {
      evaluate: async () => {
        calls += 1
        await new Promise((resolve) => setImmediate(resolve))
        return "missing"
      },
    },
    "desktop",
    0,
    (line) => lines.push(line)
  )
  diagnostic.arm("news")
  await Promise.all([diagnostic.reportFailure(100), diagnostic.reportFailure(100)])
  assert.equal(calls, 1)
  assert.equal(lines.length, 1)
  assert.match(lines[0], /phase=failure ordinal=1 endpoint_sha256=missing\n$/u)
})

test("browser registration failures and missing subscriptions produce closed classes", async () => {
  const { createPushRotationObservation } = await import(rotationHelper.href)
  for (const [getRegistration, expected] of [
    [async () => null, "unavailable"],
    [
      async () => {
        throw new Error("private")
      },
      "unavailable",
    ],
    [async () => ({ pushManager: { getSubscription: async () => null } }), "missing"],
  ]) {
    const page = {
      evaluate: async (fn) => {
        const prior = Object.getOwnPropertyDescriptor(globalThis, "navigator")
        Object.defineProperty(globalThis, "navigator", {
          configurable: true,
          value: { serviceWorker: { getRegistration } },
        })
        try {
          return await fn()
        } finally {
          if (prior === undefined) delete globalThis.navigator
          else Object.defineProperty(globalThis, "navigator", prior)
        }
      },
    }
    const lines = []
    const diagnostic = createPushRotationObservation(page, "desktop", 0, (line) => lines.push(line))
    await diagnostic.beforeWait("unknown", 100)
    await diagnostic.reportFailure(0)
    await diagnostic.beforeWait("news", 100)
    assert.equal(lines.length, 2)
    assert.match(
      lines[0],
      new RegExp(
        "scenario=unknown phase=before-wait ordinal=1 endpoint_sha256=" + expected + "\\n$",
        "u"
      )
    )
    assert.doesNotMatch(lines.join(""), /private/u)
  }
})

test("rotation default writer emits only the closed fingerprint record", async () => {
  const { createPushRotationObservation } = await import(rotationHelper.href)
  const lines = []
  const original = process.stdout.write
  process.stdout.write = (line) => {
    lines.push(line)
    return true
  }
  try {
    const diagnostic = createPushRotationObservation(
      { evaluate: async () => "missing" },
      "desktop",
      0
    )
    await diagnostic.reportFailure(100)
  } finally {
    process.stdout.write = original
  }
  assert.equal(lines.length, 1)
  assert.match(lines[0], /phase=failure ordinal=1 endpoint_sha256=missing\n$/u)
})

test("rotation capture contains unexpected host observation failures", async () => {
  const { createPushRotationObservation } = await import(rotationHelper.href)
  const lines = []
  const diagnostic = createPushRotationObservation(
    { evaluate: async () => "missing" },
    "desktop",
    0,
    (line) => lines.push(line)
  )
  const originalRace = Promise.race
  Promise.race = () => {
    throw new Error("private")
  }
  try {
    await assert.doesNotReject(diagnostic.reportFailure(1))
  } finally {
    Promise.race = originalRace
  }
  assert.equal(lines.length, 1)
  assert.match(lines[0], /endpoint_sha256=unavailable\n$/u)
  assert.doesNotMatch(lines[0], /private/u)
})

test("topic waits retain assertions and capture the subscription before waiting", async () => {
  const source = await readFile(
    new URL("./notification-topics-delivery.live.spec.ts", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("const waitForNativeNotification = async")
  const end = source.indexOf("const assertActualDelivery = async", start)
  const wait = source.slice(start, end)
  assert.match(wait, /await rotation\.beforeWait\([\s\S]*?await expect[\s\S]*?\.toBe\(1\)/u)
  assert.match(wait, /rotation\.reportFailure\([\s\S]*?throw error/u)
  assert.match(wait, /failureObservation\.disarm\(\)[\s\S]*?failureObservation\.capture\(\)/u)
  assert.match(source, /await rotationObservation\.optIn\(/u)
  for (const scenario of ["news", "events", "schedule", "release"])
    assert.ok(source.includes('rotationObservation.arm("' + scenario + '")'))
  assert.match(source, /expect\(native\.tag\)\.toBe\(notificationRow\.id\)/u)
  assert.match(source, /expect\(native\.entityId\)\.toBe\(expected\.entityId\)/u)
})

test("reply delivery observes the bound endpoint without changing native acceptance", async () => {
  const source = await readFile(new URL("./push-delivery.live.spec.ts", import.meta.url), "utf8")
  const reply = source.slice(source.indexOf('test("quoted group author gets one chat.reply'))
  assert.match(reply, /createPushRotationObservation\([\s\S]*?"reply"/u)
  assert.match(reply, /subscriptionBound = true[\s\S]*?rotationObservation\?\.optIn\(/u)
  assert.match(reply, /rotationObservation\?\.beforeWait\("reply"[\s\S]*?await expect/u)
  assert.match(
    reply,
    /const reportReplyFailure = async[\s\S]*?rotationObservation\?\.reportFailure\([\s\S]*?armFailureObservation\(expectedNotificationId, \(\) =>\s*reportReplyFailure\(\)/u
  )
  assert.match(reply, /failureObservation\.disarm\(\)/u)
  assert.match(reply, /native reply push is tagged with the persisted notification identity/u)
})
