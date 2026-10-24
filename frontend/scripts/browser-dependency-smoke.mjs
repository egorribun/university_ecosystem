import { pathToFileURL } from "node:url"

export function inspectBrowserDependencies() {
  return null
}

export function browserLaunchOptions() {
  return null
}

export async function createLoopbackFixture() {
  return null
}

export async function runBrowserChecks() {
  return null
}

export function buildSmokeReport() {
  return null
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.error("Browser dependency smoke rejected at stage: preflight")
  process.exitCode = 1
}
