import assert from "node:assert/strict"
import * as fs from "node:fs"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { PluginKind, declareFactoryPlugin } from "@stryker-mutator/api/plugin"
import { createInjector, InjectorDisposedError } from "typed-inject"
import { PluginCreator } from "../node_modules/@stryker-mutator/core/dist/src/di/plugin-creator.js"
import { BroadcastReporter } from "../node_modules/@stryker-mutator/core/dist/src/reporters/broadcast-reporter.js"

const api = await import("./stryker-progress-plugin.mjs").catch((error) => {
  if (error.code === "ERR_MODULE_NOT_FOUND") return {}
  throw error
})
const fields = ["ENABLED", "DIRECTORY", "OUTPUT", "RUN_ID", "SHARD_ID"]

function fixture(t, overrides = {}) {
  assert.equal(typeof api.STRYKER_PROGRESS_REPORTER_NAME, "string", "reporter name must exist")
  assert.equal(Array.isArray(api.strykerPlugins), true, "factory registration must exist")
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "stryker-plugin-"))
  const output = path.join(directory, "progress.json")
  const values = {
    ENABLED: "1",
    DIRECTORY: directory,
    OUTPUT: output,
    RUN_ID: "run-1",
    SHARD_ID: "shard-1",
    ...overrides,
  }
  const saved = fields.map((field) => [field, process.env[`STRYKER_PROGRESS_${field}`]])
  for (const field of fields) {
    const key = `STRYKER_PROGRESS_${field}`
    if (values[field] === undefined) delete process.env[key]
    else process.env[key] = values[field]
  }
  const injector = createInjector()
  const reporters = []
  const cleanup = async () => {
    let firstFailure
    const attempt = async (action) => {
      try {
        await action()
      } catch (error) {
        firstFailure ??= error
      }
    }
    try {
      for (const reporter of reporters) await attempt(() => reporter.wrapUp())
    } finally {
      try {
        await attempt(() => injector.dispose())
      } finally {
        try {
          for (const [field, value] of saved) {
            await attempt(() => {
              const key = `STRYKER_PROGRESS_${field}`
              if (value === undefined) delete process.env[key]
              else process.env[key] = value
            })
          }
        } finally {
          await attempt(() => {
            assert.equal(path.dirname(directory), path.resolve(os.tmpdir()))
            assert.equal(path.basename(directory).startsWith("stryker-plugin-"), true)
            fs.rmSync(directory, { recursive: true, force: true })
          })
        }
      }
    }
    if (firstFailure) throw firstFailure
  }
  t.after(cleanup)
  const creator = new PluginCreator(new Map([[PluginKind.Reporter, api.strykerPlugins]]), injector)
  return {
    directory,
    output,
    creator,
    injector,
    cleanup,
    create: () => {
      const reporter = creator.create(PluginKind.Reporter, api.STRYKER_PROGRESS_REPORTER_NAME)
      reporters.push(reporter)
      return reporter
    },
    read: () => JSON.parse(fs.readFileSync(output, "utf8")),
  }
}

test("registers a real Stryker10 factory reporter and defers filesystem work until creation", async (t) => {
  const f = fixture(t)
  const imported = await import(`./stryker-progress-plugin.mjs?fresh=${Date.now()}`)
  assert.deepEqual(fs.readdirSync(f.directory), [])
  assert.equal(imported.strykerPlugins.length, 1)
  const plugin = imported.strykerPlugins[0]
  assert.deepEqual(
    plugin,
    declareFactoryPlugin(
      PluginKind.Reporter,
      imported.STRYKER_PROGRESS_REPORTER_NAME,
      plugin.factory
    )
  )
  const reporter = f.create()
  assert.equal(reporter.writeFailed, false)
  assert.equal(f.read().phase, "initializing")
  assert.equal(fs.existsSync(`${f.output}.lock`), true)
})

