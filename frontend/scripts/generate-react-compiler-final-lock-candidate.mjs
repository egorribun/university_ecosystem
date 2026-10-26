import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { get } from "node:https"
import { createRequire } from "node:module"
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path"
import { pathToFileURL } from "node:url"
import { isDeepStrictEqual, stripVTControlCharacters } from "node:util"
import {
  NPM_TRANSPORT_ARGS,
  assertNpmCommand,
  npmCommand,
  validateRegistryMetadata,
  verifyArchiveBytes,
} from "./generate-zod-root-lock-candidate.mjs"
import {
  adapterManifest,
  assertImmutableCheckout,
  diagnoseLockScope,
} from "./generate-react-compiler-adapter-lock-candidate.mjs"
import { inspectFacadeArchive, readFacadeSources } from "./pack-react-compiler-zod-compat.mjs"

const LOCAL = "scripts/react-compiler-zod-compat"
const LEGACY = "react-compiler-zod-compat"
const LEGACY_SPEC = "file:./" + LOCAL
const FACADE = "@university-ecosystem/react-compiler-zod-compat"
const ARCHIVE = "vendor/react-compiler-zod-compat-1.0.0.tgz"
const ARCHIVE_SPEC = "file:./" + ARCHIVE
const ARCHIVE_INTEGRITY =
  "sha512-4M74nZuqffHkW97CJJq1q3dIyFNdwkv9ydjCtkyd43o/pwZMAVJlijqY5Scl+MudxRRBara/XqXY9HdqsT7cUg=="
const ARCHIVE_SHA256 = "3887a71e809e5c427392ee521eec91296bffae536aa11f8bd04863922a193ff5"
const ALIAS = "node_modules/patched-zod"
const LINK = "node_modules/" + FACADE
const OLD_LINK = "node_modules/react-compiler-zod-compat"
const COMPILER = "node_modules/eslint-plugin-react-compiler"
const OLD_ENGINE = COMPILER + "/node_modules/zod"
const FORMATTER = "node_modules/zod-validation-error"
const HOOKS = "node_modules/eslint-plugin-react-hooks"
const HOOKS_FORMATTER = HOOKS + "/node_modules/zod-validation-error"
const ENGINE = "node_modules/zod"
const EXACT_CONSUMER = "eslint-plugin-react-compiler@19.1.0-rc.2"
const SINGLETON_RANGE = ">=19.1.0-rc.2 <=19.1.0-rc.2"
const CONSUMER = "eslint-plugin-react-compiler@" + SINGLETON_RANGE
export const SOURCE_PHASE = Object.freeze({
  LEGACY_LINK: "c90-legacy-link",
  STAGED_ARCHIVE: "staged-archive",
  ALREADY_FINAL: "already-final",
})
const FINAL_OVERRIDE = Object.freeze({
  ".": "$eslint-plugin-react-compiler",
  zod: "$" + FACADE,
  "zod-validation-error": Object.freeze({ ".": "4.0.2", zod: "4.6.7" }),
})

const HOOKS_PEER = "^3.0.0 || ^4.0.0 || ^5.0.0 || ^6.0.0 || ^7.0.0 || ^8.0.0-0 || ^9.0.0 || ^10.0.0"
const FORMATTER_PEER = "^3.25.0 || ^4.0.0"
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex")

function sourceManifestPhase(manifest) {
  assert.equal(manifest.private, true)
  assert.equal(manifest.packageManager, "npm@11.17.0")
  assert.equal(manifest.devDependencies?.eslint, "^10.12.0")
  assert.equal(manifest.devDependencies?.["eslint-plugin-react-compiler"], "^19.1.0-rc.2")
  assert.equal(manifest.devDependencies?.["eslint-plugin-react-hooks"], "^7.1.1")
  const hasLegacy = Object.hasOwn(manifest.devDependencies ?? {}, LEGACY)
  const hasFacade = Object.hasOwn(manifest.devDependencies ?? {}, FACADE)
  const hasConsumerOverride = Object.hasOwn(manifest.overrides ?? {}, CONSUMER)
  let phase
  if (
    hasLegacy &&
    manifest.devDependencies[LEGACY] === LEGACY_SPEC &&
    !hasFacade &&
    !hasConsumerOverride
  ) {
    phase = SOURCE_PHASE.LEGACY_LINK
  } else if (!hasLegacy && hasFacade && manifest.devDependencies[FACADE] === ARCHIVE_SPEC) {
    if (hasConsumerOverride) {
      assert.deepEqual(manifest.overrides[CONSUMER], FINAL_OVERRIDE)
      phase = SOURCE_PHASE.ALREADY_FINAL
    } else {
      phase = SOURCE_PHASE.STAGED_ARCHIVE
    }
  } else {
    assert.fail("Unknown React Compiler dependency source phase")
  }
  for (const section of ["dependencies", "optionalDependencies", "peerDependencies"]) {
    assert(!Object.hasOwn(manifest[section] ?? {}, FACADE))
    assert(!Object.hasOwn(manifest[section] ?? {}, LEGACY))
  }
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    for (const name of ["zod", "patched-zod"]) {
      assert(!Object.hasOwn(manifest[section] ?? {}, name))
    }
  }
  assert.deepEqual(manifest.overrides?.["eslint-plugin-react-hooks"], {
    "zod-validation-error": "4.0.2",
  })
  for (const key of Object.keys(manifest.overrides ?? {})) {
    assert(!/^zod(?:@|$)/.test(key))
    if (/^eslint-plugin-react-compiler(?:@|$)/.test(key)) {
      assert.equal(key, CONSUMER)
      assert.equal(phase, SOURCE_PHASE.ALREADY_FINAL)
    }
  }
  return phase
}

export function prepareFinalManifest(manifest) {
  const phase = sourceManifestPhase(manifest)
  const candidate = structuredClone(manifest)
  if (phase === SOURCE_PHASE.LEGACY_LINK) {
    delete candidate.devDependencies[LEGACY]
    candidate.devDependencies[FACADE] = ARCHIVE_SPEC
  }
  candidate.overrides[CONSUMER] = structuredClone(FINAL_OVERRIDE)
  return candidate
}

export function prepareStrictManifest(manifest) {
  assert.equal(sourceManifestPhase(manifest), SOURCE_PHASE.ALREADY_FINAL)
  assert.deepEqual(manifest.overrides[CONSUMER], FINAL_OVERRIDE)
  return {
    name: "react-compiler-peer-proof",
    version: "1.0.0",
    private: true,
    packageManager: "npm@11.17.0",
    devDependencies: {
      eslint: "10.12.0",
      "eslint-plugin-react-compiler": "19.1.0-rc.2",
      "eslint-plugin-react-hooks": "7.1.1",
      [FACADE]: ARCHIVE_SPEC,
      zod: "4.6.7",
    },
    overrides: {
      [CONSUMER]: structuredClone(FINAL_OVERRIDE),
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
    },
  }
}

export function prepareStrictFormatterPlacementManifest(manifest) {
  // Keep the unanchored fixture above unchanged as the recorded ERESOLVE control.
  // This extra direct pin exists only in the isolated peer-placement fixture.
  const candidate = prepareStrictManifest(manifest)
  candidate.devDependencies["zod-validation-error"] = "4.0.2"
  return candidate
}

export function prepareAbsoluteArchiveGenerationManifest(manifest, archivePath) {
  assert.equal(sourceManifestPhase(manifest), SOURCE_PHASE.ALREADY_FINAL)
  assert.deepEqual(manifest.overrides?.[CONSUMER], FINAL_OVERRIDE)
  assert.equal(typeof archivePath, "string")
  assert(isAbsolute(archivePath) && resolve(archivePath) === archivePath)
  assert.equal(realpathSync(archivePath), archivePath)
  const bytes = regularBytes(archivePath, 64 * 1024)
  assert.equal(digest(bytes), ARCHIVE_SHA256)
  assert.equal("sha512-" + createHash("sha512").update(bytes).digest("base64"), ARCHIVE_INTEGRITY)
  const candidate = structuredClone(manifest)
  candidate.overrides[CONSUMER].zod = "file:" + archivePath.replaceAll("\\", "/")
  return candidate
}

function archiveLockRecord() {
  return {
    version: "1.0.0",
    resolved: "file:" + ARCHIVE,
    integrity: ARCHIVE_INTEGRITY,
    dev: true,
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  }
}

function assertSharedSourceLock(lock) {
  assert.equal(lock.lockfileVersion, 3)
  for (const [path, version] of [
    ["node_modules/body-parser", "1.20.9"],
    ["node_modules/undici", "8.12.2"],
    [COMPILER, "19.1.0-rc.2"],
    [HOOKS, "7.1.1"],
    ["node_modules/eslint", "10.12.0"],
    ["node_modules/@puppeteer/browsers", "3.2.4"],
    ["node_modules/chromium-bidi", "157.0.8090-0"],
    ["node_modules/puppeteer-core", "25.13.0"],
    ["node_modules/puppeteer-core/node_modules/devtools-protocol", "0.0.1696802"],
    ["node_modules/typed-query-selector", "2.12.3"],
    ["node_modules/webdriver-bidi-protocol", "1.0.1"],
  ]) {
    assert.equal(lock.packages[path]?.version, version)
    assert.equal(lock.packages[path].dev, true)
  }
  assert.equal(lock.packages[ENGINE].version, "4.6.7")
  assert(!Object.hasOwn(lock.packages[ENGINE], "dev"))
  assert.deepEqual(lock.packages[ALIAS], {
    name: "zod",
    ...lock.packages[ENGINE],
    dev: true,
  })
  assert.equal(lock.packages["node_modules/chromium-bidi"].dependencies.zod, "^4.6.5")
  assert.equal(lock.packages[COMPILER].dependencies.zod, "^3.22.4")
  assert.equal(lock.packages[COMPILER].dependencies["zod-validation-error"], "^3.0.3")
  assert.equal(lock.packages[COMPILER].peerDependencies.eslint, ">=7")
  assert.equal(lock.packages[HOOKS].peerDependencies.eslint, HOOKS_PEER)
}

