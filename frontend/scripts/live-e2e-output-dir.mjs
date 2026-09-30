import { lstatSync, readFileSync, realpathSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

export const LIVE_E2E_OUTPUT_OWNER_MARKER = ".ue-live-e2e-output-owner"
export const LIVE_E2E_OUTPUT_OWNER_MARKER_CONTENT = "ue-live-playwright-output-v1\n"

const OUTPUT_ENVIRONMENT_NAMES = ["LIVE_E2E_OUTPUT_DIR", "PLAYWRIGHT_TEST_OUTPUT_DIR"]
const NPM_CONFIG_FILES = [
  ["NPM_CONFIG_USERCONFIG", "npm-userconfig"],
  ["NPM_CONFIG_GLOBALCONFIG", "npm-globalconfig"],
]

function pathsMatch(left, right) {
  const normalizedLeft = path.resolve(left)
  const normalizedRight = path.resolve(right)
  return process.platform === "win32"
    ? normalizedLeft.toLowerCase() === normalizedRight.toLowerCase()
    : normalizedLeft === normalizedRight
}

function repositoryOutputDirectory(frontendRoot) {
  const root = realpathSync(frontendRoot)
  const output = path.join(root, "test-results")
  try {
    const info = lstatSync(output)
    if (!info.isDirectory() || info.isSymbolicLink() || !pathsMatch(realpathSync(output), output)) {
      throw new Error("unsafe repository output directory")
    }
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw new Error("live E2E output directory is not a safe repository path", { cause: error })
    }
  }
  return output
}

function isOwnedTemporaryOutputDirectory(output, environment, temporaryRoot) {
  try {
    const temporary = realpathSync(temporaryRoot)
    const outputInfo = lstatSync(output)
    if (!outputInfo.isDirectory() || outputInfo.isSymbolicLink()) return false

    const outputReal = realpathSync(output)
    const ownerRoot = realpathSync(path.dirname(output))
    if (
      !pathsMatch(outputReal, path.join(ownerRoot, "playwright-output")) ||
      !pathsMatch(path.dirname(ownerRoot), temporary) ||
      !path.basename(ownerRoot).startsWith("ue-live-playwright-")
    ) {
      return false
    }

    const markerPath = path.join(ownerRoot, LIVE_E2E_OUTPUT_OWNER_MARKER)
    const markerInfo = lstatSync(markerPath)
    if (
      !markerInfo.isFile() ||
      markerInfo.isSymbolicLink() ||
      readFileSync(markerPath, "utf8") !== LIVE_E2E_OUTPUT_OWNER_MARKER_CONTENT
    ) {
      return false
    }

    for (const [environmentName, expectedName] of NPM_CONFIG_FILES) {
      const configuredPath = environment[environmentName]
      if (typeof configuredPath !== "string" || !configuredPath.trim()) {
        return false
      }
      const configPath = realpathSync(configuredPath)
      const configInfo = lstatSync(configuredPath)
      if (
        !configInfo.isFile() ||
        configInfo.isSymbolicLink() ||
        configInfo.size !== 0 ||
        !pathsMatch(path.dirname(configPath), ownerRoot) ||
        path.basename(configPath) !== expectedName
      ) {
        return false
      }
    }

    return true
  } catch {
    return false
  }
}

export function assertNoLiveE2EOutputOverride(args = process.argv.slice(2)) {
  if (
    args.some(
      (argument) =>
        argument === "--output" ||
        argument.startsWith("--output=") ||
        argument === "-o" ||
        argument.startsWith("-o=")
    )
  ) {
    throw new Error("live E2E output directory cannot be overridden on the CLI")
  }
}

export function resolveLiveE2EOutputDirectory({
  environment = process.env,
  frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."),
  temporaryRoot = tmpdir(),
  args = process.argv.slice(2),
} = {}) {
  assertNoLiveE2EOutputOverride(args)

  const root = realpathSync(frontendRoot)
  const configured = []
  for (const name of OUTPUT_ENVIRONMENT_NAMES) {
    const value = environment[name]
    if (value === undefined) continue
    if (typeof value !== "string" || !value.trim()) {
      throw new Error("live E2E output overrides must be non-empty paths")
    }
    configured.push(path.isAbsolute(value) ? path.resolve(value) : path.resolve(root, value))
  }

  if (configured.length > 1 && !pathsMatch(configured[0], configured[1])) {
    throw new Error("live E2E output overrides must resolve to the same directory")
  }

  if (configured.length === 0) return repositoryOutputDirectory(root)

  const output = configured[0]
  const repositoryOutput = repositoryOutputDirectory(root)
  if (pathsMatch(output, repositoryOutput)) return repositoryOutput
  if (isOwnedTemporaryOutputDirectory(output, environment, temporaryRoot)) {
    return realpathSync(output)
  }

  throw new Error("live E2E output must use repository test-results or the owned temporary output")
}
