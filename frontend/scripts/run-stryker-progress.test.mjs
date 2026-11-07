import assert from "node:assert/strict"
import { EventEmitter } from "node:events"
import { execFile } from "node:child_process"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { promisify } from "node:util"
import { pathToFileURL } from "node:url"
import { processIsAlive } from "./run-stryker-test-helpers.mjs"
import { PRESENTATION_IGNORER } from "./stryker-presentation-ignorer.mjs"

const runnerUrl = new URL("./run-stryker.mjs", import.meta.url)
const execFileAsync = promisify(execFile)
async function progressIntegrationFixture(t) {
  const { runStrykerShardExecution } = await import(runnerUrl)
  assert.equal(
    typeof runStrykerShardExecution,
    "function",
    "actual shard execution seam must exist"
  )
  const shardTemp = await mkdtemp(path.join(os.tmpdir(), "stryker-integration-"))
  t.after(() => rm(shardTemp, { recursive: true, force: true }))
  return {
    runStrykerShardExecution,
    shardTemp,
    options: {
      args: ["existing-stryker-entry", "run"],
      description: "Stryker shard-1",
      env: { NODE_OPTIONS: "--trace-warnings", STRYKER_PROGRESS_OUTPUT: "inherited-location" },
      timeoutMs: 15_300_000,
      abortSignal: new AbortController().signal,
      shardTemp,
      runId: "run-1",
      shardId: "shard-1",
      progressEnabled: "1",
      diagnosticOutputRoot: shardTemp,
      sourceHeadSha: "a".repeat(40),
      testedSha: "b".repeat(40),
      workflowRunId: null,
      workflowRunAttempt: null,
    },
  }
}

async function liveObserverFixture(t, overrides = {}) {
  const { waitForChildClose } = await import(runnerUrl)
  const child = new EventEmitter()
  child.pid = 9876
  child.exitCode = null
  child.signalCode = null
  const controller = new AbortController()
  const timers = []
  let observations = 0
  let terminations = 0
  const ownership = { kind: "posix-process-group", rootPid: child.pid, groupId: child.pid }
  const result = waitForChildClose(child, {
    description: "live observed shard",
    timeoutMs: 15_300_000,
    abortSignal: controller.signal,
    processTreeOwnership: ownership,
    verifyProcessTree: async () => true,
    observeLive: () => {
      observations++
      return { snapshot: null, completionAdvanced: false }
    },
    terminate: async (target, owned) => {
      assert.equal(target, child)
      assert.equal(owned, ownership)
      terminations++
      return true
    },
    scheduleTimeout(callback, milliseconds) {
      const timer = {
        callback() {
          timer.cancelled = true
          callback()
        },
        milliseconds,
        cancelled: false,
      }
      timers.push(timer)
      return timer
    },
    cancelTimeout(timer) {
      timer.cancelled = true
    },
    ...overrides,
  })
  // Attach rejection handling immediately, including tests' failing RED assertions.
  void result.catch(() => undefined)
  t.after(async () => {
    child.emit("exit", 0, null)
    child.emit("close", 0, null)
    for (const timer of timers)
      if (!timer.cancelled && timer.milliseconds === 15_000) timer.callback()
    await result.catch(() => undefined)
  })
  return {
    child,
    controller,
    timers,
    result,
    get observations() {
      return observations
    },
    get terminations() {
      return terminations
    },
    tick() {
      const timer = timers.find((entry) => entry.milliseconds === 1_000 && !entry.cancelled)
      assert.ok(timer, "live observer must own a bounded polling timer")
      timer.cancelled = true
      timer.callback()
      return timer.callback
    },
  }
}

test("live observer polls missing or duplicate snapshots without inactivity termination and stops on close", async (t) => {
  const f = await liveObserverFixture(t)
  const late = f.tick()
  f.tick()
  assert.equal(f.observations, 2)
  assert.equal(f.terminations, 0)
  f.child.emit("exit", 0, null)
  f.child.emit("close", 0, null)
  await f.result
  late()
  assert.equal(f.observations, 2)
  assert.equal(
    f.timers.every((timer) => timer.cancelled),
    true
  )
  assert.equal(f.child.listenerCount("close"), 0)
})

test("live observer failure waits for existing tree termination AND child close", async (t) => {
  const failure = new Error("invalid live snapshot")
  let confirmTermination
  const confirmation = new Promise((resolve) => {
    confirmTermination = resolve
  })
  t.after(() => confirmTermination(true))
  const f = await liveObserverFixture(t, {
    observeLive: () => {
      throw failure
    },
    terminate: async () => confirmation,
  })
  let settled = false
  void f.result.catch(() => {
    settled = true
  })
  const late = f.tick()
  await Promise.resolve()
  f.child.emit("exit", null, "SIGKILL")
  f.child.emit("close", null, "SIGKILL")
  await Promise.resolve()
  assert.equal(settled, false)
  confirmTermination(true)
  await assert.rejects(f.result, (error) => error === failure && error.processQuiesced === true)
  late()
  assert.equal(
    f.timers.every((timer) => timer.cancelled),
    true
  )
})

for (const first of ["child", "abort", "timeout", "observer"]) {
  test(`live observer preserves first ${first} failure and ignores late polling`, async (t) => {
    const observerError = new Error("observer failed")
    const childError = new Error("child failed")
    const interruption = new Error("abort failed first")
    const f = await liveObserverFixture(t, {
      observeLive: () => {
        throw observerError
      },
    })
    const poll = f.timers.find((timer) => timer.milliseconds === 1_000)
    assert.ok(poll, "observer must be scheduled")
    if (first === "child") f.child.emit("error", childError)
    if (first === "abort") f.controller.abort(interruption)
    if (first === "timeout") f.timers.find((timer) => timer.milliseconds === 15_300_000).callback()
    poll.callback()
    if (first === "observer") {
      f.controller.abort(interruption)
      f.child.emit("error", childError)
    }
    f.child.emit("exit", null, "SIGKILL")
    f.child.emit("close", null, "SIGKILL")
    await assert.rejects(f.result, (error) => {
      const primary = error.cause ?? error
      if (first === "child") assert.equal(primary, childError)
      if (first === "abort") assert.equal(primary, interruption)
      if (first === "timeout") assert.match(primary.message, /exceeded 15300000ms/u)
      if (first === "observer") {
        assert.equal(primary, observerError)
        assert.equal(error.processQuiesced, false, "late child error is retained fail-closed")
        assert.equal(error.errors.includes(childError), true)
      }
      return true
    })
    assert.equal(f.terminations, 1)
    assert.equal(
      f.timers.every((timer) => timer.cancelled),
      true
    )
  })
}

