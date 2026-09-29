import assert from "node:assert/strict"
import * as fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { execFileSync } from "node:child_process"
import test from "node:test"
import { createStrykerProgressReporter } from "./stryker-progress-reporter.mjs"

// Missing implementation is an explicit assertion failure during RED, not an import error.
const api = await import("./stryker-progress-monitor.mjs").catch((error) => {
  if (error.code === "ERR_MODULE_NOT_FOUND") return {}
  throw error
})
const identity = { runId: "run-1", shardId: "shard-1" }
const initial = () => ({
  schemaVersion: 1,
  ...identity,
  phase: "initializing",
  sequence: 0,
  updatedAtMs: 100,
  plannedMutants: null,
  completedMutants: 0,
  reportReady: false,
  informational: true,
  releaseEligible: false,
})
const planned = () => ({ ...initial(), phase: "plan-ready", sequence: 2, plannedMutants: 2 })
const complete = () => ({
  ...planned(),
  phase: "wrapped-up",
  sequence: 6,
  completedMutants: 2,
  reportReady: true,
})
const genericError = (code) => (error) => {
  assert.equal(error.code, code)
  assert.equal(error.message, "Invalid Stryker progress")
  assert.equal(error.cause, undefined)
  return true
}

function fixture(t) {
  assert.equal(typeof api.readProgressSnapshot, "function", "snapshot reader must exist")
  assert.equal(typeof api.createStrykerProgressMonitor, "function", "monitor must exist")
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "stryker-monitor-"))
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  const outputPath = path.join(directory, "progress.json")
  let time = 0
  const options = { outputPath, ...identity }
  const monitor = api.createStrykerProgressMonitor(options, { now: () => time })
  return {
    directory,
    outputPath,
    options,
    monitor,
    tick: (value) => (time = value),
    write: (value) => fs.writeFileSync(outputPath, JSON.stringify(value)),
    read: () => api.readProgressSnapshot(outputPath, identity),
  }
}

test("reads actual reporter output and follows its terminal lifecycle", (t) => {
  const f = fixture(t)
  const reporter = createStrykerProgressReporter(
    {
      enabled: true,
      ownedDirectory: f.directory,
      ...f.options,
    },
    { now: () => 100 }
  )
  t.after(() => reporter.wrapUp())
  assert.deepEqual(f.read(), initial())
  assert.equal(f.monitor.observe().completionAdvanced, false)
  reporter.onDryRunCompleted({})
  reporter.onMutationTestingPlanReady({ mutantPlans: ["1", "2"].map((id) => ({ mutant: { id } })) })
  f.tick(10)
  assert.equal(f.monitor.observe().phaseAdvanced, true)
  reporter.onMutantTested({ id: "1", status: "Killed" })
  f.tick(20)
  const progress = f.monitor.observe()
  assert.equal(progress.completionAdvanced, true)
  assert.equal(progress.lastCompletionAtMs, 20)
  reporter.onMutantTested({ id: "1", status: "Survived" })
  f.tick(30)
  assert.equal(f.monitor.observe().completionAdvanced, false)
  reporter.onMutantTested({ id: "2", status: "Timeout" })
  reporter.onMutationTestReportReady({}, {})
  reporter.wrapUp()
  f.tick(40)
  assert.equal(f.monitor.validateExit(0).reportReady, true)
  assert.equal(f.monitor.failed, false)
})

test("missing startup is observational, but missing exit-zero output is failure", (t) => {
  const f = fixture(t)
  assert.equal(f.read(), null)
  assert.equal(f.monitor.observe().snapshot, null)
  assert.equal(f.monitor.failed, false)
  assert.throws(() => f.monitor.validateExit(0), genericError("STRYKER_PROGRESS_INCOMPLETE"))
  assert.equal(f.monitor.failed, true)
})

test("unchanged snapshots and producer timestamps never fabricate completion or parent time", (t) => {
  const f = fixture(t)
  f.write(planned())
  f.monitor.observe()
  f.tick(1_000_000)
  const observation = f.monitor.observe()
  assert.equal(observation.completionAdvanced, false)
  assert.equal(observation.phaseAdvanced, false)
  assert.equal(observation.lastCompletionAtMs, null)
  assert.equal(observation.observedAtMs, 1_000_000)
})

