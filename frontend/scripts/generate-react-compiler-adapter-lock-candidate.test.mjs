import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import {
  adapterManifest,
  diagnoseLockScope,
  assertImmutableCheckout,
  assertInstalledGraph,
  assertStagedLockScope,
  assertStagedNpmCommand,
  assertStagedSourcePrerequisites,
  prepareStagedManifest,
  stagedNpmCommand,
} from "./generate-react-compiler-adapter-lock-candidate.mjs"

const local = "scripts/react-compiler-zod-compat"
const alias = "node_modules/patched-zod"
const transport = [
  "--registry=https://registry.npmjs.org/",
  "--fetch-retries=0",
  "--fetch-timeout=30000",
  "--ignore-scripts",
  "--min-release-age=7",
]
const expectedPackage = {
  name: "@university-ecosystem/react-compiler-zod-compat",
  version: "1.0.0",
  private: true,
  description: "The legacy schema API used only by the pinned React Compiler ESLint gate",
  main: "index.cjs",
  files: ["index.cjs", "LICENSE", "README.md"],
  license: "MIT",
  dependencies: { "patched-zod": "npm:zod@4.6.7" },
}
const release = {
  name: "zod",
  version: "4.6.7",
  license: "MIT",
  funding: "https://github.com/sponsors/colinhacks",
  dist: {
    tarball: "https://registry.npmjs.org/zod/-/zod-4.6.7.tgz",
    integrity: "sha512-test-fixture",
  },
}

function manifestFixture() {
  return {
    name: "frontend",
    version: "1.0.0",
    packageManager: "npm@11.17.0",
    dependencies: { valibot: "^1.3.1" },
    devDependencies: { "eslint-plugin-react-compiler": "^19.1.0-rc.2" },
    overrides: {
      undici: ">=8.10.2",
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
    },
    allowScripts: { "esbuild@0.28.2": true },
  }
}

function lockFixture() {
  const manifest = manifestFixture()
  return {
    name: "frontend",
    version: "1.0.0",
    lockfileVersion: 3,
    requires: true,
    packages: {
      "": {
        name: "frontend",
        version: "1.0.0",
        dependencies: structuredClone(manifest.dependencies),
        devDependencies: structuredClone(manifest.devDependencies),
      },
      "node_modules/body-parser": { version: "1.20.9", dev: true },
      "node_modules/undici": { version: "8.12.2", dev: true },
      "node_modules/zod": {
        version: "4.6.7",
        resolved: "https://registry.npmjs.org/zod/-/zod-4.6.7.tgz",
        integrity: "sha512-test-fixture",
        license: "MIT",
        funding: { url: "https://github.com/sponsors/colinhacks" },
      },
      "node_modules/chromium-bidi/node_modules/zod": { version: "3.25.76", dev: true },
      "node_modules/eslint-plugin-react-compiler": {
        version: "19.1.0-rc.2",
        dev: true,
        dependencies: { zod: "^3.22.4", "zod-validation-error": "^3.0.3" },
      },
      "node_modules/eslint-plugin-react-compiler/node_modules/zod": {
        version: "3.25.76",
        dev: true,
      },
      "node_modules/unrelated": { version: "1.2.3", optional: true },
    },
  }
}

// This synthetic expected npm-v3 shape is independent of the implementation.
// The hosted generator must reject actual npm output that differs from it.
function candidateFixture() {
  const candidate = lockFixture()
  candidate.packages[""].devDependencies["react-compiler-zod-compat"] =
    "file:./scripts/react-compiler-zod-compat"
  candidate.packages["node_modules/react-compiler-zod-compat"] = {
    resolved: "scripts/react-compiler-zod-compat",
    link: true,
  }
  candidate.packages[local] = {
    name: "@university-ecosystem/react-compiler-zod-compat",
    version: "1.0.0",
    dev: true,
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  }
  candidate.packages[alias] = {
    name: "zod",
    version: "4.6.7",
    resolved: "https://registry.npmjs.org/zod/-/zod-4.6.7.tgz",
    integrity: "sha512-test-fixture",
    dev: true,
    license: "MIT",
    funding: { url: "https://github.com/sponsors/colinhacks" },
  }
  return candidate
}

