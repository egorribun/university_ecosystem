import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import {
  assertRegistrationWaitFits,
  computeRegistrationWaitMs,
  readPlaywrightTestSlotDeadlineAtMs,
  REGISTRATION_CADENCE_MS,
  REGISTRATION_MAX_TEST_TIMEOUT_MS,
  REGISTRATION_MAX_COST,
  REGISTRATION_UNKNOWN_DRAIN_MS,
  REGISTRATION_WINDOW_MS,
  resolveLiveRegistrationStateRoot,
  validateRegistrationLedger,
} from "./live-registration-admission.mjs"

const OWNER = "a".repeat(64)

function makeLedger({ updatedAtMs = 0, pending = null, events = [], ownerBinding = OWNER } = {}) {
  return { version: 1, ownerBinding, updatedAtMs, pending, events }
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
