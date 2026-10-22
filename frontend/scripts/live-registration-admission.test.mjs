import assert from "node:assert/strict"
import { createHash, randomUUID } from "node:crypto"
import { EventEmitter } from "node:events"
import { mkdtemp, mkdir, realpath, rm, writeFile } from "node:fs/promises"
import test from "node:test"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import {
  assertRegistrationWaitFits,
  computeRegistrationWaitMs,
  readPlaywrightTestSlotDeadlineAtMs,
  runLiveRegistrationAdmission,
  REGISTRATION_CADENCE_MS,
  REGISTRATION_MAX_TEST_TIMEOUT_MS,
  REGISTRATION_MAX_COST,
  REGISTRATION_UNKNOWN_DRAIN_MS,
  REGISTRATION_WINDOW_MS,
  resolveLiveRegistrationStateRoot,
  validateRegistrationLedger,
  waitForTrackedRequests,
} from "./live-registration-admission.mjs"

const OWNER = "a".repeat(64)

function makeLedger({ updatedAtMs = 0, pending = null, events = [], ownerBinding = OWNER } = {}) {
  return { version: 1, ownerBinding, updatedAtMs, pending, events }
}

function makeControlledTimerQueue() {
  let nextId = 0
  const timers = new Map()
  const cleared = []
  const delays = []
  return {
    cleared,
    delays,
    timers,
    schedule(callback, delayMs) {
      const id = ++nextId
      timers.set(id, { id, callback, delayMs })
      delays.push(delayMs)
      return id
    },
    clear(id) {
      cleared.push(id)
      timers.delete(id)
    },
    fireNext() {
      const next = timers.entries().next().value
      assert.ok(next, "expected a scheduled request-drain timer")
      const [id, timer] = next
      timers.delete(id)
      timer.callback()
      return timer
    },
  }
}
test("registration wait is based on request completion time", () => {
  const completedAtMs = 42_000
  const nowMs = completedAtMs + 1_000
  const waitMs = computeRegistrationWaitMs([{ completedAtMs, cost: 1 }], 1, nowMs)
  assert.equal(waitMs, REGISTRATION_CADENCE_MS - 1_000)
})

test("rolling-window admission allows a request exactly at the 60-second boundary", () => {
  const waitMs = computeRegistrationWaitMs(
    [{ completedAtMs: 10_000, cost: 1 }],
    1,
    10_000 + REGISTRATION_WINDOW_MS
  )
  assert.equal(waitMs, 0)
})

test("weighted double registration waits for enough rolling capacity", () => {
  const events = [0, 13_000, 26_000, 39_000].map((completedAtMs) => ({
    completedAtMs,
    cost: 1,
  }))
  assert.equal(computeRegistrationWaitMs(events, 2, 40_000), 20_000)
  assert.equal(REGISTRATION_MAX_COST, 5)
})

test("already-completed events survive a JSON round trip across invocations", () => {
  const original = makeLedger({
    updatedAtMs: 70_000,
    events: [
      { completedAtMs: 20_000, cost: 2 },
      { completedAtMs: 33_000, cost: 1 },
    ],
  })
  const persisted = JSON.parse(JSON.stringify(original))
  const resumed = validateRegistrationLedger(persisted, OWNER, 70_000)
  assert.deepEqual(resumed.events, original.events)
  assert.equal(computeRegistrationWaitMs(resumed.events, 2, 34_000), 12_000)
})

test("an unresolved prior request requires the full quiet drain", () => {
  const startedAtMs = 5_000
  const resumed = validateRegistrationLedger(
    makeLedger({
      updatedAtMs: startedAtMs,
      pending: { startedAtMs, cost: 2 },
    }),
    OWNER,
    startedAtMs + 1_000
  )
  assert.deepEqual(resumed.pending, { startedAtMs, cost: 2 })
  assert.equal(REGISTRATION_UNKNOWN_DRAIN_MS, REGISTRATION_WINDOW_MS)
})

test("deadline fit preserves action reserve and rejects an over-budget wait", () => {
  assert.equal(assertRegistrationWaitFits(44_000, 60_000, 0), 60_000)
  assert.throws(
    () => assertRegistrationWaitFits(44_001, 60_000, 0),
    /cannot fit the existing test deadline/u
  )
})