for (const exitCode of [0, 7]) {
  test(`live observer error discovered after root exit ${exitCode} never signals a reusable root`, async (t) => {
    const observerError = new Error("observer after root exit")
    let f
    f = await liveObserverFixture(t, {
      observeLive: () => {
        f.child.emit("exit", exitCode, null)
        throw observerError
      },
    })
    f.tick()
    assert.equal(f.terminations, 0)
    f.child.emit("close", exitCode, null)
    await assert.rejects(f.result, (error) => {
      if (exitCode === 0) assert.equal(error, observerError)
      else {
        assert.match(error.cause.message, /exited with code 7/u)
        assert.equal(error.errors[1], observerError)
      }
      assert.equal(error.processQuiesced, true)
      return true
    })
    assert.equal(f.terminations, 0)
  })
}

test("live observer stops before post-exit quiescence verification and late callbacks stay inert", async (t) => {
  let confirmAbsent
  const absent = new Promise((resolve) => {
    confirmAbsent = resolve
  })
  t.after(() => confirmAbsent(true))
  const f = await liveObserverFixture(t, { verifyProcessTree: async () => absent })
  const poll = f.timers.find((timer) => timer.milliseconds === 1_000)
  assert.ok(poll)
  f.child.emit("exit", 0, null)
  poll.callback()
  assert.equal(f.observations, 0)
  f.child.emit("close", 0, null)
  poll.callback()
  confirmAbsent(true)
  await f.result
  assert.equal(f.observations, 0)
  assert.equal(
    f.timers.every((timer) => timer.cancelled),
    true
  )
})

test("disabled child wait has no observer timer", async (t) => {
  const f = await liveObserverFixture(t, { observeLive: undefined })
  assert.deepEqual(
    f.timers.map((timer) => timer.milliseconds),
    [15_300_000]
  )
  f.child.emit("exit", 0, null)
  f.child.emit("close", 0, null)
  await f.result
})

test("actual shard seam supplies live context observation to owned execution", async (t) => {
  const f = await progressIntegrationFixture(t)
  const { createStrykerProgressReporter } = await import("./stryker-progress-reporter.mjs")
  await f.runStrykerShardExecution(f.options, {
    runChild: async (_args, _description, env, _timeout, _signal, observeLive) => {
      assert.equal(typeof observeLive, "function")
      assert.equal(observeLive().snapshot, null)
      const reporter = createStrykerProgressReporter({
        enabled: true,
        ownedDirectory: env.STRYKER_PROGRESS_DIRECTORY,
        outputPath: env.STRYKER_PROGRESS_OUTPUT,
        runId: env.STRYKER_PROGRESS_RUN_ID,
        shardId: env.STRYKER_PROGRESS_SHARD_ID,
      })
      try {
        reporter.onMutationTestingPlanReady({ mutantPlans: [{ mutant: { id: "one" } }] })
        observeLive()
        reporter.onMutantTested({ id: "one", status: "Killed" })
        assert.equal(observeLive().completionAdvanced, true)
        assert.equal(observeLive().completionAdvanced, false)
        reporter.onMutationTestReportReady({}, {})
      } finally {
        reporter.wrapUp()
      }
    },
  })
})

for (const corrupted of ["malformed", "wrong-run"]) {
  test(`live observer rejects actual ${corrupted} reporter output through owned termination`, async (t) => {
    const f = await progressIntegrationFixture(t)
    const { writeFile } = await import("node:fs/promises")
    const { createStrykerProgressReporter } = await import("./stryker-progress-reporter.mjs")
    await assert.rejects(
      () =>
        f.runStrykerShardExecution(f.options, {
          runChild: async (_args, _description, env, _timeout, _signal, observeLive) => {
            const reporter = createStrykerProgressReporter({
              enabled: true,
              ownedDirectory: env.STRYKER_PROGRESS_DIRECTORY,
              outputPath: env.STRYKER_PROGRESS_OUTPUT,
              runId: env.STRYKER_PROGRESS_RUN_ID,
              shardId: env.STRYKER_PROGRESS_SHARD_ID,
            })
            try {
              const contents =
                corrupted === "malformed"
                  ? "invalid"
                  : JSON.stringify({
                      ...JSON.parse(await readFile(env.STRYKER_PROGRESS_OUTPUT, "utf8")),
                      runId: "other",
                    })
              await writeFile(env.STRYKER_PROGRESS_OUTPUT, contents)
              const owned = await liveObserverFixture(t, { observeLive })
              owned.tick()
              owned.child.emit("exit", null, "SIGKILL")
              owned.child.emit("close", null, "SIGKILL")
              await assert.rejects(owned.result, (error) => {
                assert.equal(error.code, "STRYKER_PROGRESS_INVALID")
                assert.equal(error.processQuiesced, true)
                return true
              })
              assert.equal(owned.terminations, 1)
              await owned.result
            } finally {
              reporter.wrapUp()
            }
          },
        }),
      { code: "STRYKER_PROGRESS_INVALID" }
    )
  })
}