for (const enabled of [undefined, "", "0", "true", " 1", "1 ", "01"]) {
  test(`disabled unless opt-in is exactly 1: ${JSON.stringify(enabled)}`, (t) => {
    const f = fixture(t, {
      ENABLED: enabled,
      DIRECTORY: "private invalid",
      OUTPUT: "private invalid",
      RUN_ID: "../private",
      SHARD_ID: "",
    })
    const reporter = f.create()
    const hostilePayload = new Proxy(
      {},
      {
        get() {
          throw new Error("must not inspect payload")
        },
      }
    )
    reporter.onDryRunCompleted(hostilePayload)
    reporter.onMutationTestingPlanReady(hostilePayload)
    reporter.onMutantTested(hostilePayload)
    reporter.onMutationTestReportReady(hostilePayload, hostilePayload)
    reporter.wrapUp()
    assert.equal(reporter.writeFailed, false)
    assert.deepEqual(fs.readdirSync(f.directory), [])
  })
}

test("real factory lifecycle writes only bounded informational fields and releases its lock", (t) => {
  const f = fixture(t)
  const reporter = f.create()
  reporter.onDryRunCompleted({ fileName: "private" })
  reporter.onMutationTestingPlanReady({ mutantPlans: [{ mutant: { id: "1", source: "private" } }] })
  reporter.onMutantTested({ id: "1", status: "Killed", source: "private" })
  reporter.onMutantTested({ id: "1", status: "Survived" })
  reporter.onMutationTestReportReady({ private: true }, { private: true })
  reporter.wrapUp()
  const snapshot = f.read()
  assert.equal(snapshot.phase, "wrapped-up")
  assert.equal(snapshot.completedMutants, 1)
  assert.equal(snapshot.plannedMutants, 1)
  assert.equal(snapshot.runId, "run-1")
  assert.equal(snapshot.shardId, "shard-1")
  assert.equal(snapshot.informational, true)
  assert.equal(snapshot.releaseEligible, false)
  assert.equal(JSON.stringify(snapshot).includes("private"), false)
  assert.equal(Object.keys(snapshot).length, 11)
  assert.deepEqual(fs.readdirSync(f.directory), ["progress.json"])
})

for (const [field, value] of [
  ["DIRECTORY", undefined],
  ["OUTPUT", undefined],
  ["RUN_ID", undefined],
  ["SHARD_ID", undefined],
  ["DIRECTORY", "relative/private"],
  ["OUTPUT", "relative/private"],
  ["DIRECTORY", "x".repeat(4097)],
  ["OUTPUT", "x".repeat(4097)],
  ["RUN_ID", "x".repeat(65)],
  ["SHARD_ID", "../private"],
  ["OUTPUT", `${path.parse(os.tmpdir()).root}private\npath`],
]) {
  test(`enabled factory rejects invalid ${field} before taking ownership: ${value === undefined ? "missing" : value.length}`, (t) => {
    const f = fixture(t, { [field]: value })
    assert.throws(f.create, (error) => {
      // typed-inject wraps factory exceptions; its original cause remains generic.
      const cause = error.cause ?? error
      assert.equal(cause.message, "Invalid progress plugin options")
      assert.equal(cause.cause, undefined)
      return true
    })
    assert.deepEqual(fs.readdirSync(f.directory), [])
  })
}

test("enabled output must be a direct child of the runner-owned directory", (t) => {
  const f = fixture(t)
  process.env.STRYKER_PROGRESS_OUTPUT = path.join(f.directory, "nested", "progress.json")
  assert.throws(
    f.create,
    (error) => (error.cause ?? error).message === "Invalid progress plugin options"
  )
  assert.deepEqual(fs.readdirSync(f.directory), [])
})

test("Stryker BroadcastReporter swallows callback failures but cannot heal the failed reporter", async (t) => {
  const f = fixture(t)
  const reporter = f.create()
  const errors = []
  const logger = {
    isDebugEnabled: () => false,
    error: (...args) => errors.push(args),
    info() {},
    warn() {},
  }
  const broadcast = new BroadcastReporter({ reporters: [] }, f.creator, logger, reporter)
  await broadcast.broadcast("onMutationTestingPlanReady", { mutantPlans: null })
  assert.equal(reporter.writeFailed, true)
  assert.equal(f.read().phase, "initializing")
  await broadcast.broadcast("onMutationTestReportReady", {}, {})
  await broadcast.wrapUp()
  assert.equal(errors.length, 3)
  assert.equal(errors[0][1].code, "STRYKER_PROGRESS_INVALID_PLAN")
  assert.equal(f.read().reportReady, false)
  assert.equal(f.read().phase, "initializing")
  assert.equal(fs.existsSync(`${f.output}.lock`), false)
})

