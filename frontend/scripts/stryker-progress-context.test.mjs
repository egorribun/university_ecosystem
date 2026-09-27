import assert from "node:assert/strict"
import * as fs from "node:fs"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { createStrykerProgressReporter } from "./stryker-progress-reporter.mjs"

const api = await import("./stryker-progress-context.mjs").catch((error) => {
  if (error.code === "ERR_MODULE_NOT_FOUND") return {}
  throw error
})
const fields = ["ENABLED", "DIRECTORY", "OUTPUT", "RUN_ID", "SHARD_ID"]

function fixture(t) {
  assert.equal(typeof api.createStrykerProgressContext, "function", "context helper must exist")
  const shardTemp = fs.mkdtempSync(path.join(os.tmpdir(), "stryker-context-"))
  const reporters = []
  t.after(() => {
    let first
    try {
      for (const reporter of reporters) {
        try {
          reporter.wrapUp()
        } catch (error) {
          first ??= error
        }
      }
    } finally {
      assert.equal(path.dirname(shardTemp), path.resolve(os.tmpdir()))
      assert.equal(path.basename(shardTemp).startsWith("stryker-context-"), true)
      fs.rmSync(shardTemp, { recursive: true, force: true })
    }
    if (first) throw first
  })
  const options = {
    enabled: "1",
    shardTemp,
    runId: "run-1",
    shardId: "shard-1",
    parentEnv: { NODE_OPTIONS: "--trace-warnings" },
  }
  return {
    shardTemp,
    options,
    create: (override = {}) => api.createStrykerProgressContext({ ...options, ...override }),
    reporter(context) {
      const env = context.childEnv
      const reporter = createStrykerProgressReporter({
        enabled: true,
        ownedDirectory: env.STRYKER_PROGRESS_DIRECTORY,
        outputPath: env.STRYKER_PROGRESS_OUTPUT,
        runId: env.STRYKER_PROGRESS_RUN_ID,
        shardId: env.STRYKER_PROGRESS_SHARD_ID,
      })
      reporters.push(reporter)
      return reporter
    },
  }
}

for (const enabled of [undefined, "", "0", "true", " 1", "1 ", true]) {
  test(`disabled context ignores payloads unless explicitly string 1: ${JSON.stringify(enabled)}`, async (t) => {
    const f = fixture(t)
    const parentEnv = { NODE_OPTIONS: "--trace-warnings" }
    for (const field of fields)
      Object.defineProperty(parentEnv, `STRYKER_PROGRESS_${field}`, {
        enumerable: true,
        get() {
          return assert.fail("inherited progress payload must not be read")
        },
      })
    const options = { enabled, parentEnv }
    for (const field of ["shardTemp", "runId", "shardId"])
      Object.defineProperty(options, field, {
        get() {
          return assert.fail("disabled options must not be read")
        },
      })
    const context = await api.createStrykerProgressContext(options)
    assert.deepEqual(context.childEnv, { NODE_OPTIONS: "--trace-warnings" })
    assert.equal(context.validateSuccessfulExit(), undefined)
    assert.deepEqual(fs.readdirSync(f.shardTemp), [])
  })
}

test("enabled context creates fresh private output location and captures immutable identity", async (t) => {
  const f = fixture(t)
  const parentEnv = Object.fromEntries(
    fields.map((field) => [`STRYKER_PROGRESS_${field}`, "inherited-value"])
  )
  parentEnv.NODE_OPTIONS = "--trace-warnings"
  const original = { ...parentEnv }
  const context = await f.create({ parentEnv })
  const env = context.childEnv
  assert.deepEqual(parentEnv, original)
  assert.equal(env.NODE_OPTIONS, parentEnv.NODE_OPTIONS)
  assert.equal(env.STRYKER_PROGRESS_ENABLED, "1")
  assert.equal(env.STRYKER_PROGRESS_RUN_ID, "run-1")
  assert.equal(env.STRYKER_PROGRESS_SHARD_ID, "shard-1")
  assert.equal(path.dirname(env.STRYKER_PROGRESS_DIRECTORY), f.shardTemp)
  assert.equal(path.dirname(env.STRYKER_PROGRESS_OUTPUT), env.STRYKER_PROGRESS_DIRECTORY)
  assert.equal(fs.existsSync(env.STRYKER_PROGRESS_OUTPUT), false)
  assert.deepEqual(fs.readdirSync(env.STRYKER_PROGRESS_DIRECTORY), [])
  if (process.platform !== "win32")
    assert.equal(fs.statSync(env.STRYKER_PROGRESS_DIRECTORY).mode & 0o777, 0o700)
  assert.equal(Object.isFrozen(env), true)
  assert.equal(Object.isFrozen(context), true)
  f.options.runId = "different"
  f.options.shardId = "different"
  const reporter = f.reporter(context)
  reporter.onMutationTestingPlanReady({
    mutantPlans: [{ mutant: { id: "1", fileName: "not-saved" } }],
  })
  reporter.onMutantTested({ id: "1", status: "Killed" })
  reporter.onMutationTestReportReady({}, {})
  reporter.wrapUp()
  const snapshot = context.validateSuccessfulExit()
  assert.equal(snapshot.runId, "run-1")
  assert.equal(snapshot.completedMutants, 1)
  assert.equal(snapshot.releaseEligible, false)
  assert.equal(
    fs.existsSync(env.STRYKER_PROGRESS_DIRECTORY),
    true,
    "parent runner retains cleanup authority"
  )
})

