import assert from "node:assert/strict"
import * as fs from "node:fs"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { createStrykerProgressReporter as create } from "./stryker-progress-reporter.mjs"

function fixture(t, dependencies) {
  const ownedDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "stryker-progress-"))
  let reporter
  t.after(() => {
    try {
      reporter?.wrapUp()
    } finally {
      fs.rmSync(ownedDirectory, { recursive: true, force: true })
    }
  })
  const outputPath = path.join(ownedDirectory, "progress.json")
  const options = {
    enabled: true,
    ownedDirectory,
    outputPath,
    runId: "run-123",
    shardId: "shard-2",
  }
  reporter = create(options, dependencies)
  return { reporter, options, read: () => JSON.parse(fs.readFileSync(outputPath, "utf8")) }
}

const plan = (...ids) => ({ mutantPlans: ids.map((id) => ({ plan: "Run", mutant: { id } })) })

test("disabled reporter neither writes nor inspects event payloads", () => {
  const reporter = create()
  const poisonous = new Proxy(
    {},
    {
      get() {
        throw new Error("payload must not be read")
      },
    }
  )
  reporter.onDryRunCompleted(poisonous)
  reporter.onMutationTestingPlanReady(poisonous)
  reporter.onMutantTested(poisonous)
  reporter.onMutationTestReportReady(poisonous, poisonous)
  reporter.wrapUp()
  assert.equal(reporter.writeFailed, false)
})

test("records actual phases and unique completions, not repeated activity", (t) => {
  const { reporter, read } = fixture(t, { now: () => 100 })
  assert.equal(read().phase, "initializing")
  reporter.onDryRunCompleted({})
  assert.equal(read().phase, "dry-run-completed")
  reporter.onMutationTestingPlanReady(plan("1", "2", "2"))
  assert.equal(read().plannedMutants, 2)
  reporter.onMutantTested({ id: "1", status: "Killed" })
  const first = read()
  assert.equal(first.phase, "mutation-testing")
  assert.equal(first.completedMutants, 1)
  reporter.onMutantTested({ id: "1", status: "Survived" })
  reporter.onMutantTested({ id: "not-planned" })
  reporter.onMutantTested({ id: "2", status: "Unknown" })
  reporter.onMutantTested({ id: "2", status: "Pending" })
  reporter.onMutantTested({ id: "2" })
  reporter.onDryRunCompleted({})
  reporter.onMutationTestingPlanReady(plan("new"))
  assert.deepEqual(read(), first)
  reporter.onMutantTested({ id: "2", status: "Timeout" })
  assert.equal(read().completedMutants, 2)
  reporter.onMutationTestReportReady({}, {})
  assert.equal(read().phase, "report-ready")
  assert.equal(read().reportReady, true)
  const reportReady = read()
  reporter.onMutationTestReportReady({}, {})
  reporter.onMutantTested({ id: "new" })
  assert.deepEqual(read(), reportReady)
  reporter.wrapUp()
  const final = read()
  assert.equal(final.phase, "wrapped-up")
  reporter.wrapUp()
  reporter.onMutantTested({ id: "2" })
  reporter.onMutationTestingPlanReady(plan("late"))
  reporter.onMutationTestReportReady({}, {})
  assert.deepEqual(read(), final)
})

test("wrapUp without report is not completion or release evidence", (t) => {
  const { reporter, read } = fixture(t)
  reporter.onMutantTested({ id: "before-plan" })
  assert.equal(read().completedMutants, 0)
  reporter.wrapUp()
  assert.equal(read().reportReady, false)
  assert.equal(read().releaseEligible, false)
  assert.equal(read().informational, true)
})

test("report readiness never fabricates missing mutant completions", (t) => {
  const { reporter, read } = fixture(t)
  reporter.onMutationTestingPlanReady(plan("1", "2"))
  reporter.onMutantTested({ id: "1", status: "Killed" })
  reporter.onMutationTestReportReady({ files: { fileName: "not serialized" } }, {})
  assert.equal(read().completedMutants, 1)
  assert.equal(read().plannedMutants, 2)
  const reportReady = read()
  reporter.onMutantTested({ id: "2", status: "Killed" })
  assert.deepEqual(read(), reportReady)
})