for (const [label, value] of [
  ["array", []],
  ["null", null],
  ["extra key", { ...initial(), fileName: "private" }],
  ["missing key", Object.fromEntries(Object.entries(initial()).filter(([key]) => key !== "phase"))],
  ["foreign run", { ...initial(), runId: "other" }],
  ["foreign shard", { ...initial(), shardId: "other" }],
  ["proof claim", { ...initial(), releaseEligible: true }],
  ["not informational", { ...initial(), informational: false }],
  ["bad version", { ...initial(), schemaVersion: 2 }],
  ["unsafe counter", { ...planned(), sequence: Number.MAX_SAFE_INTEGER + 1 }],
  ["negative counter", { ...planned(), completedMutants: -1 }],
  ["fractional counter", { ...planned(), completedMutants: 0.5 }],
  ["unbounded plan", { ...planned(), plannedMutants: 1_000_001 }],
  ["count exceeds plan", { ...planned(), completedMutants: 3 }],
  ["unknown phase", { ...initial(), phase: "success" }],
  ["early readiness", { ...initial(), reportReady: true }],
  ["unplanned mutation", { ...initial(), phase: "mutation-testing", sequence: 1 }],
  ["noninteger producer time", { ...initial(), updatedAtMs: 0.5 }],
]) {
  test(`rejects ${label} with a path-free error`, (t) => {
    const f = fixture(t)
    f.write(value)
    assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
  })
}

test("rejects malformed, oversized and nonregular files without reading unbounded data", (t) => {
  const f = fixture(t)
  fs.writeFileSync(f.outputPath, "private malformed JSON")
  assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
  fs.writeFileSync(f.outputPath, " ".repeat(4097))
  assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
  fs.unlinkSync(f.outputPath)
  fs.mkdirSync(f.outputPath)
  assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
})

test("rejects symbolic-link output including dangling links", (t) => {
  const f = fixture(t)
  const target = path.join(f.directory, "target.json")
  fs.writeFileSync(target, JSON.stringify(initial()))
  try {
    fs.symlinkSync(target, f.outputPath)
  } catch (error) {
    if (error.code !== "EPERM") throw error
    t.skip("Host does not permit creating symbolic links")
    return
  }
  assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
  fs.unlinkSync(target)
  assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
})

test(
  "rejects POSIX FIFO output before opening a blocking stream",
  { skip: process.platform === "win32" },
  (t) => {
    const f = fixture(t)
    execFileSync("mkfifo", [f.outputPath], { timeout: 2000 })
    assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
  }
)

for (const [label, mutate] of [
  ["sequence regression", (s) => ({ ...s, sequence: 1 })],
  [
    "completion regression",
    (s) => ({ ...s, sequence: 4, completedMutants: 0, phase: "plan-ready" }),
  ],
  ["phase regression", (s) => ({ ...s, sequence: 4, phase: "plan-ready", completedMutants: 0 })],
  ["plan replacement", (s) => ({ ...s, sequence: 4, plannedMutants: 3 })],
  ["timestamp regression", (s) => ({ ...s, sequence: 4, updatedAtMs: 99 })],
  ["same-sequence replacement", (s) => ({ ...s, updatedAtMs: 101 })],
  ["meaningless sequence bump", (s) => ({ ...s, sequence: 4 })],
]) {
  test(`latches ${label} and cannot heal after replacement`, (t) => {
    const f = fixture(t)
    const first = { ...planned(), phase: "mutation-testing", sequence: 3, completedMutants: 1 }
    f.write(first)
    f.monitor.observe()
    f.write(mutate(first))
    let failure
    assert.throws(
      () => f.monitor.observe(),
      (error) => {
        failure = error
        return genericError("STRYKER_PROGRESS_INVALID")(error)
      }
    )
    f.write(complete())
    assert.throws(
      () => f.monitor.validateExit(0),
      (error) => error === failure
    )
    assert.equal(f.monitor.failed, true)
  })
}

test("identity is captured rather than retained as mutable caller options", (t) => {
  const f = fixture(t)
  f.options.runId = "other"
  f.options.outputPath = path.join(f.directory, "other.json")
  f.write(initial())
  assert.equal(f.monitor.observe().snapshot.runId, identity.runId)
})

test("accepted snapshots are frozen and cannot mutate monitor history", (t) => {
  const f = fixture(t)
  f.write(planned())
  const accepted = f.monitor.observe().snapshot
  assert.equal(Object.isFrozen(accepted), true)
  assert.throws(() => (accepted.completedMutants = 100), TypeError)
  assert.equal(f.monitor.observe().completionAdvanced, false)
})