test("parallel contexts have independent fresh paths and distinct captured shard identities", async (t) => {
  const f = fixture(t)
  const contexts = await Promise.all([f.create(), f.create({ shardId: "shard-2" })])
  assert.notEqual(
    contexts[0].childEnv.STRYKER_PROGRESS_OUTPUT,
    contexts[1].childEnv.STRYKER_PROGRESS_OUTPUT
  )
  for (const context of contexts) {
    const reporter = f.reporter(context)
    reporter.onMutationTestingPlanReady({ mutantPlans: [] })
    reporter.onMutationTestReportReady({}, {})
    reporter.wrapUp()
  }
  assert.equal(contexts[0].validateSuccessfulExit().shardId, "shard-1")
  assert.equal(contexts[1].validateSuccessfulExit().shardId, "shard-2")
})

for (const [name, override] of [
  ["missing parent", { shardTemp: undefined }],
  ["relative parent", { shardTemp: "relative" }],
  ["oversize parent", { shardTemp: "x".repeat(4097) }],
  ["control parent", { shardTemp: `${path.parse(os.tmpdir()).root}folder\nfile` }],
  ["missing run", { runId: undefined }],
  ["oversize run", { runId: "x".repeat(65) }],
  ["invalid shard", { shardId: "../other" }],
  ["invalid environment", { parentEnv: [] }],
]) {
  test(`invalid ${name} fails before filesystem writes`, async (t) => {
    const f = fixture(t)
    await assert.rejects(
      () => f.create(override),
      (error) => {
        assert.equal(error.code, "STRYKER_PROGRESS_CONTEXT_INVALID")
        assert.equal(error.message, "Invalid Stryker progress context")
        assert.equal(error.cause, undefined)
        return true
      }
    )
    assert.deepEqual(fs.readdirSync(f.shardTemp), [])
  })
}

test("nonexistent or non-directory parent fails without creating a parent", async (t) => {
  const f = fixture(t)
  const missing = path.join(f.shardTemp, "missing")
  await assert.rejects(() => f.create({ shardTemp: missing }), {
    code: "STRYKER_PROGRESS_CONTEXT_INVALID",
  })
  assert.equal(fs.existsSync(missing), false)
  const file = path.join(f.shardTemp, "file")
  fs.writeFileSync(file, "ordinary")
  await assert.rejects(() => f.create({ shardTemp: file }), {
    code: "STRYKER_PROGRESS_CONTEXT_INVALID",
  })
  assert.equal(fs.readFileSync(file, "utf8"), "ordinary")
})

