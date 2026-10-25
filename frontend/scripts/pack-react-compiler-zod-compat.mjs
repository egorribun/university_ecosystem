import { resolve } from "node:path"
import { pathToFileURL } from "node:url"

export function facadePackCommand() {
  return null
}

export function assertFacadePackCommand() {
  return null
}

export function validateFacadeSources() {
  return null
}

export function readFacadeSources() {
  return null
}

export function inspectFacadeArchive() {
  return null
}

export function validateFacadePackSummary() {
  return null
}

export function assertFacadePackPostflight() {
  return null
}

export function facadeArchiveEvidence() {
  return null
}

export async function runFacadePack() {
  console.error("Facade archive rejected at stage: preflight")
  return 1
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  process.exitCode = await runFacadePack()
}