test("bounds serialized schema and excludes mutant paths, source, statuses and secrets", (t) => {
  const { reporter, options, read } = fixture(t)
  reporter.onMutationTestingPlanReady(plan("credential-in-id"))
  reporter.onMutantTested({
    id: "credential-in-id",
    fileName: "/private/token",
    replacement: "secret",
    statusReason: "password",
    status: "Survived",
  })
  const snapshot = read()
  assert.deepEqual(
    Object.keys(snapshot).sort(),
    [
      "schemaVersion",
      "runId",
      "shardId",
      "phase",
      "sequence",
      "updatedAtMs",
      "plannedMutants",
      "completedMutants",
      "reportReady",
      "informational",
      "releaseEligible",
    ].sort()
  )
  const serialized = JSON.stringify(snapshot)
  assert.ok(Buffer.byteLength(serialized) < 1024)
  for (const secret of [
    "credential-in-id",
    "/private/token",
    "secret",
    "password",
    "Survived",
    options.outputPath,
  ])
    assert.ok(!serialized.includes(secret))
  assert.equal(snapshot.runId, "run-123")
  assert.equal(snapshot.shardId, "shard-2")
})

test("does not let a backwards clock regress activity timestamps", (t) => {
  let time = 100
  const { reporter, read } = fixture(t, { now: () => time })
  time = 20
  reporter.onDryRunCompleted({})
  assert.equal(read().updatedAtMs, 100)
  assert.equal(read().sequence, 1)
})

test("requires explicit bounded identity and a direct owned output path", (t) => {
  const { options } = fixture(t)
  for (const override of [
    { runId: "" },
    { shardId: "../secret" },
    { runId: "x".repeat(65) },
    { outputPath: "relative.json" },
    { outputPath: path.join(options.ownedDirectory, "..", "escape.json") },
  ]) {
    assert.throws(() => create({ ...options, ...override }), /Invalid progress reporter options/u)
  }
})

test("will not overwrite an existing file or another reporter's ownership lock", (t) => {
  const { options, read } = fixture(t)
  const previous = read()
  assert.throws(() => create(options), /Progress output is not available/u)
  assert.deepEqual(read(), previous)
  const existing = path.join(options.ownedDirectory, "existing.json")
  fs.writeFileSync(existing, "user-owned")
  assert.throws(
    () => create({ ...options, outputPath: existing }),
    /Progress output is not available/u
  )
  assert.equal(fs.readFileSync(existing, "utf8"), "user-owned")
  assert.equal(fs.existsSync(`${existing}.lock`), false)
  const reserved = path.join(options.ownedDirectory, "reserved.json")
  fs.writeFileSync(`${reserved}.lock`, "another writer")
  assert.throws(
    () => create({ ...options, outputPath: reserved }),
    /Progress output is not available/u
  )
  assert.equal(fs.readFileSync(`${reserved}.lock`, "utf8"), "another writer")
  assert.equal(fs.existsSync(reserved), false)
})

test("atomically replaces complete JSON and cleans temporary files", (t) => {
  let renamed = 0
  const injectedFs = {
    ...fs,
    renameSync(source, destination) {
      const snapshot = JSON.parse(fs.readFileSync(source, "utf8"))
      assert.equal(snapshot.informational, true)
      if (fs.existsSync(destination)) JSON.parse(fs.readFileSync(destination, "utf8"))
      renamed++
      fs.renameSync(source, destination)
    },
  }
  const { reporter, options } = fixture(t, { fs: injectedFs })
  reporter.onDryRunCompleted({})
  assert.equal(renamed, 2)
  assert.deepEqual(fs.readdirSync(options.ownedDirectory).sort(), [
    "progress.json",
    "progress.json.lock",
  ])
  reporter.wrapUp()
  assert.deepEqual(fs.readdirSync(options.ownedDirectory), ["progress.json"])
})

