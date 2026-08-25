import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { test } from "node:test"
import {
  enforcePrecacheBudget,
  enforcePrecacheBudgetForEnv,
  getPrecacheBudget,
  MAX_DIAGNOSTIC_PRECACHE_BYTES,
  MAX_PRECACHE_BYTES,
  PWA_INJECT_CONFIG,
} from "./workbox-config.mjs"

const scriptPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "build-orchestrated.mjs")
const scriptSource = await readFile(scriptPath, "utf8")
const viteConfigPath = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "vite.config.mts"
)
const viteConfigSource = await readFile(viteConfigPath, "utf8")

test("build orchestrator exposes bounded memory controls", () => {
  assert.match(scriptSource, /FRONTEND_BUILD_MAX_RSS_MB/)
  assert.match(scriptSource, /FRONTEND_BUILD_MAX_OLD_SPACE_MB/)
  assert.match(scriptSource, /--max-old-space-size=\$\{maxOldSpaceMb\}/)
  assert.match(scriptSource, /readProcessRssBytes\(child\.pid\)/)
})

test("build orchestrator terminates the exact Vite process tree on overflow", () => {
  assert.match(scriptSource, /taskkill\.exe/)
  assert.match(scriptSource, /terminateProcessTree\(child\.pid\)/)
  assert.match(scriptSource, /vite child exceeded RSS watchdog/)
  assert.match(scriptSource, /clearInterval\(memoryPoll\)/)
})

test("build orchestrator prevents overlapping RSS probes", () => {
  assert.match(scriptSource, /memoryProbeInFlight/)
  assert.match(scriptSource, /memoryPoll = setInterval\(\(\) => \{/)
  assert.match(scriptSource, /\}, 2000\)/)
})

test("build orchestrator accepts only complete, non-empty Vite artifacts", () => {
  assert.match(scriptSource, /hasUsableViteArtifacts/)
  assert.match(scriptSource, /<html\\b/i)
  assert.match(scriptSource, /hasClientAsset/)
})

test("PWA precache config excludes optional map chunks", () => {
  const ignores = PWA_INJECT_CONFIG.globIgnores ?? []

  for (const pattern of [
    "**/vendor-map-*.js",
    "**/vendor-map-*.css",
    "**/Map-*.js",
    "**/MapFeature-*.js",
    "**/MapLibreMap-*.js",
    "**/map-*.js",
  ]) {
    assert.ok(ignores.includes(pattern), `missing Workbox ignore: ${pattern}`)
  }

  assert.ok(!ignores.some((pattern) => pattern.includes("offline.html")))
})

test("optional password-strength dictionaries have stable lazy chunk names and stay out of precache", () => {
  const ignores = PWA_INJECT_CONFIG.globIgnores ?? []

  for (const [dependency, chunkName] of [
    ["@zxcvbn-ts/core", "vendor-password-strength-core"],
    ["@zxcvbn-ts/language-common", "vendor-password-strength-common"],
    ["@zxcvbn-ts/language-en", "vendor-password-strength-en"],
    ["@zxcvbn-ts/language-ru", "vendor-password-strength-ru"],
  ]) {
    assert.ok(
      viteConfigSource.includes(dependency),
      `missing manual chunk dependency: ${dependency}`
    )
    assert.ok(viteConfigSource.includes(chunkName), `missing deterministic chunk: ${chunkName}`)
  }

  assert.ok(ignores.includes("**/vendor-password-strength-*.js"))
  assert.equal(MAX_PRECACHE_BYTES, 4_800_000)
})

test("PWA precache fails closed when the aggregate browser budget is exceeded", () => {
  assert.ok(MAX_DIAGNOSTIC_PRECACHE_BYTES > MAX_PRECACHE_BYTES)
  assert.deepEqual(getPrecacheBudget({}), {
    bytes: MAX_PRECACHE_BYTES,
    label: "browser budget",
  })
  assert.deepEqual(getPrecacheBudget({ E2E_COVERAGE: "true", FRONTEND_BUILD_UNMINIFIED: "true" }), {
    bytes: MAX_DIAGNOSTIC_PRECACHE_BYTES,
    label: "E2E diagnostic browser budget",
  })
  assert.equal(
    enforcePrecacheBudget([{ url: "offline.html", revision: null, size: 1 }]).manifest.length,
    1
  )
  const oversizedManifest = [
    { url: "oversized.js", revision: null, size: MAX_DIAGNOSTIC_PRECACHE_BYTES + 1 },
  ]
  assert.throws(
    () => enforcePrecacheBudgetForEnv(oversizedManifest, {}),
    /above the \d+-byte browser budget/
  )
  assert.throws(
    () =>
      enforcePrecacheBudgetForEnv(oversizedManifest, {
        E2E_COVERAGE: "true",
        FRONTEND_BUILD_UNMINIFIED: "true",
      }),
    /above the \d+-byte E2E diagnostic browser budget/
  )
})
