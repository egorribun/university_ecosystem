import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import process from "node:process"
import test from "node:test"
import { URL } from "node:url"

const helperUrl = new URL("./push-delivery-observation.ts", import.meta.url)
const specUrl = new URL("./push-delivery.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./native-push-profile-fixtures.ts", import.meta.url)

function reportInChild(calls) {
  const childSource =
    "import { reportLivePushDeliveryObservation } from " +
    JSON.stringify(helperUrl.href) +
    ";\n" +
    calls
  const result = spawnSync(process.execPath, ["--input-type=module", "--eval", childSource], {
    encoding: "utf8",
  })
  assert.equal(result.status, 0, "the diagnostic must not throw")
  assert.equal(result.stderr, "", "the diagnostic writes no raw errors to stderr")
  return result.stdout
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
  assert.match(helper, /normalizeObservation\(await observe/u)

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
  assert.match(helper, /navigator\.serviceWorker\.ready/u)
  assert.match(helper, /navigator\.serviceWorker\.getRegistration\(\)/u)
  assert.match(helper, /registration\.getNotifications\(\)/u)
  assert.match(helper, /Notification\.permission/u)
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
    "const page = { evaluate: async (probe, options) => {\n" +
      "  if (typeof probe !== 'function' || !options || options.expectedTag !== " +
      JSON.stringify(privateId) +
      " || options.budgetMs !== 1200) throw new Error('private-probe-failure');\n" +
      "  return { permission: 'granted', ready: 'resolved', state: 'activated', " +
      "controller: true, subscription: true, matches: 0 };\n" +
      "} };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', " +
      JSON.stringify(privateId) +
      ");\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V1 project=desktop permission=granted ready=resolved " +
      "state=activated controller=1 subscription=1 matches=0\n"
  )
  assert.doesNotMatch(output, /private-notification-identity|private-probe-failure/u)
})

test("push observation snapshots accessor values once before formatting", () => {
  const output = reportInChild(
    "let permissionReads = 0;\n" +
      "const changing = { get permission() { permissionReads += 1; " +
      "return permissionReads === 1 ? 'granted' : 'private-value'; }, " +
      "ready: 'resolved', state: 'activated', controller: true, " +
      "subscription: true, matches: 1 };\n" +
      "const page = { evaluate: async () => changing };\n" +
      "await reportLivePushDeliveryObservation(page, 'mobile', 'private-id');\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V1 project=mobile permission=granted ready=resolved " +
      "state=activated controller=1 subscription=1 matches=1\n"
  )
  assert.doesNotMatch(output, /private-value|private-id/u)
})
test("push observation rejects invalid domains and private values without coercion", () => {
  const output = reportInChild(
    "const page = { evaluate: async () => ({ permission: 'granted', ready: 'resolved', " +
      "state: 'activated', controller: true, subscription: true, matches: 0 }) };\n" +
      "const privateValue = { toString() { throw new Error('private-value'); } };\n" +
      "await reportLivePushDeliveryObservation(page, 'private-project', 'private-id');\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', privateValue);\n" +
      "const invalidPage = { evaluate: async () => ({ permission: privateValue, " +
      "ready: 'resolved', state: 'activated', controller: true, subscription: true, matches: 2 }) };\n" +
      "await reportLivePushDeliveryObservation(invalidPage, 'mobile', 'private-id');\n"
  )
  assert.equal(output, "")
  assert.doesNotMatch(output, /private-value|private-id/u)
})

test("push observation deduplicates and caps output at four records", () => {
  const output = reportInChild(
    "const permissions = ['default', 'granted', 'denied', 'unsupported', 'default'];\n" +
      "const page = { evaluate: async (_probe, options) => ({ permission: options.expectedTag, " +
      "ready: 'timeout', state: 'missing', controller: false, subscription: false, matches: 0 }) };\n" +
      "for (const permission of permissions) await reportLivePushDeliveryObservation(page, 'mobile', permission);\n"
  )
  assert.equal(
    output,
    [
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=default ready=timeout state=missing controller=0 subscription=0 matches=0\n",
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=granted ready=timeout state=missing controller=0 subscription=0 matches=0\n",
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=denied ready=timeout state=missing controller=0 subscription=0 matches=0\n",
      "UE_LIVE_PUSH_OBS_V1 project=mobile permission=unsupported ready=timeout state=missing controller=0 subscription=0 matches=0\n",
    ].join("")
  )
})

test("push observation safely reports only fallback enums when browser evaluation rejects", () => {
  const output = reportInChild(
    "const page = { evaluate: async () => { throw new Error('private URL and token'); } };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n"
  )
  assert.equal(
    output,
    "UE_LIVE_PUSH_OBS_V1 project=desktop permission=unsupported ready=timeout " +
      "state=error controller=0 subscription=0 matches=0\n"
  )
  assert.doesNotMatch(output, /private|token/u)
})

test("a stdout failure cannot replace the push delivery assertion", () => {
  const output = reportInChild(
    "const page = { evaluate: async () => ({ permission: 'denied', ready: 'error', " +
      "state: 'error', controller: false, subscription: false, matches: 0 }) };\n" +
      "process.stdout.write = () => { throw new Error('private-write-error'); };\n" +
      "await reportLivePushDeliveryObservation(page, 'desktop', 'private-id');\n"
  )
  assert.equal(output, "")
})
