import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

const api = await import("./stryker-progress-diagnostic.mjs").catch((error) => {
  if (error.code === "ERR_MODULE_NOT_FOUND") return {}
  throw error
})

const sha = "a".repeat(40)
const identity = {
  runId: "run-1",
  shardId: "shard-001",
  sourceHeadSha: sha,
  testedSha: "b".repeat(40),
  workflowRunId: "123",
  workflowRunAttempt: "2",
}

test("fresh owner publishes bounded informational JSON outside private temp", async (t) => {
  assert.equal(typeof api.createStrykerDiagnosticOwner, "function")
  const outputRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-"))
  t.after(() => rm(outputRoot, { recursive: true, force: true }))
  const owner = await api.createStrykerDiagnosticOwner({ outputRoot, ...identity })
  const observation = {
    snapshot: {
      schemaVersion: 1,
      runId: identity.runId,
      shardId: identity.shardId,
      phase: "mutation-testing",
      sequence: 3,
      updatedAtMs: 123,
      plannedMutants: 2,
      completedMutants: 1,
      reportReady: false,
      informational: true,
      releaseEligible: false,
    },
    observedAtMs: 456,
    lastCompletionAtMs: 456,
  }
  await owner.publish({
    outcome: "failed",
    processQuiesced: false,
    failureCode: "child_failed",
    lastObservation: observation,
  })
  const bytes = await readFile(owner.path)
  assert.ok(bytes.length <= 8192)
  const record = JSON.parse(bytes.toString("utf8"))
  assert.deepEqual(record, {
    schemaVersion: 1,
    informational: true,
    releaseEligible: false,
    runnerRunId: identity.runId,
    shardId: identity.shardId,
    sourceHeadSha: identity.sourceHeadSha,
    testedSha: identity.testedSha,
    workflowRunId: identity.workflowRunId,
    workflowRunAttempt: identity.workflowRunAttempt,
    outcome: "failed",
    processQuiesced: false,
    failureCode: "child_failed",
    lastObservation: observation,
    resources: { cpuSeconds: null, rssBytes: null },
  })
  assert.deepEqual(await readdir(path.dirname(owner.path)), [`${identity.shardId}.json`])
  await assert.rejects(() =>
    owner.publish({
      outcome: "succeeded",
      processQuiesced: true,
      failureCode: null,
      lastObservation: null,
    })
  )
})

test("single export contains only owner-written JSON despite checkout sibling pollution", async (t) => {
  const outputRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-checkout-"))
  const exportDirectory = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-export-"))
  t.after(() => rm(outputRoot, { recursive: true, force: true }))
  t.after(() => rm(exportDirectory, { recursive: true, force: true }))
  const stale = path.join(outputRoot, "progress-diagnostics", "stale", "shard-999.json")
  await mkdir(path.dirname(stale), { recursive: true })
  await writeFile(stale, '{"untrusted":true}\n')

  const owner = await api.createStrykerDiagnosticOwner({ outputRoot, exportDirectory, ...identity })
  assert.equal(owner.path, path.join(exportDirectory, "diagnostic.json"))
  await owner.publish({
    outcome: "failed",
    processQuiesced: false,
    failureCode: "child_failed",
    lastObservation: null,
  })
  assert.deepEqual(await readdir(exportDirectory), ["diagnostic.json"])
  assert.equal(JSON.parse(await readFile(owner.path, "utf8")).releaseEligible, false)
  assert.equal(await readFile(stale, "utf8"), '{"untrusted":true}\n')
})

test("single export rejects a preexisting target without replacing it", async (t) => {
  const outputRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-checkout-"))
  const exportDirectory = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-export-"))
  t.after(() => rm(outputRoot, { recursive: true, force: true }))
  t.after(() => rm(exportDirectory, { recursive: true, force: true }))
  const target = path.join(exportDirectory, "diagnostic.json")
  await writeFile(target, '{"untrusted":true}\n')
  await assert.rejects(
    () => api.createStrykerDiagnosticOwner({ outputRoot, exportDirectory, ...identity }),
    { code: "STRYKER_DIAGNOSTIC_INVALID" }
  )
  assert.equal(await readFile(target, "utf8"), '{"untrusted":true}\n')
})

test("owner rejects invalid identity and unsafe target before publication", async (t) => {
  const outputRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-"))
  t.after(() => rm(outputRoot, { recursive: true, force: true }))
  await assert.rejects(() =>
    api.createStrykerDiagnosticOwner({ outputRoot, ...identity, testedSha: "invalid" })
  )
  assert.deepEqual(await readdir(outputRoot), [])
  const target = path.join(outputRoot, "target")
  await writeFile(target, "untouched")
  const link = path.join(outputRoot, "progress-diagnostics")
  try {
    await symlink(target, link, "junction")
  } catch (error) {
    if (process.platform !== "win32" || error.code !== "EPERM") throw error
    t.skip("Windows host cannot create links")
    return
  }
  await assert.rejects(() => api.createStrykerDiagnosticOwner({ outputRoot, ...identity }))
  assert.equal(await readFile(target, "utf8"), "untouched")
})

test("encoder refuses extra producer fields and path or secret data", async (t) => {
  const outputRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-"))
  t.after(() => rm(outputRoot, { recursive: true, force: true }))
  const owner = await api.createStrykerDiagnosticOwner({ outputRoot, ...identity })
  await assert.rejects(
    () =>
      owner.publish({
        outcome: "failed",
        processQuiesced: false,
        failureCode: "token=/private/path",
        lastObservation: null,
      }),
    { code: "STRYKER_DIAGNOSTIC_INVALID" }
  )
  const freshOwner = await api.createStrykerDiagnosticOwner({
    outputRoot,
    ...identity,
    runId: "run-2",
  })
  await assert.rejects(
    () =>
      freshOwner.publish({
        outcome: "failed",
        processQuiesced: false,
        failureCode: "child_failed",
        lastObservation: {
          snapshot: { unexpected: "private-value" },
          observedAtMs: 1,
          lastCompletionAtMs: null,
        },
      }),
    { code: "STRYKER_DIAGNOSTIC_INVALID" }
  )
  assert.deepEqual(await readdir(path.dirname(owner.path)), [])
  assert.deepEqual(await readdir(path.dirname(freshOwner.path)), [])
})

test("encoder rejects impossible or unbounded progress counters", async (t) => {
  const outputRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-diagnostic-"))
  t.after(() => rm(outputRoot, { recursive: true, force: true }))
  const owner = await api.createStrykerDiagnosticOwner({ outputRoot, ...identity })
  const snapshot = {
    schemaVersion: 1,
    runId: identity.runId,
    shardId: identity.shardId,
    phase: "mutation-testing",
    sequence: 2,
    updatedAtMs: 3,
    plannedMutants: 2,
    completedMutants: 3,
    reportReady: false,
    informational: true,
    releaseEligible: false,
  }
  await assert.rejects(() =>
    owner.publish({
      outcome: "failed",
      processQuiesced: false,
      failureCode: "child_failed",
      lastObservation: { snapshot, observedAtMs: 4, lastCompletionAtMs: 4 },
    })
  )
  assert.deepEqual(await readdir(path.dirname(owner.path)), [])
})
