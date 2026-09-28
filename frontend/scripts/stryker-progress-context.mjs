import { lstat, mkdtemp } from "node:fs/promises"
import path from "node:path"
import { createStrykerProgressMonitor } from "./stryker-progress-monitor.mjs"

const progressFields = new Set([
  "STRYKER_PROGRESS_ENABLED",
  "STRYKER_PROGRESS_DIRECTORY",
  "STRYKER_PROGRESS_OUTPUT",
  "STRYKER_PROGRESS_RUN_ID",
  "STRYKER_PROGRESS_SHARD_ID",
  "STRYKER_PROGRESS_EXPORT_DIRECTORY",
  "GITHUB_OUTPUT",
])
const invalid = () =>
  Object.assign(new Error("Invalid Stryker progress context"), {
    code: "STRYKER_PROGRESS_CONTEXT_INVALID",
  })
const validIdentity = (value) => typeof value === "string" && /^[A-Za-z0-9_-]{1,64}$/u.test(value)
const validPath = (value) =>
  typeof value === "string" &&
  value.length > 0 &&
  value.length <= 4096 &&
  [...value].every(
    (character) => character.charCodeAt(0) >= 32 && character.charCodeAt(0) !== 127
  ) &&
  path.isAbsolute(value)

/**
 * Opt-in preparation only. Caller supplies an existing private owned shardTemp
 * and retains all process/cleanup authority. lstat is a useful shape check, not
 * a hostile-filesystem ownership guarantee (including ancestor/race attacks).
 * Fresh directories remain under shardTemp for the parent's existing finalizer.
 * No timers, inactivity policy, resource probes, process wrapper or quality proof.
 * observeLive is a synchronous bounded reader; the existing child owner schedules it.
 * Invoke validateSuccessfulExit ONLY after existing runNode success/quiescence;
 * never in finally or after a child failure. Its snapshot is informational only.
 */
export async function createStrykerProgressContext(options = {}) {
  if (options === null || typeof options !== "object" || Array.isArray(options)) throw invalid()
  const parentEnv = options.parentEnv === undefined ? process.env : options.parentEnv
  if (parentEnv === null || typeof parentEnv !== "object" || Array.isArray(parentEnv))
    throw invalid()
  // Filter before reading values, including disabled mode's hostile payloads.
  const childEnv = Object.fromEntries(
    Object.keys(parentEnv)
      .filter((key) => !progressFields.has(key))
      .map((key) => [key, parentEnv[key]])
  )
  if (options.enabled !== "1") {
    return Object.freeze({
      childEnv: Object.freeze(childEnv),
      observeLive: () => undefined,
      validateSuccessfulExit: () => undefined,
    })
  }
  const { shardTemp, runId, shardId } = options
  if (!validPath(shardTemp) || !validIdentity(runId) || !validIdentity(shardId)) throw invalid()
  let ownedDirectory
  try {
    const parent = await lstat(shardTemp)
    if (!parent.isDirectory() || parent.isSymbolicLink()) throw invalid()
    ownedDirectory = await mkdtemp(path.join(shardTemp, "progress-"))
  } catch {
    throw invalid()
  }
  const outputPath = path.join(ownedDirectory, "progress.json")
  Object.assign(childEnv, {
    STRYKER_PROGRESS_ENABLED: "1",
    STRYKER_PROGRESS_DIRECTORY: ownedDirectory,
    STRYKER_PROGRESS_OUTPUT: outputPath,
    STRYKER_PROGRESS_RUN_ID: runId,
    STRYKER_PROGRESS_SHARD_ID: shardId,
  })
  const monitor = createStrykerProgressMonitor({ outputPath, runId, shardId })
  return Object.freeze({
    childEnv: Object.freeze(childEnv),
    observeLive: () => monitor.observe(),
    validateSuccessfulExit: () => monitor.validateExit(0),
    lastObservation: () => monitor.lastObservation(),
  })
}
