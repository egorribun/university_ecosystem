import assert from "node:assert/strict"
import { performance } from "node:perf_hooks"
import process from "node:process"
import test from "node:test"
import { setImmediate } from "node:timers"
import vm from "node:vm"

const helper = await import("./messenger-reconnect-diagnostic.ts").catch(() => null)

test("a failed reconnect records the selected session and preserves the original failure", async () => {
  assert.ok(helper, "the bounded reconnect diagnostic implementation must exist")
  const output = []
  let now = 100
  const diagnostic = helper.createReconnectDiagnostic(
    "desktop",
    0,
    () => now,
    (line) => output.push(line)
  )
  const session = {
    ordinal: diagnostic.socketCreated(),
    joinedChat: true,
    closed: false,
    socket: { url: () => "ws://private.invalid/?ticket=private" },
  }
  diagnostic.note("room-joined", session.ordinal)
  diagnostic.select(session.ordinal)
  diagnostic.stage("old-close-wait")
  diagnostic.note("offline-called")
  now = 15100
  const failure = new Error("private-original-failure")
  const page = {
    context() {
      throw new Error("private-CDP-error")
    },
  }
  await assert.rejects(
    async () => {
      try {
        throw failure
      } catch (error) {
        await diagnostic.reportFailure(page, [session])
        throw error
      }
    },
    (error) => error === failure
  )
  assert.equal(output.length, 1)
  const record = JSON.parse(output[0].slice("UE_LIVE_RECONNECT_V1 ".length))
  assert.equal(record.selected, 1)
  assert.equal(record.stage, "old-close-wait")
  assert.equal(record.closed, false)
  assert.equal(record.elapsedMs, 15000)
  assert.equal(record.nativeState, null)
  assert.equal(record.probe, "unavailable")
  assert.deepEqual(
    record.events.map((event) => event.kind),
    ["socket-created", "room-joined", "offline-called"]
  )
  assert.doesNotMatch(output[0], /private|ticket|ws:\/\//u)
})

test("the protocol rejects unknown fields, injection strings and numeric overflow", () => {
  assert.ok(helper)
  const valid = {
    schema: 1,
    scenario: "direct-message-replay",
    project: "desktop",
    attempt: 0,
    stage: "old-close-wait",
    selected: 1,
    sessions: 1,
    sessionsCapped: false,
    joined: true,
    closed: false,
    elapsedMs: 15000,
    elapsedCapped: false,
    offlineEvents: 1,
    onlineEvents: 0,
    online: false,
    probe: "unique",
    nativeState: 2,
    buffered: "zero",
    eventsCapped: false,
    events: [{ sequence: 1, kind: "socket-created", session: 1, elapsedMs: 0 }],
    sampleAfterFailureMs: 10,
  }
  assert.ok(helper.serializeReconnectDiagnostic(valid))
  for (const change of [
    { private: "secret" },
    { project: "desktop\nprivate" },
    { stage: "private" },
    { attempt: 2 },
    { selected: 33 },
    { sessions: true },
    { elapsedMs: Infinity },
    { elapsedMs: 120001 },
    { offlineEvents: "1" },
    { nativeState: 4 },
    { buffered: "private" },
    { events: [{ ...valid.events[0], private: "secret" }] },
    { events: [{ ...valid.events[0], sequence: 2 }] },
    { events: [{ ...valid.events[0], elapsedMs: 15001 }] },
    { probe: "unavailable" },
    { selected: 0 },
  ])
    assert.equal(helper.serializeReconnectDiagnostic({ ...valid, ...change }), null)
  for (const value of [
    null,
    [],
    "private",
    1,
    {
      ...valid,
      toJSON() {
        throw new Error("private")
      },
    },
  ]) {
    assert.equal(helper.serializeReconnectDiagnostic(value), null)
  }
  for (const events of [
    Object.assign([], { toJSON: () => ({ token: "private-array-marker" }) }),
    Object.assign([], { entries: () => [] }),
    new Array(1),
    Object.defineProperty([valid.events[0]], "0", { get: () => valid.events[0] }),
  ])
    assert.equal(helper.serializeReconnectDiagnostic({ ...valid, events }), null)
  const changing = new Proxy(valid, {
    get() {
      return "private-get-trap"
    },
  })
  assert.equal(
    helper.serializeReconnectDiagnostic(changing),
    helper.serializeReconnectDiagnostic(valid)
  )
  assert.equal(helper.serializeReconnectDiagnostic({ ...valid, sampleAfterFailureMs: null }), null)
  for (const field of ["offlineEvents", "onlineEvents", "online"]) {
    const unavailable = {
      ...valid,
      probe: "unavailable",
      nativeState: null,
      buffered: null,
      sampleAfterFailureMs: null,
      offlineEvents: null,
      onlineEvents: null,
      online: null,
    }
    assert.ok(helper.serializeReconnectDiagnostic(unavailable))
    assert.equal(
      helper.serializeReconnectDiagnostic({
        ...unavailable,
        [field]: field === "online" ? false : 1,
      }),
      null
    )
  }
  assert.equal(helper.serializeReconnectDiagnostic({ ...valid, sampleAfterFailureMs: 1001 }), null)
  const throwing = new Proxy(valid, {
    ownKeys() {
      throw new Error("private-proxy")
    },
  })
  assert.equal(helper.serializeReconnectDiagnostic(throwing), null)
  for (const change of [
    { schema: 2 },
    { scenario: "private" },
    { joined: 1 },
    { closed: null },
    { sessionsCapped: true },
    { elapsedCapped: true },
    { eventsCapped: true },
    { sampleAfterFailureMs: true },
    { online: "private" },
    { probe: "private" },
    { offlineEvents: -1 },
    { onlineEvents: 33 },
    { events: null },
    { events: Array(25).fill(valid.events[0]) },
    { events: [{ ...valid.events[0], kind: "private" }] },
    { events: [{ ...valid.events[0], session: 0 }] },
    { events: [{ ...valid.events[0], kind: "offline-called" }] },
    {
      events: [
        { ...valid.events[0], elapsedMs: 2 },
        { ...valid.events[0], sequence: 2, elapsedMs: 1 },
      ],
    },
  ])
    assert.equal(helper.serializeReconnectDiagnostic({ ...valid, ...change }), null)
  const nullPrototype = Object.assign(Object.create(null), valid)
  assert.ok(helper.serializeReconnectDiagnostic(nullPrototype))
  assert.equal(helper.serializeReconnectDiagnostic(Object.assign(Object.create({}), valid)), null)
  assert.equal(
    helper.serializeReconnectDiagnostic(
      Object.defineProperty({ ...valid }, "stage", { get: () => "private" })
    ),
    null
  )
})

const privateUrl = "wss://private.invalid/?ticket=private-ticket"
function observed(ordinal = 1, url = privateUrl) {
  return { ordinal, joinedChat: true, closed: false, socket: { url: () => url } }
}
function nativeFixture({ urls = [privateUrl], state = 2, buffered = 0, fail, hold } = {}) {
  const calls = []
  const context = vm.createContext({
    window: { __ueReconnectConnectivity: { offline: 1, online: 0 } },
    navigator: { onLine: false },
    urls,
    state,
    buffered,
  })
  vm.runInContext(
    `class WebSocket {
    constructor(url) { this.privateUrl = url }
    get url() { return this.privateUrl }
    get readyState() { return state }
    get bufferedAmount() { return buffered }
  }
  globalThis.WebSocket = WebSocket;
  globalThis.sockets = urls.map(url => new WebSocket(url));`,
    context
  )
  const cdp = {
    async send(method, parameters) {
      calls.push({ method, parameters })
      if (method === fail) throw new Error("private-protocol-error")
      if (method === hold) return new Promise(() => {})
      if (method === "Runtime.evaluate") return { result: { objectId: "private-prototype-handle" } }
      if (method === "Runtime.queryObjects")
        return { objects: { objectId: "private-object-handle" } }
      if (method === "Runtime.callFunctionOn") {
        context.args = parameters.arguments.map((argument) => argument.value)
        const value = vm.runInContext(
          `(${parameters.functionDeclaration}).apply(sockets, args)`,
          context
        )
        return { result: { value: JSON.parse(JSON.stringify(value)) } }
      }
      return {}
    },
    async detach() {
      calls.push({ method: "detach" })
      if (fail === "detach") throw new Error("private-detach-error")
    },
  }
  const page = {
    context: () => ({
      newCDPSession: async () => {
        calls.push({ method: "attach" })
        if (fail === "attach") throw new Error("private-attach-error")
        return cdp
      },
    }),
  }
  return { page, calls, context, cdp }
}

test("readonly native projection binds one observed URL and distinguishes native states without a close-request claim", async () => {
  for (const state of [0, 1, 2, 3]) {
    const { page, calls } = nativeFixture({ state, buffered: state })
    const session = observed()
    const result = await helper.probeReconnectSocket(page, session, [session], true)
    assert.deepEqual(result, {
      offlineEvents: 1,
      onlineEvents: 0,
      online: false,
      probe: "unique",
      nativeState: state,
      buffered: state === 0 ? "zero" : "nonzero",
    })
    assert.doesNotMatch(JSON.stringify(result), /private|ticket|close.request/iu)
    assert.deepEqual(
      calls.map((call) => call.method),
      [
        "attach",
        "Runtime.evaluate",
        "Runtime.queryObjects",
        "Runtime.callFunctionOn",
        "Runtime.releaseObjectGroup",
        "detach",
      ]
    )
  }
})

test("binding rejects observed URL reuse, missing/ambiguous native objects, overflow and invalid native properties", async () => {
  const session = observed()
  for (const [options, sessions, expected] of [
    [{}, [session, observed(2)], "unavailable"],
    [{ urls: [] }, [session], "missing"],
    [{ urls: [privateUrl, privateUrl] }, [session], "ambiguous"],
    [{ urls: Array(33).fill(privateUrl) }, [session], "overflow"],
    [{ state: 4 }, [session], "unavailable"],
    [{ buffered: Infinity }, [session], "unavailable"],
    [{ buffered: -1 }, [session], "unavailable"],
  ]) {
    const { page, calls } = nativeFixture(options)
    const result = await helper.probeReconnectSocket(page, session, sessions)
    assert.equal(result.probe, expected)
    assert.equal(result.nativeState, null)
    assert.equal(result.buffered, null)
    assert.equal(result.offlineEvents, null, "unarmed counters must stay unknown")
    assert.equal(calls.at(-1).method, "detach")
    assert.doesNotMatch(JSON.stringify(result), /private|ticket/u)
  }
})

test("each protocol failure is sanitized and attached sessions are released/detached", async () => {
  for (const fail of [
    "attach",
    "Runtime.evaluate",
    "Runtime.queryObjects",
    "Runtime.callFunctionOn",
    "Runtime.releaseObjectGroup",
    "detach",
  ]) {
    const { page, calls } = nativeFixture({ fail })
    const session = observed()
    const result = await helper.probeReconnectSocket(page, session, [session])
    if (!["Runtime.releaseObjectGroup", "detach"].includes(fail))
      assert.equal(result.probe, "unavailable")
    if (fail !== "attach") {
      assert.ok(calls.some((call) => call.method === "Runtime.releaseObjectGroup"))
      assert.equal(calls.at(-1).method, "detach")
    }
    assert.doesNotMatch(JSON.stringify(result), /private|ticket/u)
  }
})

test("a stalled native query ends the diagnostic budget, detaches and never starts a later read", async () => {
  const { page, calls } = nativeFixture({ hold: "Runtime.queryObjects" })
  const session = observed()
  const result = await helper.probeReconnectSocket(page, session, [session])
  assert.equal(result.probe, "unavailable")
  assert.equal(calls.at(-1).method, "detach")
  assert.ok(!calls.some((call) => call.method === "Runtime.callFunctionOn"))
})

test("a late attach is detached without evaluating native objects", async () => {
  let attach
  const { cdp, calls } = nativeFixture()
  const page = {
    context: () => ({
      newCDPSession: () =>
        new Promise((resolve) => {
          attach = resolve
        }),
    }),
  }
  const session = observed()
  assert.equal((await helper.probeReconnectSocket(page, session, [session])).probe, "unavailable")
  attach(cdp)
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(
    calls.map((call) => call.method),
    ["detach"]
  )
})

test("a timeout with a failed detach stays sanitized and never continues the native query", async () => {
  const { page, calls } = nativeFixture({ hold: "Runtime.queryObjects", fail: "detach" })
  const session = observed()
  assert.equal((await helper.probeReconnectSocket(page, session, [session])).probe, "unavailable")
  await Promise.resolve()
  assert.equal(calls.at(-1).method, "detach")
  assert.ok(!calls.some((call) => call.method === "Runtime.callFunctionOn"))
})

test("probe completion outside the sampling budget discards all later native evidence", async (context) => {
  const lines = []
  const diagnostic = helper.createReconnectDiagnostic(
    "desktop",
    0,
    () => 0,
    (line) => lines.push(line)
  )
  const session = observed(diagnostic.socketCreated())
  diagnostic.select(session.ordinal)
  diagnostic.connectivityReady(true)
  const { page } = nativeFixture()
  let tick = 0
  const clock = context.mock.method(performance, "now", () => (tick++ === 0 ? 0 : 1001))
  try {
    await diagnostic.reportFailure(page, [session])
  } finally {
    clock.mock.restore()
  }
  const record = JSON.parse(lines[0].slice("UE_LIVE_RECONNECT_V1 ".length))
  assert.equal(record.sampleAfterFailureMs, null)
  for (const key of ["nativeState", "buffered", "offlineEvents", "onlineEvents", "online"])
    assert.equal(record[key], null)
  assert.equal(record.probe, "unavailable")
})

test("connectivity observation never waits on the acceptance path and stale installation does nothing", async () => {
  let evaluate, resolve
  const page = {
    evaluate: (fn, argument) => {
      evaluate = { fn, argument }
      return new Promise((done) => {
        resolve = done
      })
    },
  }
  const ready = helper.armReconnectConnectivity(page)
  assert.equal(ready(), false)
  const handlers = new Map()
  const target = { addEventListener: (kind, handler) => handlers.set(kind, handler) }
  const native = function WebSocket() {}
  const context = vm.createContext({
    window: target,
    WebSocket: native,
    expires: evaluate.argument,
    Date: { now: () => evaluate.argument + 1 },
  })
  assert.equal(vm.runInContext(`(${evaluate.fn})(expires)`, context), false)
  assert.equal(handlers.size, 0)
  context.Date.now = () => evaluate.argument - 1
  assert.equal(vm.runInContext(`(${evaluate.fn})(expires)`, context), true)
  for (let index = 0; index < 40; index += 1) handlers.get("offline")()
  assert.equal(target.__ueReconnectConnectivity.offline, 32)
  assert.equal(context.WebSocket, native)
  const priorWindow = Object.getOwnPropertyDescriptor(globalThis, "window")
  try {
    Object.defineProperty(globalThis, "window", { value: target, configurable: true })
    assert.equal(evaluate.fn(Date.now() - 1), false)
    assert.equal(evaluate.fn(Date.now() + 1000), true)
    handlers.get("offline")()
    handlers.get("online")()
    assert.deepEqual(target.__ueReconnectConnectivity, { offline: 1, online: 1 })
  } finally {
    if (priorWindow) Object.defineProperty(globalThis, "window", priorWindow)
    else delete globalThis.window
  }
  resolve(true)
  await Promise.resolve()
  assert.equal(ready(), true)
  assert.equal(
    helper.armReconnectConnectivity({
      evaluate() {
        throw new Error("private-sync")
      },
    })(),
    false
  )
  const rejected = helper.armReconnectConnectivity({
    evaluate: async () => {
      throw new Error("private-async")
    },
  })
  await Promise.resolve()
  assert.equal(rejected(), false)
})

test("the default writer emits only the closed record and invalid diagnostic labels emit nothing", async (context) => {
  const lines = []
  const writer = context.mock.method(process.stdout, "write", (line) => {
    lines.push(line)
    return true
  })
  try {
    const diagnostic = helper.createReconnectDiagnostic("desktop", 0)
    diagnostic.note("private", 0)
    diagnostic.note("room-joined", 0)
    diagnostic.select(99)
    diagnostic.stage("private")
    diagnostic.connectivityReady(true)
    await diagnostic.reportFailure(
      {
        context() {
          throw new Error("private")
        },
      },
      []
    )
    await helper.createReconnectDiagnostic("private", 0).reportFailure(
      {
        context() {
          throw new Error("private")
        },
      },
      []
    )
  } finally {
    writer.mock.restore()
  }
  assert.equal(lines.length, 1)
  const record = JSON.parse(lines[0].slice("UE_LIVE_RECONNECT_V1 ".length))
  assert.equal(record.selected, 0)
  assert.equal(record.stage, "setup")
  assert.equal(record.offlineEvents, null)
  assert.doesNotMatch(lines[0], /private/u)
})

test("native protocol exceptions and missing object handles cannot become observed socket state", async () => {
  for (const [method, replacement] of [
    ["Runtime.evaluate", { result: {} }],
    [
      "Runtime.evaluate",
      { result: { objectId: "private" }, exceptionDetails: { text: "private" } },
    ],
    ["Runtime.queryObjects", { objects: {} }],
    ["Runtime.callFunctionOn", { result: {}, exceptionDetails: { text: "private" } }],
    ["Runtime.callFunctionOn", { result: { value: "private" } }],
    ["Runtime.callFunctionOn", { result: { value: { private: "private" } } }],
  ]) {
    const { page, cdp, calls } = nativeFixture()
    const send = cdp.send
    cdp.send = async (name, parameters) => (name === method ? replacement : send(name, parameters))
    const session = observed()
    const result = await helper.probeReconnectSocket(page, session, [session])
    assert.equal(result.probe, "unavailable")
    assert.equal(calls.at(-1).method, "detach")
    assert.doesNotMatch(JSON.stringify(result), /private/u)
  }
})

test("recording is bounded, failure-only, freezes before probing and cannot replace an assertion", async () => {
  let now = 0
  const output = []
  const diagnostic = helper.createReconnectDiagnostic(
    "mobile",
    1,
    () => now,
    (line) => output.push(line)
  )
  const sessions = Array.from({ length: 33 }, (_, index) => ({
    ...observed(index + 1, `private-${index}`),
    ordinal: diagnostic.socketCreated(),
  }))
  diagnostic.select(1)
  assert.equal(output.length, 0)
  now = 130000
  const page = {
    context() {
      sessions[0].closed = true
      diagnostic.note("socket-closed", 1)
      throw new Error("private")
    },
  }
  await diagnostic.reportFailure(page, sessions)
  await diagnostic.reportFailure(page, sessions)
  assert.equal(output.length, 1)
  const record = JSON.parse(output[0].slice("UE_LIVE_RECONNECT_V1 ".length))
  assert.equal(record.closed, false)
  assert.equal(record.sessions, 32)
  assert.equal(record.sessionsCapped, true)
  assert.equal(record.events.length, 24)
  assert.equal(record.eventsCapped, true)
  assert.equal(record.elapsedMs, 120000)
  assert.equal(record.elapsedCapped, true)
  assert.ok(record.sampleAfterFailureMs === null || record.sampleAfterFailureMs <= 1000)
  assert.doesNotMatch(output[0], /private/u)
  const brokenWriter = helper.createReconnectDiagnostic(
    "desktop",
    0,
    () => 0,
    () => {
      throw new Error("private-writer")
    }
  )
  await assert.doesNotReject(() => brokenWriter.reportFailure(page, []))
})