function assertStagedSourcePrerequisites(lock) {
  assertSharedSourceLock(lock)
  assert.equal(lock.packages[OLD_ENGINE].version, "3.25.76")
  assert.equal(lock.packages[OLD_ENGINE].dev, true)
  assert.equal(lock.packages[FORMATTER].version, "3.5.4")
  assert.equal(lock.packages[FORMATTER].dev, true)
  assert.equal(lock.packages[HOOKS_FORMATTER].version, "4.0.2")
  assert.equal(lock.packages[HOOKS_FORMATTER].dev, true)
  assert.equal(lock.packages[HOOKS_FORMATTER].peerDependencies.zod, FORMATTER_PEER)
  assert.deepEqual(lock.packages[LINK], archiveLockRecord())
  assert.equal(lock.packages[""].devDependencies[FACADE], ARCHIVE_SPEC)
  assert(!Object.hasOwn(lock.packages[""].devDependencies, LEGACY))
  assert(!Object.hasOwn(lock.packages, OLD_LINK))
  assert(!Object.hasOwn(lock.packages, LOCAL))
  assert.deepEqual(
    Object.keys(lock.packages)
      .filter((path) => /(?:^|\/)node_modules\/zod$/.test(path))
      .sort(),
    [OLD_ENGINE, ENGINE]
  )
  assert(!Object.hasOwn(lock.packages, LOCAL + "/node_modules/patched-zod"))
  return true
}

function legacyLockAsStaged(lock) {
  const staged = structuredClone(lock)
  delete staged.packages[""].devDependencies[LEGACY]
  staged.packages[""].devDependencies[FACADE] = ARCHIVE_SPEC
  delete staged.packages[OLD_LINK]
  delete staged.packages[LOCAL]
  staged.packages[LINK] = archiveLockRecord()
  return staged
}

function assertLegacyLinkSourcePrerequisites(lock) {
  assertSharedSourceLock(lock)
  assert.equal(lock.packages[OLD_ENGINE].version, "3.25.76")
  assert.equal(lock.packages[OLD_ENGINE].dev, true)
  assert.equal(lock.packages[FORMATTER].version, "3.5.4")
  assert.equal(lock.packages[FORMATTER].dev, true)
  assert.equal(lock.packages[HOOKS_FORMATTER].version, "4.0.2")
  assert.equal(lock.packages[HOOKS_FORMATTER].dev, true)
  assert.equal(lock.packages[HOOKS_FORMATTER].peerDependencies.zod, FORMATTER_PEER)
  assert.equal(lock.packages[""].devDependencies[LEGACY], LEGACY_SPEC)
  assert(!Object.hasOwn(lock.packages[""].devDependencies, FACADE))
  assert.deepEqual(lock.packages[OLD_LINK], { resolved: LOCAL, link: true })
  assert.deepEqual(lock.packages[LOCAL], {
    name: FACADE,
    version: "1.0.0",
    dev: true,
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  })
  assert(!Object.hasOwn(lock.packages, LINK))
  return assertStagedSourcePrerequisites(legacyLockAsStaged(lock))
}

function assertAlreadyFinalSourcePrerequisites(lock) {
  assertSharedSourceLock(lock)
  assert.deepEqual(lock.packages[LINK], archiveLockRecord())
  assert.deepEqual(lock.packages[OLD_ENGINE], {
    name: FACADE,
    ...archiveLockRecord(),
  })
  assert.equal(lock.packages[""].devDependencies[FACADE], ARCHIVE_SPEC)
  assert(!Object.hasOwn(lock.packages[""].devDependencies, LEGACY))
  assert(!Object.hasOwn(lock.packages, OLD_LINK))
  assert(!Object.hasOwn(lock.packages, LOCAL))
  assert.equal(lock.packages[FORMATTER].version, "4.0.2")
  assert.equal(lock.packages[FORMATTER].dev, true)
  assert.equal(lock.packages[FORMATTER].peerDependencies.zod, FORMATTER_PEER)
  assert(!Object.hasOwn(lock.packages, HOOKS_FORMATTER))
  assert.deepEqual(
    Object.keys(lock.packages)
      .filter((path) => /(?:^|\/)node_modules\/zod$/.test(path))
      .sort(),
    [OLD_ENGINE, ENGINE]
  )
  assert(!Object.hasOwn(lock.packages, LOCAL + "/node_modules/patched-zod"))
  return true
}

export function assertFinalSourcePrerequisites(lock, phase = SOURCE_PHASE.STAGED_ARCHIVE) {
  assert(Object.values(SOURCE_PHASE).includes(phase))
  if (phase === SOURCE_PHASE.LEGACY_LINK) return assertLegacyLinkSourcePrerequisites(lock)
  if (phase === SOURCE_PHASE.STAGED_ARCHIVE) return assertStagedSourcePrerequisites(lock)
  return assertAlreadyFinalSourcePrerequisites(lock)
}

export function classifyFinalSourcePhase(manifest, lock) {
  const phase = sourceManifestPhase(manifest)
  assertFinalSourcePrerequisites(lock, phase)
  const root = lock.packages[""]
  assert.equal(root.name, manifest.name)
  assert.equal(root.version, manifest.version)
  assert.deepEqual(root.dependencies, manifest.dependencies)
  assert.deepEqual(root.devDependencies, manifest.devDependencies)
  return phase
}

export function assertFacadeArchive(frontend) {
  assert.equal(realpathSync(frontend), frontend)
  const files = readFacadeSources(join(frontend, LOCAL))
  const bytes = regularBytes(join(frontend, ARCHIVE), 64 * 1024)
  const evidence = inspectFacadeArchive(bytes, files)
  assert.equal(evidence.sha256, ARCHIVE_SHA256)
  const integrity = "sha512-" + createHash("sha512").update(bytes).digest("base64")
  assert.equal(integrity, ARCHIVE_INTEGRITY)
  return { bytes: bytes.length, sha256: evidence.sha256, integrity }
}

export function validateFormatterMetadata(data, record, now = Date.now()) {
  assert.equal(data.name, "zod-validation-error")
  assert.equal(data.version, "4.0.2")
  assert.equal(data.license, "MIT")
  assert.equal(data.repository?.type, "git")
  assert.equal(data.repository?.url, "git://github.com/causaly/zod-validation-error.git")
  assert.equal(
    data.dist.tarball,
    "https://registry.npmjs.org/zod-validation-error/-/zod-validation-error-4.0.2.tgz"
  )
  assert.match(data.dist.integrity, /^sha512-[A-Za-z0-9+/]{86}==$/)
  assert.match(data.dist.shasum, /^[0-9a-f]{40}$/)
  assert.equal(record.version, data.version)
  assert.equal(record.resolved, data.dist.tarball)
  assert.equal(record.integrity, data.dist.integrity)
  assert.equal(record.license, data.license)
  assert.deepEqual(data.dependencies ?? {}, {})
  assert.deepEqual(data.engines, record.engines)
  assert.deepEqual(data.peerDependencies, { zod: FORMATTER_PEER })
  assert.deepEqual(data.peerDependencies, record.peerDependencies)
  assert(!data.deprecated)
  for (const phase of ["preinstall", "install", "postinstall"]) {
    assert(!data.scripts?.[phase])
  }
  const published = data.time?.["4.0.2"]
  assert.match(published ?? "", /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/)
  const timestamp = Date.parse(published)
  assert(Number.isFinite(now) && Number.isFinite(timestamp))
  assert(timestamp <= now - 7 * 86400000)
  return { data, published, timestamp }
}

function assertLockDeltaPaths(original, candidate, expectedPaths) {
  const paths = new Set([...Object.keys(original.packages), ...Object.keys(candidate.packages)])
  const changed = [...paths]
    .filter((path) => !isDeepStrictEqual(original.packages[path], candidate.packages[path]))
    .sort()
  assert.deepEqual(changed, [...expectedPaths].sort())
}

export function assertFinalLockScope(original, candidate, formatter, phase) {
  phase ??= Object.values(SOURCE_PHASE).find((value) => {
    try {
      assertFinalSourcePrerequisites(original, value)
      return true
    } catch {
      return false
    }
  })
  assert(Object.values(SOURCE_PHASE).includes(phase), "Unknown source lock phase")
  assertFinalSourcePrerequisites(original, phase)
  const formatterRecord =
    phase === SOURCE_PHASE.ALREADY_FINAL
      ? original.packages[FORMATTER]
      : original.packages[HOOKS_FORMATTER]
  validateFormatterMetadata(formatter, formatterRecord)
  const expected = structuredClone(original)
  let changedPaths
  if (phase === SOURCE_PHASE.LEGACY_LINK) {
    delete expected.packages[""].devDependencies[LEGACY]
    expected.packages[""].devDependencies[FACADE] = ARCHIVE_SPEC
    expected.packages[LINK] = archiveLockRecord()
    expected.packages[OLD_ENGINE] = { name: FACADE, ...archiveLockRecord() }
    delete expected.packages[OLD_LINK]
    delete expected.packages[LOCAL]
    expected.packages[FORMATTER] = structuredClone(original.packages[HOOKS_FORMATTER])
    delete expected.packages[HOOKS_FORMATTER]
    changedPaths = ["", LINK, OLD_ENGINE, OLD_LINK, LOCAL, FORMATTER, HOOKS_FORMATTER]
  } else if (phase === SOURCE_PHASE.STAGED_ARCHIVE) {
    expected.packages[OLD_ENGINE] = {
      name: FACADE,
      ...structuredClone(original.packages[LINK]),
    }
    expected.packages[FORMATTER] = structuredClone(original.packages[HOOKS_FORMATTER])
    delete expected.packages[HOOKS_FORMATTER]
    changedPaths = [OLD_ENGINE, FORMATTER, HOOKS_FORMATTER]
  } else {
    changedPaths = []
  }
  assert.deepEqual(candidate, expected)
  assertLockDeltaPaths(original, candidate, changedPaths)
  return true
}

export const FINAL_CANDIDATE_ORCHESTRATION_STAGES = Object.freeze([
  "toolMetadata",
  "toolArchive",
  "toolInstall",
  "engineMetadata",
  "engineArchive",
  "formatterMetadata",
  "formatterArchive",
  "overrideSelector",
  "candidateLockGeneration",
  "candidateLockScope",
  "fullGraphInstallAndVerify",
  "productionGraphInstallAndVerify",
  "strictPeerProof",
  "sourceSnapshotPostflight",
  "candidateDiff",
])

export function formatterRecordForSourcePhase(lock, phase) {
  assert(Object.values(SOURCE_PHASE).includes(phase))
  const path = phase === SOURCE_PHASE.ALREADY_FINAL ? FORMATTER : HOOKS_FORMATTER
  const record = lock.packages[path]
  assert(record && record.version === "4.0.2")
  return { path, record }
}

