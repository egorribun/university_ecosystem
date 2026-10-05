import { spawnSync } from "node:child_process"
import { isAbsolute, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const liveWorktreeRoot = fileURLToPath(new URL("../../", import.meta.url))

const verifierEnvironmentKeys = [
  "PATH",
  "HOME",
  ...(process.platform === "win32"
    ? ["SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA"]
    : ["TMPDIR", "TMP", "TEMP"]),
]

function getEndpoint(environment, name, hostname) {
  const value = environment[name]
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} must be set to the endpoint printed by scripts/live_stand.py`)
  }

  let parsed
  try {
    parsed = new URL(value)
  } catch {
    throw new Error(`${name} must be a valid live-stand loopback URL`)
  }
  if (
    parsed.protocol !== "http:" ||
    parsed.hostname !== hostname ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    !parsed.port ||
    Number(parsed.port) < 20_000 ||
    Number(parsed.port) > 45_000 ||
    parsed.pathname !== "/" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new Error(`${name} must be a valid live-stand loopback URL`)
  }

  return value
}

function processEnvironment(environment) {
  return Object.fromEntries(
    verifierEnvironmentKeys
      .filter((name) => typeof environment[name] === "string")
      .map((name) => [name, environment[name]])
  )
}

function getInPlaceStateRoot(environment) {
  const value = environment.LIVE_STAND_STATE_ROOT
  if (value === undefined) {
    return undefined
  }
  if (typeof value !== "string" || value.trim() === "" || !isAbsolute(value)) {
    throw new Error("LIVE_STAND_STATE_ROOT must be an absolute in-place state directory")
  }
  return resolve(value)
}

function getPrimaryRepositoryRoot(environment, inPlaceStateRoot) {
  const value = environment.LIVE_PRIMARY_REPOSITORY_ROOT
  if (typeof value !== "string" || !isAbsolute(value)) {
    throw new Error("LIVE_PRIMARY_REPOSITORY_ROOT must be an absolute primary checkout path")
  }

  const primaryRoot = resolve(value)
  const normalizedPrimaryRoot =
    process.platform === "win32" ? primaryRoot.toLowerCase() : primaryRoot
  const normalizedWorktreeRoot =
    process.platform === "win32"
      ? resolve(liveWorktreeRoot).toLowerCase()
      : resolve(liveWorktreeRoot)
  const isFrontendCheckout = normalizedPrimaryRoot === normalizedWorktreeRoot
  if (inPlaceStateRoot === undefined && isFrontendCheckout) {
    throw new Error("LIVE_PRIMARY_REPOSITORY_ROOT must point to the primary checkout")
  }
  if (inPlaceStateRoot !== undefined && !isFrontendCheckout) {
    throw new Error(
      "LIVE_PRIMARY_REPOSITORY_ROOT must match the frontend checkout for an in-place stand"
    )
  }
  return primaryRoot
}

export function createLiveStandSetup({
  environment = process.env,
  runtimeEnvironment = process.env,
  runner = spawnSync,
} = {}) {
  return async function validateLiveStandEnvironment() {
    const baseUrl = getEndpoint(environment, "LIVE_BASE_URL", "localhost")
    const mailpitUrl = getEndpoint(environment, "LIVE_MAILPIT_URL", "127.0.0.1")
    const inPlaceStateRoot = getInPlaceStateRoot(environment)
    const primaryRepositoryRoot = getPrimaryRepositoryRoot(environment, inPlaceStateRoot)
    const verifierArguments = [
      "run",
      "--frozen",
      "--no-sync",
      "python",
      "scripts/live_stand.py",
      "verify-endpoints",
      "--base-url",
      baseUrl,
      "--mailpit-url",
      mailpitUrl,
    ]
    if (inPlaceStateRoot !== undefined) {
      verifierArguments.push("--in-place", "--state-dir", inPlaceStateRoot)
    }
    const result = runner("uv", verifierArguments, {
      cwd: primaryRepositoryRoot,
      env: processEnvironment(runtimeEnvironment),
      shell: false,
      stdio: "ignore",
      timeout: 30_000,
      windowsHide: true,
    })

    if (result.error || result.status !== 0) {
      throw new Error("live stand endpoint ownership verification failed")
    }
  }
}

export default function validateLiveStandEnvironment() {
  return createLiveStandSetup()()
}