test("live observer failure stays first when tree termination fails or close never arrives", async (t) => {
  for (const closes of [true, false]) {
    const first = new Error("observer first")
    const shutdown = new Error("termination failed")
    const f = await liveObserverFixture(t, {
      observeLive: () => {
        throw first
      },
      terminate: async () => {
        throw shutdown
      },
    })
    f.tick()
    await new Promise((resolve) => setImmediate(resolve))
    if (closes) {
      f.child.emit("exit", null, "SIGKILL")
      f.child.emit("close", null, "SIGKILL")
    } else {
      f.timers.find((timer) => timer.milliseconds === 15_000).callback()
    }
    await assert.rejects(f.result, (error) => {
      assert.equal(error.cause, first)
      assert.equal(error.errors[0], first)
      assert.equal(error.errors[1], shutdown)
      assert.equal(error.processQuiesced, false)
      if (!closes) assert.match(error.errors[2].message, /did not terminate and close/u)
      return true
    })
    assert.equal(
      f.timers.every((timer) => timer.cancelled),
      true
    )
  }
})

test("live observer is never scheduled after cancellation already owns shutdown", async (t) => {
  const controller = new AbortController()
  const first = new Error("cancelled before observation")
  controller.abort(first)
  const f = await liveObserverFixture(t, { abortSignal: controller.signal })
  assert.equal(
    f.timers.some((timer) => timer.milliseconds === 1_000),
    false
  )
  f.child.emit("exit", null, "SIGKILL")
  f.child.emit("close", null, "SIGKILL")
  await assert.rejects(f.result, (error) => error === first)
  assert.equal(f.observations, 0)
})

test(
  "actual owned runNode live failure quiesces its root and descendant",
  { timeout: 45_000 },
  async (t) => {
    const f = await progressIntegrationFixture(t)
    const pidPath = path.join(f.shardTemp, "fixture-processes.json")
    const childScript = String.raw`
    const fs = require('node:fs');
    const { spawn } = require('node:child_process');
    const descendant = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)', 'university-ecosystem-live-observer-descendant'], { stdio: 'ignore', windowsHide: true });
    fs.writeFileSync(process.env.FIXTURE_PROCESS_PATH, JSON.stringify({ root: process.pid, descendant: descendant.pid }));
    fs.writeFileSync(process.env.STRYKER_PROGRESS_OUTPUT, 'invalid progress');
    setInterval(() => {}, 1000);
  `
    await assert.rejects(
      () =>
        f.runStrykerShardExecution({
          ...f.options,
          args: ["-e", childScript, "university-ecosystem-live-observer-root"],
          env: { ...process.env, STRYKER_TEMP_DIR: f.shardTemp, FIXTURE_PROCESS_PATH: pidPath },
          timeoutMs: 10_000,
        }),
      (error) => {
        assert.equal(error.code, "STRYKER_PROGRESS_INVALID", error.message)
        assert.equal(error.processQuiesced, true)
        return true
      }
    )
    const pids = JSON.parse(await readFile(pidPath, "utf8"))
    assert.equal(Number.isSafeInteger(pids.root) && pids.root > 0, true)
    assert.equal(Number.isSafeInteger(pids.descendant) && pids.descendant > 0, true)
    assert.equal(processIsAlive(pids.root), false)
    assert.equal(processIsAlive(pids.descendant), false)
  }
)

test("progress integration uses context then owned-child success then terminal validation before continuation", async (t) => {
  const f = await progressIntegrationFixture(t)
  const { createStrykerProgressContext } = await import("./stryker-progress-context.mjs")
  const { createStrykerProgressReporter } = await import("./stryker-progress-reporter.mjs")
  const calls = []
  const hostEvidence = { sourceSha256: "a".repeat(64), binarySha256: "b".repeat(64) }
  const result = await f.runStrykerShardExecution(f.options, {
    createProgressContext: async (options) => {
      calls.push("context")
      assert.equal(options.enabled, "1")
      assert.equal(options.runId, "run-1")
      assert.equal(options.shardId, "shard-1")
      const context = await createStrykerProgressContext(options)
      return {
        childEnv: context.childEnv,
        validateSuccessfulExit() {
          calls.push("terminal")
          return context.validateSuccessfulExit()
        },
      }
    },
    runChild: async (args, description, env, timeoutMs, signal) => {
      calls.push("owned-child")
      assert.equal(args, f.options.args)
      assert.equal(description, f.options.description)
      assert.equal(timeoutMs, 15_300_000)
      assert.equal(signal, f.options.abortSignal)
      assert.equal(env.NODE_OPTIONS, "--trace-warnings")
      assert.notEqual(env.STRYKER_PROGRESS_OUTPUT, "inherited-location")
      const reporter = createStrykerProgressReporter({
        enabled: true,
        ownedDirectory: env.STRYKER_PROGRESS_DIRECTORY,
        outputPath: env.STRYKER_PROGRESS_OUTPUT,
        runId: env.STRYKER_PROGRESS_RUN_ID,
        shardId: env.STRYKER_PROGRESS_SHARD_ID,
      })
      reporter.onMutationTestingPlanReady({ mutantPlans: [{ mutant: { id: "1" } }] })
      reporter.onMutantTested({ id: "1", status: "Survived" })
      reporter.onMutationTestReportReady({}, {})
      reporter.wrapUp()
      calls.push("quiesced-success")
      return hostEvidence
    },
  })
  calls.push("report-and-evidence-continuation")
  assert.equal(result, hostEvidence)
  assert.deepEqual(calls, [
    "context",
    "owned-child",
    "quiesced-success",
    "terminal",
    "report-and-evidence-continuation",
  ])
  assert.equal(f.options.env.STRYKER_PROGRESS_OUTPUT, "inherited-location")
})

test("progress integration rejects exit-zero missing output before report/evidence continuation", async (t) => {
  const f = await progressIntegrationFixture(t)
  let continued = false
  await assert.rejects(
    async () => {
      await f.runStrykerShardExecution(f.options, { runChild: async () => undefined })
      continued = true
    },
    { code: "STRYKER_PROGRESS_INCOMPLETE" }
  )
  assert.equal(continued, false)
  const directories = await (
    await import("node:fs/promises")
  ).readdir(path.join(f.shardTemp, "progress-diagnostics"))
  const record = JSON.parse(
    await readFile(
      path.join(f.shardTemp, "progress-diagnostics", directories[0], "shard-1.json"),
      "utf8"
    )
  )
  assert.equal(record.failureCode, "terminal_incomplete")
  assert.equal(record.processQuiesced, true)
})