test("staged manifest adds only the local dev adapter without mutating the source", () => {
  const manifest = manifestFixture()
  const before = JSON.stringify(manifest)
  assert.deepEqual(prepareStagedManifest(manifest), {
    ...manifest,
    devDependencies: {
      ...manifest.devDependencies,
      "react-compiler-zod-compat": "file:./scripts/react-compiler-zod-compat",
    },
  })
  assert.equal(JSON.stringify(manifest), before)
})

test("local package is private, script-free and pins only the patched engine", () => {
  assert.deepEqual(adapterManifest(), expectedPackage)
})

test("staging rejects existing direct Zod, engine alias and adapter declarations", () => {
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    for (const name of ["zod", "patched-zod", "react-compiler-zod-compat"]) {
      const manifest = manifestFixture()
      manifest[section] = { ...manifest[section], [name]: "unapproved" }
      assert.throws(() => prepareStagedManifest(manifest))
    }
  }
})

test("staging rejects premature consumer overrides or a different compiler", () => {
  for (const name of [
    "zod",
    "zod@4.6.7",
    "eslint-plugin-react-compiler",
    "eslint-plugin-react-compiler@19.1.0-rc.2",
  ]) {
    const manifest = manifestFixture()
    manifest.overrides[name] = { zod: "4.6.7" }
    assert.throws(() => prepareStagedManifest(manifest))
  }
  for (const mutate of [
    (value) => {
      value.devDependencies["eslint-plugin-react-compiler"] = "19.1.0-rc.3"
    },
    (value) => {
      value.packageManager = "npm@11.19.0"
    },
  ]) {
    const manifest = manifestFixture()
    mutate(manifest)
    assert.throws(() => prepareStagedManifest(manifest))
  }
})

test("source prerequisites require patched root and preserve both old consumer nodes", () => {
  assertStagedSourcePrerequisites(lockFixture())
  for (const [path, field, value] of [
    ["node_modules/body-parser", "version", "1.20.8"],
    ["node_modules/body-parser", "dev", false],
    ["node_modules/undici", "version", "8.10.2"],
    ["node_modules/undici", "dev", false],
    ["node_modules/zod", "version", "4.6.5"],
    ["node_modules/zod", "dev", true],
    ["node_modules/chromium-bidi/node_modules/zod", "version", "4.6.7"],
    ["node_modules/chromium-bidi/node_modules/zod", "dev", false],
    ["node_modules/eslint-plugin-react-compiler/node_modules/zod", "version", "4.6.7"],
    ["node_modules/eslint-plugin-react-compiler", "version", "19.1.0-rc.3"],
    ["node_modules/eslint-plugin-react-compiler", "dev", false],
    ["node_modules/eslint-plugin-react-compiler/node_modules/zod", "dev", false],
  ]) {
    const lock = lockFixture()
    lock.packages[path][field] = value
    assert.throws(() => assertStagedSourcePrerequisites(lock))
  }
  for (const path of [
    "node_modules/eslint-plugin-react-compiler",
    "node_modules/eslint-plugin-react-compiler/node_modules/zod",
  ]) {
    const lock = lockFixture()
    delete lock.packages[path].dev
    assert.throws(() => assertStagedSourcePrerequisites(lock))
  }
  for (const key of [
    "node_modules/react-compiler-zod-compat",
    local,
    alias,
    "node_modules/other/node_modules/zod",
    local + "/node_modules/patched-zod",
  ]) {
    const lock = lockFixture()
    lock.packages[key] = { version: "unapproved" }
    assert.throws(() => assertStagedSourcePrerequisites(lock))
  }
})

test("whole-lock scope accepts only the staged three-node dev graph and preserves input", () => {
  const original = lockFixture()
  const before = JSON.stringify(original)
  assertStagedLockScope(original, candidateFixture(), release)
  assert.equal(JSON.stringify(original), before)
})

test("whole-lock scope rejects unobserved nested or duplicate alias placements", () => {
  for (const keepRoot of [false, true]) {
    const candidate = candidateFixture()
    const record = structuredClone(candidate.packages[alias])
    candidate.packages[local + "/node_modules/patched-zod"] = record
    if (!keepRoot) delete candidate.packages[alias]
    assert.throws(() => assertStagedLockScope(lockFixture(), candidate, release))
  }
})

