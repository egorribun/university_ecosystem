import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import * as path from "node:path"
import { join } from "node:path"
import test from "node:test"
import { isDeepStrictEqual } from "node:util"
import { fileURLToPath } from "node:url"
import {
  assertFinalInstalledGraph,
  assertFinalLockScope,
  assertFinalNpmCommand,
  assertFinalSourcePrerequisites,
  assertArchiveOverrideTarget,
  assertOverrideSelectorControl,
  assertStrictLock,
  classifyFinalSourcePhase,
  FINAL_CANDIDATE_ORCHESTRATION_STAGES,
  finalNpmCommand,
  inspectInstalledEngineLicense,
  inspectOverrideSelector,
  orchestrateFinalCandidateStages,
  prepareAbsoluteArchiveGenerationManifest,
  prepareFinalManifest,
  prepareStrictFormatterPlacementManifest,
  prepareStrictManifest,
  strictPeerEnvironment,
  strictVerificationPhase,
  summarizeStrictListFailure,
  summarizeStrictNpmFailure,
  SOURCE_PHASE,
  validateFormatterMetadata,
} from "./generate-react-compiler-final-lock-candidate.mjs"

const LOCAL = "scripts/react-compiler-zod-compat"
const LEGACY = "react-compiler-zod-compat"
const LEGACY_SPEC = "file:./" + LOCAL
const FACADE = "@university-ecosystem/react-compiler-zod-compat"
const ARCHIVE = "vendor/react-compiler-zod-compat-1.0.0.tgz"
const ARCHIVE_SPEC = "file:./" + ARCHIVE
const LINK = "node_modules/" + FACADE
const CONSUMER = "eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2"
const TEST_FRONTEND = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const FACADE_SOURCE = Object.fromEntries(
  ["package.json", "index.cjs", "LICENSE", "README.md"].map((name) => [
    name,
    readFileSync(path.join(TEST_FRONTEND, LOCAL, name)),
  ])
)
const ARCHIVE_BYTES = readFileSync(path.join(TEST_FRONTEND, ARCHIVE))
const COMPILER = "node_modules/eslint-plugin-react-compiler"
const OLD_ENGINE = COMPILER + "/node_modules/zod"
const FORMATTER = "node_modules/zod-validation-error"
const HOOKS_FORMATTER = "node_modules/eslint-plugin-react-hooks/node_modules/zod-validation-error"
const FINAL_OVERRIDE = Object.freeze({
  ".": "$eslint-plugin-react-compiler",
  zod: "$" + FACADE,
  "zod-validation-error": Object.freeze({ ".": "4.0.2", zod: "4.6.7" }),
})
const TRANSPORT = [
  "--registry=https://registry.npmjs.org/",
  "--fetch-retries=0",
  "--fetch-timeout=30000",
  "--ignore-scripts",
  "--min-release-age=7",
]
const NOW = Date.parse("2026-10-24T00:00:00Z")

function sri(value) {
  return "sha512-" + createHash("sha512").update(value).digest("base64")
}

function packageRecord(name, version, extra = {}) {
  const archive = name.split("/").at(-1)
  return {
    version,
    resolved: "https://registry.npmjs.org/" + name + "/-/" + archive + "-" + version + ".tgz",
    integrity: sri(name + "@" + version),
    dev: true,
    license: "MIT",
    ...extra,
  }
}

function manifest() {
  return {
    name: "frontend",
    version: "0.1.0",
    private: true,
    packageManager: "npm@11.17.0",
    dependencies: { valibot: "^1.4.0" },
    devDependencies: {
      eslint: "^10.12.0",
      "eslint-plugin-react-compiler": "^19.1.0-rc.2",
      "eslint-plugin-react-hooks": "^7.1.1",
      [FACADE]: ARCHIVE_SPEC,
    },
    overrides: {
      undici: ">=8.10.2",
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
      "eslint-plugin-boundaries@7.2.0": { micromatch: "$micromatch" },
    },
  }
}

function legacyManifest() {
  const source = manifest()
  delete source.devDependencies[FACADE]
  source.devDependencies[LEGACY] = LEGACY_SPEC
  return source
}

function sourceLock() {
  const source = manifest()
  const rootZod = packageRecord("zod", "4.6.7", {
    funding: { url: "https://github.com/sponsors/colinhacks" },
  })
  delete rootZod.dev
  const lock = {
    name: source.name,
    version: source.version,
    lockfileVersion: 3,
    requires: true,
    packages: {
      "": {
        name: source.name,
        version: source.version,
        dependencies: structuredClone(source.dependencies),
        devDependencies: structuredClone(source.devDependencies),
      },
      [COMPILER]: packageRecord("eslint-plugin-react-compiler", "19.1.0-rc.2", {
        dependencies: {
          "@babel/core": "^7.24.4",
          "@babel/parser": "^7.24.4",
          "@babel/plugin-proposal-private-methods": "^7.18.6",
          "hermes-parser": "^0.25.1",
          zod: "^3.22.4",
          "zod-validation-error": "^3.0.3",
        },
        peerDependencies: { eslint: ">=7" },
      }),
      [OLD_ENGINE]: packageRecord("zod", "3.25.76"),
      [FORMATTER]: packageRecord("zod-validation-error", "3.5.4", {
        engines: { node: ">=18.0.0" },
        peerDependencies: { zod: "^3.24.4" },
      }),
      [HOOKS_FORMATTER]: packageRecord("zod-validation-error", "4.0.2", {
        engines: { node: ">=18.0.0" },
        peerDependencies: { zod: "^3.25.0 || ^4.0.0" },
      }),
      "node_modules/eslint": packageRecord("eslint", "10.12.0"),
      "node_modules/eslint-plugin-react-hooks": packageRecord(
        "eslint-plugin-react-hooks",
        "7.1.1",
        {
          dependencies: { zod: "^3.25.0 || ^4.0.0", "zod-validation-error": "^3.5.0 || ^4.0.0" },
          peerDependencies: {
            eslint:
              "^3.0.0 || ^4.0.0 || ^5.0.0 || ^6.0.0 || ^7.0.0 || ^8.0.0-0 || ^9.0.0 || ^10.0.0",
          },
        }
      ),
      "node_modules/zod": rootZod,
      "node_modules/patched-zod": { name: "zod", ...rootZod, dev: true },
      [LINK]: {
        version: "1.0.0",
        resolved: "file:" + ARCHIVE,
        integrity: sri(ARCHIVE_BYTES),
        dev: true,
        license: "MIT",
        dependencies: { "patched-zod": "npm:zod@4.6.7" },
      },
      "node_modules/unrelated": packageRecord("unrelated", "1.0.0", {
        optional: true,
        dependencies: { preserved: "^1" },
      }),
    },
  }
  for (const [name, version] of [
    ["body-parser", "1.20.9"],
    ["undici", "8.12.2"],
    ["@puppeteer/browsers", "3.2.4"],
    ["chromium-bidi", "157.0.8090-0"],
    ["puppeteer-core", "25.13.0"],
    ["puppeteer-core/node_modules/devtools-protocol", "0.0.1696802"],
    ["typed-query-selector", "2.12.3"],
    ["webdriver-bidi-protocol", "1.0.1"],
  ]) {
    lock.packages["node_modules/" + name] = packageRecord(
      name.split("/node_modules/").at(-1),
      version
    )
  }
  lock.packages["node_modules/chromium-bidi"].dependencies = { zod: "^4.6.5" }
  return lock
}

function legacySourceLock() {
  const source = sourceLock()
  delete source.packages[""].devDependencies[FACADE]
  source.packages[""].devDependencies[LEGACY] = LEGACY_SPEC
  delete source.packages[LINK]
  source.packages["node_modules/" + LEGACY] = { resolved: LOCAL, link: true }
  source.packages[LOCAL] = {
    name: FACADE,
    version: "1.0.0",
    dev: true,
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  }
  return source
}

function expectedFinalLock() {
  const candidate = sourceLock()
  candidate.packages[OLD_ENGINE] = { name: FACADE, ...structuredClone(candidate.packages[LINK]) }
  candidate.packages[FORMATTER] = structuredClone(candidate.packages[HOOKS_FORMATTER])
  delete candidate.packages[HOOKS_FORMATTER]
  return candidate
}

function expectedLegacyFinalLock() {
  const candidate = legacySourceLock()
  delete candidate.packages[""].devDependencies[LEGACY]
  candidate.packages[""].devDependencies[FACADE] = ARCHIVE_SPEC
  delete candidate.packages["node_modules/" + LEGACY]
  delete candidate.packages[LOCAL]
  candidate.packages[LINK] = structuredClone(sourceLock().packages[LINK])
  candidate.packages[OLD_ENGINE] = {
    name: FACADE,
    ...structuredClone(candidate.packages[LINK]),
  }
  candidate.packages[FORMATTER] = structuredClone(candidate.packages[HOOKS_FORMATTER])
  delete candidate.packages[HOOKS_FORMATTER]
  return candidate
}