test("factory never serializes unrelated inherited environment values", (t) => {
  const f = fixture(t)
  const saved = process.env.STRYKER_PROGRESS_PRIVATE_FIELD
  t.after(() => {
    if (saved === undefined) delete process.env.STRYKER_PROGRESS_PRIVATE_FIELD
    else process.env.STRYKER_PROGRESS_PRIVATE_FIELD = saved
  })
  process.env.STRYKER_PROGRESS_PRIVATE_FIELD = "private-environment-marker"
  const reporter = f.create()
  reporter.wrapUp()
  assert.equal(fs.readFileSync(f.output, "utf8").includes("private-environment-marker"), false)
  assert.equal(Object.keys(f.read()).length, 11)
})

test("a second factory instance cannot take or remove the first instance ownership", (t) => {
  const f = fixture(t)
  const first = f.create()
  const original = fs.readFileSync(f.output, "utf8")
  assert.throws(
    f.create,
    (error) => (error.cause ?? error).message === "Progress output is not available"
  )
  assert.equal(fs.readFileSync(f.output, "utf8"), original)
  assert.equal(fs.existsSync(`${f.output}.lock`), true)
  first.wrapUp()
  assert.equal(fs.existsSync(`${f.output}.lock`), false)
})

test("fixture cleanup preserves a failed reporter cause and still disposes, restores and removes owned resources", async (t) => {
  const before = fields.map((field) => [field, process.env[`STRYKER_PROGRESS_${field}`]])
  const f = fixture(t)
  const reporter = f.create()
  let first
  assert.throws(
    () => reporter.onMutationTestingPlanReady({ mutantPlans: null }),
    (error) => {
      first = error
      return error.code === "STRYKER_PROGRESS_INVALID_PLAN"
    }
  )
  await assert.rejects(f.cleanup, (error) => error === first)
  assert.equal(fs.existsSync(f.directory), false)
  assert.deepEqual(
    fields.map((field) => [field, process.env[`STRYKER_PROGRESS_${field}`]]),
    before
  )
  assert.throws(f.create, InjectorDisposedError)
})

test("fixture attempts every reporter and retains its first failure over injector disposal failure", async (t) => {
  const before = fields.map((field) => [field, process.env[`STRYKER_PROGRESS_${field}`]])
  const f = fixture(t)
  const firstReporter = f.create()
  process.env.STRYKER_PROGRESS_OUTPUT = path.join(f.directory, "second.json")
  const secondReporter = f.create()
  let first
  assert.throws(
    () => firstReporter.onMutationTestingPlanReady({ mutantPlans: null }),
    (error) => {
      first = error
      return error.code === "STRYKER_PROGRESS_INVALID_PLAN"
    }
  )
  assert.throws(
    () => secondReporter.onMutationTestingPlanReady({ mutantPlans: null }),
    (error) => error !== first && error.code === "STRYKER_PROGRESS_INVALID_PLAN"
  )
  let disposalAttempted = false
  f.injector
    .provideFactory("failed-disposable", () => ({
      dispose() {
        disposalAttempted = true
        throw new Error("secondary disposal failure")
      },
    }))
    .resolve("failed-disposable")
  await assert.rejects(f.cleanup, (error) => error === first)
  assert.equal(disposalAttempted, true)
  assert.equal(fs.existsSync(f.directory), false)
  assert.deepEqual(
    fields.map((field) => [field, process.env[`STRYKER_PROGRESS_${field}`]]),
    before
  )
  // A failed reporter closes during wrapUp; a second call cannot throw again.
  assert.doesNotThrow(() => secondReporter.wrapUp())
  assert.throws(f.create, InjectorDisposedError)
})
