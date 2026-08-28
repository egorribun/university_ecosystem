import { existsSync } from "node:fs"
import path from "node:path"
import process from "node:process"

/**
 * Resolve npm to a JavaScript entrypoint that can be run by Node.
 *
 * Windows `.cmd` shims require `cmd.exe`; passing URL or flag arguments
 * through that interpreter would re-enable command parsing (`&`, `|`, `%`,
 * and friends) even when Node's `shell` option is false. npm exposes its own
 * CLI path while executing package scripts; the adjacent bundled CLI is the
 * deterministic fallback for direct `node` invocation.
 */
export function resolveNpmCliPath({
  env = process.env,
  execPath = process.execPath,
  exists = existsSync,
} = {}) {
  const configured = env.npm_execpath ?? env.NPM_EXEC_PATH
  const nodeDir = path.dirname(execPath)
  const candidates = [configured, path.join(nodeDir, "node_modules", "npm", "bin", "npm-cli.js")]

  for (const candidate of candidates) {
    if (
      !candidate ||
      !path.isAbsolute(candidate) ||
      path.extname(candidate).toLowerCase() !== ".js"
    ) {
      continue
    }
    if (exists(candidate)) return candidate
  }
  return undefined
}

/**
 * Build a shell-free child-process invocation for the commands used by LHCI.
 * On Windows npm is invoked as `node npm-cli.js ...` rather than via
 * `cmd.exe /c npm.cmd ...`, so every argument remains an argv value.
 */
export function buildSafeCommandInvocation(
  command,
  args,
  {
    platform = process.platform,
    execPath = process.execPath,
    env = process.env,
    npmCliPath,
    exists = existsSync,
  } = {}
) {
  if (!Array.isArray(args)) throw new TypeError("Command arguments must be an array")
  if (platform !== "win32") return { executable: command, args: [...args] }
  if (command === "npx") {
    throw new Error("npx is not supported on Windows; use the shell-free npm exec invocation")
  }
  if (command !== "npm") return { executable: command, args: [...args] }

  const cliPath = npmCliPath ?? resolveNpmCliPath({ env, execPath, exists })
  if (!cliPath || path.extname(cliPath).toLowerCase() !== ".js") {
    throw new Error("Unable to resolve the bundled npm CLI on Windows; refusing to invoke cmd.exe")
  }
  return { executable: execPath, args: [cliPath, ...args] }
}
