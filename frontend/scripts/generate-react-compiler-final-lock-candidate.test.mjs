import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import {
  assertFinalInstalledGraph,
  assertFinalLockScope,
  assertFinalNpmCommand,
  assertFinalSourcePrerequisites,
  assertStrictLock,
  finalNpmCommand,
  inspectInstalledEngineLicense,
  inspectOverrideSelector,
  prepareFinalManifest,
  prepareStrictManifest,
  strictPeerEnvironment,
  validateFormatterMetadata,
} from "./generate-react-compiler-final-lock-candidate.mjs"

const LOCAL = "scripts/react-compiler-zod-compat"
const COMPILER = "node_modules/eslint-plugin-react-compiler"
const OLD_ENGINE = COMPILER + "/node_modules/zod"
const FORMATTER = "node_modules/zod-validation-error"
const HOOKS_FORMATTER = "node_modules/eslint-plugin-react-hooks/node_modules/zod-validation-error"
const FINAL_OVERRIDE = Object.freeze({
  zod: "$react-compiler-zod-compat",
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
      "react-compiler-zod-compat": "file:./" + LOCAL,
    },
    overrides: {
      undici: ">=8.10.2",
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
      "eslint-plugin-boundaries@7.2.0": { micromatch: "$micromatch" },
    },
  }
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
      "node_modules/react-compiler-zod-compat": { resolved: LOCAL, link: true },
      [LOCAL]: {
        name: "@university-ecosystem/react-compiler-zod-compat",
        version: "1.0.0",
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

function expectedFinalLock() {
  const candidate = sourceLock()
  candidate.packages[OLD_ENGINE] = { resolved: LOCAL, link: true }
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
      "react-compiler-zod-compat": "file:./" + LOCAL,
      zod: "4.6.7",
    },
  }
  candidate.packages["node_modules/zod"].dev = true
  return candidate
}

function formatterMetadata() {
  const record = sourceLock().packages[HOOKS_FORMATTER]
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
  if (mode === "production") {
    writePackage(root, LOCAL, {
      name: "@university-ecosystem/react-compiler-zod-compat",
      version: "1.0.0",
      main: "index.cjs",
    })
    return {}
  }
  writePackage(root, LOCAL, {
    name: "@university-ecosystem/react-compiler-zod-compat",
    version: "1.0.0",
    private: true,
    description: "The legacy schema API used only by the pinned React Compiler ESLint gate",
    main: "index.cjs",
    files: ["index.cjs", "LICENSE", "README.md"],
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  })
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
  symlinkSync(join(root, LOCAL), join(root, OLD_ENGINE), "dir")
  symlinkSync(join(root, LOCAL), join(root, "node_modules/react-compiler-zod-compat"), "dir")
  return {
    compilerBundleSha256: createHash("sha256").update(compilerEntry).digest("hex"),
    compilerDependencies: lock.packages[COMPILER].dependencies,
  }
}

test("final manifest changes only the exact legacy consumer override", () => {
  const original = manifest()
  const snapshot = structuredClone(original)
  const expected = structuredClone(original)
  expected.overrides["eslint-plugin-react-compiler@19.1.0-rc.2"] = FINAL_OVERRIDE
  assert.deepEqual(prepareFinalManifest(original), expected)
  assert.deepEqual(original, snapshot)
})