export async function orchestrateFinalCandidateStages({
  sourcePhase,
  sourceLock,
  runStage,
  now = Date.now(),
}) {
  assert(Object.values(SOURCE_PHASE).includes(sourcePhase))
  assertFinalSourcePrerequisites(sourceLock, sourcePhase)
  assert.equal(typeof runStage, "function")
  const formatterSource = formatterRecordForSourcePhase(sourceLock, sourcePhase)
  const state = {
    sourcePhase,
    sourceLock,
    formatterSourcePath: formatterSource.path,
    formatterSourceRecord: formatterSource.record,
    completedStages: [],
  }
  for (const stage of FINAL_CANDIDATE_ORCHESTRATION_STAGES) {
    state.currentStage = stage
    const value = await runStage(stage, state)
    if (stage === "toolMetadata") {
      state.toolMetadata = validateRegistryMetadata(value, "npm", "11.17.0", now)
    } else if (stage === "toolArchive") {
      assertArchiveStageEvidence(value, state.toolMetadata.data, "npm tool")
      state.toolArchive = value
    } else if (stage === "toolInstall") {
      assert(value && typeof value.cli === "string" && value.cli.length > 0)
      state.cli = value.cli
      state.toolInstall = value
    } else if (stage === "engineMetadata") {
      state.engine = validateRegistryMetadata(value, "zod", "4.6.7", now)
      assert.equal(state.engine.data.dist.tarball, sourceLock.packages[ENGINE].resolved)
      assert.equal(state.engine.data.dist.integrity, sourceLock.packages[ENGINE].integrity)
      assert.equal(state.engine.data.license, sourceLock.packages[ENGINE].license)
      assert.deepEqual(state.engine.data.dependencies ?? {}, {})
    } else if (stage === "engineArchive") {
      assertArchiveStageEvidence(value, state.engine.data, "patched engine")
      state.engineArchive = value
    } else if (stage === "formatterMetadata") {
      state.formatter = validateFormatterMetadata(value, state.formatterSourceRecord, now)
    } else if (stage === "formatterArchive") {
      assertArchiveStageEvidence(value, state.formatter.data, "formatter")
      state.formatterArchive = value
    } else if (stage === "overrideSelector") {
      state.selectorDiagnostic = assertOverrideSelectorControl(value)
    } else if (stage === "candidateLockGeneration") {
      assert(value && Buffer.isBuffer(value.bytes))
      assert(value.candidate && typeof value.candidate === "object")
      assert(typeof value.path === "string" && value.path.length > 0)
      state.candidateLock = value.candidate
      state.candidateLockBytes = value.bytes
      state.candidateLockPath = value.path
    } else if (stage === "candidateLockScope") {
      try {
        assertFinalLockScope(sourceLock, state.candidateLock, state.formatter.data, sourcePhase)
      } catch {
        const diagnostic = JSON.stringify(diagnoseLockScope(sourceLock, state.candidateLock))
        assert(Buffer.byteLength(diagnostic) <= 16384)
        console.error("FINAL_COMPILER_REJECTED_SCOPE " + diagnostic)
        throw new Error("Rejected generated lock scope")
      }
      state.candidateLockScopeVerified = true
    } else if (stage === "fullGraphInstallAndVerify") {
      assert(value && value.verified === true)
      assert(value.licenseEvidence && typeof value.licenseEvidence === "object")
      state.licenseEvidence = value.licenseEvidence
      state.fullGraphInstallVerified = true
    } else if (stage === "productionGraphInstallAndVerify") {
      assert(value && value.verified === true)
      state.productionGraphInstallVerified = true
    } else if (stage === "strictPeerProof") {
      assert(value && value.verified === true)
      assert(Buffer.isBuffer(value.strictLockBytes))
      assert(value.strictNpmListVerified === true)
      assert.deepEqual(value.licenseEvidence, state.licenseEvidence)
      state.strictLockBytes = value.strictLockBytes
      state.strictPeerProof = value
    } else if (stage === "sourceSnapshotPostflight") {
      assert.equal(value, true)
      state.sourceSnapshotPostflightVerified = true
    } else if (stage === "candidateDiff") {
      assert.equal(typeof value, "string")
      if (sourcePhase === SOURCE_PHASE.ALREADY_FINAL) assert.equal(Buffer.byteLength(value), 0)
      else assert(Buffer.byteLength(value) > 0)
      assert(Buffer.byteLength(value) <= 16384)
      state.patch = value
    }
    state.completedStages.push(stage)
  }
  return state
}

function assertArchiveStageEvidence(evidence, metadata, description) {
  assert(evidence && evidence.verified === true, description + " archive was not verified")
  assert(Number.isSafeInteger(evidence.bytes) && evidence.bytes > 0)
  assert.equal(evidence.integrity, metadata.dist.integrity)
  assert.match(evidence.sha256 ?? "", /^[0-9a-f]{64}$/)
  assert.equal(typeof evidence.path, "string")
  return true
}

function assertConfigPaths(paths) {
  for (const name of ["userconfig", "globalconfig"]) {
    assert(typeof paths[name] === "string")
    assert(isAbsolute(paths[name]) && resolve(paths[name]) === paths[name])
  }
  assert.equal(dirname(paths.userconfig), dirname(paths.globalconfig))
  assert.notEqual(paths.userconfig, paths.globalconfig)
}

export function finalNpmCommand(operation, paths = {}) {
  const operations = {
    generateLock: ["update", "zod", "zod-validation-error", "--package-lock-only"],
    fullGraph: ["ci", "--include=dev"],
    productionGraph: ["ci", "--omit=dev"],
    strictGenerate: ["install", "--package-lock-only", "--json"],
    strictInstall: ["ci", "--include=dev"],
    strictList: ["ls", "--all", "--json", "--long"],
  }
  assert(Object.hasOwn(operations, operation))
  const strict = []
  if (operation.startsWith("strict")) {
    assertConfigPaths(paths)
    strict.push(
      "--legacy-peer-deps=false",
      "--strict-peer-deps",
      "--userconfig=" + paths.userconfig,
      "--globalconfig=" + paths.globalconfig
    )
  }
  return Object.freeze([
    ...operations[operation],
    ...strict,
    "--no-audit",
    "--no-fund",
    ...NPM_TRANSPORT_ARGS,
  ])
}

export function assertFinalNpmCommand(operation, args, paths = {}) {
  assert.deepEqual(args, finalNpmCommand(operation, paths))
  return true
}

export function strictPeerEnvironment(original, paths) {
  assertConfigPaths(paths)
  for (const name of ["home", "cache"]) {
    assert(typeof paths[name] === "string")
    assert(isAbsolute(paths[name]) && resolve(paths[name]) === paths[name])
    assert.equal(dirname(paths[name]), dirname(paths.userconfig))
  }
  assert(typeof original.PATH === "string" && original.PATH.length > 0)
  return {
    PATH: original.PATH,
    HOME: paths.home,
    npm_config_cache: paths.cache,
    npm_config_userconfig: paths.userconfig,
    npm_config_globalconfig: paths.globalconfig,
    npm_config_legacy_peer_deps: "false",
    npm_config_strict_peer_deps: "true",
    npm_config_ignore_scripts: "true",
  }
}

export function strictVerificationPhase(phase) {
  const labels = {
    native: "native graph verification",
    license: "license equality",
    npmList: "npm ls execution",
    json: "npm ls JSON decoding",
    identity: "npm ls identity verification",
    problems: "npm ls problem-list verification",
    fixture: "fixture byte immutability",
    configuration: "empty configuration verification",
    source: "source snapshot verification",
  }
  assert.equal(typeof phase, "string")
  assert(Object.hasOwn(labels, phase))
  return "isolated strict root-formatter " + labels[phase]
}

export function summarizeStrictNpmFailure(result) {
  assert(result.status !== 0 || result.error || result.signal)
  let exitCode = null
  if (Number.isInteger(result.status) && result.status > 0 && result.status <= 255) {
    exitCode = result.status
  }
  const report = {
    kind: "react-compiler-strict-npm-failure",
    operation: "strictGenerate",
    exitCode,
    timedOut: result.error?.code === "ETIMEDOUT",
    terminated: Boolean(result.signal),
    jsonRecognized: false,
    errorCode: "unrecognized",
    observations: [],
    omitted: false,
    candidateAccepted: false,
  }
  if (typeof result.stdout !== "string" || Buffer.byteLength(result.stdout) > 65536) {
    return report
  }
  let error
  try {
    const parsed = JSON.parse(result.stdout)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return report
    error = parsed.error
  } catch {
    return report
  }
  if (!error || typeof error !== "object" || Array.isArray(error)) return report
  report.jsonRecognized = true
  const codes = new Set([
    "ERESOLVE",
    "EOVERRIDE",
    "EUSAGE",
    "ETARGET",
    "E404",
    "ENOENT",
    "EINTEGRITY",
    "EBADENGINE",
    "ETIMEDOUT",
    "ECONNRESET",
    "ENOTFOUND",
    "EAI_AGAIN",
    "EACCES",
    "EPERM",
    "ELSPROBLEMS",
  ])
  if (codes.has(error.code)) report.errorCode = error.code
  const versions = new Map([
    ["eslint", ["10.12.0"]],
    ["eslint-plugin-react-compiler", ["19.1.0-rc.2"]],
    ["eslint-plugin-react-hooks", ["7.1.1"]],
    ["zod", ["1.0.0", "3.25.76", "4.6.7"]],
    ["zod-validation-error", ["3.5.4", "4.0.2"]],
    ["react-compiler-peer-proof", ["1.0.0"]],
    ["react-compiler-zod-compat", ["1.0.0"]],
    ["@university-ecosystem/react-compiler-zod-compat", ["1.0.0"]],
    ["patched-zod", ["4.6.7"]],
  ])
  const ranges = new Set([
    "^3.22.4",
    "^3.24.4",
    FORMATTER_PEER,
    HOOKS_PEER,
    "^3.0.3",
    "4.0.2",
    "4.6.7",
    ">=7",
    "*",
    "file:./scripts/react-compiler-zod-compat",
    "file:../../scripts/react-compiler-zod-compat",
  ])
  const node = (value) => {
    const match = /^([@a-z0-9/_-]+)@([0-9][0-9A-Za-z.+-]*)(.*)$/.exec(value)
    if (!match || !versions.get(match[1])?.includes(match[2])) return null
    if (!/^(?: (?:dev|optional|peer|bundled|overridden|extraneous))*$/.test(match[3])) return null
    return { name: match[1], version: match[2] }
  }
  const seen = new Set()
  const append = (observation) => {
    const key = JSON.stringify(observation)
    if (seen.has(key)) return
    seen.add(key)
    if (report.observations.length < 8) report.observations.push(observation)
    else report.omitted = true
  }
  for (const raw of typeof error.detail === "string" ? error.detail.split("\n") : []) {
    const line = stripVTControlCharacters(raw).trim()
    const heading = /^(Found|While resolving|Conflicting peer dependency): (.+)$/.exec(line)
    if (heading) {
      const value = node(heading[2])
      if (value) {
        const kind = {
          Found: "found",
          "While resolving": "resolving",
          "Conflicting peer dependency": "conflicting",
        }[heading[1]]
        append({ kind, ...value })
      }
      continue
    }
    const peer = /^(?:peer|peerOptional) (?:overridden )?([@a-z0-9/_-]+)@"([^"]+)"(.*)$/.exec(line)
    if (!peer || !versions.has(peer[1]) || !ranges.has(peer[2])) continue
    const from = /^(?: \(was "([^"]+)"\))? from (.+)$/.exec(peer[3])
    if (!from || (from[1] !== undefined && !ranges.has(from[1]))) continue
    const consumer = node(from[2])
    if (!consumer) continue
    append({
      kind: "peer",
      name: peer[1],
      range: peer[2],
      originalRange: from[1] ?? null,
      consumer: consumer.name,
      consumerVersion: consumer.version,
    })
  }
  assert(Buffer.byteLength(JSON.stringify(report)) <= 4096)
  return report
}