function strictLock() {
  const candidate = expectedFinalLock()
  candidate.name = "react-compiler-peer-proof"
  candidate.version = "1.0.0"
  candidate.packages[""] = {
    name: "react-compiler-peer-proof",
    version: "1.0.0",
    devDependencies: {
      eslint: "10.12.0",
      "eslint-plugin-react-compiler": "19.1.0-rc.2",
      "eslint-plugin-react-hooks": "7.1.1",
      [FACADE]: ARCHIVE_SPEC,
      zod: "4.6.7",
    },
  }
  candidate.packages["node_modules/zod"].dev = true
  return candidate
}

function formatterMetadata(record = sourceLock().packages[HOOKS_FORMATTER]) {
  return {
    name: "zod-validation-error",
    version: "4.0.2",
    license: "MIT",
    repository: {
      type: "git",
      url: "git://github.com/causaly/zod-validation-error.git",
    },
    engines: record.engines,
    peerDependencies: record.peerDependencies,
    scripts: { prepare: "husky" },
    dist: {
      tarball: record.resolved,
      integrity: record.integrity,
      shasum: createHash("sha1").update("public formatter fixture").digest("hex"),
    },
    time: { "4.0.2": "2026-10-16T00:00:00Z" },
  }
}

function registryMetadata(name, version, { gitHead, integrity } = {}) {
  const archive = Buffer.from("synthetic registry metadata fixture: " + name + "@" + version)
  const value = {
    name,
    version,
    dist: {
      tarball: "https://registry.npmjs.org/" + name + "/-/" + name + "-" + version + ".tgz",
      integrity: integrity ?? sri(archive),
      shasum: createHash("sha1").update(archive).digest("hex"),
    },
    time: { [version]: "2026-10-16T00:00:00Z" },
  }
  if (name === "zod") {
    value.license = "MIT"
    value.repository = { type: "git", url: "git+https://github.com/colinhacks/zod.git" }
    value.gitHead = gitHead
    value.dependencies = {}
  }
  return value
}

function withDirectory(run) {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), "compiler-final-guard-")))
  try {
    return run(directory)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
}

function writePackage(
  root,
  relative,
  value,
  entry = "throw new Error('Guard fixture must not execute')\n"
) {
  const location = join(root, relative)
  mkdirSync(location, { recursive: true })
  writeFileSync(join(location, "package.json"), JSON.stringify(value))
  writeFileSync(join(location, "index.cjs"), entry)
}

function installedFixture(root, mode = "full") {
  const lock = expectedFinalLock()
  writePackage(root, "node_modules/zod", { name: "zod", version: "4.6.7", main: "index.cjs" })
  mkdirSync(join(root, LOCAL), { recursive: true })
  for (const [name, bytes] of Object.entries(FACADE_SOURCE)) {
    writeFileSync(join(root, LOCAL, name), bytes)
  }
  mkdirSync(join(root, "vendor"), { recursive: true })
  writeFileSync(join(root, ARCHIVE), ARCHIVE_BYTES)
  if (mode === "production") return {}
  writePackage(root, "node_modules/patched-zod", {
    name: "zod",
    version: "4.6.7",
    main: "index.cjs",
  })
  const compilerEntry = "throw new Error('Compiler fixture must not execute')\n"
  writePackage(
    root,
    COMPILER,
    {
      name: "eslint-plugin-react-compiler",
      version: "19.1.0-rc.2",
      main: "index.cjs",
      dependencies: lock.packages[COMPILER].dependencies,
      peerDependencies: { eslint: ">=7" },
    },
    compilerEntry
  )
  writePackage(root, FORMATTER, {
    name: "zod-validation-error",
    version: "4.0.2",
    main: "index.cjs",
    exports: { ".": "./index.cjs" },
    peerDependencies: { zod: "^3.25.0 || ^4.0.0" },
  })
  for (const name of ["eslint", "eslint-plugin-react-hooks"]) {
    writePackage(root, "node_modules/" + name, {
      name,
      version: lock.packages["node_modules/" + name].version,
      main: "index.cjs",
      peerDependencies: lock.packages["node_modules/" + name].peerDependencies,
    })
  }
  mkdirSync(join(root, COMPILER, "node_modules"), { recursive: true })
  const installedFacade = {
    name: FACADE,
    version: "1.0.0",
    private: true,
    description: "The legacy schema API used only by the pinned React Compiler ESLint gate",
    main: "index.cjs",
    files: ["index.cjs", "LICENSE", "README.md"],
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  }
  writePackage(root, LINK, installedFacade)
  writePackage(root, OLD_ENGINE, installedFacade)
  return {
    compilerBundleSha256: createHash("sha256").update(compilerEntry).digest("hex"),
    compilerDependencies: lock.packages[COMPILER].dependencies,
  }
}

test("final manifest changes only the exact legacy consumer override", () => {
  const original = manifest()
  const snapshot = structuredClone(original)
  const expected = structuredClone(original)
  expected.overrides["eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2"] = FINAL_OVERRIDE
  assert.deepEqual(prepareFinalManifest(original), expected)
  assert.deepEqual(original, snapshot)
})

test("existing consumer or global engine overrides cannot be silently replaced", () => {
  for (const key of [
    "zod",
    "zod@4",
    "eslint-plugin-react-compiler",
    "eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2",
    "eslint-plugin-react-compiler@19.1.0-rc.2",
    "eslint-plugin-react-compiler@*",
  ]) {
    const value = manifest()
    value.overrides[key] = "different"
    assert.throws(() => prepareFinalManifest(value), { name: "AssertionError" })
  }
})

test("final manifest requires the staged private dev dependency and pinned consumer", () => {
  for (const mutate of [
    (value) => delete value.devDependencies[FACADE],
    (value) => (value.dependencies[FACADE] = ARCHIVE_SPEC),
    (value) => (value.devDependencies["eslint-plugin-react-compiler"] = "^20"),
    (value) => (value.packageManager = "npm@11.19.0"),
    (value) => (value.overrides["eslint-plugin-react-hooks"] = { "zod-validation-error": "3" }),
  ]) {
    const value = manifest()
    mutate(value)
    assert.throws(() => prepareFinalManifest(value), { name: "AssertionError" })
  }
})

test("source graph accepts the existing honest staged package without mutation", () => {
  const original = sourceLock()
  const snapshot = structuredClone(original)
  assert.equal(assertFinalSourcePrerequisites(original), true)
  assert.deepEqual(original, snapshot)
})

test("c90 legacy links promote through the exact complete seven-record lock delta", () => {
  const originalManifest = legacyManifest()
  const originalLock = legacySourceLock()
  const sourceSnapshot = structuredClone(originalLock)
  const candidateManifest = prepareFinalManifest(originalManifest)
  const candidateLock = expectedLegacyFinalLock()
  assert.equal(classifyFinalSourcePhase(originalManifest, originalLock), SOURCE_PHASE.LEGACY_LINK)
  assert.equal(assertFinalSourcePrerequisites(originalLock, SOURCE_PHASE.LEGACY_LINK), true)
  assert.equal(
    assertFinalLockScope(
      originalLock,
      candidateLock,
      formatterMetadata(),
      SOURCE_PHASE.LEGACY_LINK
    ),
    true
  )
  assert.deepEqual(candidateLock, expectedFinalLock())
  assert.deepEqual(originalLock, sourceSnapshot)
  assert.equal(candidateManifest.devDependencies[FACADE], ARCHIVE_SPEC)
  assert(!Object.hasOwn(candidateManifest.devDependencies, LEGACY))
  assert.deepEqual(originalLock.packages[""].devDependencies, originalManifest.devDependencies)
})

test("staged archive graph retains the exact three-record promotion path", () => {
  const originalManifest = manifest()
  const originalLock = sourceLock()
  const candidate = expectedFinalLock()
  assert.equal(
    classifyFinalSourcePhase(originalManifest, originalLock),
    SOURCE_PHASE.STAGED_ARCHIVE
  )
  assert.equal(assertFinalLockScope(originalLock, candidate, formatterMetadata()), true)
})

test("already-final graph requires exact source identity and zero lock delta", () => {
  const finalManifest = prepareFinalManifest(manifest())
  const finalLock = expectedFinalLock()
  assert.equal(classifyFinalSourcePhase(finalManifest, finalLock), SOURCE_PHASE.ALREADY_FINAL)
  assert.equal(assertFinalSourcePrerequisites(finalLock, SOURCE_PHASE.ALREADY_FINAL), true)
  assert.equal(
    assertFinalLockScope(
      finalLock,
      structuredClone(finalLock),
      formatterMetadata(),
      SOURCE_PHASE.ALREADY_FINAL
    ),
    true
  )
  for (const mutate of [
    (value) => (value.packages["node_modules/unrelated"].version = "2.0.0"),
    (value) => (value.packages[OLD_ENGINE].version = "1.0.1"),
    (value) => (value.packages[FORMATTER].version = "4.0.3"),
  ]) {
    const candidate = structuredClone(finalLock)
    mutate(candidate)
    assert.throws(
      () =>
        assertFinalLockScope(finalLock, candidate, formatterMetadata(), SOURCE_PHASE.ALREADY_FINAL),
      {
        name: "AssertionError",
      }
    )
  }
})