test("whole-lock scope rejects changed, removed and unexpected records", () => {
  for (const path of Object.keys(lockFixture().packages)) {
    const changed = candidateFixture()
    changed.packages[path].unexpected = true
    assert.throws(() => assertStagedLockScope(lockFixture(), changed, release))
    const missing = candidateFixture()
    delete missing.packages[path]
    assert.throws(() => assertStagedLockScope(lockFixture(), missing, release))
  }
  const candidate = candidateFixture()
  candidate.packages["node_modules/new-unrelated"] = { version: "1.0.0", dev: true }
  assert.throws(() => assertStagedLockScope(lockFixture(), candidate, release))
})

test("whole-lock scope rejects existing-value and top-level metadata changes", () => {
  for (const [path, field, value] of [
    ["node_modules/zod", "version", "4.6.8"],
    ["node_modules/zod", "integrity", "different"],
    ["node_modules/chromium-bidi/node_modules/zod", "version", "4.6.7"],
    ["node_modules/eslint-plugin-react-compiler/node_modules/zod", "version", "4.6.7"],
    ["node_modules/body-parser", "version", "1.20.8"],
    ["node_modules/undici", "version", "8.10.2"],
    ["node_modules/eslint-plugin-react-compiler", "version", "19.1.0-rc.3"],
    ["node_modules/eslint-plugin-react-compiler", "dependencies", { zod: "4.6.7" }],
    ["node_modules/unrelated", "version", "9.9.9"],
    ["", "dependencies", { valibot: "^2.0.0" }],
  ]) {
    const candidate = candidateFixture()
    candidate.packages[path][field] = value
    assert.throws(() => assertStagedLockScope(lockFixture(), candidate, release))
  }
  for (const [field, value] of [
    ["name", "changed"],
    ["version", "2.0.0"],
    ["lockfileVersion", 2],
    ["requires", false],
    ["unexpected", true],
  ]) {
    const candidate = candidateFixture()
    candidate[field] = value
    assert.throws(() => assertStagedLockScope(lockFixture(), candidate, release))
  }
})

test("whole-lock scope rejects masquerading, runtime placement and wider metadata", () => {
  for (const [path, field, value] of [
    ["node_modules/react-compiler-zod-compat", "resolved", "../elsewhere"],
    ["node_modules/react-compiler-zod-compat", "link", false],
    [local, "name", "zod"],
    [local, "dev", false],
    [local, "hasInstallScript", true],
    [local, "dependencies", { "patched-zod": "npm:zod@4.6.8" }],
    [alias, "name", "patched-zod"],
    [alias, "version", "3.25.76"],
    [alias, "resolved", "https://untrusted.test/zod.tgz"],
    [alias, "integrity", "wrong"],
    [alias, "dev", false],
    [alias, "hasInstallScript", true],
  ]) {
    const candidate = candidateFixture()
    candidate.packages[path][field] = value
    assert.throws(() => assertStagedLockScope(lockFixture(), candidate, release))
  }
  for (const path of ["node_modules/react-compiler-zod-compat", local, alias]) {
    const candidate = candidateFixture()
    delete candidate.packages[path]
    assert.throws(() => assertStagedLockScope(lockFixture(), candidate, release))
  }
})

test("whole-lock scope binds the alias to the verified unchanged root engine", () => {
  for (const mutate of [
    (value) => {
      value.name = "other"
    },
    (value) => {
      value.version = "4.6.8"
    },
    (value) => {
      value.dist.integrity = "different"
    },
    (value) => {
      value.dist.tarball = "https://example.test/zod.tgz"
    },
    (value) => {
      value.license = "other"
    },
    (value) => {
      value.dependencies = { surprise: "1.0.0" }
    },
    (value) => {
      value.engines = { node: "unapproved" }
    },
  ]) {
    const changed = structuredClone(release)
    mutate(changed)
    assert.throws(() => assertStagedLockScope(lockFixture(), candidateFixture(), changed))
  }
})

