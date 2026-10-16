import assert from "node:assert/strict"
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  utimesSync,
  writeFileSync,
} from "node:fs"
import { readFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { test } from "node:test"
import { loadConfigFromFile } from "vite"
import { advanceArtifactStability, captureViteArtifactSnapshot } from "./build-orchestrated.mjs"
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
const loadedViteConfig = await loadConfigFromFile(
  { command: "build", mode: "production" },
  viteConfigPath,
  undefined,
  "silent"
)
const resolveModulePreloadDependencies =
  loadedViteConfig?.config?.build?.modulePreload?.resolveDependencies

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

test("build orchestrator fingerprints both artifacts during the stability debounce", () => {
  assert.match(scriptSource, /captureViteArtifactSnapshot/)
  assert.match(scriptSource, /advanceArtifactStability/)
  assert.match(scriptSource, /createHash\(["']sha256["']\)/)
  assert.match(scriptSource, /startedAt: startTime/)
  assert.match(scriptSource, /STABLE_DEBOUNCE_TICKS = 4/)
  assert.match(scriptSource, /POLL_INTERVAL_MS = 500/)
})

test("build orchestrator accepts only complete, non-empty Vite artifacts", () => {
  assert.match(scriptSource, /hasUsableViteArtifacts/)
  assert.match(scriptSource, /<html\\b/i)
  assert.match(scriptSource, /hasClientAsset/)
})

test("Workbox inject stages into a distinct file before replacing the service worker", () => {
  assert.match(scriptSource, /workboxTempPath/)
  assert.match(scriptSource, /swDest: workboxTempPath/)
  assert.match(scriptSource, /rename\(workboxTempPath, swPath\)/)
  assert.doesNotMatch(scriptSource, /swSrc: swPath,\s*swDest: swPath/u)
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

test("English and Russian password analyzers do not preload the opposite locale", () => {
  assert.equal(typeof resolveModulePreloadDependencies, "function")

  const sharedRuntimeDependency = "assets/rolldown-runtime-hash.js"
  const commonDictionaryDependency = "assets/vendor-password-strength-common-hash.js"
  const context = {
    hostId: "assets/passwordStrength-hash.js",
    hostType: "js",
  }

  assert.deepEqual(
    resolveModulePreloadDependencies(
      "assets/vendor-password-strength-en-hash.js",
      [
        "assets/vendor-password-strength-ru-hash.js",
        commonDictionaryDependency,
        sharedRuntimeDependency,
      ],
      context
    ),
    [sharedRuntimeDependency]
  )
  assert.deepEqual(
    resolveModulePreloadDependencies(
      "assets/vendor-password-strength-ru-hash.js",
      [
        "assets/vendor-password-strength-en-hash.js",
        commonDictionaryDependency,
        sharedRuntimeDependency,
      ],
      context
    ),
    [sharedRuntimeDependency]
  )
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

function createArtifactFixture(t) {
  const root = mkdtempSync(path.join(tmpdir(), "ue-vite-artifact-stability-"))
  const assetsDir = path.join(root, "dist", "client", "assets")
  const shellPath = path.join(root, "dist", "client", "_shell.html")
  const serverPath = path.join(root, "dist", "server", "server.js")
  const assetPath = path.join(assetsDir, "app.js")
  mkdirSync(assetsDir, { recursive: true })
  mkdirSync(path.dirname(serverPath), { recursive: true })
  writeFileSync(shellPath, "<!doctype html><html><body>Shell!</body></html>\n")
  writeFileSync(serverPath, 'export const serverValue = "1"; // stable payload\n')
  writeFileSync(assetPath, "client asset\n")
  t.after(() => rmSync(root, { recursive: true, force: true }))
  return { root, assetsDir, shellPath, serverPath, assetPath, startedAt: Date.now() }
}

function sampleArtifacts(fixture, startedAt = fixture.startedAt) {
  return captureViteArtifactSnapshot({
    shellPath: fixture.shellPath,
    serverPath: fixture.serverPath,
    assetsDir: fixture.assetsDir,
    startedAt,
    freshnessGraceMs: 1500,
  })
}

function advanceFixture(state, fixture, startedAt = fixture.startedAt) {
  return advanceArtifactStability(state, sampleArtifacts(fixture, startedAt), 4)
}

test("paired Vite artifacts need four unchanged fresh samples before stabilization", (t) => {
  const fixture = createArtifactFixture(t)
  let state = { fingerprint: null, count: 0, stable: false }

  for (let tick = 1; tick <= 4; tick += 1) {
    state = advanceFixture(state, fixture)
    assert.equal(state.count, tick)
    assert.equal(state.stable, tick === 4)
  }
})

test("same-metadata content changes reset the paired stability period", () => {
  const shellPath = "synthetic/_shell.html"
  const serverPath = "synthetic/server.js"
  const assetsDir = "synthetic/assets"
  const shell = Buffer.from("<!doctype html><html>same shell</html>\n")
  let server = Buffer.from('export const serverValue = "1"; // stable payload\n')
  const statFor = (contents) => ({
    dev: 1n,
    ino: 2n,
    mode: 0o100644n,
    size: BigInt(contents.byteLength),
    mtimeNs: 3n,
    ctimeNs: 4n,
    birthtimeNs: 5n,
    isFile: () => true,
  })
  const io = {
    statSync(filePath) {
      return statFor(filePath === shellPath ? shell : server)
    },
    readFileSync(filePath) {
      return filePath === shellPath ? shell : server
    },
    readdirSync() {
      return ["app.js"]
    },
  }
  const options = { shellPath, serverPath, assetsDir }
  const first = captureViteArtifactSnapshot(options, io)
  let state = advanceArtifactStability({ fingerprint: null, count: 0 }, first, 4)
  state = advanceArtifactStability(state, first, 4)
  assert.equal(state.count, 2)

  server = Buffer.from('export const serverValue = "2"; // stable payload\n')
  assert.equal(
    server.byteLength,
    Buffer.byteLength('export const serverValue = "1"; // stable payload\n')
  )
  const changed = captureViteArtifactSnapshot(options, io)
  assert.notEqual(changed?.fingerprint, first?.fingerprint)
  state = advanceArtifactStability(state, changed, 4)
  assert.equal(state.count, 1)
  assert.equal(state.stable, false)
})

test("changes to either required output restart stability despite restored mtime", (t) => {
  for (const target of ["shellPath", "serverPath"]) {
    const fixture = createArtifactFixture(t)
    let state = advanceFixture({ fingerprint: null, count: 0 }, fixture)
    state = advanceFixture(state, fixture)
    assert.equal(state.count, 2)

    const targetPath = fixture[target]
    const originalStat = statSync(targetPath)
    const replacement =
      target === "shellPath"
        ? "<!doctype html><html><body>Other!</body></html>\n"
        : 'export const serverValue = "2"; // stable payload\n'
    writeFileSync(targetPath, replacement)
    utimesSync(targetPath, originalStat.atime, originalStat.mtime)

    state = advanceFixture(state, fixture)
    assert.equal(state.count, 1, `${target} content update must restart the debounce`)
    assert.equal(state.stable, false)
  }
})

test("missing artifacts reset stability and reappearance starts a new period", (t) => {
  for (const target of ["shellPath", "serverPath"]) {
    const fixture = createArtifactFixture(t)
    let state = advanceFixture({ fingerprint: null, count: 0 }, fixture)
    state = advanceFixture(state, fixture)
    assert.equal(state.count, 2)

    const targetPath = fixture[target]
    const original = readFileSync(targetPath)
    rmSync(targetPath)
    state = advanceFixture(state, fixture)
    assert.equal(state.count, 0)
    assert.equal(state.stable, false)

    writeFileSync(targetPath, original)
    const now = Date.now() / 1000
    utimesSync(targetPath, now, now)
    state = advanceFixture(state, fixture)
    assert.equal(state.count, 1)
    assert.equal(state.stable, false)
  }
})

test("stale artifacts do not start a stability period until both are fresh", (t) => {
  const fixture = createArtifactFixture(t)
  const startedAt = Date.now()
  const staleAt = (startedAt - 10_000) / 1000
  utimesSync(fixture.serverPath, staleAt, staleAt)

  let state = advanceFixture({ fingerprint: null, count: 0 }, fixture, startedAt)
  assert.equal(state.count, 0)
  assert.equal(state.stable, false)

  const freshAt = Date.now() / 1000
  utimesSync(fixture.serverPath, freshAt, freshAt)
  state = advanceFixture(state, fixture, startedAt)
  assert.equal(state.count, 1)
  assert.equal(state.stable, false)
})

test("a missing client asset also resets the usable-artifact stability state", (t) => {
  const fixture = createArtifactFixture(t)
  let state = advanceFixture({ fingerprint: null, count: 0 }, fixture)
  state = advanceFixture(state, fixture)
  assert.equal(state.count, 2)

  rmSync(fixture.assetPath)
  state = advanceFixture(state, fixture)
  assert.equal(state.count, 0)

  writeFileSync(fixture.assetPath, "client asset\n")
  const now = Date.now() / 1000
  utimesSync(fixture.assetPath, now, now)
  state = advanceFixture(state, fixture)
  assert.equal(state.count, 1)
})

test("continuous valid artifact churn cannot stabilize until four paired samples repeat", (t) => {
  const fixture = createArtifactFixture(t)
  const requiredTicks = 4
  let state = { fingerprint: null, count: 0, stable: false }
  let previousFingerprint = null
  let producerVersion = 0

  // This producer writes complete, usable outputs without launching Vite or a
  // child process. A final write occurs after the last churn observation, so
  // the settled period starts with a genuinely new artifact pair.
  const fakeProducer = (version) => {
    writeFileSync(fixture.shellPath, `<!doctype html><html><body>Shell ${version}</body></html>\n`)
    writeFileSync(
      fixture.serverPath,
      `export const serverValue = ${JSON.stringify(`server-${version}`)}; // stable payload\n`
    )
  }
  const observeProductionStability = () => {
    const snapshot = sampleArtifacts(fixture, fixture.startedAt)
    assert.ok(snapshot, "the fixture producer must emit both usable artifacts")
    state = advanceArtifactStability(state, snapshot, requiredTicks)
    return snapshot
  }

  for (let poll = 1; poll <= 8; poll += 1) {
    producerVersion += 1
    fakeProducer(producerVersion)
    const snapshot = observeProductionStability()
    assert.notEqual(snapshot.fingerprint, previousFingerprint)
    assert.equal(state.count, 1, `churn poll ${poll} must restart the consecutive-sample count`)
    assert.equal(state.stable, false, `churn poll ${poll} must not stabilize the build`)
    previousFingerprint = snapshot.fingerprint
  }

  producerVersion += 1
  fakeProducer(producerVersion)
  const firstSettledSnapshot = observeProductionStability()
  assert.notEqual(firstSettledSnapshot.fingerprint, previousFingerprint)
  assert.equal(state.count, 1)
  assert.equal(state.stable, false)

  for (let sample = 2; sample <= requiredTicks; sample += 1) {
    const snapshot = observeProductionStability()
    assert.equal(snapshot.fingerprint, firstSettledSnapshot.fingerprint)
    assert.equal(state.count, sample)
    assert.equal(state.stable, sample === requiredTicks)
  }
})
