import * as nodeFs from "node:fs"
import path from "node:path"
import { randomUUID } from "node:crypto"

const completedStatuses = new Set([
  "Killed",
  "Survived",
  "NoCoverage",
  "CompileError",
  "RuntimeError",
  "Timeout",
  "Ignored",
])
const validIdentity = (value) => typeof value === "string" && /^[A-Za-z0-9_-]{1,64}$/u.test(value)

/**
 * Standalone @stryker-mutator/api 10 Reporter callbacks; no plugin registration.
 * The caller must supply a fresh output file in a private, existing owned directory.
 * Events use synchronous atomic replacement to avoid stale async writes after wrapUp.
 * Failure latches and throws a path-free error. Stryker's BroadcastReporter catches
 * reporter errors: an integrating runner MUST observe writeFailed/freshness itself.
 * This record is informational only, never mutation/release acceptance evidence.
 */
export function createStrykerProgressReporter(options = {}, { fs = nodeFs, now = Date.now } = {}) {
  const enabled = options.enabled === true
  let failure = null
  let closed = false
  let ownsLock = false
  let plannedIds = null
  const completedIds = new Set()
  let outputPath
  let lockPath
  let snapshot

  const writeFailure = () =>
    (failure ??= Object.assign(new Error("Unable to write Stryker progress"), {
      code: "STRYKER_PROGRESS_WRITE_FAILED",
    }))
  const invalidPlan = () =>
    (failure ??= Object.assign(new Error("Invalid mutation testing plan"), {
      code: "STRYKER_PROGRESS_INVALID_PLAN",
    }))

  const releaseLock = () => {
    if (ownsLock) {
      try {
        fs.unlinkSync(lockPath)
        ownsLock = false
      } catch {
        throw writeFailure()
      }
    }
  }

  const write = (next) => {
    const temporary = `${outputPath}.${randomUUID()}.tmp`
    let descriptor = null
    let ownsTemporary = false
    try {
      const time = now()
      if (!Number.isSafeInteger(time) || time < 0) throw new Error("Invalid progress clock")
      next.updatedAtMs = Math.max(snapshot?.updatedAtMs ?? 0, time)
      descriptor = fs.openSync(temporary, "wx", 0o600)
      ownsTemporary = true
      fs.writeFileSync(descriptor, `${JSON.stringify(next)}\n`)
      fs.closeSync(descriptor)
      descriptor = null
      fs.renameSync(temporary, outputPath)
      ownsTemporary = false
      snapshot = next
    } catch {
      writeFailure()
    }
    // At most one cleanup close after a failed write/close. Never remove a
    // temporary path when exclusive open failed: it could belong to someone else.
    if (descriptor !== null) {
      try {
        fs.closeSync(descriptor)
      } catch {
        writeFailure()
      }
    }
    if (ownsTemporary) {
      try {
        fs.unlinkSync(temporary)
      } catch (error) {
        if (error.code !== "ENOENT") writeFailure()
      }
    }
    if (failure) throw failure
  }

  const active = () => {
    if (!enabled || closed) return false
    if (failure) throw failure
    return true
  }
  const advance = (phase, changes = {}) =>
    write({
      ...snapshot,
      ...changes,
      phase,
      sequence: snapshot.sequence + 1,
    })

  if (enabled) {
    if (
      !validIdentity(options.runId) ||
      !validIdentity(options.shardId) ||
      typeof options.outputPath !== "string" ||
      !path.isAbsolute(options.outputPath) ||
      typeof options.ownedDirectory !== "string" ||
      !path.isAbsolute(options.ownedDirectory) ||
      path.dirname(path.resolve(options.outputPath)) !== path.resolve(options.ownedDirectory)
    )
      throw new Error("Invalid progress reporter options")
    try {
      outputPath = path.join(
        fs.realpathSync(options.ownedDirectory),
        path.basename(options.outputPath)
      )
    } catch {
      throw new Error("Invalid progress reporter options")
    }
    lockPath = `${outputPath}.lock`
    let lockDescriptor = null
    try {
      lockDescriptor = fs.openSync(lockPath, "wx", 0o600)
      ownsLock = true
      try {
        fs.closeSync(lockDescriptor)
      } catch {
        throw writeFailure()
      }
      lockDescriptor = null
      try {
        fs.lstatSync(outputPath)
        throw new Error("Existing output")
      } catch (error) {
        if (error.code !== "ENOENT") throw error
      }
    } catch {
      if (lockDescriptor !== null) {
        try {
          fs.closeSync(lockDescriptor)
        } catch {
          writeFailure()
        }
      }
      releaseLock()
      if (failure) throw failure
      throw new Error("Progress output is not available")
    }
    try {
      write({
        schemaVersion: 1,
        runId: options.runId,
        shardId: options.shardId,
        phase: "initializing",
        sequence: 0,
        updatedAtMs: 0,
        plannedMutants: null,
        completedMutants: 0,
        reportReady: false,
        informational: true,
        releaseEligible: false,
      })
    } catch (error) {
      releaseLock()
      throw error
    }
  }

  return {
    get writeFailed() {
      return failure !== null
    },
    onDryRunCompleted() {
      if (active() && snapshot.phase === "initializing") advance("dry-run-completed")
    },
    onMutationTestingPlanReady(event) {
      if (!active() || plannedIds !== null || snapshot.reportReady) return
      if (!Array.isArray(event?.mutantPlans) || event.mutantPlans.length > 1_000_000) {
        throw invalidPlan()
      }
      const ids = new Set()
      for (const entry of event.mutantPlans) {
        const mutant = entry?.mutant
        if (typeof mutant?.id !== "string" || mutant.id.length === 0 || mutant.id.length > 128) {
          throw invalidPlan()
        }
        ids.add(mutant.id)
      }
      advance("plan-ready", { plannedMutants: ids.size })
      plannedIds = ids
    },
    onMutantTested(result) {
      if (!active() || plannedIds === null || snapshot.reportReady) return
      if (
        !plannedIds.has(result?.id) ||
        completedIds.has(result.id) ||
        !completedStatuses.has(result.status)
      )
        return
      advance("mutation-testing", { completedMutants: completedIds.size + 1 })
      completedIds.add(result.id)
    },
    onMutationTestReportReady() {
      if (active() && !snapshot.reportReady) advance("report-ready", { reportReady: true })
    },
    wrapUp() {
      if (!enabled || closed) return
      try {
        if (failure) throw failure
        advance("wrapped-up")
      } finally {
        closed = true
        releaseLock()
      }
    },
  }
}