test("npm operations permit only generation and explicit dev or production installs", () => {
  assert.deepEqual(stagedNpmCommand("generateLock"), [
    "install",
    "--package-lock-only",
    "--no-audit",
    "--no-fund",
    ...transport,
  ])
  assert.deepEqual(stagedNpmCommand("fullGraph"), [
    "ci",
    "--include=dev",
    "--no-audit",
    "--no-fund",
    ...transport,
  ])
  assert.deepEqual(stagedNpmCommand("productionGraph"), [
    "ci",
    "--omit=dev",
    "--no-audit",
    "--no-fund",
    ...transport,
  ])
  for (const operation of ["generateLock", "fullGraph", "productionGraph"]) {
    assert(Object.isFrozen(stagedNpmCommand(operation)))
  }
  assert.throws(() => stagedNpmCommand("auditFix"))
})

test("npm argv guard rejects retry, lifecycle, registry and cooldown bypasses", () => {
  const operations = [
    ["generateLock", ["install", "--package-lock-only"]],
    ["fullGraph", ["ci", "--include=dev"]],
    ["productionGraph", ["ci", "--omit=dev"]],
  ]
  for (const [operation, command] of operations) {
    const args = [...command, "--no-audit", "--no-fund", ...transport]
    assertStagedNpmCommand(operation, args)
    for (const extra of [
      "--ignore-scripts=false",
      "--min-release-age=0",
      "--min-release-age-exclude=zod",
      "--fetch-retries=1",
      "--registry=https://example.test",
      "zod",
      "--force",
    ]) {
      assert.throws(() => assertStagedNpmCommand(operation, [...args, extra]))
    }
  }
})

test("immutable preflight rejects wrong, dirty or installed source", () => {
  const state = {
    expectedSha: "a".repeat(40),
    head: "a".repeat(40),
    status: "",
    node: "v24.21.0",
    repository: "egorribun/university_ecosystem",
    hasNodeModules: false,
  }
  assertImmutableCheckout(state)
  for (const [field, value] of [
    ["expectedSha", "egorribun"],
    ["head", "b".repeat(40)],
    ["status", "?? untracked.txt\n"],
    ["status", " M frontend/package.json\n"],
    ["node", "v24.20.0"],
    ["repository", "someone/else"],
    ["hasNodeModules", true],
  ]) {
    assert.throws(() => assertImmutableCheckout({ ...state, [field]: value }))
  }
})

function installedFixture() {
  const root = mkdtempSync(join(tmpdir(), "staged-adapter-graph-test-"))
  const put = (path, value) => {
    const target = join(root, path)
    mkdirSync(dirname(target), { recursive: true })
    writeFileSync(target, typeof value === "string" ? value : JSON.stringify(value))
  }
  put(local + "/package.json", expectedPackage)
  put("node_modules/zod/package.json", { name: "zod", version: "4.6.7" })
  put("node_modules/eslint-plugin-react-compiler/package.json", {
    name: "eslint-plugin-react-compiler",
    version: "19.1.0-rc.2",
  })
  put("node_modules/eslint-plugin-react-compiler/node_modules/zod/package.json", {
    name: "zod",
    version: "3.25.76",
  })
  put(alias + "/package.json", { name: "zod", version: "4.6.7" })
  for (const path of [
    local + "/index.cjs",
    alias + "/index.js",
    "node_modules/zod/index.js",
    "node_modules/eslint-plugin-react-compiler/index.js",
    "node_modules/eslint-plugin-react-compiler/node_modules/zod/index.js",
  ]) {
    put(path, "throw new Error('Library code must not execute')")
  }
  symlinkSync(join(root, local), join(root, "node_modules/react-compiler-zod-compat"), "dir")
  return { root, put }
}