test("failed atomic write preserves the old file, latches generic failure, and releases ownership", (t) => {
  let fail = false
  const injectedFs = {
    ...fs,
    renameSync(source, destination) {
      if (fail) throw new Error("secret/path failure")
      fs.renameSync(source, destination)
    },
  }
  const { reporter, read, options } = fixture(t, { fs: injectedFs })
  const before = read()
  fail = true
  assert.throws(
    () => reporter.onDryRunCompleted({}),
    (error) =>
      error.code === "STRYKER_PROGRESS_WRITE_FAILED" &&
      error.message === "Unable to write Stryker progress"
  )
  assert.equal(reporter.writeFailed, true)
  assert.deepEqual(read(), before)
  assert.throws(
    () => reporter.onMutationTestingPlanReady(plan("1")),
    /Unable to write Stryker progress/u
  )
  assert.throws(() => reporter.wrapUp(), /Unable to write Stryker progress/u)
  assert.deepEqual(fs.readdirSync(options.ownedDirectory), ["progress.json"])
  reporter.wrapUp()
})

test("malformed plans latch failure and cannot be healed by later valid events", (t) => {
  for (const event of [
    {},
    { mutantPlans: [null] },
    { mutantPlans: [{ mutant: { id: "" } }] },
    { mutantPlans: [{ mutant: { id: "x".repeat(129) } }] },
  ]) {
    const { reporter, read, options } = fixture(t)
    const before = read()
    let original
    assert.throws(
      () => reporter.onMutationTestingPlanReady(event),
      (error) => {
        original = error
        return (
          error.message === "Invalid mutation testing plan" &&
          error.code === "STRYKER_PROGRESS_INVALID_PLAN"
        )
      }
    )
    try {
      assert.equal(reporter.writeFailed, true)
      for (const later of [
        () => reporter.onDryRunCompleted({}),
        () => reporter.onMutationTestingPlanReady(plan("1")),
        () => reporter.onMutantTested({ id: "1", status: "Killed" }),
        () => reporter.onMutationTestReportReady({}, {}),
      ])
        assert.throws(later, (error) => error === original)
      assert.deepEqual(read(), before)
    } finally {
      try {
        reporter.wrapUp()
      } catch (error) {
        assert.equal(error, original)
      }
    }
    assert.equal(fs.existsSync(`${options.outputPath}.lock`), false)
    assert.deepEqual(read(), before)
  }
})

test("exclusive temporary-file collision never deletes a foreign file", (t) => {
  let collide = false
  let foreignPath
  const foreignBytes = "foreign owner data"
  const collision = (target) => {
    foreignPath = target
    fs.writeFileSync(target, foreignBytes)
    throw Object.assign(new Error("private collision path"), { code: "EEXIST" })
  }
  const injectedFs = {
    ...fs,
    openSync(target, ...args) {
      if (collide && target.endsWith(".tmp")) collision(target)
      return fs.openSync(target, ...args)
    },
    writeFileSync(target, ...args) {
      if (collide && typeof target === "string" && target.endsWith(".tmp")) collision(target)
      return fs.writeFileSync(target, ...args)
    },
  }
  const { reporter, read } = fixture(t, { fs: injectedFs })
  const before = read()
  collide = true
  assert.throws(() => reporter.onDryRunCompleted({}), /Unable to write Stryker progress/u)
  try {
    assert.equal(fs.existsSync(foreignPath), true)
    assert.equal(fs.readFileSync(foreignPath, "utf8"), foreignBytes)
    assert.deepEqual(read(), before)
    assert.equal(reporter.writeFailed, true)
  } finally {
    assert.throws(() => reporter.wrapUp(), /Unable to write Stryker progress/u)
  }
})