test("rejects invalid or backwards parent clocks without using producer time", (t) => {
  for (const clock of [NaN, Infinity, -1]) {
    const f = fixture(t)
    f.write(initial())
    f.tick(clock)
    assert.throws(() => f.monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
  }
  const f = fixture(t)
  f.write(initial())
  f.tick(20)
  f.monitor.observe()
  f.tick(19)
  assert.throws(() => f.monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
})

test("zero exit requires wrapped-up readiness, never upgrades nonzero child exit", (t) => {
  for (const snapshot of [
    initial(),
    planned(),
    { ...planned(), phase: "report-ready", sequence: 3, reportReady: true },
    { ...planned(), phase: "wrapped-up", sequence: 3 },
  ]) {
    const f = fixture(t)
    f.write(snapshot)
    assert.throws(() => f.monitor.validateExit(0), genericError("STRYKER_PROGRESS_INCOMPLETE"))
  }
  const f = fixture(t)
  f.write(complete())
  assert.throws(() => f.monitor.validateExit(1), genericError("STRYKER_PROGRESS_CHILD_FAILED"))
  assert.equal(f.monitor.failed, true)
})

test("report-ready never requires fabricated counts or claims mutation quality", (t) => {
  const f = fixture(t)
  f.write({ ...complete(), completedMutants: 1, sequence: 5 })
  const terminal = f.monitor.validateExit(0)
  assert.equal(terminal.completedMutants, 1)
  assert.equal(terminal.plannedMutants, 2)
  assert.equal(terminal.releaseEligible, false)
})

test("permits reporter lifecycle skips without treating an unplanned final report as valid exit zero", (t) => {
  const f = fixture(t)
  f.write({ ...initial(), phase: "report-ready", sequence: 1, reportReady: true })
  assert.equal(f.monitor.observe().snapshot.plannedMutants, null)
  f.write({ ...initial(), phase: "wrapped-up", sequence: 2, reportReady: true })
  assert.equal(f.monitor.observe().snapshot.phase, "wrapped-up")
  assert.throws(() => f.monitor.validateExit(0), genericError("STRYKER_PROGRESS_INCOMPLETE"))
})

for (const phase of ["report-ready", "wrapped-up"]) {
  test(`cannot add completions after ${phase}`, (t) => {
    const f = fixture(t)
    const snapshot = { ...complete(), phase, completedMutants: 1, sequence: 5 }
    f.write(snapshot)
    f.monitor.observe()
    f.write({ ...snapshot, completedMutants: 2, sequence: 6 })
    assert.throws(() => f.monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
  })
}

test("observation never exposes injected clock errors or their private causes", (t) => {
  const f = fixture(t)
  const monitor = api.createStrykerProgressMonitor(f.options, {
    now: () => {
      throw new Error("Invalid Stryker progress", { cause: new Error("private/path") })
    },
  })
  assert.throws(() => monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
})

test("a report without a plan cannot acquire a plan during wrap-up", (t) => {
  const f = fixture(t)
  f.write({ ...initial(), phase: "report-ready", sequence: 1, reportReady: true })
  f.monitor.observe()
  f.write({ ...initial(), phase: "wrapped-up", sequence: 2, reportReady: true, plannedMutants: 0 })
  assert.throws(() => f.monitor.validateExit(0), genericError("STRYKER_PROGRESS_INVALID"))
})

test("completion growth cannot exceed the number of reporter events", (t) => {
  const f = fixture(t)
  const snapshot = {
    ...planned(),
    plannedMutants: 10,
    phase: "mutation-testing",
    sequence: 3,
    completedMutants: 1,
  }
  f.write(snapshot)
  f.monitor.observe()
  f.write({ ...snapshot, sequence: 4, completedMutants: 3 })
  assert.throws(() => f.monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
})

test("a first snapshot cannot claim more completions than its event sequence", (t) => {
  const f = fixture(t)
  f.write({ ...planned(), phase: "mutation-testing", sequence: 1, completedMutants: 2 })
  assert.throws(f.read, genericError("STRYKER_PROGRESS_INVALID"))
})

test("missing output after acceptance cannot reset the monotonic history", (t) => {
  const f = fixture(t)
  f.write(initial())
  f.monitor.observe()
  fs.unlinkSync(f.outputPath)
  assert.throws(() => f.monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
})

test("invalid monitor options fail before touching output", (t) => {
  const f = fixture(t)
  for (const override of [{ runId: "../secret" }, { shardId: "" }, { outputPath: "relative" }]) {
    assert.throws(
      () => api.createStrykerProgressMonitor({ ...f.options, ...override }),
      genericError("STRYKER_PROGRESS_INVALID")
    )
  }
  assert.deepEqual(fs.readdirSync(f.directory), [])
})

function replacingFs(f, replacement, repeat = false) {
  const descriptors = new Set()
  let opens = 0
  const injectedFs = {
    ...fs,
    openSync(target, flags) {
      opens++
      if (repeat || opens === 1) {
        const temporary = path.join(f.directory, `replacement-${opens}.json`)
        fs.writeFileSync(temporary, JSON.stringify(replacement))
        fs.renameSync(temporary, f.outputPath)
      }
      const descriptor = fs.openSync(target, flags)
      descriptors.add(descriptor)
      return descriptor
    },
    closeSync(descriptor) {
      fs.closeSync(descriptor)
      descriptors.delete(descriptor)
    },
  }
  return { fs: injectedFs, descriptors, opens: () => opens }
}

test("retries legitimate atomic reporter replacement between lstat and open", (t) => {
  const f = fixture(t)
  f.write(initial())
  const replacement = { ...initial(), phase: "dry-run-completed", sequence: 1 }
  const seam = replacingFs(f, replacement)
  const monitor = api.createStrykerProgressMonitor(f.options, { now: () => 10, fs: seam.fs })
  const observation = monitor.observe()
  assert.equal(observation.snapshot.phase, replacement.phase)
  assert.equal(observation.completionAdvanced, false)
  assert.equal(seam.opens(), 2)
  assert.equal(seam.descriptors.size, 0)
  assert.equal(monitor.failed, false)
})

test("persistent identity races have bounded attempts and close every acquired descriptor", (t) => {
  const f = fixture(t)
  f.write(initial())
  const seam = replacingFs(f, initial(), true)
  const monitor = api.createStrykerProgressMonitor(f.options, { now: () => 10, fs: seam.fs })
  assert.throws(() => monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
  assert.equal(seam.opens(), 3)
  assert.equal(seam.descriptors.size, 0)
  assert.equal(monitor.failed, true)
  assert.throws(() => monitor.observe(), genericError("STRYKER_PROGRESS_INVALID"))
  assert.equal(seam.opens(), 3)
})

test("identity-race retry still rejects wrong-run replacement rather than reading a stale original", (t) => {
  const f = fixture(t)
  f.write(initial())
  const seam = replacingFs(f, { ...initial(), runId: "foreign" })
  assert.throws(
    () => api.readProgressSnapshot(f.outputPath, identity, { fs: seam.fs }),
    genericError("STRYKER_PROGRESS_INVALID")
  )
  assert.equal(seam.opens(), 2)
  assert.equal(seam.descriptors.size, 0)
})

test("descriptor close failure stops identity-race retries and latches the first error", (t) => {
  const f = fixture(t)
  f.write(initial())
  const seam = replacingFs(f, initial(), true)
  const close = seam.fs.closeSync
  let closes = 0
  seam.fs.closeSync = (descriptor) => {
    closes++
    close(descriptor)
    throw new Error("private close failure")
  }
  const monitor = api.createStrykerProgressMonitor(f.options, { fs: seam.fs })
  let first
  assert.throws(
    () => monitor.observe(),
    (error) => {
      first = error
      return genericError("STRYKER_PROGRESS_INVALID")(error)
    }
  )
  assert.equal(seam.opens(), 1)
  assert.equal(closes, 1)
  assert.equal(seam.descriptors.size, 0)
  assert.throws(
    () => monitor.validateExit(1),
    (error) => error === first
  )
  assert.equal(seam.opens(), 1)
})

test("malformed snapshot is terminal without repeated descriptor acquisitions", (t) => {
  const f = fixture(t)
  fs.writeFileSync(f.outputPath, "private malformed JSON")
  let opens = 0
  let closes = 0
  const injectedFs = {
    ...fs,
    openSync(...args) {
      opens++
      return fs.openSync(...args)
    },
    closeSync(descriptor) {
      closes++
      fs.closeSync(descriptor)
    },
  }
  assert.throws(
    () => api.readProgressSnapshot(f.outputPath, identity, { fs: injectedFs }),
    genericError("STRYKER_PROGRESS_INVALID")
  )
  assert.equal(opens, 1)
  assert.equal(closes, 1)
})

test("nonregular replacement is rejected without identity-race retries", (t) => {
  const f = fixture(t)
  f.write(initial())
  let opens = 0
  let acquired = 0
  let closes = 0
  const injectedFs = {
    ...fs,
    openSync(target, flags) {
      opens++
      fs.unlinkSync(f.outputPath)
      fs.mkdirSync(f.outputPath)
      const descriptor = fs.openSync(target, flags)
      acquired++
      return descriptor
    },
    closeSync(descriptor) {
      closes++
      fs.closeSync(descriptor)
    },
  }
  assert.throws(
    () => api.readProgressSnapshot(f.outputPath, identity, { fs: injectedFs }),
    genericError("STRYKER_PROGRESS_INVALID")
  )
  assert.equal(opens, 1)
  assert.equal(closes, acquired)
})