test("full graph resolves the adapter and alias without executing library code", () => {
  const { root, put } = installedFixture()
  try {
    assertInstalledGraph(root, "full")
    for (const [path, value] of [
      [alias + "/package.json", { name: "patched-zod", version: "4.6.7" }],
      [alias + "/package.json", { name: "zod", version: "3.25.76" }],
      [
        "node_modules/eslint-plugin-react-compiler/node_modules/zod/package.json",
        { name: "zod", version: "4.6.7" },
      ],
    ]) {
      const original = path.startsWith(alias)
        ? { name: "zod", version: "4.6.7" }
        : { name: "zod", version: "3.25.76" }
      put(path, value)
      assert.throws(() => assertInstalledGraph(root, "full"))
      put(path, original)
    }
    rmSync(join(root, "node_modules/react-compiler-zod-compat"))
    symlinkSync(
      join(root, "node_modules/zod"),
      join(root, "node_modules/react-compiler-zod-compat"),
      "dir"
    )
    assert.throws(() => assertInstalledGraph(root, "full"))
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("production graph rejects the adapter, compiler and patched alias", () => {
  const { root, put } = installedFixture()
  try {
    assert.throws(() => assertInstalledGraph(root, "production"))
    rmSync(join(root, "node_modules/react-compiler-zod-compat"))
    rmSync(join(root, "node_modules/eslint-plugin-react-compiler"), { recursive: true })
    rmSync(join(root, alias), { recursive: true })
    assertInstalledGraph(root, "production")
    for (const path of [
      "node_modules/react-compiler-zod-compat",
      "node_modules/eslint-plugin-react-compiler",
      alias,
      local + "/node_modules/patched-zod",
    ]) {
      put(path + "/package.json", { name: "unexpected", version: "1.0.0" })
      assert.throws(() => assertInstalledGraph(root, "production"))
      rmSync(join(root, path), { recursive: true })
    }
    assert.throws(() => assertInstalledGraph(root, "unknown"))
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("scope diagnostics report only changed paths and field names, never lock values", () => {
  const original = {
    name: "frontend",
    packages: {
      "": { devDependencies: { a: "1" } },
      "node_modules/old": { version: "1" },
      "node_modules/stays": { version: "1", integrity: "old" },
    },
  }
  const candidate = {
    name: "changed",
    packages: {
      "": { devDependencies: { a: "1", adapter: "file:./local" } },
      "node_modules/new": { version: "2" },
      "node_modules/stays": { version: "2", integrity: "never-print-this-value" },
    },
  }
  assert.deepEqual(diagnoseLockScope(original, candidate), {
    packageChanges: [
      { path: "", kind: "changed", fields: ["devDependencies"] },
      { path: "node_modules/new", kind: "added", fields: [] },
      { path: "node_modules/old", kind: "removed", fields: [] },
      { path: "node_modules/stays", kind: "changed", fields: ["integrity", "version"] },
    ],
    topLevelFields: ["name"],
    omitted: 0,
  })
})

test("scope diagnostics bound output and suppress unsafe paths or field names", () => {
  const original = { packages: {} }
  const candidate = { packages: {} }
  for (let index = 0; index < 20; index += 1) {
    candidate.packages["node_modules/package-" + String(index).padStart(2, "0")] = {
      version: "not-a-log-value",
    }
  }
  const bounded = diagnoseLockScope(original, candidate)
  assert.equal(bounded?.packageChanges.length, 16)
  assert.equal(bounded?.omitted, 4)
  const unsafe = {
    packages: {
      "node_modules/unsafe\nprivate": { version: "do-not-print" },
      "node_modules/safe": { version: "2", "unsafe\nfield": "do-not-print" },
    },
  }
  assert.deepEqual(
    diagnoseLockScope({ packages: { "node_modules/safe": { version: "1" } } }, unsafe),
    {
      packageChanges: [{ path: "node_modules/safe", kind: "changed", fields: ["version"] }],
      topLevelFields: [],
      omitted: 2,
    }
  )
  assert.deepEqual(diagnoseLockScope(null, unsafe), { unavailable: true })
})

test("import is inert and direct execution fails closed before network", () => {
  const url = new URL("./generate-react-compiler-adapter-lock-candidate.mjs", import.meta.url)
  const env = { GITHUB_WORKSPACE: "/staged-adapter-generator-test-does-not-exist" }
  const direct = spawnSync(process.execPath, [fileURLToPath(url)], {
    env,
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 4096,
  })
  assert.equal(direct.status, 1)
  assert.equal(direct.stdout, "")
  assert.equal(direct.stderr, "Staged adapter candidate rejected at stage: preflight\n")
  const imported = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", "import " + JSON.stringify(url.href)],
    { env, encoding: "utf8", timeout: 10000, maxBuffer: 4096 }
  )
  assert.equal(imported.status, 0)
  assert.equal(imported.stdout, "")
  assert.equal(imported.stderr, "")
})