test("progress integration preserves owned-child failure and false-quiescence rather than validating in finally", async (t) => {
  const f = await progressIntegrationFixture(t)
  const failure = Object.assign(new Error("owned child failed first"), { processQuiesced: false })
  await assert.rejects(
    () =>
      f.runStrykerShardExecution(f.options, {
        runChild: async () => {
          throw failure
        },
      }),
    (error) => error === failure
  )
  assert.equal(failure.processQuiesced, false)
  const directories = await (
    await import("node:fs/promises")
  ).readdir(path.join(f.shardTemp, "progress-diagnostics"))
  assert.equal(directories.length, 1)
  const record = JSON.parse(
    await readFile(
      path.join(f.shardTemp, "progress-diagnostics", directories[0], "shard-1.json"),
      "utf8"
    )
  )
  assert.equal(record.outcome, "failed")
  assert.equal(record.processQuiesced, false)
  assert.equal(record.failureCode, "child_failed")
  assert.equal(record.lastObservation, null)
  assert.equal(record.releaseEligible, false)
})

test("successful owned shard leaves a durable last validated progress observation", async (t) => {
  const f = await progressIntegrationFixture(t)
  const { createStrykerProgressReporter } = await import("./stryker-progress-reporter.mjs")
  await f.runStrykerShardExecution(f.options, {
    runChild: async (_args, _description, env, _timeout, _signal, observeLive) => {
      const reporter = createStrykerProgressReporter({
        enabled: true,
        ownedDirectory: env.STRYKER_PROGRESS_DIRECTORY,
        outputPath: env.STRYKER_PROGRESS_OUTPUT,
        runId: env.STRYKER_PROGRESS_RUN_ID,
        shardId: env.STRYKER_PROGRESS_SHARD_ID,
      })
      reporter.onMutationTestingPlanReady({ mutantPlans: [{ mutant: { id: "one" } }] })
      reporter.onMutantTested({ id: "one", status: "Killed" })
      observeLive()
      reporter.onMutationTestReportReady({}, {})
      reporter.wrapUp()
    },
  })
  const directories = await (
    await import("node:fs/promises")
  ).readdir(path.join(f.shardTemp, "progress-diagnostics"))
  const record = JSON.parse(
    await readFile(
      path.join(f.shardTemp, "progress-diagnostics", directories[0], "shard-1.json"),
      "utf8"
    )
  )
  assert.equal(record.outcome, "succeeded")
  assert.equal(record.lastObservation.snapshot.phase, "wrapped-up")
  assert.equal(record.lastObservation.snapshot.completedMutants, 1)
  assert.deepEqual(record.resources, { cpuSeconds: null, rssBytes: null })
})

test("publication failure preserves child first cause and false quiescence", async (t) => {
  const f = await progressIntegrationFixture(t)
  const childFailure = Object.assign(new Error("child first"), {
    code: "STRYKER_TIMEOUT",
    processQuiesced: false,
  })
  const publicationFailure = new Error("publication second: token=/private/path")
  const warnings = []
  await assert.rejects(
    () =>
      f.runStrykerShardExecution(f.options, {
        runChild: async () => {
          throw childFailure
        },
        createDiagnosticOwner: async () => ({
          publish: async () => {
            throw publicationFailure
          },
        }),
        warnDiagnostic: (message) => warnings.push(message),
      }),
    (error) => error === childFailure
  )
  assert.equal(childFailure.code, "STRYKER_TIMEOUT")
  assert.equal(childFailure.processQuiesced, false)
  assert.deepEqual(warnings, ["Stryker progress diagnostic unavailable\n"])
})

for (const outcome of ["succeeded", "failed"]) {
  test(`owned ${outcome} shard publishes only to its single export directory`, async (t) => {
    const f = await progressIntegrationFixture(t)
    const exportDirectory = await mkdtemp(path.join(os.tmpdir(), "stryker-export-"))
    t.after(() => rm(exportDirectory, { recursive: true, force: true }))
    const diagnosticOutputFile = `${exportDirectory}-step-output`
    t.after(() => rm(diagnosticOutputFile, { force: true }))
    const options = {
      ...f.options,
      diagnosticExportDirectory: exportDirectory,
      diagnosticOutputFile,
    }
    const failure = Object.assign(new Error("child failure"), { processQuiesced: true })
    const runChild = async () => {
      if (outcome === "failed") throw failure
      return { sourceSha256: "a".repeat(64) }
    }
    const execution = () =>
      f.runStrykerShardExecution(options, {
        runChild,
        createProgressContext: async () => ({
          childEnv: {},
          validateSuccessfulExit: () => undefined,
          lastObservation: () => null,
        }),
      })
    if (outcome === "failed") {
      await assert.rejects(execution, (error) => error === failure)
    } else {
      await execution()
    }
    const record = JSON.parse(await readFile(path.join(exportDirectory, "diagnostic.json"), "utf8"))
    assert.equal(record.outcome, outcome)
    assert.equal(record.processQuiesced, true)
    assert.equal(await readFile(diagnosticOutputFile, "utf8"), "progress_diagnostic=published\n")
    assert.deepEqual(await (await import("node:fs/promises")).readdir(exportDirectory), [
      "diagnostic.json",
    ])
    assert.deepEqual(await (await import("node:fs/promises")).readdir(f.shardTemp), [])
  })
}