const orchestrationPhaseCases = [
  {
    name: "c90 legacy link",
    sourcePhase: SOURCE_PHASE.LEGACY_LINK,
    sourceManifest: legacyManifest(),
    sourceLock: legacySourceLock(),
    candidateLock: expectedLegacyFinalLock(),
    formatterPath: HOOKS_FORMATTER,
    deltaCount: 7,
  },
  {
    name: "staged archive",
    sourcePhase: SOURCE_PHASE.STAGED_ARCHIVE,
    sourceManifest: manifest(),
    sourceLock: sourceLock(),
    candidateLock: expectedFinalLock(),
    formatterPath: HOOKS_FORMATTER,
    deltaCount: 3,
  },
  {
    name: "already-final graph",
    sourcePhase: SOURCE_PHASE.ALREADY_FINAL,
    sourceManifest: prepareFinalManifest(manifest()),
    sourceLock: expectedFinalLock(),
    candidateLock: expectedFinalLock(),
    formatterPath: FORMATTER,
    deltaCount: 0,
  },
]

for (const scenario of orchestrationPhaseCases) {
  test(
    "synthetic " + scenario.name + " orchestration uses its formatter record through postflight",
    async () => {
      const { sourcePhase, sourceManifest, sourceLock, candidateLock, formatterPath, deltaCount } =
        scenario
      assert.equal(classifyFinalSourcePhase(sourceManifest, sourceLock), sourcePhase)
      if (sourcePhase === SOURCE_PHASE.ALREADY_FINAL) {
        assert.equal(sourceLock.packages[HOOKS_FORMATTER], undefined)
      }

      const calls = []
      const licenseEvidence = {
        packageName: "zod",
        version: "4.6.7",
        license: "MIT",
        licenseSha256: "b".repeat(64),
      }
      const archiveEvidence = (metadata, path) => ({
        verified: true,
        bytes: 1,
        integrity: metadata.dist.integrity,
        sha256: "a".repeat(64),
        path: "synthetic-archive-fixture/" + path,
      })
      const emittedPatch = deltaCount === 0 ? "" : "synthetic-" + sourcePhase + "-lock-patch"
      const state = await orchestrateFinalCandidateStages({
        sourcePhase,
        sourceLock,
        now: NOW,
        runStage: async (stage, current) => {
          calls.push(stage)
          if (stage === "toolMetadata") return registryMetadata("npm", "11.17.0")
          if (stage === "toolArchive") {
            return archiveEvidence(current.toolMetadata.data, "npm.tgz")
          }
          if (stage === "toolInstall") return { cli: "synthetic-pinned-npm-cli" }
          if (stage === "engineMetadata") {
            return registryMetadata("zod", "4.6.7", {
              gitHead: "b500a2ee95134f81d74da7911d7378dd2853d042",
              integrity: sourceLock.packages["node_modules/zod"].integrity,
            })
          }
          if (stage === "engineArchive") {
            return archiveEvidence(current.engine.data, "zod.tgz")
          }
          if (stage === "formatterMetadata") {
            assert.equal(current.formatterSourcePath, formatterPath)
            assert.strictEqual(current.formatterSourceRecord, sourceLock.packages[formatterPath])
            return formatterMetadata(current.formatterSourceRecord)
          }
          if (stage === "formatterArchive") {
            return archiveEvidence(current.formatter.data, "formatter.tgz")
          }
          if (stage === "overrideSelector") return selectorDiagnostic()
          if (stage === "candidateLockGeneration") {
            const bytes = Buffer.from(JSON.stringify(candidateLock))
            return {
              path: "synthetic-" + sourcePhase + "/package-lock.json",
              bytes,
              candidate: structuredClone(candidateLock),
            }
          }
          if (stage === "candidateLockScope") return true
          if (stage === "fullGraphInstallAndVerify") {
            return { verified: true, licenseEvidence }
          }
          if (stage === "productionGraphInstallAndVerify") return { verified: true }
          if (stage === "strictPeerProof") {
            return {
              verified: true,
              strictNpmListVerified: true,
              strictLockBytes: Buffer.from("synthetic strict fixture lock"),
              licenseEvidence,
            }
          }
          if (stage === "sourceSnapshotPostflight") return true
          if (stage === "candidateDiff") return emittedPatch
          assert.fail("Unexpected synthetic orchestration stage: " + stage)
        },
      })

      assert.deepEqual(calls, FINAL_CANDIDATE_ORCHESTRATION_STAGES)
      assert.deepEqual(state.completedStages, FINAL_CANDIDATE_ORCHESTRATION_STAGES)
      assert.equal(state.formatterSourcePath, formatterPath)
      assert.strictEqual(state.formatterSourceRecord, sourceLock.packages[formatterPath])
      assert.equal(state.cli, "synthetic-pinned-npm-cli")
      assert.equal(state.candidateLockScopeVerified, true)
      assert.equal(state.fullGraphInstallVerified, true)
      assert.equal(state.productionGraphInstallVerified, true)
      assert.equal(state.strictPeerProof.strictNpmListVerified, true)
      assert.equal(state.sourceSnapshotPostflightVerified, true)
      assert.equal(state.patch, emittedPatch)
      assert.equal(state.patch.length > 0, deltaCount > 0)
      const changedPackagePaths = new Set([
        ...Object.keys(sourceLock.packages),
        ...Object.keys(candidateLock.packages),
      ])
      assert.equal(
        [...changedPackagePaths].filter(
          (path) => !isDeepStrictEqual(sourceLock.packages[path], candidateLock.packages[path])
        ).length,
        deltaCount
      )
    }
  )
}
test("source phase classifier rejects mixed and broadened dependency shapes", () => {
  for (const mutate of [
    (value) => (value.devDependencies[FACADE] = ARCHIVE_SPEC),
    (value) => (value.devDependencies[LEGACY] = "file:./scripts/other-compat"),
    (value) => (value.overrides[CONSUMER] = { zod: "*" }),
    (value) => (value.overrides["eslint-plugin-react-compiler@*"] = FINAL_OVERRIDE),
  ]) {
    const source = legacyManifest()
    mutate(source)
    assert.throws(() => prepareFinalManifest(source), { name: "AssertionError" })
  }
  const sourceLockValue = legacySourceLock()
  sourceLockValue.packages[LOCAL].dependencies["patched-zod"] = "npm:zod@3.25.76"
  assert.throws(() => assertFinalSourcePrerequisites(sourceLockValue, SOURCE_PHASE.LEGACY_LINK), {
    name: "AssertionError",
  })
})

test("source graph rejects changed engines, consumer versions and unexpected old Zod", () => {
  for (const mutate of [
    (value) => (value.packages[COMPILER].version = "19.1.0-rc.3"),
    (value) => (value.packages["node_modules/zod"].version = "4.6.5"),
    (value) => (value.packages["node_modules/patched-zod"].version = "3.25.76"),
    (value) => (value.packages[OLD_ENGINE].version = "3.25.77"),
    (value) => (value.packages[LINK].dev = false),
    (value) => (value.packages["node_modules/extra/node_modules/zod"] = { version: "3.25.76" }),
    (value) => (value.packages["node_modules/puppeteer-core"].version = "25.12.0"),
    (value) => (value.packages["node_modules/chromium-bidi"].dependencies.zod = "^3"),
  ]) {
    const value = sourceLock()
    mutate(value)
    assert.throws(() => assertFinalSourcePrerequisites(value), { name: "AssertionError" })
  }
})

test("accepted final lock has only the hand-derived three-record delta", () => {
  const original = sourceLock()
  const candidate = expectedFinalLock()
  const snapshot = structuredClone(candidate)
  assert.equal(assertFinalLockScope(original, candidate, formatterMetadata()), true)
  assert.deepEqual(candidate, snapshot)
})

test("unrelated package, root-manifest and top-level lock changes are rejected", () => {
  for (const mutate of [
    (value) => (value.packages["node_modules/unrelated"].version = "2.0.0"),
    (value) => (value.packages[""].devDependencies.eslint = "^9"),
    (value) => (value.lockfileVersion = 2),
    (value) => (value.packages["node_modules/zod"].dev = true),
    (value) => delete value.packages["node_modules/patched-zod"],
    (value) => (value.packages[COMPILER].integrity = sri("different compiler")),
    (value) => (value.packages[COMPILER].dependencies.zod = "*"),
    (value) => (value.packages["node_modules/new"] = { version: "1.0.0" }),
  ]) {
    const value = expectedFinalLock()
    mutate(value)
    assert.throws(() => assertFinalLockScope(sourceLock(), value, formatterMetadata()), {
      name: "AssertionError",
    })
  }
})

