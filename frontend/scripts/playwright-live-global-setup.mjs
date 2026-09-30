import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url))

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

export function createLiveStandSetup({
  environment = process.env,
  runtimeEnvironment = process.env,
  runner = spawnSync,
} = {}) {
  return async function validateLiveStandEnvironment() {
    const baseUrl = getEndpoint(environment, "LIVE_BASE_URL", "localhost")
    const mailpitUrl = getEndpoint(environment, "LIVE_MAILPIT_URL", "127.0.0.1")
    const result = runner(
      "uv",
      [
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
      ],
      {
        cwd: repositoryRoot,
        env: processEnvironment(runtimeEnvironment),
        shell: false,
        stdio: "ignore",
        timeout: 30_000,
        windowsHide: true,
      }
    )

    if (result.error || result.status !== 0) {
      throw new Error("live stand endpoint ownership verification failed")
    }
  }
}

export default function validateLiveStandEnvironment() {
  return createLiveStandSetup()()
}