test("unquiesced child failure never marks a diagnostic uploadable", async (t) => {
  const f = await progressIntegrationFixture(t)
  const exportDirectory = await mkdtemp(path.join(os.tmpdir(), "stryker-export-"))
  t.after(() => rm(exportDirectory, { recursive: true, force: true }))
  const diagnosticOutputFile = `${exportDirectory}-step-output`
  t.after(() => rm(diagnosticOutputFile, { force: true }))
  const failure = Object.assign(new Error("child failure"), { processQuiesced: false })
  await assert.rejects(
    () =>
      f.runStrykerShardExecution(
        { ...f.options, diagnosticExportDirectory: exportDirectory, diagnosticOutputFile },
        {
          runChild: async () => {
            throw failure
          },
          createProgressContext: async () => ({
            childEnv: {},
            validateSuccessfulExit: () => undefined,
            lastObservation: () => null,
          }),
        }
      ),
    (error) => error === failure
  )
  const record = JSON.parse(await readFile(path.join(exportDirectory, "diagnostic.json"), "utf8"))
  assert.equal(record.processQuiesced, false)
  await assert.rejects(() => readFile(diagnosticOutputFile, "utf8"), { code: "ENOENT" })
})

test("preexisting export target never marks an uploadable diagnostic", async (t) => {
  const f = await progressIntegrationFixture(t)
  const exportDirectory = await mkdtemp(path.join(os.tmpdir(), "stryker-export-"))
  t.after(() => rm(exportDirectory, { recursive: true, force: true }))
  const diagnosticOutputFile = `${exportDirectory}-step-output`
  t.after(() => rm(diagnosticOutputFile, { force: true }))
  const target = path.join(exportDirectory, "diagnostic.json")
  await writeFile(target, "untrusted checkout file\n")
  const warnings = []
  await f.runStrykerShardExecution(
    { ...f.options, diagnosticExportDirectory: exportDirectory, diagnosticOutputFile },
    {
      runChild: async () => undefined,
      createProgressContext: async () => ({
        childEnv: {},
        validateSuccessfulExit: () => undefined,
        lastObservation: () => null,
      }),
      warnDiagnostic: (message) => warnings.push(message),
    }
  )
  assert.equal(await readFile(target, "utf8"), "untrusted checkout file\n")
  await assert.rejects(() => readFile(diagnosticOutputFile, "utf8"), { code: "ENOENT" })
  assert.deepEqual(warnings, ["Stryker progress diagnostic unavailable\n"])
})

test("publication failure after successful child permits report continuation", async (t) => {
  const f = await progressIntegrationFixture(t)
  const publicationFailure = new Error("publication failed: token=/private/path")
  const warnings = []
  const hostEvidence = { sourceSha256: "a".repeat(64) }
  const result = await f.runStrykerShardExecution(f.options, {
    runChild: async () => hostEvidence,
    createProgressContext: async () => ({
      childEnv: {},
      validateSuccessfulExit: () => undefined,
    }),
    createDiagnosticOwner: async () => ({
      publish: async () => {
        throw publicationFailure
      },
    }),
    warnDiagnostic: (message) => warnings.push(message),
  })
  assert.equal(result, hostEvidence)
  assert.deepEqual(warnings, ["Stryker progress diagnostic unavailable\n"])
})

test("diagnostic owner initialization failure cannot skip the owned child", async (t) => {
  const f = await progressIntegrationFixture(t)
  const warnings = []
  let launches = 0
  const hostEvidence = { sourceSha256: "a".repeat(64) }
  const result = await f.runStrykerShardExecution(f.options, {
    runChild: async () => {
      launches++
      return hostEvidence
    },
    createProgressContext: async () => ({
      childEnv: {},
      validateSuccessfulExit: () => undefined,
    }),
    createDiagnosticOwner: async () => {
      throw new Error("unsafe path and token=/private/path")
    },
    warnDiagnostic: (message) => warnings.push(message),
  })
  assert.equal(result, hostEvidence)
  assert.equal(launches, 1)
  assert.deepEqual(warnings, ["Stryker progress diagnostic unavailable\n"])
})

test("disabled progress integration launches the existing child with scrubbed fields and no progress directories", async (t) => {
  const f = await progressIntegrationFixture(t)
  let launches = 0
  const result = await f.runStrykerShardExecution(
    { ...f.options, progressEnabled: "0" },
    {
      runChild: async (_args, _description, env) => {
        launches++
        assert.deepEqual(env, { NODE_OPTIONS: "--trace-warnings" })
        return undefined
      },
    }
  )
  assert.equal(result, undefined)
  assert.equal(launches, 1)
  assert.deepEqual(await (await import("node:fs/promises")).readdir(f.shardTemp), [])
})

test("cancellation before or after owned-child success preserves its reason and blocks terminal continuation", async (t) => {
  for (const timing of ["before", "after"]) {
    const f = await progressIntegrationFixture(t)
    const controller = new AbortController()
    const interruption = Object.assign(new Error("interrupted by SIGTERM"), {
      code: "STRYKER_INTERRUPTED",
      signalName: "SIGTERM",
    })
    let launches = 0
    if (timing === "before") controller.abort(interruption)
    await assert.rejects(
      () =>
        f.runStrykerShardExecution(
          { ...f.options, abortSignal: controller.signal },
          {
            runChild: async () => {
              launches++
              controller.abort(interruption)
            },
          }
        ),
      (error) => error === interruption
    )
    assert.equal(launches, timing === "before" ? 0 : 1)
  }
})