for (const state of [
  "missing",
  "malformed",
  "wrong-run",
  "unplanned",
  "nonwrapped",
  "swallowed-failure",
]) {
  test(`success-only terminal hook rejects ${state} output and latches failure`, async (t) => {
    const f = fixture(t)
    const context = await f.create()
    const output = context.childEnv.STRYKER_PROGRESS_OUTPUT
    if (state !== "missing") {
      const reporter = f.reporter(context)
      if (state === "swallowed-failure") {
        assert.throws(() => reporter.onMutationTestingPlanReady({ mutantPlans: null }), {
          code: "STRYKER_PROGRESS_INVALID_PLAN",
        })
        // Emulate Stryker's documented catch behavior; writer failure is still latched.
        assert.throws(() => reporter.wrapUp(), { code: "STRYKER_PROGRESS_INVALID_PLAN" })
      } else {
        if (state !== "unplanned") reporter.onMutationTestingPlanReady({ mutantPlans: [] })
        reporter.onMutationTestReportReady({}, {})
        if (state !== "nonwrapped") reporter.wrapUp()
        if (state === "malformed") fs.writeFileSync(output, "malformed")
        if (state === "wrong-run") {
          const snapshot = JSON.parse(fs.readFileSync(output, "utf8"))
          fs.writeFileSync(output, JSON.stringify({ ...snapshot, runId: "other" }))
        }
      }
    }
    let first
    assert.throws(context.validateSuccessfulExit, (error) => {
      first = error
      return ["STRYKER_PROGRESS_INCOMPLETE", "STRYKER_PROGRESS_INVALID"].includes(error.code)
    })
    assert.throws(context.validateSuccessfulExit, (error) => error === first)
  })
}

test("success-only placement cannot replace an existing child failure with missing progress", async (t) => {
  const f = fixture(t)
  const context = await f.create()
  const childFailure = new Error("child failed first")
  const execute = async () => {
    await Promise.reject(childFailure)
    context.validateSuccessfulExit()
  }
  await assert.rejects(execute, (error) => error === childFailure)
  assert.equal(fs.existsSync(context.childEnv.STRYKER_PROGRESS_DIRECTORY), true)
})

for (const value of [null, [], "invalid"]) {
  test(`rejects nonrecord context options: ${JSON.stringify(value)}`, async (t) => {
    const f = fixture(t)
    await assert.rejects(() => api.createStrykerProgressContext(value), {
      code: "STRYKER_PROGRESS_CONTEXT_INVALID",
      message: "Invalid Stryker progress context",
    })
    assert.deepEqual(fs.readdirSync(f.shardTemp), [])
  })
}

test("symbolic-link parent is rejected without changing its target", async (t) => {
  const f = fixture(t)
  const target = path.join(f.shardTemp, "target")
  const link = path.join(f.shardTemp, "link")
  fs.mkdirSync(target)
  try {
    fs.symlinkSync(target, link, "junction")
  } catch (error) {
    if (process.platform !== "win32" || error.code !== "EPERM") throw error
    t.skip("Windows host cannot create directory links; Linux verification required")
    return
  }
  await assert.rejects(() => f.create({ shardTemp: link }), {
    code: "STRYKER_PROGRESS_CONTEXT_INVALID",
  })
  assert.deepEqual(fs.readdirSync(target), [])
})

test("live context observes actual completed mutants without treating duplicate output as progress", async (t) => {
  const f = fixture(t)
  const context = await f.create()
  assert.equal(typeof context.observeLive, "function")
  assert.equal(context.observeLive().snapshot, null)
  const reporter = f.reporter(context)
  reporter.onMutationTestingPlanReady({ mutantPlans: [{ mutant: { id: "one" } }] })
  assert.equal(context.observeLive().completionAdvanced, false)
  reporter.onMutantTested({ id: "one", status: "Killed" })
  const advanced = context.observeLive()
  assert.equal(advanced.completionAdvanced, true)
  assert.equal(advanced.snapshot.completedMutants, 1)
  assert.equal(context.observeLive().completionAdvanced, false)
  reporter.onMutationTestReportReady({}, {})
  reporter.wrapUp()
  assert.equal(context.validateSuccessfulExit().phase, "wrapped-up")
})

test("live context failure cannot be healed by a later terminal reporter snapshot", async (t) => {
  const f = fixture(t)
  const context = await f.create()
  assert.equal(typeof context.observeLive, "function")
  const reporter = f.reporter(context)
  fs.writeFileSync(context.childEnv.STRYKER_PROGRESS_OUTPUT, "malformed")
  let first
  assert.throws(context.observeLive, (error) => {
    first = error
    return error.code === "STRYKER_PROGRESS_INVALID"
  })
  reporter.onMutationTestingPlanReady({ mutantPlans: [] })
  reporter.onMutationTestReportReady({}, {})
  reporter.wrapUp()
  assert.throws(context.validateSuccessfulExit, (error) => error === first)
})

test("disabled live context is inert without progress files", async (t) => {
  const f = fixture(t)
  const context = await f.create({ enabled: "0" })
  assert.equal(typeof context.observeLive, "function")
  assert.equal(context.observeLive(), undefined)
  assert.deepEqual(fs.readdirSync(f.shardTemp), [])
})
