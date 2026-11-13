import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import process from "node:process"
import test from "node:test"
import { URL } from "node:url"

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
} = {}) {
  const call =
    phase === "subscribe"
      ? "await awaitPushSubscribeWithObservation(Promise.reject(new Error('save failed')), page, 'desktop').catch(() => {});\n"
      : "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n"
  const registration = registered
    ? "{ active: { state: 'activated' }, getNotifications: async () => [], pushManager: { " +
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

test("failure observation is armed around the unchanged native poll and runs during profile teardown", async () => {
  const [spec, helper, fixture] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(helperUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
  ])
  const pollStart = spec.indexOf("const expectedNotificationId = notificationId")
  const armIndex = spec.indexOf(
    "const failureObservation = nativePushProfiles.armFailureObservation(expectedNotificationId)",
    pollStart
  )
  const timeoutIndex = spec.indexOf("timeout: 60_000", armIndex)
  const pollSuccess = spec.indexOf(".toBe(1)", timeoutIndex)
  const disarmIndex = spec.indexOf("failureObservation.disarm()", pollSuccess)
  assert.ok(pollStart >= 0 && armIndex > pollStart)
  assert.ok(timeoutIndex > armIndex && pollSuccess > timeoutIndex && disarmIndex > pollSuccess)
  assert.match(spec.slice(armIndex, disarmIndex), /expect\s*\.\s*poll/u)
  assert.doesNotMatch(spec.slice(armIndex, disarmIndex), /catch\s*\(/u)
  assert.doesNotMatch(spec, /reportLivePushDeliveryObservation/u)
  assert.match(helper, /normalizeObservation\(\s*await observe/u)

  const statusGate = fixture.indexOf("if (testInfo.status !== testInfo.expectedStatus)")
  const consume = fixture.indexOf(
    "const failureObservation = pendingFailureObservation",
    statusGate
  )
  const clear = fixture.indexOf("pendingFailureObservation = undefined", consume)
  const report = fixture.indexOf("await failureObservation()", clear)
  const profileVerification = fixture.indexOf("verifyProfileBeforeRemoval(record)", report)
  assert.ok(statusGate >= 0 && consume > statusGate && clear > consume && report > clear)
  assert.ok(profileVerification > report)
  assert.match(fixture, /let pendingFailureObservation: \(\(\) => Promise<void>\) \| undefined/u)
  assert.match(
    fixture,
    /reportLivePushDeliveryObservation\(primary\.page, testInfo\.project\.name, expectedTag\)/u
  )
  assert.match(fixture, /if \(pendingFailureObservation\) \{[\s\S]*already armed/u)
  assert.match(
    fixture,
    /if \(pendingFailureObservation === observation\) \{[\s\S]*pendingFailureObservation = undefined/u
  )
  assert.match(
    fixture,
    /catch \{[\s\S]*Observation must not replace the original assertion or timeout/u
  )
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
  assert.match(helper, /matches = notificationsResult\.value\.some[\s\S]*?\? 1\s*:\s*0/u)
  assert.match(helper, /MAX_RECORDS = 4/u)
  assert.match(helper, /notification\.tag === expectedTag/u)
  assert.doesNotMatch(
    helper,
    /\bfetch\s*\(|\brequest\s*\(|\.locator\s*\(|new URL|\.endpoint\b|\.body\b|\.title\b|process\.stderr/u
  )
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
      "controller: true, subscription: true, matches: 0, probe: 'skipped' };\n" +
      "} };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', " +
      JSON.stringify(privateId) +
      ");\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V1 project=desktop permission=granted ready=resolved " +
      "state=activated controller=1 subscription=1 matches=0 probe=skipped\n"
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
      "subscription: true, matches: 1, probe: 'skipped' };\n" +
      "const page = { evaluate: async () => { evaluations += 1; " +
      "return evaluations === 1 ? 'granted' : changing; } };\n" +
      "await reportLivePushDeliveryObservation(page, 'mobile', 'private-id');\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V1 project=mobile permission=granted ready=resolved " +
      "state=activated controller=1 subscription=1 matches=1 probe=skipped\n"
  )
  assert.doesNotMatch(output, /private-value|private-id/u)
})
test("push observation rejects invalid domains and private values without coercion", () => {
  const output = reportInChild(
    "const page = { evaluate: async () => ({ permission: 'granted', ready: 'resolved', " +
      "state: 'activated', controller: true, subscription: true, matches: 0, probe: 'skipped' }) };\n" +
      "const privateValue = { toString() { throw new Error('private-value'); } };\n" +
      "await reportLivePushDeliveryObservation(page, 'private-project', 'private-id');\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', privateValue);\n" +
      "let invalidEvaluations = 0;\n" +
      "const invalidPage = { evaluate: async () => { invalidEvaluations += 1; " +
      "return invalidEvaluations === 1 ? 'granted' : ({ permission: privateValue, " +
      "ready: 'resolved', state: 'activated', controller: true, subscription: true, matches: 2, probe: 'skipped' }); } };\n" +
      "await reportLivePushDeliveryObservation(invalidPage, 'mobile', 'private-id');\n" +
      "let probeEvaluations = 0;\n" +
      "const invalidProbePage = { evaluate: async () => { probeEvaluations += 1; " +
      "return probeEvaluations === 1 ? 'granted' : ({ permission: 'granted', ready: 'resolved', " +
      "state: 'activated', controller: true, subscription: true, matches: 0, probe: 'private-probe' }); } };\n" +
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
      "controller: false, subscription: false, matches: 0, probe: 'skipped' }; } };\n" +
      "for (const permission of permissions) await reportLivePushDeliveryObservation(page, 'mobile', permission);\n"
  )
  assert.equal(
    output,
    [
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=default ready=timeout state=missing controller=0 subscription=0 matches=0 probe=skipped\n",
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=granted ready=timeout state=missing controller=0 subscription=0 matches=0 probe=skipped\n",
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=denied ready=timeout state=missing controller=0 subscription=0 matches=0 probe=skipped\n",
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=unsupported ready=timeout state=missing controller=0 subscription=0 matches=0 probe=skipped\n",
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
    "UE_LIVE_PUSH_OBS_V1 project=desktop permission=unsupported ready=error " +
      "state=missing controller=0 subscription=0 matches=0 probe=skipped\n"
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
    "UE_LIVE_PUSH_OBS_V1 project=desktop permission=denied ready=timeout " +
      "state=error controller=0 subscription=0 matches=0 probe=skipped\n"
  )
})

test("a stdout write failure is contained after a valid observation", () => {
  const output = reportInChild(
    "let evaluations = 0;\n" +
      "let writeAttempts = 0;\n" +
      "const page = { evaluate: async () => { evaluations += 1; " +
      "if (evaluations === 1) return 'denied'; " +
      "return { permission: 'denied', ready: 'error', state: 'error', " +
      "controller: false, subscription: false, matches: 0, probe: 'skipped' }; } };\n" +
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
    "UE_LIVE_PUSH_OBS_V1 project=desktop permission=granted ready=resolved " +
      "state=activated controller=0 subscription=0 matches=0 probe=skipped\n"
  )
  assert.equal(plain.log.subscribeCalls, 0)

  const subscribePhase = runProbeChild({ phase: "subscribe" })
  assert.equal(
    subscribePhase.record,
    "UE_LIVE_PUSH_OBS_V1 project=desktop permission=granted ready=resolved " +
      "state=activated controller=0 subscription=0 matches=0 probe=subscribed\n"
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
      "UE_LIVE_PUSH_OBS_V1 project=desktop permission=granted ready=resolved " +
        "state=activated controller=0 subscription=0 matches=0 probe=" +
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