test("actual Stryker configuration opts in only exact 1 while preserving release settings", async (t) => {
  const savedEnabled = process.env.STRYKER_PROGRESS_ENABLED
  const savedShard = process.env.STRYKER_SHARD_RUN
  t.after(() => {
    if (savedEnabled === undefined) delete process.env.STRYKER_PROGRESS_ENABLED
    else process.env.STRYKER_PROGRESS_ENABLED = savedEnabled
    if (savedShard === undefined) delete process.env.STRYKER_SHARD_RUN
    else process.env.STRYKER_SHARD_RUN = savedShard
  })
  let iteration = 0
  for (const shard of ["0", "1"])
    for (const enabled of [undefined, "0", "true", " 1", "1 ", "1"]) {
      process.env.STRYKER_SHARD_RUN = shard
      if (enabled === undefined) delete process.env.STRYKER_PROGRESS_ENABLED
      else process.env.STRYKER_PROGRESS_ENABLED = enabled
      const url = new URL("../stryker.config.mjs", import.meta.url)
      url.searchParams.set("progress-test", String(iteration++))
      const config = (await import(url)).default
      assert.deepEqual(config.plugins, [
        "@stryker-mutator/*",
        "./scripts/stryker-presentation-ignorer.mjs",
        ...(enabled === "1" ? ["./scripts/stryker-progress-plugin.mjs"] : []),
      ])
      assert.deepEqual(config.reporters, [
        "clear-text",
        "progress",
        ...(shard === "1" ? [] : ["html"]),
        "json",
        ...(enabled === "1" ? ["owned-progress"] : []),
      ])
      assert.deepEqual(config.thresholds, {
        high: 100,
        low: 100,
        break: shard === "1" ? null : 100,
      })
      assert.equal(config.dryRunTimeoutMinutes, 30)
      assert.equal(config.incremental, false)
      assert.equal(config.coverageAnalysis, "perTest")
      assert.deepEqual(config.checkers, ["typescript"])
      assert.equal(config.tsconfigFile, "tsconfig.json")
      assert.deepEqual(config.typescriptChecker, {
        prioritizePerformanceOverAccuracy: false,
        experimentalNativePreview: false,
      })
      assert.deepEqual(config.mutator, { plugins: null, excludedMutations: [] })
      assert.deepEqual(config.ignorers, [PRESENTATION_IGNORER])
    }
})

test("actual Stryker configuration matches the shared checker contract", async () => {
  const config = (await import(new URL("../stryker.config.mjs?checker-contract", import.meta.url)))
    .default
  const { canonicalTypeScriptCheckerConfig } = await import("./validate-stryker-inventory.mjs")

  assert.deepEqual(
    {
      checkers: config.checkers,
      tsconfigFile: config.tsconfigFile,
      typescriptChecker: config.typescriptChecker,
    },
    canonicalTypeScriptCheckerConfig
  )
})

test("pins the checker dependency and records the TypeScript alias and runtime separately", async () => {
  const packageManifest = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8")
  )
  const packageLock = JSON.parse(
    await readFile(new URL("../package-lock.json", import.meta.url), "utf8")
  )
  const checkerLock = packageLock.packages["node_modules/@stryker-mutator/typescript-checker"]
  const typescriptLock = packageLock.packages["node_modules/typescript"]
  const typescriptManifest = JSON.parse(
    await readFile(new URL("../node_modules/typescript/package.json", import.meta.url), "utf8")
  )
  const { createRequire } = await import("node:module")
  const typescriptRuntime = createRequire(import.meta.url)("typescript")

  assert.equal(packageManifest.devDependencies["@stryker-mutator/typescript-checker"], "10.1.1")
  assert.equal(
    packageLock.packages[""].devDependencies["@stryker-mutator/typescript-checker"],
    "10.1.1"
  )
  assert.equal(checkerLock.version, "10.1.1")
  assert.match(checkerLock.integrity, /^sha512-[A-Za-z0-9+/]+=*$/u)
  assert.equal(packageManifest.devDependencies.typescript, "npm:@typescript/typescript6@^6.0.2")
  assert.equal(
    packageLock.packages[""].devDependencies.typescript,
    packageManifest.devDependencies.typescript
  )
  assert.equal(typescriptLock.name, "@typescript/typescript6")
  assert.equal(typescriptLock.version, "6.0.2")
  assert.equal(typescriptManifest.name, "@typescript/typescript6")
  assert.equal(typescriptManifest.version, typescriptLock.version)
  assert.equal(typescriptRuntime.version, "6.0.3")
})

const adapterUrl = new URL("./stryker-safe-error-string.mjs", import.meta.url)
const utilUrl = import.meta.resolve("@stryker-mutator/util")
const errorUrl = new URL("./errors.js", utilUrl).href
const serializerUrl = import.meta.resolve("@vitest/utils/error")
const strykerApiUrl = import.meta.resolve("@stryker-mutator/api/test-runner")
const vitestRunnerUrl = new URL(
  "./vitest-test-runner.js",
  import.meta.resolve("@stryker-mutator/vitest-runner")
).href
const reporterUrl = new URL(
  "./reporters/mutation-test-report-helper.js",
  import.meta.resolve("@stryker-mutator/core")
).href

async function runChild(source, { enabled = "1", preload = adapterUrl, extraArgs = [] } = {}) {
  return execFileAsync(process.execPath, [...extraArgs, "--input-type=module", "-e", source], {
    env: {
      ...process.env,
      NODE_OPTIONS: preload ? `--import=${preload.href}` : "",
      STRYKER_SHARD_RUN: enabled,
    },
    encoding: "utf8",
    timeout: 10_000,
  })
}

const applicationProbe = String.raw`
  const results = []
  const sentinel = new TypeError("Cannot convert object to primitive value")
  const cases = [undefined, null, false, 0, 42, 42n, Symbol("native"), {}, [], new String("boxed")]
  for (const value of cases) results.push(String(value))
  for (const kind of ["badPrimitive", "matchingTypeError", "throwingGetter", "badMethods", "proxy"]) {
    const events = []
    let value
    if (kind === "badPrimitive") value = { [Symbol.toPrimitive](hint) { events.push(hint); return {} } }
    if (kind === "matchingTypeError") value = { [Symbol.toPrimitive](hint) { events.push(hint); throw sentinel } }
    if (kind === "throwingGetter") value = { get [Symbol.toPrimitive]() { events.push("getter"); throw sentinel } }
    if (kind === "badMethods") value = { toString() { events.push("toString"); return {} }, valueOf() { events.push("valueOf"); return {} } }
    if (kind === "proxy") value = new Proxy({ [Symbol.toPrimitive]() { events.push("coerce"); return {} } }, { get(target, key, receiver) { events.push(typeof key === "symbol" ? key.description : key); return Reflect.get(target, key, receiver) } })
    try { results.push({ kind, returned: String(value), events }) }
    catch (error) { results.push({ kind, error: error.message, sentinel: error === sentinel, events }) }
  }
  try { results.push({ constructorSymbol: new String(Symbol("constructor")).valueOf() }) }
  catch (error) { results.push({ constructorSymbolError: error.message }) }
  const record = Object.assign(Object.create(null), { message: "ordinary object" })
  try { results.push({ record: String(record) }) }
  catch (error) { results.push({ recordError: error.message }) }
  class StringSubclass extends String {}
  const boxed = new StringSubclass(42)
  results.push({ native: String === "".constructor, constructor: String.prototype.constructor === String, boxed: boxed.valueOf(), subclass: boxed instanceof StringSubclass, string: boxed instanceof String, raw: String.raw({raw:["a", "b"]}, "-"), noArgument: String(), explicitUndefined: new String(undefined).valueOf() })
  process.stdout.write(JSON.stringify(results))
`