export function summarizeStrictListFailure(result) {
  assert(result.status !== 0 || result.error || result.signal)
  const report = {
    kind: "react-compiler-strict-list-failure",
    operation: "strictList",
    exitCode:
      Number.isInteger(result.status) && result.status > 0 && result.status <= 255
        ? result.status
        : null,
    timedOut: result.error?.code === "ETIMEDOUT",
    terminated: Boolean(result.signal),
    outputLimitExceeded: result.error?.code === "ENOBUFS",
    jsonRecognized: false,
    errorCode: "unrecognized",
    problemCategories: { invalid: 0, missing: 0, extraneous: 0, unrecognized: 0 },
    observations: [],
    omitted: false,
    candidateAccepted: false,
  }
  if (typeof result.stdout !== "string" || Buffer.byteLength(result.stdout) > 1024 * 1024) {
    return report
  }
  let parsed
  try {
    parsed = JSON.parse(result.stdout)
  } catch {
    return report
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return report
  report.jsonRecognized = true
  if (["ELSPROBLEMS", "EJSONPARSE", "EOVERRIDE", "EUSAGE"].includes(parsed.error?.code)) {
    report.errorCode = parsed.error.code
  }
  const versions = new Map([
    ["eslint", ["10.12.0"]],
    ["eslint-plugin-react-compiler", ["19.1.0-rc.2"]],
    ["eslint-plugin-react-hooks", ["7.1.1"]],
    ["zod", ["1.0.0", "3.25.76", "4.6.7"]],
    ["zod-validation-error", ["3.5.4", "4.0.2"]],
    ["react-compiler-zod-compat", ["1.0.0"]],
    ["@university-ecosystem/react-compiler-zod-compat", ["1.0.0"]],
    ["patched-zod", ["4.6.7"]],
  ])
  const identities = new Map()
  for (const [name, values] of versions) {
    for (const version of values) identities.set(name + "@" + version, { name, version })
  }
  for (const [name, packageName, version] of [
    ["zod", "@university-ecosystem/react-compiler-zod-compat", "1.0.0"],
    ["react-compiler-zod-compat", "@university-ecosystem/react-compiler-zod-compat", "1.0.0"],
    ["patched-zod", "zod", "4.6.7"],
  ]) {
    identities.set(name + "@npm:" + packageName + "@" + version, {
      name,
      version,
      packageName,
    })
  }
  const seen = new Set()
  const append = (item) => {
    const key = JSON.stringify(item)
    if (seen.has(key)) return
    seen.add(key)
    if (report.observations.length < 8) report.observations.push(item)
    else report.omitted = true
  }
  if (parsed.problems !== undefined && !Array.isArray(parsed.problems)) report.omitted = true
  const problems = Array.isArray(parsed.problems) ? parsed.problems : []
  if (problems.length > 64) report.omitted = true
  for (const problem of problems.slice(0, 64)) {
    const match =
      typeof problem === "string" && problem.length <= 4096
        ? (/^(invalid|extraneous): (\S+) .+$/.exec(problem) ??
          /^(missing): (\S+), required by .+$/.exec(problem))
        : null
    const kind = match?.[1] ?? "unrecognized"
    report.problemCategories[kind] += 1
    const identity = identities.get(match?.[2])
    if (identity) append({ kind, ...identity })
    else report.omitted = true
  }
  const ranges = new Set([
    "^3.22.4",
    "^3.24.4",
    FORMATTER_PEER,
    HOOKS_PEER,
    "^3.0.3",
    "4.0.2",
    "4.6.7",
    ">=7",
    "file:./scripts/react-compiler-zod-compat",
    "file:../../scripts/react-compiler-zod-compat",
  ])
  const consumers = new Map([
    ["the root project", "react-compiler-peer-proof"],
    [COMPILER, "eslint-plugin-react-compiler"],
    [HOOKS, "eslint-plugin-react-hooks"],
    [FORMATTER, "zod-validation-error"],
    [LOCAL, "@university-ecosystem/react-compiler-zod-compat"],
  ])
  // Inspect only these fixed dependency keys, at most two levels deep.
  for (const keys of [
    ["eslint"],
    ["eslint-plugin-react-compiler"],
    ["eslint-plugin-react-compiler", "zod"],
    ["eslint-plugin-react-compiler", "zod-validation-error"],
    ["eslint-plugin-react-hooks"],
    ["eslint-plugin-react-hooks", "zod-validation-error"],
    ["zod-validation-error"],
    ["zod"],
    ["react-compiler-zod-compat"],
    ["react-compiler-zod-compat", "patched-zod"],
  ]) {
    let node = parsed
    for (const key of keys) node = node?.dependencies?.[key]
    if (node?.invalid === undefined) continue
    if (
      typeof node.invalid !== "string" ||
      node.invalid.length > 2048 ||
      !versions.get(node.name)?.includes(node.version)
    ) {
      report.omitted = true
      continue
    }
    const fragments = node.invalid.split(", ")
    if (fragments.length > 8) report.omitted = true
    for (const fragment of fragments.slice(0, 8)) {
      const match = /^"([^"]+)" from (.+)$/.exec(fragment)
      const consumer = consumers.get(match?.[2])
      if (!match || !ranges.has(match[1]) || !consumer) {
        report.omitted = true
        continue
      }
      const name = keys.at(-1)
      append({
        kind: "invalid-edge",
        name,
        version: node.version,
        ...(name !== node.name ? { packageName: node.name } : {}),
        range: match[1],
        consumer,
      })
    }
  }
  assert(Buffer.byteLength(JSON.stringify(report)) <= 4096)
  return report
}

function artifactIdentity(record) {
  assert(record && typeof record === "object")
  const identity = { ...record }
  for (const field of ["dev", "devOptional", "optional", "peer"]) delete identity[field]
  return identity
}

export function assertStrictLock(strict, project, rootFormatterPinned = false) {
  assert.equal(typeof rootFormatterPinned, "boolean")
  assert.equal(strict.lockfileVersion, 3)
  assert.equal(strict.name, "react-compiler-peer-proof")
  assert.equal(strict.version, "1.0.0")
  const expectedDevDependencies = {
    eslint: "10.12.0",
    "eslint-plugin-react-compiler": "19.1.0-rc.2",
    "eslint-plugin-react-hooks": "7.1.1",
    [FACADE]: ARCHIVE_SPEC,
    zod: "4.6.7",
  }
  if (rootFormatterPinned) expectedDevDependencies["zod-validation-error"] = "4.0.2"
  assert.deepEqual(strict.packages[""].devDependencies, expectedDevDependencies)
  for (const path of [
    COMPILER,
    FORMATTER,
    HOOKS,
    "node_modules/eslint",
    ENGINE,
    ALIAS,
    LINK,
    OLD_ENGINE,
  ]) {
    assert.deepEqual(
      artifactIdentity(strict.packages[path]),
      artifactIdentity(project.packages[path])
    )
  }
  assert.equal(strict.packages["node_modules/eslint"].version, "10.12.0")
  assert.equal(strict.packages[COMPILER].version, "19.1.0-rc.2")
  assert.equal(strict.packages[COMPILER].peerDependencies.eslint, ">=7")
  assert.equal(strict.packages[HOOKS].version, "7.1.1")
  assert.equal(strict.packages[HOOKS].peerDependencies.eslint, HOOKS_PEER)
  assert.equal(strict.packages[FORMATTER].version, "4.0.2")
  assert.equal(strict.packages[FORMATTER].peerDependencies.zod, FORMATTER_PEER)
  assert.equal(strict.packages[LINK].version, "1.0.0")
  assert.equal(strict.packages[LINK].dependencies["patched-zod"], "npm:zod@4.6.7")
  assert.equal(strict.packages[OLD_ENGINE].name, FACADE)
  assert(!Object.hasOwn(strict.packages, OLD_LINK))
  assert(!Object.hasOwn(strict.packages, LOCAL))
  assert(!Object.hasOwn(strict.packages, HOOKS_FORMATTER))
  assert.deepEqual(
    Object.keys(strict.packages)
      .filter((path) => /(?:^|\/)node_modules\/zod$/.test(path))
      .sort(),
    [OLD_ENGINE, ENGINE]
  )
  return true
}

function regularBytes(path, limit) {
  const stat = lstatSync(path, { throwIfNoEntry: false })
  assert(stat?.isFile() && !stat.isSymbolicLink())
  assert(stat.size > 0 && stat.size <= limit)
  assert.equal(realpathSync(path), path)
  const bytes = readFileSync(path)
  assert.equal(bytes.length, stat.size)
  return bytes
}