test("the observed consumer-relative facade fourth record remains rejected", () => {
  const misplaced = "node_modules/eslint-plugin-react-compiler/scripts/react-compiler-zod-compat"
  for (const redirect of [false, true]) {
    const value = expectedFinalLock()
    value.packages[misplaced] = {}
    if (redirect) value.packages[OLD_ENGINE] = { resolved: misplaced, link: true }
    assert.throws(() => assertFinalLockScope(sourceLock(), value, formatterMetadata()), {
      name: "AssertionError",
    })
  }
})

test("alternate formatter placement and fake schema versions are not accepted", () => {
  for (const mutate of [
    (value) => (value.packages[OLD_ENGINE] = packageRecord("zod", "4.6.7")),
    (value) => (value.packages[OLD_ENGINE] = { resolved: "scripts/other", link: true }),
    (value) => (value.packages[HOOKS_FORMATTER] = sourceLock().packages[HOOKS_FORMATTER]),
    (value) => (value.packages[FORMATTER].version = "4.0.3"),
    (value) => (value.packages[FORMATTER].peerDependencies.zod = "*"),
  ]) {
    const value = expectedFinalLock()
    mutate(value)
    assert.throws(() => assertFinalLockScope(sourceLock(), value, formatterMetadata()), {
      name: "AssertionError",
    })
  }
})

test("metadata proves formatter maturity and the exact existing artifact", () => {
  const data = formatterMetadata()
  const expected = {
    data,
    published: "2026-10-16T00:00:00Z",
    timestamp: Date.parse("2026-10-16T00:00:00Z"),
  }
  assert.deepEqual(
    validateFormatterMetadata(data, sourceLock().packages[HOOKS_FORMATTER], NOW),
    expected
  )
})

test("metadata accepts the exact seven-day boundary without a cooldown exception", () => {
  const data = formatterMetadata()
  data.time["4.0.2"] = "2026-10-17T00:00:00Z"
  assert.deepEqual(validateFormatterMetadata(data, sourceLock().packages[HOOKS_FORMATTER], NOW), {
    data,
    published: "2026-10-17T00:00:00Z",
    timestamp: NOW - 7 * 86400000,
  })
})

test("metadata rejects immature, deprecated, wrong-origin and replaced formatter bytes", () => {
  for (const mutate of [
    (value) => (value.time["4.0.2"] = "2026-10-23T00:00:00Z"),
    (value) => (value.time["4.0.2"] = "2026-10-17T00:00:00.001Z"),
    (value) => (value.time["4.0.2"] = "2026-10-31T00:00:00Z"),
    (value) => (value.time["4.0.2"] = "not-a-date"),
    (value) => delete value.time["4.0.2"],
    (value) => (value.deprecated = "unsafe"),
    (value) => (value.name = "different"),
    (value) => (value.dist.tarball = "https://example.test/formatter.tgz"),
    (value) => (value.dist.integrity = sri("replacement")),
    (value) => (value.dist.shasum = "invalid"),
    (value) => (value.repository.url = "git://github.com/other/project.git"),
    (value) => (value.peerDependencies.zod = "*"),
    (value) => (value.dependencies = { zod: "^3" }),
  ]) {
    const data = formatterMetadata()
    mutate(data)
    assert.throws(
      () => validateFormatterMetadata(data, sourceLock().packages[HOOKS_FORMATTER], NOW),
      { name: "AssertionError" }
    )
  }
})

test("ordinary graph commands keep scripts disabled without claiming strict peer proof", () => {
  for (const [operation, prefix] of [
    ["generateLock", ["update", "zod", "zod-validation-error", "--package-lock-only"]],
    ["fullGraph", ["ci", "--include=dev"]],
    ["productionGraph", ["ci", "--omit=dev"]],
  ]) {
    const expected = [...prefix, "--no-audit", "--no-fund", ...TRANSPORT]
    assert.deepEqual(finalNpmCommand(operation), expected)
    assert.equal(assertFinalNpmCommand(operation, expected), true)
  }
})

test("final generation rejects stale install, unbounded updates and additional targets", () => {
  for (const prefix of [
    ["install", "--package-lock-only"],
    ["update", "--package-lock-only"],
    ["update", "zod", "--package-lock-only"],
    ["update", "zod-validation-error", "--package-lock-only"],
    ["update", "zod", "zod-validation-error", "eslint", "--package-lock-only"],
  ]) {
    assert.throws(
      () =>
        assertFinalNpmCommand("generateLock", [...prefix, "--no-audit", "--no-fund", ...TRANSPORT]),
      { name: "AssertionError" }
    )
  }
})

test("a successful npm no-op cannot be accepted as a remediated candidate", () => {
  assert.throws(() => assertFinalLockScope(sourceLock(), sourceLock(), formatterMetadata()), {
    name: "AssertionError",
  })
})

test("strict peer commands explicitly disable legacy resolution and bind isolated configs", () => {
  withDirectory((root) => {
    const paths = {
      userconfig: join(root, "user.npmrc"),
      globalconfig: join(root, "global.npmrc"),
    }
    for (const [operation, prefix] of [
      ["strictGenerate", ["install", "--package-lock-only", "--json"]],
      ["strictInstall", ["ci", "--include=dev"]],
      ["strictList", ["ls", "--all", "--json", "--long"]],
    ]) {
      const expected = [
        ...prefix,
        "--legacy-peer-deps=false",
        "--strict-peer-deps",
        "--userconfig=" + paths.userconfig,
        "--globalconfig=" + paths.globalconfig,
        "--no-audit",
        "--no-fund",
        ...TRANSPORT,
      ]
      assert.deepEqual(finalNpmCommand(operation, paths), expected)
      assert.equal(assertFinalNpmCommand(operation, expected, paths), true)
    }
  })
})

test("command guards reject bypasses, extra targets and noncanonical config paths", () => {
  const ordinary = ["ci", "--include=dev", "--no-audit", "--no-fund", ...TRANSPORT]
  for (const extra of ["--force", "--legacy-peer-deps", "--ignore-scripts=false", "unrelated"]) {
    assert.throws(() => assertFinalNpmCommand("fullGraph", [...ordinary, extra]), {
      name: "AssertionError",
    })
  }
  assert.throws(() => finalNpmCommand("unknown"), { name: "AssertionError" })
  assert.throws(
    () => finalNpmCommand("strictInstall", { userconfig: "../user", globalconfig: "/global" }),
    { name: "AssertionError" }
  )
  withDirectory((root) => {
    for (const globalconfig of [join(root, "nested/global.npmrc"), join(root, "user.npmrc")]) {
      assert.throws(
        () =>
          finalNpmCommand("strictInstall", {
            userconfig: join(root, "user.npmrc"),
            globalconfig,
          }),
        { name: "AssertionError" }
      )
    }
  })
})

test("strict subprocess environment excludes inherited credentials and npm relaxation", () => {
  withDirectory((root) => {
    const paths = {
      home: join(root, "home"),
      cache: join(root, "cache"),
      userconfig: join(root, "user.npmrc"),
      globalconfig: join(root, "global.npmrc"),
    }
    const original = {
      PATH: "/usr/bin:/bin",
      HOME: "/untrusted-home",
      NPM_CONFIG_LEGACY_PEER_DEPS: "true",
      npm_config_force: "true",
      NODE_OPTIONS: "--require=/untrusted.js",
      UNRELATED: "not-forwarded",
    }
    const expected = {
      PATH: "/usr/bin:/bin",
      HOME: paths.home,
      npm_config_cache: paths.cache,
      npm_config_userconfig: paths.userconfig,
      npm_config_globalconfig: paths.globalconfig,
      npm_config_legacy_peer_deps: "false",
      npm_config_strict_peer_deps: "true",
      npm_config_ignore_scripts: "true",
    }
    assert.deepEqual(strictPeerEnvironment(original, paths), expected)
    assert.equal(original.NPM_CONFIG_LEGACY_PEER_DEPS, "true")
  })
})

test("strict fixture pins real current ESLint and consumers instead of downgrading peers", () => {
  const input = manifest()
  input.overrides["eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2"] = FINAL_OVERRIDE
  assert.deepEqual(prepareStrictManifest(input), {
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
      "eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2": FINAL_OVERRIDE,
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
    },
  })
})

test("absolute archive paths are generation-only and never mutate the portable manifest", () => {
  const portable = prepareFinalManifest(manifest())
  const snapshot = structuredClone(portable)
  const archivePath = join(TEST_FRONTEND, ARCHIVE)
  const generation = prepareAbsoluteArchiveGenerationManifest(portable, archivePath)
  assert.equal(
    generation.overrides["eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2"].zod,
    "file:" + path.resolve(archivePath).replaceAll("\\", "/")
  )
  assert.deepEqual(generation.devDependencies, portable.devDependencies)
  assert.deepEqual(portable, snapshot)
  for (const invalid of [
    ARCHIVE_SPEC,
    join(TEST_FRONTEND, "package.json"),
    TEST_FRONTEND + "\\vendor\\..\\vendor\\react-compiler-zod-compat-1.0.0.tgz",
  ]) {
    assert.throws(() => prepareAbsoluteArchiveGenerationManifest(portable, invalid), {
      name: "AssertionError",
    })
  }
})