test("Stryker diagnostic preload preserves all native application String conversions", async () => {
  const native = await runChild(applicationProbe, { preload: null })
  const adapted = await runChild(applicationProbe)
  assert.equal(adapted.stdout, native.stdout)
})

test("Stryker diagnostic preload is inactive without the producer flag", async () => {
  for (const enabled of ["", "0", "true"]) {
    const result = await runChild(
      `
      import { errorToString } from ${JSON.stringify(utilUrl)}
      import { serializeError } from ${JSON.stringify(serializerUrl)}
      let threw = false
      try { errorToString(serializeError(new Error("unadapted"))) } catch { threw = true }
      process.stdout.write(JSON.stringify({ native: String === "".constructor, threw }))
    `,
      { enabled }
    )
    assert.deepEqual(JSON.parse(result.stdout), { native: true, threw: true })
  }
})

test("Stryker diagnostics preserve actual Vitest errors through structured cloning", async () => {
  const result = await runChild(`
    import assert from "node:assert/strict"
    import { errorToString } from ${JSON.stringify(utilUrl)}
    import { serializeError } from ${JSON.stringify(serializerUrl)}
    const error = new TypeError("mutant callback failed")
    error.stack = "TypeError: mutant callback failed\\n    at mutant-test"
    const record = serializeError(error)
    const plain = structuredClone(record)
    assert.equal(Object.getPrototypeOf(record), null)
    assert.equal(Object.getPrototypeOf(plain), Object.prototype)
    assert.equal(typeof plain.toString, "string")
    assert.equal(errorToString(record), error.stack)
    assert.equal(errorToString(plain), error.stack)
    assert.throws(() => String(record), TypeError)
    assert.throws(() => String(plain), TypeError)
    const normal = [undefined, null, false, 0, "", "failure", 42, Symbol("failure"), {}, error]
    process.stdout.write(JSON.stringify(normal.map(errorToString)))
  `)
  const native = await runChild(
    `
    import { errorToString } from ${JSON.stringify(utilUrl)}
    const error = new TypeError("mutant callback failed")
    error.stack = "TypeError: mutant callback failed\\n    at mutant-test"
    process.stdout.write(JSON.stringify([undefined, null, false, 0, "", "failure", 42, Symbol("failure"), {}, error].map(errorToString)))
  `,
    { preload: null }
  )
  assert.equal(result.stdout, native.stdout)
})

test("Stryker diagnostic fallback reads data without retrying coercion or invoking accessors", async () => {
  const { formatStrykerErrorValue } = await import("./stryker-error-formatter.mjs")
  let coercions = 0
  let getters = 0
  const value = {
    [Symbol.toPrimitive]() {
      coercions++
      return {}
    },
    get stack() {
      getters++
      throw new Error("must not invoke stack getter")
    },
    name: "TypeError",
    message: "original diagnostic",
  }
  assert.equal(formatStrykerErrorValue(value), "TypeError: original diagnostic")
  assert.equal(coercions, 1)
  assert.equal(getters, 0)
  for (const [properties, expected] of [
    [{ stack: "original stack", name: "Error", message: "message" }, "original stack"],
    [{ message: "message" }, "message"],
    [{ name: "Error" }, "Error"],
    [{}, "<unserializable error object>"],
  ])
    assert.equal(formatStrykerErrorValue(Object.assign(Object.create(null), properties)), expected)
  const events = []
  const proxy = new Proxy(
    {},
    {
      get() {
        events.push("get")
        throw new Error("proxy coercion")
      },
      getOwnPropertyDescriptor() {
        events.push("descriptor")
        throw new Error("must not inspect")
      },
    }
  )
  assert.equal(formatStrykerErrorValue(proxy), "<unserializable error object>")
  assert.deepEqual(events, ["get"])
})

test("Stryker diagnostic repair retains the real runner and RuntimeError report classification", async () => {
  const result = await runChild(`
    import assert from "node:assert/strict"
    import { serializeError } from ${JSON.stringify(serializerUrl)}
    import { VitestTestRunner } from ${JSON.stringify(vitestRunnerUrl)}
    import { toMutantRunResult } from ${JSON.stringify(strykerApiUrl)}
    import { MutationTestReportHelper } from ${JSON.stringify(reporterUrl)}
    const error = new TypeError("actual unhandled error")
    error.stack = "TypeError: actual unhandled error\\n    at mutation-fixture"
    const runner = Object.create(VitestTestRunner.prototype)
    runner.options = { vitest: { related: false } }
    runner.ctx = {
      config: {}, projects: [], start: async () => {},
      state: { filesMap: new Map(), errorsSet: new Set([structuredClone(serializeError(error))]), getFiles: () => [] },
    }
    const dryRun = await runner.run()
    assert.equal(dryRun.status, "error")
    assert.match(dryRun.errorMessage, /actual unhandled error/)
    const mutantRun = toMutantRunResult(dryRun)
    const helper = Object.create(MutationTestReportHelper.prototype)
    helper.partialResults = []
    helper.reporter = { onMutantTested() {} }
    const report = helper.reportMutantRunResult({ id: "1", location: { start: { line: 0, column: 0 }, end: { line: 0, column: 1 } } }, mutantRun)
    assert.equal(report.status, "RuntimeError")
    assert.equal(report.statusReason, dryRun.errorMessage)
    process.stdout.write(JSON.stringify(report))
  `)
  assert.equal(JSON.parse(result.stdout).status, "RuntimeError")
})

