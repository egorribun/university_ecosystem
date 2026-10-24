import { pathToFileURL } from "node:url"

// Tests-first checkpoint: no lock generation or network access is implemented.
export function prepareFinalManifest() {
  return null
}

export function prepareStrictManifest() {
  return null
}

export function assertFinalSourcePrerequisites() {
  return null
}

export function assertFinalLockScope() {
  return null
}

export function finalNpmCommand() {
  return null
}

export function assertFinalNpmCommand() {
  return null
}

export function strictPeerEnvironment() {
  return null
}

export function assertStrictLock() {
  return null
}

export function assertFinalInstalledGraph() {
  return null
}

export function inspectInstalledEngineLicense() {
  return null
}

export function validateFormatterMetadata() {
  return null
}

export async function runFinalCompilerGenerator() {
  return 1
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.stderr.write("Final compiler candidate rejected at stage: preflight\n")
  process.exitCode = 1
}