test("root formatter pin is confined to the isolated fixture", () => {
  const project = prepareFinalManifest(manifest())
  const snapshot = structuredClone(project)
  const unanchored = prepareStrictManifest(project)
  const anchored = prepareStrictFormatterPlacementManifest(project)
  assert.deepEqual(anchored, {
    ...unanchored,
    devDependencies: { ...unanchored.devDependencies, "zod-validation-error": "4.0.2" },
  })
  assert.equal(Object.hasOwn(unanchored.devDependencies, "zod-validation-error"), false)
  assert.equal(Object.hasOwn(project.devDependencies, "zod-validation-error"), false)
  assert.deepEqual(project, snapshot)
})

test("strict formatter placement keeps the exact pin and original peers", () => {
  const project = expectedFinalLock()
  const anchored = strictLock()
  anchored.packages[""].devDependencies["zod-validation-error"] = "4.0.2"
  assert.equal(assertStrictLock(anchored, project, true), true)
  assert.throws(() => assertStrictLock(anchored, project), { name: "AssertionError" })
  for (const mode of [null, "true", 1]) {
    assert.throws(() => assertStrictLock(anchored, project, mode), { name: "AssertionError" })
  }
  for (const mutate of [
    (value) => delete value.packages[""].devDependencies["zod-validation-error"],
    (value) => (value.packages[""].devDependencies["zod-validation-error"] = "4.0.3"),
    (value) => (value.packages[""].devDependencies["zod-validation-error"] = "*"),
    (value) => (value.packages[""].devDependencies.unrelated = "1.0.0"),
    (value) => (value.packages[FORMATTER].peerDependencies.zod = "*"),
    (value) => (value.packages[FORMATTER].integrity = sri("different formatter")),
    (value) => (value.packages[COMPILER].peerDependencies.eslint = "*"),
  ]) {
    const value = structuredClone(anchored)
    mutate(value)
    assert.throws(() => assertStrictLock(value, project, true), { name: "AssertionError" })
  }
})

test("fixture-only formatter pin must not leak into the accepted project lock", () => {
  const candidate = expectedFinalLock()
  candidate.packages[""].devDependencies["zod-validation-error"] = "4.0.2"
  assert.throws(() => assertFinalLockScope(sourceLock(), candidate, formatterMetadata()), {
    name: "AssertionError",
  })
})

test("strict graph binds the exact target artifacts and original ESLint peer declarations", () => {
  const project = expectedFinalLock()
  const strict = strictLock()
  assert.equal(assertStrictLock(strict, project), true)
})

test("strict proof rejects changed peers, selected versions and artifact replacements", () => {
  for (const mutate of [
    (value) => (value.packages["node_modules/eslint"].version = "9.0.0"),
    (value) => (value.packages["node_modules/eslint-plugin-react-hooks"].version = "7.1.0"),
    (value) =>
      (value.packages["node_modules/eslint-plugin-react-hooks"].peerDependencies.eslint = "*"),
    (value) => (value.packages[""].devDependencies.eslint = "9.0.0"),
    (value) =>
      (value.packages[""].devDependencies["eslint-plugin-react-compiler"] = "^19.1.0-rc.2"),
    (value) => (value.packages[""].devDependencies["eslint-plugin-react-hooks"] = "^7.1.1"),
    (value) => (value.packages[""].devDependencies.zod = "4.6.6"),
    (value) => (value.packages[COMPILER].peerDependencies.eslint = "*"),
    (value) => (value.packages[FORMATTER].peerDependencies.zod = "*"),
    (value) => (value.packages[FORMATTER].integrity = sri("different formatter")),
    (value) => (value.packages[OLD_ENGINE] = { version: "3.25.76" }),
    (value) => (value.packages[OLD_ENGINE].dependencies["patched-zod"] = "npm:zod@3.25.76"),
  ]) {
    const project = expectedFinalLock()
    const strict = strictLock()
    mutate(strict)
    assert.throws(() => assertStrictLock(strict, project), { name: "AssertionError" })
  }
})

test("native installed resolution binds compiler facade and formatter genuine Zod", () => {
  withDirectory((root) => {
    const controls = installedFixture(root)
    assert.equal(assertFinalInstalledGraph(root, "full", controls), true)
  })
})

test("production graph accepts tracked adapter source without installed dev dependencies", () => {
  withDirectory((root) => {
    installedFixture(root, "production")
    assert.equal(assertFinalInstalledGraph(root, "production", {}), true)
  })
})

test("production graph rejects each installed development compatibility consumer", () => {
  for (const [path, name, version] of [
    ["patched-zod", "zod", "4.6.7"],
    ["eslint-plugin-react-compiler", "eslint-plugin-react-compiler", "19.1.0-rc.2"],
    [FACADE, FACADE, "1.0.0"],
    ["zod-validation-error", "zod-validation-error", "4.0.2"],
    ["eslint-plugin-react-hooks", "eslint-plugin-react-hooks", "7.1.1"],
  ]) {
    withDirectory((root) => {
      installedFixture(root, "production")
      writePackage(root, "node_modules/" + path, { name, version, main: "index.cjs" })
      assert.throws(() => assertFinalInstalledGraph(root, "production", {}), {
        name: "AssertionError",
      })
    })
  }
})

test("consumer resolution rejects the original vulnerable engine and a replacement bundle", () => {
  for (const change of ["old-engine", "bundle"]) {
    withDirectory((root) => {
      const controls = installedFixture(root)
      if (change === "old-engine") {
        rmSync(join(root, OLD_ENGINE), { recursive: true })
        writePackage(root, OLD_ENGINE, { name: "zod", version: "3.25.76", main: "index.cjs" })
      } else {
        writeFileSync(join(root, COMPILER, "index.cjs"), "// changed compiler artifact\n")
      }
      assert.throws(() => assertFinalInstalledGraph(root, "full", controls), {
        name: "AssertionError",
      })
    })
  }
})

test("formatter peer cannot resolve the facade or an external same-version engine", () => {
  for (const change of ["facade-peer", "external-engine"]) {
    withDirectory((root) => {
      const controls = installedFixture(root)
      mkdirSync(join(root, FORMATTER, "node_modules"), { recursive: true })
      if (change === "facade-peer") {
        symlinkSync(join(root, LOCAL), join(root, FORMATTER, "node_modules/zod"), "dir")
      } else {
        writePackage(root, "outside", { name: "zod", version: "4.6.7", main: "index.cjs" })
        symlinkSync(join(root, "outside"), join(root, FORMATTER, "node_modules/zod"), "dir")
      }
      assert.throws(() => assertFinalInstalledGraph(root, "full", controls), {
        name: "AssertionError",
      })
    })
  }
})

test("unknown installed graph mode cannot accidentally select a relaxed path", () => {
  withDirectory((root) => {
    const controls = installedFixture(root)
    assert.throws(() => assertFinalInstalledGraph(root, "unknown", controls), {
      name: "AssertionError",
    })
  })
})

test("physical engine license evidence reads bounded bytes without executing package code", () => {
  withDirectory((root) => {
    const metadata = { name: "zod", version: "4.6.7", license: "MIT", main: "index.cjs" }
    const license = "MIT License\n\nPublic package license test fixture.\n"
    writePackage(root, "node_modules/patched-zod", metadata)
    writeFileSync(join(root, "node_modules/patched-zod/LICENSE"), license)
    assert.deepEqual(inspectInstalledEngineLicense(root), {
      packageName: "zod",
      version: "4.6.7",
      declaredLicense: "MIT",
      licenseFile: {
        bytes: Buffer.byteLength(license),
        sha256: createHash("sha256").update(license).digest("hex"),
      },
    })
  })
})

