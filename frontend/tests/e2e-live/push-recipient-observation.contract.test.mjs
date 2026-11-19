import assert from "node:assert/strict"
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
  assert.match(
    topics,
    /await reportLivePushDeliveryObservation\(page, test\.info\(\)\.project\.name, notificationId\)/u
  )
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
