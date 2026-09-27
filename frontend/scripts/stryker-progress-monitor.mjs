import * as nodeFs from "node:fs"
import path from "node:path"
import { performance } from "node:perf_hooks"

const maximumBytes = 4096
const maximumMutants = 1_000_000
const keys = [
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
]
const phases = [
  "initializing",
  "dry-run-completed",
  "plan-ready",
  "mutation-testing",
  "report-ready",
  "wrapped-up",
]
const validIdentity = (value) => typeof value === "string" && /^[A-Za-z0-9_-]{1,64}$/u.test(value)
const counter = (value, maximum = Number.MAX_SAFE_INTEGER) =>
  Number.isSafeInteger(value) && value >= 0 && value <= maximum
const invalid = (code = "STRYKER_PROGRESS_INVALID") =>
  Object.assign(new Error("Invalid Stryker progress"), { code })

function assertOptions(outputPath, identity) {
  if (
    typeof outputPath !== "string" ||
    !path.isAbsolute(outputPath) ||
    !validIdentity(identity?.runId) ||
    !validIdentity(identity?.shardId)
  )
    throw invalid()
}

function validateSnapshot(snapshot, identity) {
  if (
    snapshot === null ||
    typeof snapshot !== "object" ||
    Array.isArray(snapshot) ||
    Object.keys(snapshot).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(snapshot, key)) ||
    snapshot.schemaVersion !== 1 ||
    snapshot.runId !== identity.runId ||
    snapshot.shardId !== identity.shardId ||
    snapshot.informational !== true ||
    snapshot.releaseEligible !== false ||
    !phases.includes(snapshot.phase) ||
    !counter(snapshot.sequence, maximumMutants + 4) ||
    !counter(snapshot.updatedAtMs) ||
    !counter(snapshot.completedMutants, maximumMutants) ||
    snapshot.completedMutants > snapshot.sequence ||
    typeof snapshot.reportReady !== "boolean" ||
    (snapshot.plannedMutants !== null && !counter(snapshot.plannedMutants, maximumMutants)) ||
    snapshot.completedMutants > (snapshot.plannedMutants ?? 0)
  )
    throw invalid()

  const { phase, plannedMutants, completedMutants, sequence, reportReady } = snapshot
  if (
    (phase === "initializing" && sequence !== 0) ||
    (phase !== "initializing" && sequence === 0) ||
    (["initializing", "dry-run-completed"].includes(phase) &&
      (plannedMutants !== null || completedMutants !== 0)) ||
    (["plan-ready", "mutation-testing"].includes(phase) && plannedMutants === null) ||
    (phase === "plan-ready" && completedMutants !== 0) ||
    (phase === "mutation-testing" && completedMutants === 0) ||
    (phase === "report-ready" && !reportReady) ||
    (reportReady && !["report-ready", "wrapped-up"].includes(phase))
  )
    throw invalid()
  return Object.freeze(snapshot)
}

/**
 * Bounded informational snapshot reader. Missing startup output returns null.
 * Nonregular/symlink paths and malformed records fail with path-free errors.
 * Uses a descriptor and no-follow/nonblocking flags where supported so a path
 * substitution cannot turn an ordinary read into an unbounded pipe read.
 * The caller owns the private directory; this reader never writes or removes it.
 */
export function readProgressSnapshot(outputPath, identity, { fs = nodeFs } = {}) {
  assertOptions(outputPath, identity)
  const identityRace = Symbol("identity race")
  // Atomic reporter rename may occur between lstat and open. Retry only that
  // identity race, without sleeps, and close each descriptor before retrying.
  for (let attempt = 0; attempt < 3; attempt++) {
    let before
    try {
      before = fs.lstatSync(outputPath)
    } catch (error) {
      if (error.code === "ENOENT") return null
      throw invalid()
    }
    if (!before.isFile() || before.isSymbolicLink() || before.size > maximumBytes) throw invalid()
    let descriptor = null
    let failure = null
    let result
    try {
      descriptor = fs.openSync(
        outputPath,
        fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0) | (fs.constants.O_NONBLOCK ?? 0)
      )
      const opened = fs.fstatSync(descriptor)
      if (!opened.isFile() || opened.size > maximumBytes) throw invalid()
      if (opened.dev !== before.dev || opened.ino !== before.ino) throw identityRace
      const bytes = Buffer.alloc(maximumBytes + 1)
      let length = 0
      while (length < bytes.length) {
        const read = fs.readSync(descriptor, bytes, length, bytes.length - length, null)
        if (read === 0) break
        length += read
      }
      if (length > maximumBytes) throw invalid()
      result = validateSnapshot(JSON.parse(bytes.subarray(0, length).toString("utf8")), identity)
    } catch (error) {
      failure = error === identityRace ? identityRace : invalid()
    } finally {
      if (descriptor !== null) {
        try {
          fs.closeSync(descriptor)
        } catch {
          // A close failure cannot turn into another acquisition attempt.
          if (failure === null || failure === identityRace) failure = invalid()
        }
      }
    }
    if (failure === identityRace) continue
    if (failure) throw failure
    return result
  }
  throw invalid()
}