test("Stryker diagnostic preload reaches inherited workers and nested processes", async () => {
  const probe = `
    import { errorToString } from ${JSON.stringify(utilUrl)}
    import { serializeError } from ${JSON.stringify(serializerUrl)}
    export const result = { native: String === "".constructor, formatted: errorToString(serializeError(new Error("inherited transport error"))) }
  `
  const result = await runChild(`
    import { Worker } from "node:worker_threads"
    import { once } from "node:events"
    import { execFileSync } from "node:child_process"
    const workerCode = ${JSON.stringify(probe)} + ';import {parentPort} from "node:worker_threads";parentPort.postMessage(result)'
    const worker = new Worker(new URL('data:text/javascript,' + encodeURIComponent(workerCode)))
    const [thread] = await once(worker, "message")
    const processCode = ${JSON.stringify(probe)} + ';process.stdout.write(JSON.stringify(result))'
    const child = JSON.parse(execFileSync(process.execPath, ["--input-type=module", "-e", processCode], {encoding:"utf8"}))
    process.stdout.write(JSON.stringify({ thread, child }))
  `)
  for (const value of Object.values(JSON.parse(result.stdout))) {
    assert.equal(value.native, true)
    assert.match(value.formatted, /inherited transport error/)
  }
})

test("Stryker diagnostic adapter rejects source and package drift", async () => {
  const { rewriteStrykerErrorFormatter } = await import(adapterUrl)
  const source = await readFile(new URL(errorUrl), "utf8")
  assert.throws(
    () => rewriteStrykerErrorFormatter(source, { name: "wrong", version: "10.1.1" }),
    /requires/
  )
  const rewritten = rewriteStrykerErrorFormatter(source, {
    name: "@stryker-mutator/util",
    version: "10.1.1",
  })
  assert.equal(source.split("return String(error);").length - 1, 1)
  assert.equal(rewritten.includes("return String(error);"), false)
  assert.equal(rewritten.includes("return formatStrykerErrorValue(error);"), true)
  for (const version of ["10.0.0", "10.0.1", "10.1.0", "10.1.2", "11.0.0"]) {
    assert.throws(
      () => rewriteStrykerErrorFormatter(source, { name: "@stryker-mutator/util", version }),
      /requires/
    )
  }
  assert.throws(
    () =>
      rewriteStrykerErrorFormatter(`${source}\n`, {
        name: "@stryker-mutator/util",
        version: "10.1.1",
      }),
    /source changed/
  )
})

test("Stryker diagnostic adapter rejects missing or malformed checksum records", async () => {
  const fixtureRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-checksum-contract-"))
  const fixtureAdapter = pathToFileURL(path.join(fixtureRoot, "stryker-safe-error-string.mjs"))
  const fixtureChecksum = path.join(fixtureRoot, "stryker-util-errors.sha256")
  const checksum = await readFile(new URL("./stryker-util-errors.sha256", import.meta.url), "utf8")
  try {
    await writeFile(fixtureAdapter, await readFile(adapterUrl, "utf8"))
    await assert.rejects(
      runChild("", { enabled: "0", preload: fixtureAdapter }),
      /ENOENT.*stryker-util-errors\.sha256/su
    )
    for (const malformed of [
      "",
      checksum.slice(1),
      checksum.toUpperCase(),
      checksum.replace("  ", " "),
      checksum.replace("dist/src/errors.js", "dist/src/other.js"),
      checksum.replace("dist/src/errors.js", "../dist/src/errors.js"),
      checksum + checksum,
      checksum + "unexpected trailing data\n",
    ]) {
      await writeFile(fixtureChecksum, malformed)
      await assert.rejects(
        runChild("", { enabled: "0", preload: fixtureAdapter }),
        /checksum record is malformed/u
      )
    }
  } finally {
    await rm(fixtureRoot, { recursive: true, force: true })
  }
})

test("Stryker diagnostic adapter refuses a formatter cached by an earlier preload", async () => {
  await assert.rejects(
    runChild(
      `
    await import(${JSON.stringify(errorUrl)})
    await import(${JSON.stringify(adapterUrl.href)})
  `,
      { preload: null }
    ),
    /loaded before its adapter/
  )
})

test("Stryker diagnostic adapter refuses load hooks that change the guarded module", async () => {
  for (const change of [
    'return { ...loaded, source: String(loaded.source) + "\\n" }',
    'return { ...loaded, format: "commonjs" }',
  ]) {
    await assert.rejects(
      runChild(
        `
      import { registerHooks } from "node:module"
      registerHooks({ load(url, context, nextLoad) {
        const loaded = nextLoad(url, context)
        if (url !== ${JSON.stringify(errorUrl)}) return loaded
        ${change}
      } })
      await import(${JSON.stringify(adapterUrl.href)})
    `,
        { preload: null }
      ),
      /source changed|module format changed/
    )
  }
})

test("Stryker child environment preserves NODE_OPTIONS and appends the trusted preload", async () => {
  const { buildStrykerChildEnvironment, strykerSafeErrorStringPreloadOption } = await import(
    runnerUrl
  )
  const parentEnv = { NODE_OPTIONS: "--trace-warnings", STRYKER_SHARD_RUN: "1" }

  const childEnv = buildStrykerChildEnvironment(parentEnv)

  assert.equal(parentEnv.NODE_OPTIONS, "--trace-warnings")
  assert.equal(childEnv.STRYKER_SHARD_RUN, "1")
  assert.match(childEnv.NODE_OPTIONS, /^--trace-warnings\s/u)
  assert.match(childEnv.NODE_OPTIONS, /--import=/u)
  assert.equal(childEnv.NODE_OPTIONS.endsWith(strykerSafeErrorStringPreloadOption), true)
})