test("pinned TestInfo slot deadline is translated into the local performance clock", () => {
  const localBeforeMs = 12_345
  const playwrightNowMs = 50_000
  const localAfterMs = localBeforeMs + 0.25
  const sampleClockPair = () => ({ localBeforeMs, playwrightNowMs, localAfterMs })
  const makeTestInfo = (timeout) => ({
    timeout,
    _deadline() {
      return { deadline: playwrightNowMs + timeout - 250, timeout }
    },
  })

  for (const timeout of [210_000, 360_000]) {
    const testInfo = makeTestInfo(timeout)
    assert.equal("startTime" in testInfo, false)
    assert.equal(
      readPlaywrightTestSlotDeadlineAtMs(
        testInfo,
        REGISTRATION_MAX_TEST_TIMEOUT_MS,
        sampleClockPair
      ),
      localBeforeMs + timeout - 250
    )
  }
  assert.equal(
    readPlaywrightTestSlotDeadlineAtMs(
      makeTestInfo(360_001),
      REGISTRATION_MAX_TEST_TIMEOUT_MS,
      sampleClockPair
    ),
    null
  )
})

test("pinned TestInfo deadline clock translation remains fail closed", () => {
  const timeout = 1_000
  const localBeforeMs = 100
  const localAfterMs = 100.25
  const playwrightNowMs = 500
  const sample =
    (values = {}) =>
    () => ({
      localBeforeMs,
      playwrightNowMs,
      localAfterMs,
      ...values,
    })
  const makeTestInfo = (deadline, slotTimeout = timeout) => ({
    timeout,
    _deadline() {
      return { deadline, timeout: slotTimeout }
    },
  })
  const read = (deadline, slotTimeout, clock) =>
    readPlaywrightTestSlotDeadlineAtMs(makeTestInfo(deadline, slotTimeout), timeout, clock)

  assert.equal(read(playwrightNowMs + timeout + 1, timeout, sample()), localBeforeMs + timeout + 1)
  assert.equal(read(playwrightNowMs + timeout + 1.001, timeout, sample()), null)
  assert.equal(read(playwrightNowMs, timeout, sample()), null)
  assert.equal(read(playwrightNowMs + 500, timeout - 1, sample()), null)
  assert.equal(read(playwrightNowMs + 500, timeout, sample({ playwrightNowMs: Number.NaN })), null)
  assert.equal(
    read(playwrightNowMs + 0.1, timeout, sample({ localAfterMs: localBeforeMs + 0.2 })),
    null
  )
})

test("ledger owner binding mismatch fails closed", () => {
  assert.throws(
    () => validateRegistrationLedger(makeLedger(), "b".repeat(64), 0),
    /owner does not match/u
  )
})

test("malformed and over-budget persisted events fail closed", () => {
  const malformed = makeLedger({
    events: [{ completedAtMs: 0, cost: 1, requestUrl: "https://invalid.example/" }],
  })
  assert.throws(() => validateRegistrationLedger(malformed, OWNER, 0), /malformed event/u)

  const overBudget = makeLedger({
    updatedAtMs: 2,
    events: [
      { completedAtMs: 0, cost: 2 },
      { completedAtMs: 1, cost: 2 },
      { completedAtMs: 2, cost: 2 },
    ],
  })
  assert.throws(
    () => validateRegistrationLedger(overBudget, OWNER, 2),
    /exceeds its rolling budget/u
  )
})

test("timestamps beyond the bounded clock-skew allowance fail closed", () => {
  const future = makeLedger({
    updatedAtMs: 6_000,
    events: [{ completedAtMs: 6_000, cost: 1 }],
  })
  assert.throws(() => validateRegistrationLedger(future, OWNER, 0), /out-of-range/u)
})

test("state root resolution distinguishes verified in-place and legacy modes", () => {
  const base = process.cwd()
  const primary = `${base}/primary`
  const worktree = `${base}/owned-worktree`
  const state = `${base}/run-state`
  assert.equal(
    resolveLiveRegistrationStateRoot(
      { LIVE_PRIMARY_REPOSITORY_ROOT: primary, LIVE_STAND_STATE_ROOT: state },
      primary,
      "win32"
    ),
    resolve(state)
  )
  assert.equal(
    resolveLiveRegistrationStateRoot({ LIVE_PRIMARY_REPOSITORY_ROOT: primary }, worktree, "win32"),
    resolve(worktree)
  )
  assert.throws(
    () =>
      resolveLiveRegistrationStateRoot(
        { LIVE_PRIMARY_REPOSITORY_ROOT: worktree, LIVE_STAND_STATE_ROOT: state },
        primary,
        "win32"
      ),
    /invalid in-place owner binding/u
  )
})

