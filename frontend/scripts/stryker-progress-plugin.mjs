import path from "node:path"
import { declareFactoryPlugin, PluginKind } from "@stryker-mutator/api/plugin"
import { createStrykerProgressReporter } from "./stryker-progress-reporter.mjs"

export const STRYKER_PROGRESS_REPORTER_NAME = "owned-progress"

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
 * Stryker10 factory-only adapter: importing this module never owns files/locks.
 * Runner-owned context contract: STRYKER_PROGRESS_ENABLED="1", plus
 * STRYKER_PROGRESS_DIRECTORY, STRYKER_PROGRESS_OUTPUT, STRYKER_PROGRESS_RUN_ID,
 * STRYKER_PROGRESS_SHARD_ID. Paths refer to a private existing runner-owned
 * directory and its fresh direct-child output; directory ownership is not
 * established by accepting an environment variable. No other environment data
 * is read or serialized. Disabled mode ignores all payload fields.
 * BroadcastReporter swallows callback failures, so the runner must independently
 * validate output lifecycle/freshness, retain wall deadlines and quality gates.
 */
function createReporter() {
  if (process.env.STRYKER_PROGRESS_ENABLED !== "1")
    return createStrykerProgressReporter({ enabled: false })
  const ownedDirectory = process.env.STRYKER_PROGRESS_DIRECTORY
  const outputPath = process.env.STRYKER_PROGRESS_OUTPUT
  const runId = process.env.STRYKER_PROGRESS_RUN_ID
  const shardId = process.env.STRYKER_PROGRESS_SHARD_ID
  if (
    !validPath(ownedDirectory) ||
    !validPath(outputPath) ||
    !validIdentity(runId) ||
    !validIdentity(shardId) ||
    path.dirname(path.resolve(outputPath)) !== path.resolve(ownedDirectory)
  )
    throw new Error("Invalid progress plugin options")
  return createStrykerProgressReporter({
    enabled: true,
    ownedDirectory,
    outputPath,
    runId,
    shardId,
  })
}

export const strykerPlugins = [
  declareFactoryPlugin(PluginKind.Reporter, STRYKER_PROGRESS_REPORTER_NAME, createReporter),
]