test("existing consumer or global engine overrides cannot be silently replaced", () => {
  for (const key of [
    "zod",
    "zod@4",
    "eslint-plugin-react-compiler",
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
    (value) => delete value.devDependencies["react-compiler-zod-compat"],
    (value) => (value.dependencies["react-compiler-zod-compat"] = "file:./" + LOCAL),
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

test("source graph rejects changed engines, consumer versions and unexpected old Zod", () => {
  for (const mutate of [
    (value) => (value.packages[COMPILER].version = "19.1.0-rc.3"),
    (value) => (value.packages["node_modules/zod"].version = "4.6.5"),
    (value) => (value.packages["node_modules/patched-zod"].version = "3.25.76"),
    (value) => (value.packages[LOCAL].version = "3.25.76"),
    (value) => (value.packages[LOCAL].dev = false),
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
      ["strictGenerate", ["install", "--package-lock-only"]],
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
  input.overrides["eslint-plugin-react-compiler@19.1.0-rc.2"] = FINAL_OVERRIDE
  assert.deepEqual(prepareStrictManifest(input), {
    name: "react-compiler-peer-proof",
    version: "1.0.0",
    private: true,
    packageManager: "npm@11.17.0",
    devDependencies: {
      eslint: "10.12.0",
      "eslint-plugin-react-compiler": "19.1.0-rc.2",
      "eslint-plugin-react-hooks": "7.1.1",
      "react-compiler-zod-compat": "file:./" + LOCAL,
      zod: "4.6.7",
    },
    overrides: {
      "eslint-plugin-react-compiler@19.1.0-rc.2": FINAL_OVERRIDE,
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
    },
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
    (value) => (value.packages[LOCAL].dependencies["patched-zod"] = "npm:zod@3.25.76"),
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
    ["react-compiler-zod-compat", "@university-ecosystem/react-compiler-zod-compat", "1.0.0"],
    ["zod-validation-error", "zod-validation-error", "4.0.2"],
    ["eslint-plugin-react-hooks", "eslint-plugin-react-hooks", "7.1.1"],
  ]) {
    withDirectory((root) => {
      installedFixture(root, "production")
      if (path === "react-compiler-zod-compat") {
        symlinkSync(join(root, LOCAL), join(root, "node_modules", path), "dir")
      } else {
        writePackage(root, "node_modules/" + path, { name, version, main: "index.cjs" })
      }
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
        rmSync(join(root, OLD_ENGINE))
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

function selectorToolFixture(root, attached = false) {
  const tool = join(root, "tool")
  const compiler = "eslint-plugin-react-compiler"
  const selector = compiler + "@19.1.0-rc.2"
  writePackage(root, "tool", { name: "npm", version: "11.17.0" })
  writePackage(
    tool,
    "node_modules/semver",
    { name: "semver", version: "7.8.4", main: "index.cjs" },
    "module.exports = { satisfies: () => true, intersects: () => false }\n"
  )
  writePackage(
    tool,
    "node_modules/@npmcli/arborist",
    { name: "@npmcli/arborist", version: "9.8.0", main: "index.cjs" }
  )
  mkdirSync(join(tool, "node_modules/@npmcli/arborist/lib"))
  writeFileSync(
    join(tool, "node_modules/@npmcli/arborist/lib/override-set.js"),
    [
      "const assert = require('node:assert/strict')",
      "module.exports = class OverrideSet {",
      "  constructor({ overrides }) {",
      "    assert.equal(overrides[" +
        JSON.stringify(selector) +
        "].zod, '$react-compiler-zod-compat')",
      "    this.rule = { key: " + JSON.stringify(selector) + " }",
      "  }",
      "  getEdgeRule(edge) {",
      "    assert.deepEqual(edge, " +
        JSON.stringify({ name: compiler, rawSpec: "^19.1.0-rc.2", spec: "^19.1.0-rc.2" }) +
        ")",
      "    return " + (attached ? "this.rule" : "this"),
      "  }",
      "  getNodeRule(node) {",
      "    assert.deepEqual(node, " +
        JSON.stringify({ name: compiler, version: "19.1.0-rc.2" }) +
        ")",
      "    return this.rule",
      "  }",
      "}",
      "",
    ].join("\n")
  )
  const candidate = manifest()
  candidate.overrides[selector] = FINAL_OVERRIDE
  return { tool, candidate }
}

test("selector diagnostic retains tool results without treating them as a graph proof", () => {
  for (const attached of [false, true]) {
    withDirectory((root) => {
      const { tool, candidate } = selectorToolFixture(root, attached)
      assert.deepEqual(inspectOverrideSelector(tool, candidate), {
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
        edgeRule: attached ? "eslint-plugin-react-compiler@19.1.0-rc.2" : null,
        nodeRule: "eslint-plugin-react-compiler@19.1.0-rc.2",
        candidateAccepted: false,
      })
    })
  }
})

test("selector diagnostic rejects changed tool versions and external resolution", () => {
  for (const mutation of ["npm", "semver", "arborist", "linked-semver", "nonboolean"]) {
    withDirectory((root) => {
      const { tool, candidate } = selectorToolFixture(root)
      if (mutation === "linked-semver") {
        writePackage(root, "outside", { name: "semver", version: "7.8.4" })
        rmSync(join(tool, "node_modules/semver"), { recursive: true })
        symlinkSync(join(root, "outside"), join(tool, "node_modules/semver"), "dir")
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
        }[mutation]
        writeFileSync(
          join(tool, relative, "package.json"),
          JSON.stringify({
            name: mutation === "arborist" ? "@npmcli/arborist" : mutation,
            version: "0.0.0",
          })
        )
      }
      assert.throws(() => inspectOverrideSelector(tool, candidate), { name: "AssertionError" })
    })
  }
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