for (const failurePoint of ["partial-write", "close"]) {
  test(`${failurePoint} failure closes its descriptor and removes only its own incomplete temporary file`, (t) => {
    let fail = false
    let usedOwnedDescriptor = false
    const descriptors = new Set()
    const injectedFs = {
      ...fs,
      openSync(target, ...args) {
        const fd = fs.openSync(target, ...args)
        descriptors.add(fd)
        return fd
      },
      writeFileSync(target, ...args) {
        if (fail) usedOwnedDescriptor = typeof target === "number" && descriptors.has(target)
        if (fail && failurePoint === "partial-write") {
          fs.writeFileSync(target, "incomplete")
          throw new Error("private partial write")
        }
        return fs.writeFileSync(target, ...args)
      },
      closeSync(fd) {
        if (fail && failurePoint === "close") {
          fail = false
          throw new Error("private close path")
        }
        fs.closeSync(fd)
        descriptors.delete(fd)
      },
    }
    const { reporter, options, read } = fixture(t, { fs: injectedFs })
    const before = read()
    fail = true
    assert.throws(() => reporter.onDryRunCompleted({}), /Unable to write Stryker progress/u)
    try {
      assert.deepEqual(read(), before)
      assert.equal(reporter.writeFailed, true)
      assert.equal(usedOwnedDescriptor, true)
      assert.equal(descriptors.size, 0)
      assert.deepEqual(fs.readdirSync(options.ownedDirectory).sort(), [
        "progress.json",
        "progress.json.lock",
      ])
    } finally {
      assert.throws(() => reporter.wrapUp(), /Unable to write Stryker progress/u)
    }
  })
}

test("initial lock close failure has bounded descriptor cleanup and a path-free error", (t) => {
  const ownedDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "stryker-progress-lock-"))
  const descriptors = new Set()
  t.after(() => {
    for (const fd of descriptors) fs.closeSync(fd)
    fs.rmSync(ownedDirectory, { recursive: true, force: true })
  })
  let closeAttempts = 0
  const injectedFs = {
    ...fs,
    openSync(target, ...args) {
      const fd = fs.openSync(target, ...args)
      descriptors.add(fd)
      return fd
    },
    closeSync(fd) {
      if (++closeAttempts === 1) throw new Error("private lock descriptor")
      fs.closeSync(fd)
      descriptors.delete(fd)
    },
  }
  assert.throws(
    () =>
      create(
        {
          enabled: true,
          ownedDirectory,
          outputPath: path.join(ownedDirectory, "progress.json"),
          runId: "run",
          shardId: "shard",
        },
        { fs: injectedFs }
      ),
    (error) =>
      error.code === "STRYKER_PROGRESS_WRITE_FAILED" &&
      error.message === "Unable to write Stryker progress"
  )
  assert.equal(closeAttempts, 2)
  assert.equal(descriptors.size, 0)
  assert.deepEqual(fs.readdirSync(ownedDirectory), [])
})

test("initial write failure removes only its own lock and temporary file", (t) => {
  const ownedDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "stryker-progress-initial-"))
  t.after(() => fs.rmSync(ownedDirectory, { recursive: true, force: true }))
  const options = {
    enabled: true,
    ownedDirectory,
    outputPath: path.join(ownedDirectory, "progress.json"),
    runId: "run",
    shardId: "shard",
  }
  assert.throws(
    () =>
      create(options, {
        fs: {
          ...fs,
          renameSync() {
            throw new Error("private write failure")
          },
        },
      }),
    /Unable to write Stryker progress/u
  )
  assert.deepEqual(fs.readdirSync(ownedDirectory), [])
})

test("ownership cleanup failure is generic and distinguishable, not a false healthy writer", (t) => {
  let fail = false
  const injectedFs = {
    ...fs,
    unlinkSync(target) {
      if (fail && target.endsWith(".lock")) throw new Error("private lock path")
      fs.unlinkSync(target)
    },
  }
  const { reporter, options } = fixture(t, { fs: injectedFs })
  fail = true
  assert.throws(
    () => reporter.wrapUp(),
    (error) =>
      error.code === "STRYKER_PROGRESS_WRITE_FAILED" &&
      error.message === "Unable to write Stryker progress"
  )
  assert.equal(reporter.writeFailed, true)
  assert.equal(fs.existsSync(`${options.outputPath}.lock`), true)
})