test("tracked-request drain rechecks an early timer and accepts completion", async () => {
  let nowMs = 0
  const timerQueue = makeControlledTimerQueue()
  const activeRequests = new Set(["registration"])
  const changed = []
  const waiting = waitForTrackedRequests(activeRequests, changed, 10_000, {
    now: () => nowMs,
    scheduleTimer: timerQueue.schedule,
    clearTimer: timerQueue.clear,
  })

  const initialTimer = timerQueue.fireNext()
  assert.equal(initialTimer.delayMs, 9_000)
  const rearmedTimer = timerQueue.timers.values().next().value
  assert.equal(rearmedTimer.delayMs, 1_000)
  assert.equal(changed.length, 1)

  activeRequests.clear()
  const onChanged = changed[0]
  onChanged()
  assert.equal(await waiting, true)
  onChanged()
  assert.deepEqual(timerQueue.cleared, [rearmedTimer.id])
  assert.equal(timerQueue.timers.size, 0)
  assert.equal(changed.length, 0)
})

test("a queued drain timer callback stays inert after request completion", async () => {
  let nowMs = 0
  const timerQueue = makeControlledTimerQueue()
  const activeRequests = new Set(["registration"])
  const changed = []
  const waiting = waitForTrackedRequests(activeRequests, changed, 10_000, {
    now: () => nowMs,
    scheduleTimer: timerQueue.schedule,
    clearTimer: timerQueue.clear,
  })
  const queuedTimer = timerQueue.timers.values().next().value
  assert.ok(queuedTimer)
  const queuedCallback = queuedTimer.callback
  const resolutionValues = []
  waiting.then((value) => resolutionValues.push(value))

  activeRequests.clear()
  const onChanged = changed[0]
  assert.equal(typeof onChanged, "function")
  onChanged()
  assert.equal(await waiting, true)
  assert.deepEqual(timerQueue.cleared, [queuedTimer.id])
  assert.equal(timerQueue.timers.size, 0)
  assert.equal(changed.length, 0)

  queuedCallback()
  queuedCallback()
  await Promise.resolve()
  assert.equal(timerQueue.timers.size, 0)
  assert.equal(changed.length, 0)
  assert.deepEqual(resolutionValues, [true])
})
test("tracked-request drain expires at the original deadline margin", async () => {
  let nowMs = 0
  const timerQueue = makeControlledTimerQueue()
  const activeRequests = new Set(["registration"])
  const changed = []
  const waiting = waitForTrackedRequests(activeRequests, changed, 10_000, {
    now: () => nowMs,
    scheduleTimer: timerQueue.schedule,
    clearTimer: timerQueue.clear,
  })

  const initialTimer = timerQueue.fireNext()
  assert.equal(initialTimer.delayMs, 9_000)
  const rearmedTimer = timerQueue.timers.values().next().value
  assert.equal(rearmedTimer.delayMs, 1_000)
  nowMs = 9_000
  assert.equal(timerQueue.fireNext().id, rearmedTimer.id)
  assert.equal(await waiting, false)
  assert.equal(activeRequests.size, 1)
  assert.equal(timerQueue.delays.length, 2)
  assert.equal(timerQueue.timers.size, 0)
  assert.equal(changed.length, 0)
})

