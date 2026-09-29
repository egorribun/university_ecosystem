import { randomUUID } from "node:crypto"
import { link, lstat, mkdir, open, readdir, rm } from "node:fs/promises"
import path from "node:path"

const maximumBytes = 8192
const identityPattern = /^[A-Za-z0-9_-]{1,64}$/u
const shaPattern = /^[0-9a-f]{40}$/u
const decimalPattern = /^[1-9][0-9]{0,19}$/u
const phases = new Set([
  "initializing",
  "dry-run-completed",
  "plan-ready",
  "mutation-testing",
  "report-ready",
  "wrapped-up",
])
const failureCodes = new Set([
  "cancelled",
  "child_failed",
  "observer_invalid",
  "terminal_incomplete",
])
const invalid = () =>
  Object.assign(new Error("Invalid Stryker diagnostic"), { code: "STRYKER_DIAGNOSTIC_INVALID" })
const publicationFailed = () =>
  Object.assign(new Error("Stryker diagnostic publication failed"), {
    code: "STRYKER_DIAGNOSTIC_PUBLICATION_FAILED",
  })
const exactKeys = (value, keys) =>
  value !== null &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key))
const counter = (value) => Number.isSafeInteger(value) && value >= 0
const validWorkflowId = (value) =>
  value === null || (typeof value === "string" && decimalPattern.test(value))

function validateObservation(observation, runId, shardId) {
  if (observation === null) return null
  if (!exactKeys(observation, ["snapshot", "observedAtMs", "lastCompletionAtMs"])) throw invalid()
  const snapshot = observation.snapshot
  if (
    !exactKeys(snapshot, [
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
    ]) ||
    snapshot.schemaVersion !== 1 ||
    snapshot.runId !== runId ||
    snapshot.shardId !== shardId ||
    !phases.has(snapshot.phase) ||
    !counter(snapshot.sequence) ||
    snapshot.sequence > 1_000_004 ||
    !counter(snapshot.updatedAtMs) ||
    (snapshot.plannedMutants !== null &&
      (!counter(snapshot.plannedMutants) || snapshot.plannedMutants > 1_000_000)) ||
    !counter(snapshot.completedMutants) ||
    snapshot.completedMutants > 1_000_000 ||
    snapshot.completedMutants > snapshot.sequence ||
    snapshot.completedMutants > (snapshot.plannedMutants ?? 0) ||
    typeof snapshot.reportReady !== "boolean" ||
    snapshot.informational !== true ||
    snapshot.releaseEligible !== false ||
    !Number.isFinite(observation.observedAtMs) ||
    observation.observedAtMs < 0 ||
    (observation.lastCompletionAtMs !== null &&
      (!Number.isFinite(observation.lastCompletionAtMs) ||
        observation.lastCompletionAtMs < 0 ||
        observation.lastCompletionAtMs > observation.observedAtMs))
  )
    throw invalid()
  return {
    snapshot: Object.fromEntries(
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
      ].map((key) => [key, snapshot[key]])
    ),
    observedAtMs: observation.observedAtMs,
    lastCompletionAtMs: observation.lastCompletionAtMs,
  }
}

function encode(identity, result) {
  if (
    !exactKeys(result, ["outcome", "processQuiesced", "failureCode", "lastObservation"]) ||
    !["succeeded", "failed", "interrupted"].includes(result.outcome) ||
    typeof result.processQuiesced !== "boolean" ||
    (result.outcome === "succeeded"
      ? result.failureCode !== null
      : !failureCodes.has(result.failureCode))
  )
    throw invalid()
  const record = {
    schemaVersion: 1,
    informational: true,
    releaseEligible: false,
    runnerRunId: identity.runId,
    shardId: identity.shardId,
    sourceHeadSha: identity.sourceHeadSha,
    testedSha: identity.testedSha,
    workflowRunId: identity.workflowRunId,
    workflowRunAttempt: identity.workflowRunAttempt,
    outcome: result.outcome,
    processQuiesced: result.processQuiesced,
    failureCode: result.failureCode,
    lastObservation: validateObservation(result.lastObservation, identity.runId, identity.shardId),
    resources: { cpuSeconds: null, rssBytes: null },
  }
  const bytes = Buffer.from(`${JSON.stringify(record)}\n`, "utf8")
  if (bytes.length > maximumBytes) throw invalid()
  return bytes
}

/** Informational only. The caller owns outputRoot and all process lifecycle decisions. */
export async function createStrykerDiagnosticOwner(identity) {
  const {
    outputRoot,
    runId,
    shardId,
    sourceHeadSha,
    testedSha,
    workflowRunId,
    workflowRunAttempt,
    exportDirectory,
  } = identity ?? {}
  if (
    typeof outputRoot !== "string" ||
    !path.isAbsolute(outputRoot) ||
    !identityPattern.test(runId) ||
    !identityPattern.test(shardId) ||
    !shaPattern.test(sourceHeadSha) ||
    !shaPattern.test(testedSha) ||
    !validWorkflowId(workflowRunId) ||
    !validWorkflowId(workflowRunAttempt) ||
    (workflowRunId === null) !== (workflowRunAttempt === null) ||
    (exportDirectory !== undefined &&
      exportDirectory !== null &&
      (typeof exportDirectory !== "string" || !path.isAbsolute(exportDirectory)))
  )
    throw invalid()
  const singleExport = exportDirectory !== undefined && exportDirectory !== null
  const parent = path.join(outputRoot, "progress-diagnostics")
  const ownedDirectory = singleExport ? exportDirectory : path.join(parent, runId)
  const target = path.join(ownedDirectory, singleExport ? "diagnostic.json" : `${shardId}.json`)
  try {
    const root = await lstat(outputRoot)
    if (!root.isDirectory() || root.isSymbolicLink()) throw invalid()
    if (singleExport) {
      // The workflow supplies a fresh, private runner-temp directory. Never
      // publish into a directory containing another checkout or attempt's file.
      const directory = await lstat(ownedDirectory)
      if (!directory.isDirectory() || directory.isSymbolicLink()) throw invalid()
      if ((await readdir(ownedDirectory)).length !== 0) throw invalid()
    } else {
      try {
        await mkdir(parent)
      } catch (error) {
        if (error.code !== "EEXIST") throw error
      }
      const parentStat = await lstat(parent)
      if (!parentStat.isDirectory() || parentStat.isSymbolicLink()) throw invalid()
      await mkdir(ownedDirectory, { mode: 0o700 })
    }
  } catch {
    throw invalid()
  }
  const frozenIdentity = Object.freeze({
    runId,
    shardId,
    sourceHeadSha,
    testedSha,
    workflowRunId,
    workflowRunAttempt,
  })
  let attempted = false
  return Object.freeze({
    path: target,
    async publish(result) {
      if (attempted) throw publicationFailed()
      attempted = true
      const bytes = encode(frozenIdentity, result)
      const temporary = path.join(ownedDirectory, `.${randomUUID()}.tmp`)
      let failure = null
      try {
        const directory = await lstat(ownedDirectory)
        if (!directory.isDirectory() || directory.isSymbolicLink()) throw publicationFailed()
        const handle = await open(temporary, "wx", 0o600)
        try {
          await handle.writeFile(bytes)
        } finally {
          await handle.close()
        }
        // Linking a fully closed private file creates the final name atomically
        // without overwriting a preexisting record on either POSIX or Windows.
        await link(temporary, target)
      } catch {
        failure = publicationFailed()
      }
      try {
        await rm(temporary, { force: true })
      } catch {
        failure ??= publicationFailed()
      }
      if (failure) throw failure
    },
  })
}