test("physical engine license evidence rejects unbounded or substituted package files", () => {
  for (const mutation of [
    "name",
    "version",
    "license",
    "missing-file",
    "oversized-license",
    "oversized-manifest",
    "directory",
    "linked-license",
    "linked-manifest",
    "linked-engine",
  ]) {
    withDirectory((root) => {
      const metadata = { name: "zod", version: "4.6.7", license: "MIT", main: "index.cjs" }
      const license = "MIT License\n\nPublic package license test fixture.\n"
      const packageDirectory = join(root, "node_modules/patched-zod")
      const licensePath = join(packageDirectory, "LICENSE")
      const manifestPath = join(packageDirectory, "package.json")
      writePackage(root, "node_modules/patched-zod", metadata)
      writeFileSync(licensePath, license)
      if (["name", "version", "license"].includes(mutation)) {
        metadata[mutation] = "unreviewed"
        writeFileSync(manifestPath, JSON.stringify(metadata))
      } else if (mutation === "missing-file") {
        rmSync(licensePath)
      } else if (mutation === "oversized-license") {
        writeFileSync(licensePath, "x".repeat(8193))
      } else if (mutation === "oversized-manifest") {
        writeFileSync(manifestPath, JSON.stringify(metadata) + " ".repeat(32768))
      } else if (mutation === "directory") {
        rmSync(licensePath)
        mkdirSync(licensePath)
      } else {
        writePackage(root, "outside", metadata)
        writeFileSync(join(root, "outside/LICENSE"), license)
        if (mutation === "linked-license") {
          rmSync(licensePath)
          symlinkSync(join(root, "outside/LICENSE"), licensePath, "file")
        } else if (mutation === "linked-manifest") {
          rmSync(manifestPath)
          symlinkSync(join(root, "outside/package.json"), manifestPath, "file")
        } else {
          assert.equal(mutation, "linked-engine")
          rmSync(packageDirectory, { recursive: true })
          symlinkSync(join(root, "outside"), packageDirectory, "dir")
        }
      }
      assert.throws(() => inspectInstalledEngineLicense(root), { name: "AssertionError" })
    })
  }
})

function selectorToolFixture(root, attached = true) {
  const tool = join(root, "tool")
  const compiler = "eslint-plugin-react-compiler"
  const exact = compiler + "@19.1.0-rc.2"
  const selected = compiler + "@>=19.1.0-rc.2 <=19.1.0-rc.2"
  writePackage(root, "tool", { name: "npm", version: "11.17.0" })
  writePackage(
    tool,
    "node_modules/semver",
    { name: "semver", version: "7.8.4", main: "index.cjs" },
    [
      "module.exports = {",
      "  satisfies: (version) => ['19.1.0-rc.2', '19.1.0-rc.2+fixture'].includes(version),",
      "  intersects: (_, range) => range === '>=19.1.0-rc.2 <=19.1.0-rc.2' && " + attached,
      "}",
      "",
    ].join("\n")
  )
  writePackage(tool, "node_modules/@npmcli/arborist", {
    name: "@npmcli/arborist",
    version: "9.8.0",
    main: "index.cjs",
  })
  mkdirSync(join(tool, "node_modules/@npmcli/arborist/lib"))
  writeFileSync(
    join(tool, "node_modules/@npmcli/arborist/lib/override-set.js"),
    [
      "const assert = require('node:assert/strict')",
      "module.exports = class OverrideSet {",
      "  constructor({ overrides }) {",
      "    this.key = [" +
        JSON.stringify(exact) +
        ", " +
        JSON.stringify(selected) +
        "].find(key => overrides[key])",
      "    assert.equal(overrides[this.key].zod, this.key === " +
        JSON.stringify(exact) +
        " ? '$react-compiler-zod-compat' : '$@university-ecosystem/react-compiler-zod-compat')",
      "    this.rule = { key: this.key }",
      "  }",
      "  getEdgeRule(edge) {",
      "    assert.deepEqual(edge, " +
        JSON.stringify({ name: compiler, rawSpec: "^19.1.0-rc.2", spec: "^19.1.0-rc.2" }) +
        ")",
      "    return this.key === " +
        JSON.stringify(selected) +
        " && " +
        attached +
        " ? this.rule : this",
      "  }",
      "  getNodeRule(node) {",
      "    assert.equal(node.name, " + JSON.stringify(compiler) + ")",
      "    return ['19.1.0-rc.2', '19.1.0-rc.2+fixture'].includes(node.version) ? this.rule : this",
      "  }",
      "}",
      "",
    ].join("\n")
  )
  writeFileSync(
    join(tool, "node_modules/@npmcli/arborist/lib/edge.js"),
    "module.exports = class Edge {}\n"
  )
  writeFileSync(
    join(tool, "node_modules/@npmcli/arborist/lib/node.js"),
    [
      "const assert = require('node:assert/strict')",
      "const { join } = require('node:path')",
      "const Edge = require('./edge.js')",
      "module.exports = class Node {",
      "  constructor({ loadOverrides, pkg, path, parent }) {",
      "    if (parent) {",
      "      this.path = join(parent.path, 'node_modules', pkg.name)",
      "      const edge = new Edge()",
      "      edge.name = 'zod'",
      "      edge.rawSpec = pkg.dependencies.zod",
      "      const spec = parent.rule.zod",
      "      edge.spec = spec.startsWith('$') ? parent.pkg.devDependencies[spec.slice(1)] : spec",
      "      edge.from = this",
      "      this.edgesOut = new Map([['zod', edge]])",
      "      return",
      "    }",
      "    assert.equal(loadOverrides, true)",
      "    assert.equal(pkg.name, 'react-compiler-selector-control')",
      "    this.path = path",
      "    this.pkg = pkg",
      "    const key = Object.keys(pkg.overrides)[0]",
      "    const name = 'eslint-plugin-react-compiler'",
      "    this.rule = pkg.overrides[key]",
      "    const edge = new Edge()",
      "    edge.overrides = { key }",
      "    edge.rawSpec = pkg.devDependencies[name]",
      "    edge.spec = this.rule['.'] === '$' + name ? edge.rawSpec : key.slice(name.length + 1)",
      "    this.edgesOut = new Map([[name, edge]])",
      "  }",
      "  assertRootOverrides() {",
      "    const edge = this.edgesOut.get('eslint-plugin-react-compiler')",
      "    if (edge.spec !== edge.rawSpec) {",
      "      throw Object.assign(new Error('synthetic conflict'), { code: 'EOVERRIDE' })",
      "    }",
      "  }",
      "}",
      "",
    ].join("\n")
  )
  writePackage(
    tool,
    "node_modules/npm-package-arg",
    { name: "npm-package-arg", version: "13.0.2", main: "index.cjs" },
    [
      "const assert = require('node:assert/strict')",
      "const { resolve } = require('node:path')",
      "module.exports = { resolve(name, spec, where) {",
      "  assert(['zod', '@university-ecosystem/react-compiler-zod-compat'].includes(name))",
      "  assert.equal(spec.startsWith('file:'), true)",
      "  const fetchSpec = resolve(where, spec.slice(5))",
      "  return { type: fetchSpec.endsWith('.tgz') ? 'file' : 'directory', fetchSpec }",
      "} }",
      "",
    ].join("\n")
  )
  mkdirSync(join(tool, "node_modules/@npmcli/arborist/lib/arborist"))
  writeFileSync(
    join(tool, "node_modules/@npmcli/arborist/lib/arborist/build-ideal-tree.js"),
    "throw new Error('Resolver control must not execute build-ideal-tree')\n"
  )
  const frontend = join(root, "frontend")
  installedFixture(frontend)
  const candidate = manifest()
  candidate.overrides[selected] = FINAL_OVERRIDE
  return { tool, candidate, frontend }
}

function selectorDiagnostic(attached = true) {
  return {
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
    nodeRule: "eslint-plugin-react-compiler@19.1.0-rc.2",
    selectedSelector: {
      range: ">=19.1.0-rc.2 <=19.1.0-rc.2",
      satisfies: true,
      intersects: attached,
      edgeRule: attached ? "eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2" : null,
      nodeRule: "eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2",
    },
    versionChecks: [
      { version: "19.1.0-rc.1", exact: false, selected: false, nodeAttached: false },
      { version: "19.1.0-rc.2", exact: true, selected: true, nodeAttached: true },
      { version: "19.1.0-rc.2+fixture", exact: true, selected: true, nodeAttached: true },
      { version: "19.1.0-rc.3", exact: false, selected: false, nodeAttached: false },
      { version: "19.1.0", exact: false, selected: false, nodeAttached: false },
      { version: "19.1.1-rc.2", exact: false, selected: false, nodeAttached: false },
      { version: "20.0.0", exact: false, selected: false, nodeAttached: false },
    ],
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
  }
}

test("selector diagnostic preserves exact baseline and requires singleton attachment", () => {
  for (const attached of [false, true]) {
    withDirectory((root) => {
      const { tool, candidate, frontend } = selectorToolFixture(root, attached)
      const report = inspectOverrideSelector(tool, candidate, frontend)
      assert.deepEqual(report, selectorDiagnostic(attached))
      if (attached) assert.equal(assertOverrideSelectorControl(report), true)
      else assert.throws(() => assertOverrideSelectorControl(report), { name: "AssertionError" })
    })
  }
})

