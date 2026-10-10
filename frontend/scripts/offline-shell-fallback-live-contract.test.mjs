import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

import { PWA_INJECT_CONFIG } from "./workbox-config.mjs"

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const specPath = path.join(frontendRoot, "tests", "e2e", "offline-shell-fallback.spec.ts")
const precachingPath = path.join(frontendRoot, "src", "sw", "precaching.ts")
const [specSource, precachingSource] = await Promise.all([
  readFile(specPath, "utf8"),
  readFile(precachingPath, "utf8"),
])

test("offline shell browser acceptance exercises the real worker and precached app assets", () => {
  assert.match(specSource, /serviceWorker:\s*"preserve"/u)
  assert.match(specSource, /Network\.setCacheDisabled/u)
  assert.match(specSource, /context\.setOffline\(true\)/u)
  assert.match(specSource, /page\.goto\("\/events"/u)
  assert.match(specSource, /data-render-mode/u)
  assert.match(specSource, /window\.__APP_HYDRATED/u)
  assert.match(specSource, /workbox-precache/u)
  assert.doesNotMatch(specSource, /\bvi\.mock\s*\(|\bpage\.route\s*\(/u)

  assert.match(precachingSource, /new NetworkOnly\(/u)
  assert.match(precachingSource, /handlerDidError/u)
  assert.match(precachingSource, /matchPrecache\("_shell\.html"\)/u)
  assert.ok(
    PWA_INJECT_CONFIG.globPatterns.some((pattern) =>
      ["js", "css", "html"].every((extension) => pattern.includes(extension))
    ),
    "the production precache must include HTML shells and their JavaScript/CSS assets"
  )
})
