import { resolve } from "node:path"
import { pathToFileURL } from "node:url"

// Deliberately inert RED checkpoint: no network, workspace writes or engine imports.
export function diagnoseLockScope() {
  return null
}

export function assertImmutableCheckout() {
  return null
}

export function assertInstalledGraph() {
  return null
}

export function adapterManifest() {
  return null
}

export function prepareStagedManifest() {
  return null
}

export function assertStagedSourcePrerequisites() {
  return null
}

export function assertStagedLockScope() {
  return null
}

export function stagedNpmCommand() {
  return null
}

export function assertStagedNpmCommand() {
  return null
}

export async function runStagedAdapterGenerator() {
  process.exitCode = 1
  console.error("Staged adapter candidate rejected at stage: preflight")
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await runStagedAdapterGenerator()
}