function packageMetadata(path) {
  return JSON.parse(regularBytes(path, 32768))
}

export function inspectInstalledEngineLicense(frontend) {
  assert.equal(realpathSync(frontend), frontend)
  const directory = join(frontend, ALIAS)
  const stat = lstatSync(directory, { throwIfNoEntry: false })
  assert(stat?.isDirectory() && !stat.isSymbolicLink())
  assert.equal(realpathSync(directory), directory)
  const manifest = packageMetadata(join(directory, "package.json"))
  assert.equal(manifest.name, "zod")
  assert.equal(manifest.version, "4.6.7")
  assert.equal(manifest.license, "MIT")
  const license = regularBytes(join(directory, "LICENSE"), 8192)
  return {
    packageName: manifest.name,
    version: manifest.version,
    declaredLicense: manifest.license,
    licenseFile: { bytes: license.length, sha256: digest(license) },
  }
}

export function assertArchiveOverrideTarget(frontend, consumer, target) {
  assert.equal(realpathSync(frontend), frontend)
  assert.equal(consumer, join(frontend, COMPILER))
  assert.equal(target, join(frontend, ARCHIVE))
  const bytes = regularBytes(target, 64 * 1024)
  assert.equal(digest(bytes), ARCHIVE_SHA256)
  assert.equal("sha512-" + createHash("sha512").update(bytes).digest("base64"), ARCHIVE_INTEGRITY)
  return true
}

export function inspectOverrideSelector(toolRoot, manifest, frontend) {
  assert.equal(realpathSync(toolRoot), toolRoot)
  sourceManifestPhase(manifest)
  assert.deepEqual(manifest.overrides[CONSUMER], FINAL_OVERRIDE)
  const npmPath = join(toolRoot, "package.json")
  const npmMetadata = packageMetadata(npmPath)
  assert.equal(npmMetadata.name, "npm")
  assert.equal(npmMetadata.version, "11.17.0")
  const toolRequire = createRequire(npmPath)
  const packages = {}
  for (const [name, version] of [
    ["semver", "7.8.4"],
    ["@npmcli/arborist", "9.8.0"],
    ["npm-package-arg", "13.0.2"],
  ]) {
    const packagePath = toolRequire.resolve(name + "/package.json")
    assert.equal(packagePath, join(toolRoot, "node_modules", name, "package.json"))
    const metadata = packageMetadata(packagePath)
    assert.equal(metadata.name, name)
    assert.equal(metadata.version, version)
    packages[name] = { path: dirname(packagePath), version: metadata.version }
  }
  assert.equal(realpathSync(frontend), frontend)
  const npaPath = toolRequire.resolve("npm-package-arg")
  assert(npaPath.startsWith(packages["npm-package-arg"].path + sep))
  regularBytes(npaPath, 128 * 1024)
  const buildPath = join(packages["@npmcli/arborist"].path, "lib/arborist/build-ideal-tree.js")
  regularBytes(buildPath, 128 * 1024)
  const arboristRequire = createRequire(buildPath)
  assert.equal(arboristRequire.resolve("npm-package-arg"), npaPath)
  assert.equal(
    arboristRequire.resolve("npm-package-arg/package.json"),
    join(packages["npm-package-arg"].path, "package.json")
  )
  const semverPath = toolRequire.resolve("semver")
  assert(semverPath.startsWith(packages.semver.path + sep))
  regularBytes(semverPath, 128 * 1024)
  const overridePath = join(packages["@npmcli/arborist"].path, "lib/override-set.js")
  regularBytes(overridePath, 128 * 1024)
  const nodePath = join(packages["@npmcli/arborist"].path, "lib/node.js")
  const edgePath = join(packages["@npmcli/arborist"].path, "lib/edge.js")
  regularBytes(nodePath, 128 * 1024)
  regularBytes(edgePath, 128 * 1024)
  // Only the already verified npm tool's own resolver is inspected. No project
  // package entrypoint or npm install/update operation is invoked here.
  const npa = toolRequire(npaPath)
  const semver = toolRequire(semverPath)
  const OverrideSet = toolRequire(overridePath)
  const Node = toolRequire(nodePath)
  const Edge = toolRequire(edgePath)
  // Retain the previously observed exact-selector failure as a separate control.
  const baselineOverrides = structuredClone(manifest.overrides)
  delete baselineOverrides[CONSUMER]
  baselineOverrides[EXACT_CONSUMER] = structuredClone(FINAL_OVERRIDE)
  delete baselineOverrides[EXACT_CONSUMER]["."]
  baselineOverrides[EXACT_CONSUMER].zod = "$react-compiler-zod-compat"
  const baseline = new OverrideSet({ overrides: baselineOverrides })
  const selected = new OverrideSet({ overrides: structuredClone(manifest.overrides) })
  const name = "eslint-plugin-react-compiler"
  const version = "19.1.0-rc.2"
  const range = manifest.devDependencies[name]
  const edge = { name, rawSpec: range, spec: range }
  const node = { name, version }
  const identity = (root, rule, key) => {
    if (rule === root) return null
    assert.equal(rule?.key, key)
    return rule.key
  }
  const boolean = (value) => {
    assert.equal(typeof value, "boolean")
    return value
  }
  const selectedIdentity = (rule) => identity(selected, rule, CONSUMER)
  // Node and Edge model this one direct dependency in memory; no tree is loaded
  // from disk and no installer runs. The root package reference must preserve
  // the compiler's declared version range and point at the tracked archive.
  const directRoot = (override) =>
    new Node({
      path: frontend,
      loadOverrides: true,
      pkg: {
        name: "react-compiler-selector-control",
        version: "1.0.0",
        devDependencies: {
          [name]: range,
          [FACADE]: manifest.devDependencies[FACADE],
        },
        overrides: { [CONSUMER]: structuredClone(override) },
      },
    })
  const direct = directRoot(FINAL_OVERRIDE)
  const directEdge = direct.edgesOut.get(name)
  assert(directEdge instanceof Edge)
  assert.equal(directEdge.overrides.key, CONSUMER)
  direct.assertRootOverrides()
  const withoutReference = structuredClone(FINAL_OVERRIDE)
  delete withoutReference["."]
  assert.throws(() => directRoot(withoutReference).assertRootOverrides(), {
    code: "EOVERRIDE",
  })
  const consumer = (override) => {
    const instance = new Node({
      parent: directRoot(override),
      pkg: { name, version, dependencies: { zod: "^3.22.4" } },
    })
    assert.equal(instance.path, join(frontend, COMPILER))
    const dependency = instance.edgesOut.get("zod")
    assert(dependency instanceof Edge)
    assert.equal(dependency.rawSpec, "^3.22.4")
    return { instance, dependency }
  }
  const relativeDirectory = consumer({
    ...FINAL_OVERRIDE,
    zod: "file:../../scripts/react-compiler-zod-compat",
  })
  const relativeParsed = npa.resolve(
    "zod",
    relativeDirectory.dependency.spec,
    relativeDirectory.instance.path
  )
  assert.equal(relativeParsed.type, "directory")
  assert.equal(relativeParsed.fetchSpec, join(frontend, LOCAL))
  const resolvedRoot = npa.resolve(FACADE, manifest.devDependencies[FACADE], frontend)
  assert.equal(resolvedRoot.type, "file")
  assert.equal(resolvedRoot.fetchSpec, join(frontend, ARCHIVE))
  const selectedConsumer = consumer(FINAL_OVERRIDE)
  assert.equal(selectedConsumer.dependency.spec, ARCHIVE_SPEC)
  assertArchiveOverrideTarget(frontend, selectedConsumer.instance.path, resolvedRoot.fetchSpec)
  const versionChecks = [
    "19.1.0-rc.1",
    "19.1.0-rc.2",
    "19.1.0-rc.2+fixture",
    "19.1.0-rc.3",
    "19.1.0",
    "19.1.1-rc.2",
    "20.0.0",
  ].map((candidate) => ({
    version: candidate,
    exact: boolean(semver.satisfies(candidate, version)),
    selected: boolean(semver.satisfies(candidate, SINGLETON_RANGE)),
    nodeAttached: selectedIdentity(selected.getNodeRule({ name, version: candidate })) !== null,
  }))
  const result = {
    kind: "react-compiler-override-selector-diagnostic",
    npm: npmMetadata.version,
    semver: packages.semver.version,
    arborist: packages["@npmcli/arborist"].version,
    packageName: name,
    declaredRange: range,
    installedVersion: version,
    selectorVersion: version,
    satisfiesRange: boolean(semver.satisfies(version, range)),
    satisfiesSelector: boolean(semver.satisfies(version, version)),
    intersectsSelector: boolean(semver.intersects(range, version)),
    edgeRule: identity(baseline, baseline.getEdgeRule(edge), EXACT_CONSUMER),
    nodeRule: identity(baseline, baseline.getNodeRule(node), EXACT_CONSUMER),
    selectedSelector: {
      range: SINGLETON_RANGE,
      satisfies: boolean(semver.satisfies(version, SINGLETON_RANGE)),
      intersects: boolean(semver.intersects(range, SINGLETON_RANGE)),
      edgeRule: selectedIdentity(selected.getEdgeRule(edge)),
      nodeRule: selectedIdentity(selected.getNodeRule(node)),
    },
    versionChecks,
    directDependency: {
      rawSpec: directEdge.rawSpec,
      effectiveSpec: directEdge.spec,
      rootOverrideAccepted: true,
      missingReferenceError: "EOVERRIDE",
    },
    localDependency: {
      parser: "npm-package-arg",
      parserVersion: packages["npm-package-arg"].version,
      rawSpec: selectedConsumer.dependency.rawSpec,
      baselineSpec: relativeDirectory.dependency.spec,
      baselineTarget: relative(frontend, relativeParsed.fetchSpec).split(sep).join("/"),
      selectedSpec: selectedConsumer.dependency.spec,
      selectedTarget: relative(frontend, resolvedRoot.fetchSpec).split(sep).join("/"),
      targetType: resolvedRoot.type,
      targetCanonical: true,
    },
    candidateAccepted: true,
  }
  assert(Buffer.byteLength(JSON.stringify(result)) <= 2048)
  return result
}