test("singleton selector controls reject wider versions, lost evidence and altered tooling", () => {
  for (const mutate of [
    (value) => (value.npm = "11.19.0"),
    (value) => (value.semver = "7.8.3"),
    (value) => (value.arborist = "9.7.0"),
    (value) => (value.intersectsSelector = true),
    (value) => (value.edgeRule = value.nodeRule),
    (value) => (value.selectedSelector.range = "*"),
    (value) => (value.selectedSelector.edgeRule = "eslint-plugin-react-compiler"),
    (value) => (value.selectedSelector.nodeRule = value.nodeRule),
    (value) => (value.selectedSelector.intersects = false),
    (value) => (value.versionChecks[0].selected = true),
    (value) => (value.versionChecks[3].selected = true),
    (value) => (value.versionChecks[4].selected = true),
    (value) => (value.versionChecks[5].selected = true),
    (value) => (value.versionChecks[6].selected = true),
    (value) => (value.versionChecks[0].nodeAttached = true),
    (value) => (value.versionChecks[1].nodeAttached = false),
    (value) => value.versionChecks.pop(),
    (value) => (value.directDependency.rawSpec = "19.1.0-rc.2"),
    (value) => (value.directDependency.effectiveSpec = value.selectedSelector.range),
    (value) => (value.directDependency.rootOverrideAccepted = false),
    (value) => (value.directDependency.missingReferenceError = null),
    (value) => (value.localDependency.parserVersion = "13.0.1"),
    (value) => (value.localDependency.rawSpec = "*"),
    (value) => (value.localDependency.baselineTarget = COMPILER + "/" + LOCAL),
    (value) => (value.localDependency.selectedTarget = LOCAL),
    (value) =>
      (value.localDependency.selectedSpec = "file:../vendor/react-compiler-zod-compat-1.0.0.tgz"),
    (value) => (value.localDependency.targetType = "directory"),
    (value) => (value.localDependency.targetCanonical = false),
    (value) => (value.candidateAccepted = false),
  ]) {
    const report = selectorDiagnostic()
    mutate(report)
    assert.throws(() => assertOverrideSelectorControl(report), { name: "AssertionError" })
  }
})

test("selector diagnostic rejects changed tool versions and external resolution", () => {
  for (const mutation of [
    "npm",
    "semver",
    "arborist",
    "npm-package-arg",
    "linked-semver",
    "shadow-parser",
    "nonboolean",
  ]) {
    withDirectory((root) => {
      const { tool, candidate, frontend } = selectorToolFixture(root)
      if (mutation === "linked-semver") {
        writePackage(root, "outside", { name: "semver", version: "7.8.4" })
        rmSync(join(tool, "node_modules/semver"), { recursive: true })
        symlinkSync(join(root, "outside"), join(tool, "node_modules/semver"), "dir")
      } else if (mutation === "shadow-parser") {
        writePackage(tool, "node_modules/@npmcli/arborist/node_modules/npm-package-arg", {
          name: "npm-package-arg",
          version: "13.0.2",
          main: "index.cjs",
        })
      } else if (mutation === "nonboolean") {
        writeFileSync(
          join(tool, "node_modules/semver/index.cjs"),
          "module.exports = { satisfies: () => true, intersects: () => 'unbounded' }\n"
        )
      } else {
        const relative = {
          npm: "",
          semver: "node_modules/semver",
          arborist: "node_modules/@npmcli/arborist",
          "npm-package-arg": "node_modules/npm-package-arg",
        }[mutation]
        writeFileSync(
          join(tool, relative, "package.json"),
          JSON.stringify({
            name: mutation === "arborist" ? "@npmcli/arborist" : mutation,
            version: "0.0.0",
          })
        )
      }
      assert.throws(() => inspectOverrideSelector(tool, candidate, frontend), {
        name: "AssertionError",
      })
    })
  }
})

test("archive override target is portable and rejects unrelated paths or symlinks", () => {
  withDirectory((root) => {
    const frontend = join(root, "frontend")
    installedFixture(frontend)
    const consumer = join(frontend, COMPILER)
    const target = join(frontend, ARCHIVE)
    assert.equal(assertArchiveOverrideTarget(frontend, consumer, target), true)
    for (const [parent, destination] of [
      [join(frontend, "node_modules/other-consumer"), target],
      [consumer, join(frontend, COMPILER, ARCHIVE)],
      [consumer, join(frontend, "node_modules", ARCHIVE)],
      [consumer, join(root, "outside.tgz")],
    ]) {
      assert.throws(() => assertArchiveOverrideTarget(frontend, parent, destination), {
        name: "AssertionError",
      })
    }
    const outside = join(root, "outside.tgz")
    writeFileSync(outside, ARCHIVE_BYTES)
    rmSync(target)
    symlinkSync(outside, target, "file")
    assert.throws(() => assertArchiveOverrideTarget(frontend, consumer, target), {
      name: "AssertionError",
    })
  })
})

test("strict npm failure diagnostics retain only reviewed dependency tuples", () => {
  const report = summarizeStrictNpmFailure({
    status: 1,
    signal: null,
    stderr: "/private/fixture",
    stdout: JSON.stringify({
      error: {
        code: "ERESOLVE",
        summary: "/private/fixture",
        detail: [
          "\u001b[34mWhile resolving: react-compiler-peer-proof@1.0.0\u001b[0m",
          "\u001b[31mFound: zod@1.0.0 overridden\u001b[0m",
          "node_modules/private-fixture",
          'peer overridden zod@"4.6.7" (was "^3.25.0 || ^4.0.0") from zod-validation-error@4.0.2',
          "Conflicting peer dependency: zod@4.6.7",
        ].join("\n"),
      },
    }),
  })
  assert.deepEqual(report, {
    kind: "react-compiler-strict-npm-failure",
    operation: "strictGenerate",
    exitCode: 1,
    timedOut: false,
    terminated: false,
    jsonRecognized: true,
    errorCode: "ERESOLVE",
    observations: [
      { kind: "resolving", name: "react-compiler-peer-proof", version: "1.0.0" },
      { kind: "found", name: "zod", version: "1.0.0" },
      {
        kind: "peer",
        name: "zod",
        range: "4.6.7",
        originalRange: "^3.25.0 || ^4.0.0",
        consumer: "zod-validation-error",
        consumerVersion: "4.0.2",
      },
      { kind: "conflicting", name: "zod", version: "4.6.7" },
    ],
    omitted: false,
    candidateAccepted: false,
  })
  assert.equal(JSON.stringify(report).includes("private"), false)
})

test("strict npm diagnostics reject unknown fields, packages, versions and ranges", () => {
  for (const detail of [
    "Found: private-package@1.0.0",
    "Found: zod@999.0.0",
    'peer zod@"unreviewed-value" from zod-validation-error@4.0.2',
    'peer zod@"4.6.7" from private-package@1.0.0',
    'peer zod@"4.6.7" (was "unreviewed-value") from zod-validation-error@4.0.2',
    "Found: zod@4.6.7 /private/fixture",
    "https://example.invalid/private-fixture",
  ]) {
    const report = summarizeStrictNpmFailure({
      status: 1,
      stdout: JSON.stringify({
        error: { code: "UNREVIEWED", summary: "/private/fixture", detail, extra: "ignored" },
      }),
    })
    assert.equal(report.errorCode, "unrecognized")
    assert.deepEqual(report.observations, [])
    assert.equal(JSON.stringify(report).includes("private"), false)
    assert.equal(JSON.stringify(report).includes("unreviewed-value"), false)
  }
})

test("strict npm diagnostics bound malformed, oversized and interrupted results", () => {
  const oversized = (padding) =>
    JSON.stringify({
      error: { code: "ERESOLVE", summary: padding, detail: "Found: zod@4.6.7" },
    })
  for (const stdout of [
    "not json",
    "null",
    "[]",
    "{}",
    '{"error":[]}',
    "x".repeat(65537),
    oversized("x".repeat(65536)),
    oversized("é".repeat(32768)),
  ]) {
    const report = summarizeStrictNpmFailure({
      status: null,
      signal: "SIGTERM",
      error: { code: "ETIMEDOUT", message: "/private/fixture" },
      stdout,
    })
    assert.equal(report.jsonRecognized, false)
    assert.equal(report.exitCode, null)
    assert.equal(report.timedOut, true)
    assert.equal(report.terminated, true)
    assert.deepEqual(report.observations, [])
    assert.equal(JSON.stringify(report).includes("private"), false)
  }
  assert.throws(() => summarizeStrictNpmFailure({ status: 0, stdout: "{}" }), {
    name: "AssertionError",
  })
})

test("strict npm diagnostics deduplicate and cap reviewed observations", () => {
  const headings = ["Found", "While resolving", "Conflicting peer dependency"]
  const detail = [
    ...Array(30).fill("Found: zod@4.6.7"),
    ...headings.flatMap((heading) =>
      ["1.0.0", "3.25.76", "4.6.7"].map((version) => heading + ": zod@" + version)
    ),
  ].join("\n")
  const report = summarizeStrictNpmFailure({
    status: 1,
    stdout: JSON.stringify({ error: { code: "ERESOLVE", detail } }),
  })
  assert.equal(report.observations.length, 8)
  assert.equal(new Set(report.observations.map((item) => JSON.stringify(item))).size, 8)
  assert.equal(report.omitted, true)
  assert.ok(Buffer.byteLength(JSON.stringify(report)) < 4096)
})