test("tracked-request drain bounds repeated early timer callbacks", async () => {
  let nowMs = 0
  const timerQueue = makeControlledTimerQueue()
  const activeRequests = new Set(["registration"])
  const changed = []
  const waiting = waitForTrackedRequests(activeRequests, changed, 10_000, {
    now: () => nowMs,
    scheduleTimer: timerQueue.schedule,
    clearTimer: timerQueue.clear,
  })

  assert.equal(timerQueue.fireNext().delayMs, 9_000)
  nowMs = 1
  assert.equal(timerQueue.fireNext().delayMs, 1_000)
  assert.equal(await waiting, false)
  assert.equal(activeRequests.size, 1)
  assert.deepEqual(timerQueue.delays, [9_000, 1_000])
  assert.equal(timerQueue.timers.size, 0)
  assert.equal(changed.length, 0)
})
test("an early request-drain timer callback does not fail before the test deadline", async () => {
  const baseUrl = "http://127.0.0.1:43127"
  const repositoryRoot = await realpath(fileURLToPath(new URL("../../", import.meta.url)))
  const stateRoot = await mkdtemp(join(tmpdir(), "ue-registration-drain-test-"))
  const secretsDirectory = join(stateRoot, ".secrets")
  const ledgerDirectory = join(secretsDirectory, ".live-registration-admission")
  const ownerProject = "ue-live-" + randomUUID().replaceAll("-", "").slice(0, 16)
  const ownerVersion = 3
  const comparablePath = (value) => {
    const absolute = resolve(value)
    return process.platform === "win32" ? absolute.toLowerCase() : absolute
  }
  const realStateRoot = await realpath(stateRoot)
  const ownerBinding = createHash("sha256")
    .update(
      JSON.stringify([
        ownerVersion,
        comparablePath(repositoryRoot),
        comparablePath(realStateRoot),
        ownerProject,
      ]),
      "utf8"
    )
    .digest("hex")
  const ownerMarker = {
    version: ownerVersion,
    repository: repositoryRoot,
    worktree: realStateRoot,
    project_name: ownerProject,
    signature: "a".repeat(64),
  }
  await mkdir(secretsDirectory, { mode: 0o700 })
  await mkdir(ledgerDirectory, { mode: 0o700 })
  await writeFile(join(secretsDirectory, "live-stand.json"), JSON.stringify(ownerMarker) + "\n", {
    mode: 0o600,
  })
  await writeFile(
    join(ledgerDirectory, "ledger.json"),
    JSON.stringify({
      version: 1,
      ownerBinding,
      updatedAtMs: Date.now(),
      pending: null,
      events: [],
    }) + "\n",
    { mode: 0o600 }
  )

  const baseEnvironment = {
    LIVE_BASE_URL: process.env.LIVE_BASE_URL,
    LIVE_PRIMARY_REPOSITORY_ROOT: process.env.LIVE_PRIMARY_REPOSITORY_ROOT,
    LIVE_STAND_STATE_ROOT: process.env.LIVE_STAND_STATE_ROOT,
  }
  const nativeSetTimeout = globalThis.setTimeout
  const page = new EventEmitter()
  page.url = () => baseUrl + "/register"
  let injectedEarlyTimer = false
  let requestScheduled = false
  let settleRequest
  const requestCompleted = new Promise((resolvePromise) => {
    settleRequest = resolvePromise
  })

  try {
    process.env.LIVE_BASE_URL = baseUrl
    process.env.LIVE_PRIMARY_REPOSITORY_ROOT = repositoryRoot
    process.env.LIVE_STAND_STATE_ROOT = stateRoot
    globalThis.setTimeout = (callback, delay, ...args) => {
      if (!injectedEarlyTimer && typeof delay === "number" && delay > 1_000) {
        injectedEarlyTimer = true
        return nativeSetTimeout(callback, 0, ...args)
      }
      return nativeSetTimeout(callback, delay, ...args)
    }

    const result = await runLiveRegistrationAdmission(
      page,
      performance.now() + 30_000,
      1,
      async () => {
        const request = {
          method: () => "POST",
          url: () => baseUrl + "/api/v1/auth/register",
        }
        page.emit("request", request)
        requestScheduled = true
        nativeSetTimeout(() => {
          page.emit("requestfinished", request)
          settleRequest()
        }, 25)
        return "clicked"
      }
    )

    assert.equal(injectedEarlyTimer, true)
    assert.equal(result, "clicked")
  } finally {
    globalThis.setTimeout = nativeSetTimeout
    if (requestScheduled) await requestCompleted
    page.removeAllListeners()
    for (const [key, previousValue] of Object.entries(baseEnvironment)) {
      if (previousValue === undefined) delete process.env[key]
      else process.env[key] = previousValue
    }
    await rm(stateRoot, { recursive: true, force: true })
  }
})