/**
 * Manual observations only: no timers, inactivity policy, resource probes or
 * process ownership. Parent monotonic time is independent of producer time.
 * A valid terminal lifecycle is not a mutation score or release authorization.
 * Cross-process midrun writeFailed is unavailable: frozen output can represent
 * either a failed reporter or legitimate work. Runner integration must retain
 * wall deadlines, quiescence proof and authoritative mutation report validation.
 */
export function createStrykerProgressMonitor(
  options,
  { now = () => performance.now(), fs = nodeFs } = {}
) {
  const outputPath = options?.outputPath
  const identity = Object.freeze({ runId: options?.runId, shardId: options?.shardId })
  assertOptions(outputPath, identity)
  let previous = null
  let observedAt = null
  let lastCompletionAt = null
  let failure = null
  const fail = (error) => {
    failure ??= error
    throw failure
  }
  const observe = () => {
    if (failure) throw failure
    try {
      const time = now()
      if (!Number.isFinite(time) || time < 0 || (observedAt !== null && time < observedAt))
        throw invalid()
      const snapshot = readProgressSnapshot(outputPath, identity, { fs })
      if (snapshot === null && previous !== null) throw invalid()
      if (snapshot && previous) {
        if (
          snapshot.sequence < previous.sequence ||
          snapshot.completedMutants < previous.completedMutants ||
          snapshot.completedMutants - previous.completedMutants >
            snapshot.sequence - previous.sequence ||
          snapshot.updatedAtMs < previous.updatedAtMs ||
          phases.indexOf(snapshot.phase) < phases.indexOf(previous.phase) ||
          (previous.plannedMutants !== null &&
            snapshot.plannedMutants !== previous.plannedMutants) ||
          (previous.reportReady && !snapshot.reportReady) ||
          (previous.reportReady && snapshot.completedMutants !== previous.completedMutants) ||
          (previous.reportReady && snapshot.plannedMutants !== previous.plannedMutants) ||
          (previous.phase === "wrapped-up" &&
            keys.some((key) => snapshot[key] !== previous[key])) ||
          (snapshot.sequence === previous.sequence &&
            keys.some((key) => snapshot[key] !== previous[key])) ||
          (snapshot.sequence > previous.sequence &&
            snapshot.phase === previous.phase &&
            snapshot.completedMutants === previous.completedMutants)
        )
          throw invalid()
      }
      const completionAdvanced =
        snapshot !== null && snapshot.completedMutants > (previous?.completedMutants ?? 0)
      const phaseAdvanced =
        snapshot !== null && snapshot.phase !== (previous?.phase ?? "initializing")
      if (completionAdvanced) lastCompletionAt = time
      observedAt = time
      previous = snapshot
      return Object.freeze({
        snapshot,
        completionAdvanced,
        phaseAdvanced,
        observedAtMs: time,
        lastCompletionAtMs: lastCompletionAt,
      })
    } catch {
      return fail(invalid())
    }
  }
  return {
    get failed() {
      return failure !== null
    },
    observe,
    validateExit(exitCode) {
      if (failure) throw failure
      if (exitCode !== 0) return fail(invalid("STRYKER_PROGRESS_CHILD_FAILED"))
      const { snapshot } = observe()
      if (
        snapshot === null ||
        snapshot.phase !== "wrapped-up" ||
        !snapshot.reportReady ||
        snapshot.plannedMutants === null
      ) {
        return fail(invalid("STRYKER_PROGRESS_INCOMPLETE"))
      }
      return snapshot
    },
  }
}