test("strict verification labels are fixed and distinguish every post-install boundary", () => {
  for (const [phase, label] of [
    ["native", "native graph verification"],
    ["license", "license equality"],
    ["npmList", "npm ls execution"],
    ["json", "npm ls JSON decoding"],
    ["identity", "npm ls identity verification"],
    ["problems", "npm ls problem-list verification"],
    ["fixture", "fixture byte immutability"],
    ["configuration", "empty configuration verification"],
    ["source", "source snapshot verification"],
  ]) {
    assert.equal(strictVerificationPhase(phase), "isolated strict root-formatter " + label)
  }
})

test("strict verification labels reject arbitrary data and prototype keys", () => {
  for (const phase of ["", "/private/fixture", "unreviewed", "__proto__", "toString", null, 1]) {
    assert.throws(() => strictVerificationPhase(phase), { name: "AssertionError" })
  }
})

test("strict npm ls diagnostics classify only reviewed package and alias identities", () => {
  const report = summarizeStrictListFailure({
    status: 1,
    stdout: JSON.stringify({
      name: "react-compiler-peer-proof",
      version: "1.0.0",
      error: { code: "ELSPROBLEMS", summary: "/private/fixture", detail: "ignored" },
      problems: [
        "invalid: zod@npm:@university-ecosystem/react-compiler-zod-compat@1.0.0 /private/fixture",
        "missing: zod-validation-error@4.0.2, required by private-fixture",
        "extraneous: patched-zod@npm:zod@4.6.7 /private/fixture",
      ],
      dependencies: {
        "eslint-plugin-react-compiler": {
          name: "eslint-plugin-react-compiler",
          version: "19.1.0-rc.2",
          dependencies: {
            zod: {
              name: "@university-ecosystem/react-compiler-zod-compat",
              version: "1.0.0",
              path: "/private/fixture",
              resolved: "/private/fixture",
              invalid:
                '"file:../../scripts/react-compiler-zod-compat" from node_modules/eslint-plugin-react-compiler',
            },
          },
        },
      },
    }),
  })
  assert.deepEqual(report, {
    kind: "react-compiler-strict-list-failure",
    operation: "strictList",
    exitCode: 1,
    timedOut: false,
    terminated: false,
    outputLimitExceeded: false,
    jsonRecognized: true,
    errorCode: "ELSPROBLEMS",
    problemCategories: { invalid: 1, missing: 1, extraneous: 1, unrecognized: 0 },
    observations: [
      {
        kind: "invalid",
        name: "zod",
        version: "1.0.0",
        packageName: "@university-ecosystem/react-compiler-zod-compat",
      },
      { kind: "missing", name: "zod-validation-error", version: "4.0.2" },
      { kind: "extraneous", name: "patched-zod", version: "4.6.7", packageName: "zod" },
      {
        kind: "invalid-edge",
        name: "zod",
        version: "1.0.0",
        packageName: "@university-ecosystem/react-compiler-zod-compat",
        range: "file:../../scripts/react-compiler-zod-compat",
        consumer: "eslint-plugin-react-compiler",
      },
    ],
    omitted: false,
    candidateAccepted: false,
  })
  assert.equal(JSON.stringify(report).includes("private"), false)
})

test("strict npm ls diagnostics do not expose unreviewed identities or metadata", () => {
  for (const [name, version, invalid] of [
    ["private-package", "1.0.0", '"4.6.7" from node_modules/zod-validation-error'],
    ["zod", "999.0.0", '"4.6.7" from node_modules/zod-validation-error'],
    ["zod", "4.6.7", '"private-range" from node_modules/zod-validation-error'],
    ["zod", "4.6.7", '"4.6.7" from node_modules/private-package'],
    ["zod", "4.6.7", '"4.6.7" from /private/fixture'],
  ]) {
    const report = summarizeStrictListFailure({
      status: 1,
      stderr: "/private/fixture",
      stdout: JSON.stringify({
        error: { code: "PRIVATE_CODE", detail: "/private/fixture" },
        problems: ["invalid: private-package@1.0.0 /private/fixture"],
        dependencies: {
          zod: { name, version, invalid, _path: "/private/fixture", linkTargets: "ignored" },
        },
      }),
    })
    assert.equal(report.errorCode, "unrecognized")
    assert.deepEqual(report.observations, [])
    assert.equal(report.omitted, true)
    assert.equal(JSON.stringify(report).includes("private"), false)
  }
})

test("strict npm ls diagnostics bound malformed JSON and byte-sized input", () => {
  for (const stdout of [
    "not json",
    "null",
    "[]",
    '{"dependencies":',
    JSON.stringify({ padding: "x".repeat(1024 * 1024) }),
    JSON.stringify({ padding: "é".repeat(512 * 1024) }),
  ]) {
    const report = summarizeStrictListFailure({
      status: null,
      signal: "SIGTERM",
      error: { code: "ETIMEDOUT", message: "/private/fixture" },
      stdout,
    })
    assert.equal(report.jsonRecognized, false)
    assert.equal(report.exitCode, null)
    assert.equal(report.timedOut, true)
    assert.equal(report.terminated, true)
    assert.deepEqual(report.observations, [])
    assert.equal(JSON.stringify(report).includes("private"), false)
  }
  const overflow = summarizeStrictListFailure({
    status: null,
    error: { code: "ENOBUFS", message: "/private/fixture" },
    stdout: "{}",
  })
  assert.equal(overflow.outputLimitExceeded, true)
  assert.throws(() => summarizeStrictListFailure({ status: 0, stdout: "{}" }), {
    name: "AssertionError",
  })
})

test("strict npm ls diagnostics cap observations and avoid arbitrary traversal", () => {
  const problems = [
    ...Array(30).fill("invalid: zod@4.6.7 /private/fixture"),
    ...["invalid", "missing", "extraneous"].flatMap((kind) =>
      ["1.0.0", "3.25.76", "4.6.7"].map((version) =>
        kind === "missing"
          ? "missing: zod@" + version + ", required by private-fixture"
          : kind + ": zod@" + version + " /private/fixture"
      )
    ),
    ...Array(40).fill("unrecognized private-fixture"),
  ]
  const report = summarizeStrictListFailure({
    status: 1,
    stdout: JSON.stringify({
      problems,
      dependencies: {
        "private-package": {
          dependencies: {
            zod: {
              name: "zod",
              version: "4.6.7",
              invalid: '"4.6.7" from node_modules/zod-validation-error',
            },
          },
        },
      },
    }),
  })
  assert.equal(report.observations.length, 8)
  assert.equal(new Set(report.observations.map((item) => JSON.stringify(item))).size, 8)
  assert.equal(
    Object.values(report.problemCategories).reduce((sum, value) => sum + value),
    64
  )
  assert.equal(
    report.observations.some((item) => item.kind === "invalid-edge"),
    false
  )
  assert.equal(report.omitted, true)
  assert.ok(Buffer.byteLength(JSON.stringify(report)) <= 4096)
})

test("strict npm ls diagnostics reject malformed problem and invalid-edge shapes", () => {
  for (const value of [null, {}, 1, ["invalid: zod@4.6.7 /private/fixture"]]) {
    const report = summarizeStrictListFailure({
      status: 1,
      stdout: JSON.stringify({
        problems: [value, "invalid: zod@4.6.7 " + "x".repeat(4096)],
        dependencies: { zod: { name: "zod", version: "4.6.7", invalid: value } },
      }),
    })
    assert.deepEqual(report.observations, [])
    assert.equal(report.omitted, true)
  }
  const report = summarizeStrictListFailure({
    status: 1,
    stdout: JSON.stringify({
      problems: "invalid: zod@4.6.7 /private/fixture",
      dependencies: {
        zod: {
          name: "zod",
          version: "4.6.7",
          invalid: '"4.6.7" from node_modules/zod-validation-error'.repeat(64),
        },
      },
    }),
  })
  assert.deepEqual(report.observations, [])
  assert.equal(report.omitted, true)
})

test("import is inert and direct execution produces no false candidate evidence", () => {
  const url = new URL("./generate-react-compiler-final-lock-candidate.mjs", import.meta.url)
  const options = {
    env: { GITHUB_WORKSPACE: "/final-compiler-generator-test-does-not-exist" },
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 4096,
  }
  const direct = spawnSync(process.execPath, [fileURLToPath(url)], options)
  assert.equal(direct.status, 1)
  assert.equal(direct.stdout, "")
  assert.equal(direct.stderr, "Final compiler candidate rejected at stage: preflight\n")
  const imported = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", "import " + JSON.stringify(url.href)],
    options
  )
  assert.equal(imported.status, 0)
  assert.equal(imported.stdout, "")
  assert.equal(imported.stderr, "")
})