export function assertOverrideSelectorControl(report) {
  const versionChecks = [
    ["19.1.0-rc.1", false],
    ["19.1.0-rc.2", true],
    ["19.1.0-rc.2+fixture", true],
    ["19.1.0-rc.3", false],
    ["19.1.0", false],
    ["19.1.1-rc.2", false],
    ["20.0.0", false],
  ].map(([version, accepted]) => ({
    version,
    exact: accepted,
    selected: accepted,
    nodeAttached: accepted,
  }))
  assert.deepEqual(report, {
    kind: "react-compiler-override-selector-diagnostic",
    npm: "11.17.0",
    semver: "7.8.4",
    arborist: "9.8.0",
    packageName: "eslint-plugin-react-compiler",
    declaredRange: "^19.1.0-rc.2",
    installedVersion: "19.1.0-rc.2",
    selectorVersion: "19.1.0-rc.2",
    satisfiesRange: true,
    satisfiesSelector: true,
    intersectsSelector: false,
    edgeRule: null,
    nodeRule: EXACT_CONSUMER,
    selectedSelector: {
      range: SINGLETON_RANGE,
      satisfies: true,
      intersects: true,
      edgeRule: CONSUMER,
      nodeRule: CONSUMER,
    },
    versionChecks,
    directDependency: {
      rawSpec: "^19.1.0-rc.2",
      effectiveSpec: "^19.1.0-rc.2",
      rootOverrideAccepted: true,
      missingReferenceError: "EOVERRIDE",
    },
    localDependency: {
      parser: "npm-package-arg",
      parserVersion: "13.0.2",
      rawSpec: "^3.22.4",
      baselineSpec: "file:../../scripts/react-compiler-zod-compat",
      baselineTarget: LOCAL,
      selectedSpec: ARCHIVE_SPEC,
      selectedTarget: ARCHIVE,
      targetType: "file",
      targetCanonical: true,
    },
    candidateAccepted: true,
  })
  return true
}

export function assertFinalInstalledGraph(frontend, mode, controls) {
  assert(mode === "full" || mode === "production")
  assert.equal(realpathSync(frontend), frontend)
  const rootPath = join(frontend, ENGINE, "package.json")
  const root = packageMetadata(rootPath)
  assert.equal(root.name, "zod")
  assert.equal(root.version, "4.6.7")
  assertFacadeArchive(frontend)
  assert(!existsSync(join(frontend, LOCAL, "node_modules/patched-zod")))
  if (mode === "production") {
    for (const path of [ALIAS, LINK, COMPILER, FORMATTER, HOOKS, OLD_LINK]) {
      assert(!lstatSync(join(frontend, path), { throwIfNoEntry: false }))
    }
    return true
  }

  const local = join(frontend, LOCAL)
  assert.equal(realpathSync(local), local)
  assert.deepEqual(packageMetadata(join(local, "package.json")), adapterManifest())
  const facadePath = join(frontend, LINK, "package.json")
  const facade = packageMetadata(facadePath)
  assert.deepEqual(facade, adapterManifest())
  const enginePath = createRequire(facadePath).resolve("patched-zod/package.json")
  assert.equal(enginePath, join(frontend, ALIAS, "package.json"))
  const engine = packageMetadata(enginePath)
  assert.equal(engine.name, "zod")
  assert.equal(engine.version, "4.6.7")

  const compilerPath = join(frontend, COMPILER, "package.json")
  const compiler = packageMetadata(compilerPath)
  assert.equal(compiler.name, "eslint-plugin-react-compiler")
  assert.equal(compiler.version, "19.1.0-rc.2")
  assert.deepEqual(compiler.dependencies, controls.compilerDependencies)
  assert.equal(compiler.peerDependencies.eslint, ">=7")
  const compilerRequire = createRequire(compilerPath)
  const nestedFacadePath = compilerRequire.resolve("zod/package.json")
  assert.equal(nestedFacadePath, join(frontend, OLD_ENGINE, "package.json"))
  const nestedFacade = packageMetadata(nestedFacadePath)
  assert.deepEqual(nestedFacade, adapterManifest())
  assert.equal(
    createRequire(nestedFacadePath).resolve("patched-zod/package.json"),
    join(frontend, ALIAS, "package.json")
  )
  const compilerEntry = compilerRequire.resolve("./")
  assert(compilerEntry.startsWith(join(frontend, COMPILER) + sep))
  assert.match(controls.compilerBundleSha256 ?? "", /^[0-9a-f]{64}$/)
  assert.equal(digest(regularBytes(compilerEntry, 8 * 1024 * 1024)), controls.compilerBundleSha256)
  const formatterPath = join(frontend, FORMATTER, "package.json")
  const formatter = packageMetadata(formatterPath)
  const formatterEntry = compilerRequire.resolve("zod-validation-error")
  assert.equal(formatterEntry, resolve(frontend, FORMATTER, formatter.main))
  regularBytes(formatterEntry, 1024 * 1024)
  assert.equal(formatter.name, "zod-validation-error")
  assert.equal(formatter.version, "4.0.2")
  assert.equal(formatter.peerDependencies.zod, FORMATTER_PEER)
  assert.equal(createRequire(formatterPath).resolve("zod/package.json"), rootPath)
  for (const [name, version] of [
    ["eslint", "10.12.0"],
    ["eslint-plugin-react-hooks", "7.1.1"],
  ]) {
    const installed = packageMetadata(join(frontend, "node_modules", name, "package.json"))
    assert.equal(installed.name, name)
    assert.equal(installed.version, version)
    if (name === "eslint-plugin-react-hooks") {
      assert.equal(installed.peerDependencies.eslint, HOOKS_PEER)
    }
  }
  return true
}

export async function runFinalCompilerGenerator() {
  let stage = "preflight"
  let scratch
  let snapshots
  const copied = []
  let git
  let sourceTree
  let sourcePhase
  let report
  let patch
  let candidateManifestBytes
  let failed = false
  const deadline = performance.now() + 7 * 60_000
  const remaining = (cap) => {
    const budget = Math.floor(deadline - performance.now())
    assert(budget > 0, "Generation deadline exceeded")
    return Math.min(cap, budget)
  }
  const reject = () => {
    failed = true
    console.error("Final compiler candidate rejected at stage: " + stage)
  }
  try {
    const workspace = realpathSync(process.env.GITHUB_WORKSPACE)
    const frontend = join(workspace, "frontend")
    assert.equal(realpathSync(process.cwd()), frontend)
    const sourceNames = [
      "frontend/package.json",
      "frontend/package-lock.json",
      "frontend/.npmrc",
      "frontend/" + LOCAL + "/package.json",
      "frontend/" + LOCAL + "/legacy-baseline.json",
    ]
    snapshots = sourceNames.map((name) => {
      const path = join(workspace, name)
      return { path, bytes: regularBytes(path, 4 * 1024 * 1024) }
    })
    const [manifestBytes, lockBytes, configBytes, localManifestBytes, goldenBytes] = snapshots.map(
      (item) => item.bytes
    )
    const manifest = JSON.parse(manifestBytes)
    const lock = JSON.parse(lockBytes)
    const golden = JSON.parse(goldenBytes)
    assert.equal(golden.kind, "react-compiler-legacy-baseline")
    assert.equal(golden.schemaVersion, 1)
    assert.equal(golden.compilerVersion, "19.1.0-rc.2")
    assert.equal(golden.compilerIntegrity, lock.packages[COMPILER].integrity)
    assert.match(golden.compilerBundleSha256, /^[0-9a-f]{64}$/)
    const controls = {
      compilerBundleSha256: golden.compilerBundleSha256,
      compilerDependencies: lock.packages[COMPILER].dependencies,
    }
    assert.deepEqual(JSON.parse(localManifestBytes), adapterManifest())
    scratch = mkdtempSync(join(realpathSync(process.env.RUNNER_TEMP), "compiler-final-lock-"))
    const userConfig = join(scratch, "empty-user.npmrc")
    const globalConfig = join(scratch, "empty-global.npmrc")
    writeFileSync(userConfig, "", { flag: "wx", mode: 0o400 })
    writeFileSync(globalConfig, "", { flag: "wx", mode: 0o400 })
    const npmEnv = {
      PATH: dirname(process.execPath) + ":/usr/bin:/bin",
      HOME: scratch,
      TMPDIR: scratch,
      CI: "true",
      NO_COLOR: "1",
      NPM_CONFIG_USERCONFIG: userConfig,
      NPM_CONFIG_GLOBALCONFIG: globalConfig,
      NPM_CONFIG_CACHE: join(scratch, "cache"),
      NPM_CONFIG_REGISTRY: "https://registry.npmjs.org/",
    }
    function command(executable, args, cwd, options = {}) {
      const result = spawnSync(executable, args, {
        cwd,
        env: options.env ?? npmEnv,
        encoding: "utf8",
        shell: false,
        timeout: options.postflight ? 10_000 : remaining(options.timeout ?? 120_000),
        maxBuffer: 4 * 1024 * 1024,
      })
      if (options.strictDiagnostic && (result.error || result.signal || result.status !== 0)) {
        console.error(
          "FINAL_COMPILER_STRICT_FAILURE " + JSON.stringify(summarizeStrictNpmFailure(result))
        )
      }
      if (options.strictListDiagnostic && (result.error || result.signal || result.status !== 0)) {
        console.error(
          "FINAL_COMPILER_STRICT_LIST_FAILURE " + JSON.stringify(summarizeStrictListFailure(result))
        )
      }
      assert(!result.error && !result.signal && result.status === 0)
      return result.stdout
    }
    git = (args, postflight = false) =>
      command("/usr/bin/git", args, workspace, { timeout: 10_000, postflight })
    assertImmutableCheckout({
      expectedSha: process.env.SOURCE_SHA,
      head: git(["rev-parse", "HEAD"]).trim(),
      status: git(["status", "--porcelain=v1", "--untracked-files=all"]),
      node: process.version,
      repository: process.env.GITHUB_REPOSITORY,
      hasNodeModules: existsSync(join(frontend, "node_modules")),
    })
    sourceTree = git(["rev-parse", "HEAD^{tree}"]).trim()
    assert.match(sourceTree, /^[0-9a-f]{40}$/)
    assert.equal(
      configBytes.toString(),
      "legacy-peer-deps=true\nengine-strict=true\nmin-release-age=7\nstrict-allow-scripts=true\n"
    )
    sourcePhase = classifyFinalSourcePhase(manifest, lock)
    assertFacadeArchive(frontend)
    const candidateManifest = prepareFinalManifest(manifest)
    candidateManifestBytes = Buffer.from(JSON.stringify(candidateManifest, null, 2) + "\n")
    const localDirectories = []
    const localFiles = []
    for (const section of ["dependencies", "devDependencies", "optionalDependencies"]) {
      for (const value of Object.values(candidateManifest[section] ?? {})) {
        if (typeof value !== "string" || !value.startsWith("file:")) continue
        const rel = value.slice(5).replace(/^\.\//, "")
        const path = join(frontend, rel)
        const stat = lstatSync(path, { throwIfNoEntry: false })
        assert(stat && !stat.isSymbolicLink())
        if (stat.isDirectory()) localDirectories.push(rel)
        else if (stat.isFile()) localFiles.push(rel)
        else assert.fail("Unsupported local package input")
      }
    }
    assert.deepEqual(localDirectories.sort(), [
      "scripts/boundary-micromatch-compat",
      "wasm-sanitizer/pkg",
    ])
    assert.deepEqual(localFiles.sort(), [ARCHIVE])
    // The unpacked source remains an explicit integrity input even though the
    // npm graph consumes only its already-reviewed archive.
    localDirectories.push(LOCAL)
    localDirectories.sort()
    stage = "bounded isolated source inputs"
    let copiedBytes = 0
    for (const directory of localDirectories) {
      const sourceDirectory = join(frontend, directory)
      assert.equal(realpathSync(sourceDirectory), sourceDirectory)
      assert(lstatSync(sourceDirectory).isDirectory())
      const names = git(["ls-files", "-z", "--", "frontend/" + directory])
        .split("\0")
        .filter(Boolean)
      assert(names.includes("frontend/" + directory + "/package.json"))
      for (const name of names) {
        remaining(1)
        assert(name.startsWith("frontend/" + directory + "/"))
        const path = join(workspace, name)
        const bytes = regularBytes(path, 16 * 1024 * 1024)
        const rel = relative(frontend, path)
        assert(!rel.startsWith("../") && !rel.startsWith("/") && !rel.includes("\\"))
        assert(!rel.split("/").includes("node_modules"))
        copiedBytes += bytes.length
        assert(copiedBytes <= 64 * 1024 * 1024 && copied.length < 1024)
        copied.push({ path, rel, bytes })
      }
    }
    for (const rel of localFiles) {
      remaining(1)
      const names = git(["ls-files", "-z", "--", "frontend/" + rel])
        .split("\0")
        .filter(Boolean)
      assert.deepEqual(names, ["frontend/" + rel])
      const path = join(frontend, rel)
      const bytes = regularBytes(path, 64 * 1024)
      copiedBytes += bytes.length
      assert(copiedBytes <= 64 * 1024 * 1024 && copied.length < 1024)
      copied.push({ path, rel, bytes })
    }
    function mirror(name, rootManifest, rootLock, strict = false) {
      const target = join(scratch, name)
      mkdirSync(target)
      const files = [
        ["package.json", rootManifest],
        ...copied
          .filter((item) => !strict || item.rel.startsWith(LOCAL + "/") || item.rel === ARCHIVE)
          .map((item) => [item.rel, item.bytes]),
      ]
      if (rootLock) files.push(["package-lock.json", rootLock])
      if (!strict) files.push([".npmrc", configBytes])
      for (const [path, bytes] of files) {
        const destination = join(target, path)
        mkdirSync(dirname(destination), { recursive: true })
        writeFileSync(destination, bytes, { flag: "wx" })
      }
      return target
    }
    const generation = mirror("generation", candidateManifestBytes, lockBytes)
    const generationManifestBytes = Buffer.from(
      JSON.stringify(
        prepareAbsoluteArchiveGenerationManifest(
          candidateManifest,
          realpathSync(join(generation, ARCHIVE))
        ),
        null,
        2
      ) + "\n"
    )
    writeFileSync(join(generation, "package.json"), generationManifestBytes)
    const bootstrap = realpathSync(join(dirname(process.execPath), "npm"))
    assert.equal(
      bootstrap,
      join(dirname(dirname(process.execPath)), "lib/node_modules/npm/bin/npm-cli.js")
    )
    function npm(cli, operation, cwd, paths = {}, env = npmEnv) {
      const helper = ["version", "toolMetadata", "targetMetadata", "toolInstall"].includes(
        operation
      )
      const args = helper ? npmCommand(operation, paths) : finalNpmCommand(operation, paths)
      if (helper) assertNpmCommand(operation, args, paths)
      else assertFinalNpmCommand(operation, args, paths)
      return command(process.execPath, [cli, ...args], cwd, {
        env,
        strictDiagnostic: operation === "strictGenerate",
        strictListDiagnostic: operation === "strictList",
      })
    }
    assert.equal(npm(bootstrap, "version", generation).trim(), "11.19.0")
    async function verifiedArchive(meta, destination, limit) {
      const timeout = remaining(30000)
      const bytes = await new Promise((resolveBytes, rejectArchive) => {
        const chunks = []
        let size = 0
        const request = get(
          meta.dist.tarball,
          { headers: { Accept: "application/octet-stream" } },
          (response) => {
            if (response.statusCode !== 200) {
              response.destroy()
              rejectArchive(new Error("Non-200 archive response"))
              return
            }
            response.on("data", (chunk) => {
              size += chunk.length
              if (size > limit) request.destroy(new Error("Archive size exceeded"))
              else chunks.push(chunk)
            })
            response.on("error", rejectArchive)
            response.on("end", () => resolveBytes(Buffer.concat(chunks)))
          }
        )
        const timer = setTimeout(() => request.destroy(new Error("Archive timeout")), timeout)
        request.on("close", () => clearTimeout(timer))
        request.on("error", rejectArchive)
      })
      verifyArchiveBytes(meta, bytes, limit)
      writeFileSync(destination, bytes, { flag: "wx", mode: 0o600 })
      return {
        verified: true,
        bytes: bytes.length,
        integrity: meta.dist.integrity,
        sha256: digest(bytes),
        path: destination,
      }
    }

    const pipeline = await orchestrateFinalCandidateStages({
      sourcePhase,
      sourceLock: lock,
      runStage: async (name, state) => {
        if (name === "toolMetadata") {
          stage = "npm tool metadata and archive verification"
          return JSON.parse(npm(bootstrap, "toolMetadata", generation))
        }
        if (name === "toolArchive") {
          const path = join(scratch, "npm-11.17.0.tgz")
          return await verifiedArchive(state.toolMetadata.data, path, 16 * 1024 * 1024)
        }
        if (name === "toolInstall") {
          stage = "isolated npm tool installation"
          const toolPrefix = join(scratch, "tool")
          mkdirSync(toolPrefix)
          npm(bootstrap, "toolInstall", scratch, {
            prefix: toolPrefix,
            archive: join(scratch, "npm-11.17.0.tgz"),
          })
          const cli = realpathSync(join(toolPrefix, "node_modules/npm/bin/npm-cli.js"))
          assert(cli.startsWith(toolPrefix + sep))
          assert.equal(npm(cli, "version", generation).trim(), "11.17.0")
          return { cli }
        }
        if (name === "engineMetadata") {
          stage = "mature patched engine metadata and archive verification"
          return JSON.parse(npm(state.cli, "targetMetadata", generation))
        }
        if (name === "engineArchive") {
          const path = join(scratch, "zod-4.6.7.tgz")
          return await verifiedArchive(state.engine.data, path, 4 * 1024 * 1024)
        }
        if (name === "formatterMetadata") {
          stage = "mature formatter metadata and archive verification"
          return JSON.parse(
            command(
              process.execPath,
              [state.cli, "view", "zod-validation-error@4.0.2", "--json", ...NPM_TRANSPORT_ARGS],
              generation
            )
          )
        }
        if (name === "formatterArchive") {
          const path = join(scratch, "zod-validation-error-4.0.2.tgz")
          return await verifiedArchive(state.formatter.data, path, 4 * 1024 * 1024)
        }
        if (name === "overrideSelector") {
          stage = "pinned npm override selector diagnostic"
          const diagnostic = inspectOverrideSelector(
            dirname(dirname(state.cli)),
            candidateManifest,
            generation
          )
          console.log("FINAL_COMPILER_OVERRIDE_DIAGNOSTIC " + JSON.stringify(diagnostic))
          return diagnostic
        }
        if (name === "candidateLockGeneration") {
          stage = "isolated final consumer lock generation"
          npm(state.cli, "generateLock", generation)
          const path = join(generation, "package-lock.json")
          const bytes = regularBytes(path, 4 * 1024 * 1024)
          const candidate = JSON.parse(bytes)
          assert(!existsSync(join(generation, "node_modules")))
          writeFileSync(join(generation, "package.json"), candidateManifestBytes)
          assert.deepEqual(readFileSync(join(generation, "package.json")), candidateManifestBytes)
          assert.deepEqual(readFileSync(join(generation, ".npmrc")), configBytes)
          assert.deepEqual(
            readFileSync(join(generation, LOCAL, "package.json")),
            localManifestBytes
          )
          return { path, bytes, candidate }
        }
        if (name === "candidateLockScope") {
          stage = "whole-lock scope verification"
          return true
        }
        if (name === "fullGraphInstallAndVerify") {
          stage = "full project-configured graph installation"
          const target = mirror("full", candidateManifestBytes, state.candidateLockBytes)
          npm(state.cli, "fullGraph", target)
          stage = "full project-configured physical graph verification"
          assertFinalInstalledGraph(target, "full", controls)
          const licenseEvidence = inspectInstalledEngineLicense(target)
          assert.deepEqual(readFileSync(join(target, "package.json")), candidateManifestBytes)
          assert.deepEqual(
            readFileSync(join(target, "package-lock.json")),
            state.candidateLockBytes
          )
          assert.deepEqual(readFileSync(join(target, ".npmrc")), configBytes)
          assert.deepEqual(readFileSync(join(target, LOCAL, "package.json")), localManifestBytes)
          return { verified: true, licenseEvidence }
        }
        if (name === "productionGraphInstallAndVerify") {
          stage = "production project-configured graph installation"
          const target = mirror("production", candidateManifestBytes, state.candidateLockBytes)
          npm(state.cli, "productionGraph", target)
          stage = "production project-configured physical graph verification"
          assertFinalInstalledGraph(target, "production", controls)
          assert.deepEqual(readFileSync(join(target, "package.json")), candidateManifestBytes)
          assert.deepEqual(
            readFileSync(join(target, "package-lock.json")),
            state.candidateLockBytes
          )
          assert.deepEqual(readFileSync(join(target, ".npmrc")), configBytes)
          assert.deepEqual(readFileSync(join(target, LOCAL, "package.json")), localManifestBytes)
          return { verified: true }
        }
        if (name === "strictPeerProof") {
          stage = "isolated strict root-formatter fixture preparation"
          const strictPaths = {
            home: join(scratch, "strict-home"),
            cache: join(scratch, "strict-cache"),
            userconfig: join(scratch, "strict-user.npmrc"),
            globalconfig: join(scratch, "strict-global.npmrc"),
          }
          mkdirSync(strictPaths.home)
          mkdirSync(strictPaths.cache)
          for (const path of [strictPaths.userconfig, strictPaths.globalconfig]) {
            writeFileSync(path, "", { flag: "wx", mode: 0o400 })
          }
          const strictEnvironment = strictPeerEnvironment(npmEnv, strictPaths)
          const strictManifest = Buffer.from(
            JSON.stringify(prepareStrictFormatterPlacementManifest(candidateManifest), null, 2) +
              "\n"
          )
          const strict = mirror("strict", strictManifest, null, true)
          assert(!existsSync(join(strict, ".npmrc")))
          const strictGenerationManifestBytes = Buffer.from(
            JSON.stringify(
              prepareAbsoluteArchiveGenerationManifest(
                JSON.parse(strictManifest),
                realpathSync(join(strict, ARCHIVE))
              ),
              null,
              2
            ) + "\n"
          )
          writeFileSync(join(strict, "package.json"), strictGenerationManifestBytes)
          stage = "isolated strict root-formatter lock generation"
          npm(state.cli, "strictGenerate", strict, strictPaths, strictEnvironment)
          const strictLockBytes = regularBytes(join(strict, "package-lock.json"), 4 * 1024 * 1024)
          assertStrictLock(JSON.parse(strictLockBytes), state.candidateLock, true)
          writeFileSync(join(strict, "package.json"), strictManifest)
          assert.deepEqual(readFileSync(join(strict, "package.json")), strictManifest)
          stage = "isolated strict root-formatter installation"
          npm(state.cli, "strictInstall", strict, strictPaths, strictEnvironment)
          stage = strictVerificationPhase("native")
          assertFinalInstalledGraph(strict, "full", controls)
          stage = strictVerificationPhase("license")
          assert.deepEqual(inspectInstalledEngineLicense(strict), state.licenseEvidence)
          stage = strictVerificationPhase("npmList")
          const strictListingOutput = npm(
            state.cli,
            "strictList",
            strict,
            strictPaths,
            strictEnvironment
          )
          stage = strictVerificationPhase("json")
          const strictListing = JSON.parse(strictListingOutput)
          stage = strictVerificationPhase("identity")
          assert.equal(strictListing.name, "react-compiler-peer-proof")
          assert.equal(strictListing.version, "1.0.0")
          stage = strictVerificationPhase("problems")
          assert.deepEqual(strictListing.problems ?? [], [])
          stage = strictVerificationPhase("fixture")
          assert.deepEqual(readFileSync(join(strict, "package.json")), strictManifest)
          assert.deepEqual(readFileSync(join(strict, "package-lock.json")), strictLockBytes)
          assert(!existsSync(join(strict, ".npmrc")))
          stage = strictVerificationPhase("configuration")
          for (const path of [
            userConfig,
            globalConfig,
            strictPaths.userconfig,
            strictPaths.globalconfig,
          ]) {
            assert.equal(readFileSync(path).length, 0)
          }
          return {
            verified: true,
            strictNpmListVerified: true,
            strictLockBytes,
            licenseEvidence: state.licenseEvidence,
          }
        }
        if (name === "sourceSnapshotPostflight") {
          stage = strictVerificationPhase("source")
          for (const item of copied) assert.deepEqual(readFileSync(item.path), item.bytes)
          return true
        }
        if (name === "candidateDiff") {
          stage = "bounded generated candidate diff"
          function diff(before, after, path) {
            const result = spawnSync(
              "/usr/bin/git",
              ["diff", "--no-index", "--no-ext-diff", "--no-color", "--", before, after],
              {
                cwd: workspace,
                env: npmEnv,
                encoding: "utf8",
                shell: false,
                timeout: remaining(10_000),
                maxBuffer: 32 * 1024,
              }
            )
            assert(!result.error && !result.signal && (result.status === 0 || result.status === 1))
            if (result.status === 0) return ""
            return result.stdout
              .replace(/^diff --git .*$/m, "diff --git a/" + path + " b/" + path)
              .replace(/^--- .*$/m, "--- a/" + path)
              .replace(/^\+\+\+ .*$/m, "+++ b/" + path)
          }
          return (
            diff(snapshots[0].path, join(generation, "package.json"), "frontend/package.json") +
            diff(snapshots[1].path, state.candidateLockPath, "frontend/package-lock.json")
          )
        }
        assert.fail("Unknown final candidate orchestration stage: " + name)
      },
    })
    const {
      toolMetadata,
      engine,
      formatter,
      licenseEvidence,
      strictLockBytes,
      candidateLockBytes: candidateBytes,
    } = pipeline
    patch = pipeline.patch
    report = {
      kind: "react-compiler-final-lock-candidate",
      sourceSha: process.env.SOURCE_SHA,
      sourceTree,
      sourcePhase,
      node: process.version,
      npm: "11.17.0",
      bootstrapNpm: "11.19.0",
      registry: "https://registry.npmjs.org/",
      compiler: {
        version: "19.1.0-rc.2",
        integrity: golden.compilerIntegrity,
        bundleSha256: golden.compilerBundleSha256,
        originalArtifactPreserved: true,
      },
      patchedEngine: {
        name: engine.data.name,
        version: engine.data.version,
        published: engine.published,
        integrity: engine.data.dist.integrity,
        registryGitHead: engine.data.gitHead,
        tarballVerified: true,
      },
      formatter: {
        name: formatter.data.name,
        version: formatter.data.version,
        published: formatter.published,
        integrity: formatter.data.dist.integrity,
        peerDependencies: formatter.data.peerDependencies,
        tarballVerified: true,
      },
      engineLicense: licenseEvidence,
      licenseEvidenceScope: "physical package metadata and LICENSE bytes; not scanner disposition",
      changedPackagePaths:
        sourcePhase === SOURCE_PHASE.LEGACY_LINK
          ? ["", LINK, OLD_ENGINE, OLD_LINK, LOCAL, FORMATTER, HOOKS_FORMATTER]
          : sourcePhase === SOURCE_PHASE.STAGED_ARCHIVE
            ? [OLD_ENGINE, FORMATTER, HOOKS_FORMATTER]
            : [],
      removedPackagePaths:
        sourcePhase === SOURCE_PHASE.LEGACY_LINK
          ? [OLD_LINK, LOCAL, HOOKS_FORMATTER]
          : sourcePhase === SOURCE_PHASE.STAGED_ARCHIVE
            ? [HOOKS_FORMATTER]
            : [],
      zeroLockDeltaVerified: sourcePhase === SOURCE_PHASE.ALREADY_FINAL,
      consumerOverrideAdded: true,
      globalZodOverrideAdded: false,
      fullGraphInstallVerified: true,
      productionGraphInstallVerified: true,
      graphInstallPolicy: "project-configured legacy-peer-deps=true; ignore-scripts",
      strictPeerCompatibilityVerified: true,
      strictPeerScope: "isolated direct-formatter fixture; not whole-project strict resolution",
      strictPeerFixture: {
        rootFormatterPin: "zod-validation-error@4.0.2",
        targetArtifactsMatchProject: true,
        unanchoredResolutionRechecked: false,
        wholeProjectStrictResolutionVerified: false,
      },
      strictPeerVersions: {
        eslint: "10.12.0",
        compiler: "19.1.0-rc.2",
        hooks: "7.1.1",
        formatter: "4.0.2",
        facade: "1.0.0",
        zod: "4.6.7",
      },
      strictPeerDeclarations: {
        compilerEslint: ">=7",
        hooksEslint: HOOKS_PEER,
        formatterZod: FORMATTER_PEER,
      },
      strictNpmLsVerified: true,
      strictLegacyPeerDeps: false,
      cooldownException: false,
      compilerDiagnosticParityVerified: false,
      normalLifecycleOrBuildVerified: false,
      cryptographicPublishProvenanceVerified: false,
      projectLibraryCodeExecuted: false,
      lifecycleScriptsExecuted: false,
      checkoutModified: false,
      originalManifestSha256: digest(manifestBytes),
      candidateManifestSha256: digest(candidateManifestBytes),
      originalLockSha256: digest(lockBytes),
      candidateLockSha256: digest(candidateBytes),
      sourceManifestSha256: digest(manifestBytes),
      sourceLockSha256: digest(lockBytes),
      strictLockSha256: digest(strictLockBytes),
      projectNpmrcSha256: digest(configBytes),
      npmToolPublished: toolMetadata.published,
      npmToolIntegrity: toolMetadata.data.dist.integrity,
    }
  } catch {
    reject()
  } finally {
    try {
      stage = "original source verification"
      for (const item of [...(snapshots ?? []), ...copied]) {
        assert.deepEqual(readFileSync(item.path), item.bytes)
      }
      if (git) {
        assert.equal(git(["rev-parse", "HEAD"], true).trim(), process.env.SOURCE_SHA)
        if (sourceTree) assert.equal(git(["rev-parse", "HEAD^{tree}"], true).trim(), sourceTree)
        assert.equal(git(["status", "--porcelain=v1", "--untracked-files=all"], true), "")
      }
    } catch {
      reject()
    } finally {
      stage = "temporary workspace cleanup"
      try {
        if (scratch) rmSync(scratch, { recursive: true, force: true })
      } catch {
        reject()
      }
    }
  }
  if (failed) return 1
  console.log("FINAL_COMPILER_CANDIDATE_METADATA " + JSON.stringify(report))
  console.log(
    "FINAL_COMPILER_CANDIDATE_PATCH_BEGIN\n" + patch + "FINAL_COMPILER_CANDIDATE_PATCH_END"
  )
  console.log(
    "Source unchanged; isolated graph proof does not establish compiler parity, a passing audit or normal CI."
  )
  return 0
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  process.exitCode = await runFinalCompilerGenerator()
}
