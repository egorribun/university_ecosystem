import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { spawnSync } from "node:child_process"
import test from "node:test"
import { fileURLToPath } from "node:url"
import {
  assertNpmCommand,
  assertSourceLockPrerequisites,
  assertZodLockScope,
  npmCommand,
  prepareTemporaryManifest,
  validateRegistryMetadata,
  verifyArchiveBytes,
} from "./generate-zod-root-lock-candidate.mjs"

const now = Date.parse("2026-10-24T00:00:00.000Z")
const age = 7 * 86400000
const sourceGitHead = "a".repeat(40)
const archive = Buffer.from("Synthetic archive bytes for isolated Zod guard tests")
const nested = [
  "node_modules/chromium-bidi/node_modules/zod",
  "node_modules/eslint-plugin-react-compiler/node_modules/zod",
]
const transport = [
  "--registry=https://registry.npmjs.org/",
  "--fetch-retries=0",
  "--fetch-timeout=30000",
  "--ignore-scripts",
  "--min-release-age=7",
]
const paths = { prefix: "/tmp/zod-test/tool", archive: "/tmp/zod-test/npm-11.17.0.tgz" }

function metadata(name = "zod", published = new Date(now - age).toISOString()) {
  const version = name === "zod" ? "4.6.7" : "11.17.0"
  return {
    name,
    version,
    license: "MIT",
    funding: "https://github.com/sponsors/colinhacks",
    repository: { type: "git", url: "git+https://github.com/colinhacks/zod.git" },
    gitHead: sourceGitHead,
    scripts: { build: "not executed", prepublishOnly: "not executed" },
    time: { [version]: published },
    dist: {
      tarball: "https://registry.npmjs.org/" + name + "/-/" + name + "-" + version + ".tgz",
      integrity: "sha512-" + createHash("sha512").update(archive).digest("base64"),
      shasum: createHash("sha1").update(archive).digest("hex"),
    },
  }
}

function lockFixture() {
  return {
    name: "frontend",
    lockfileVersion: 3,
    packages: {
      "": { name: "frontend", devDependencies: { example: "1.0.0" } },
      "node_modules/body-parser": { version: "1.20.9", dev: true },
      "node_modules/undici": { version: "8.12.2", dev: true },
      "node_modules/zod": {
        version: "4.6.5",
        resolved: "https://registry.npmjs.org/zod/-/zod-4.6.5.tgz",
        integrity: "old-fixture-integrity",
        license: "MIT",
        funding: { url: "https://github.com/sponsors/colinhacks" },
      },
      "node_modules/chromium-bidi/node_modules/zod": {
        version: "3.25.76",
        resolved: "https://registry.npmjs.org/zod/-/zod-3.25.76.tgz",
        integrity: "nested-fixture-integrity",
        dev: true,
      },
      "node_modules/eslint-plugin-react-compiler/node_modules/zod": {
        version: "3.25.76",
        resolved: "https://registry.npmjs.org/zod/-/zod-3.25.76.tgz",
        integrity: "nested-fixture-integrity",
        dev: true,
      },
    },
  }
}

function candidateFixture(original, release) {
  const candidate = structuredClone(original)
  Object.assign(candidate.packages["node_modules/zod"], {
    version: release.version,
    resolved: release.dist.tarball,
    integrity: release.dist.integrity,
  })
  return candidate
}

test("targeted npm operations prohibit broad update and mutable transport arguments", () => {
  assert.deepEqual(npmCommand("targetUpdate"), [
    "update",
    "zod",
    "--package-lock-only",
    "--no-audit",
    "--no-fund",
    ...transport,
  ])
  assert.deepEqual(npmCommand("targetMetadata"), ["view", "zod@4.6.7", "--json", ...transport])
  assert.deepEqual(npmCommand("toolMetadata"), ["view", "npm@11.17.0", "--json", ...transport])
  assert.deepEqual(npmCommand("version"), ["--version"])
  for (const operation of ["toolInstall", "targetUpdate", "targetMetadata", "toolMetadata"]) {
    const args = npmCommand(operation, paths)
    assert(Object.isFrozen(args))
    for (const flag of transport) assert.equal(args.filter((arg) => arg === flag).length, 1)
    assertNpmCommand(operation, args, paths)
    assert.throws(() => args.push("--fetch-retries=1"), TypeError)
  }
  assert.throws(() => npmCommand("auditFix"))
  assert.throws(() => npmCommand("toolInstall", { ...paths, prefix: "relative/tool" }))
  assert.throws(() =>
    npmCommand("toolInstall", { ...paths, archive: "/tmp/other/npm-11.17.0.tgz" })
  )
  assert.throws(() => npmCommand("toolInstall", { ...paths, archive: "/tmp/zod-test/other.tgz" }))
})

test("argv guard rejects retry aliases, bypass flags and additional update targets", () => {
  const args = ["update", "zod", "--package-lock-only", "--no-audit", "--no-fund", ...transport]
  for (const extra of [
    "--fetch-retries=1",
    "--fetch-retries=-1",
    "--fetch-retries=no",
    "--fetch-retries=0",
    "--fetchRetries=1",
    "--fetch-retries",
    "--ignore-scripts=false",
    "--min-release-age=0",
    "--min-release-age-exclude=zod",
    "--registry=https://example.test/",
    "--fetch-timeout=0",
    "body-parser",
  ]) {
    assert.throws(() => assertNpmCommand("targetUpdate", [...args, extra]))
  }
  assert.throws(() =>
    assertNpmCommand(
      "targetUpdate",
      args.filter((arg) => arg !== "--fetch-retries=0")
    )
  )
})

test("registry metadata enforces seven full days for Zod and pinned npm", () => {
  for (const name of ["zod", "npm"]) {
    const release = metadata(name)
    for (const published of [
      new Date(now - age + 1).toISOString(),
      new Date(now + 1).toISOString(),
      "not-a-date",
    ]) {
      assert.throws(() =>
        validateRegistryMetadata(
          metadata(name, published),
          name,
          release.version,
          now,
          sourceGitHead
        )
      )
    }
    const missing = metadata(name)
    delete missing.time[missing.version]
    assert.throws(() =>
      validateRegistryMetadata(missing, name, missing.version, now, sourceGitHead)
    )
    assert.equal(
      validateRegistryMetadata(release, name, release.version, now, sourceGitHead).timestamp,
      now - age
    )
  }
})

test("registry metadata rejects alternate artifacts, source identity and install lifecycle scripts", () => {
  const mutations = [
    (value) => {
      value.name = "other"
    },
    (value) => {
      value.version = "4.6.8"
    },
    (value) => {
      value.deprecated = "Do not use"
    },
    (value) => {
      value.dist.tarball = "https://example.test/zod-4.6.7.tgz"
    },
    (value) => {
      value.dist.integrity = "sha512-invalid"
    },
    (value) => {
      value.dist.shasum = "invalid"
    },
    (value) => {
      value.repository.url = "git+https://github.com/example/zod.git"
    },
    (value) => {
      value.repository.type = "svn"
    },
    (value) => {
      value.gitHead = "0".repeat(40)
    },
    (value) => {
      value.scripts.prepare = "unexpected command"
    },
    ...["preinstall", "install", "postinstall"].map((phase) => (value) => {
      value.scripts[phase] = "unexpected command"
    }),
  ]
  for (const mutate of mutations) {
    const release = metadata()
    mutate(release)
    assert.throws(() => validateRegistryMetadata(release, "zod", "4.6.7", now, sourceGitHead))
  }
  assert.throws(() => validateRegistryMetadata(metadata(), "zod", "4.6.8", now, sourceGitHead))
})

test("archive validation requires independent SHA-512 and SHA-1 matches and bounded nonempty bytes", () => {
  const release = metadata()
  for (const field of ["integrity", "shasum"]) {
    const changed = structuredClone(release)
    changed.dist[field] = "mismatched-test-digest"
    assert.throws(() => verifyArchiveBytes(changed, archive, 1024))
  }
  assert.throws(() => verifyArchiveBytes(release, Buffer.alloc(0), 1024))
  assert.throws(() => verifyArchiveBytes(release, archive, archive.length - 1))
  assert.throws(() => verifyArchiveBytes(release, archive, 16 * 1024 * 1024 + 1))
  assert.throws(() => verifyArchiveBytes(release, Buffer.from("altered"), 1024))
  verifyArchiveBytes(release, archive, archive.length)
})

test("whole-lock guard preserves both nested Zod consumers and permits only three root artifact fields", () => {
  const original = lockFixture()
  const before = JSON.stringify(original)
  const release = metadata()
  const mutations = [
    ...nested.map((path) => (value) => {
      value.packages[path].version = "4.6.7"
    }),
    ...nested.map((path) => (value) => {
      value.packages[path].integrity = "changed"
    }),
    (value) => {
      value.lockfileVersion = 2
    },
    (value) => {
      value.packages[""].name = "changed"
    },
    (value) => {
      value.packages["node_modules/body-parser"].version = "1.20.8"
    },
    (value) => {
      value.packages["node_modules/undici"].version = "8.11.0"
    },
    (value) => {
      value.packages["node_modules/unrelated"] = { version: "1.0.0" }
    },
    (value) => {
      value.packages["node_modules/zod"].dev = true
    },
    (value) => {
      value.packages["node_modules/zod"].license = "changed"
    },
    (value) => {
      value.packages["node_modules/zod"].funding.url = "changed"
    },
    (value) => {
      value.packages["node_modules/zod"].dependencies = { surprise: "1.0.0" }
    },
    (value) => {
      value.packages["node_modules/zod"].version = "4.6.8"
    },
    (value) => {
      value.packages["node_modules/zod"].integrity = "wrong"
    },
  ]
  for (const mutate of mutations) {
    const candidate = candidateFixture(original, release)
    mutate(candidate)
    assert.throws(() => assertZodLockScope(original, candidate, release))
  }
  for (const field of ["dependencies", "engines", "license", "funding"]) {
    const changed = structuredClone(release)
    changed[field] = field === "license" || field === "funding" ? "changed" : { surprise: "1.0.0" }
    assert.throws(() => assertZodLockScope(original, candidateFixture(original, release), changed))
  }
  assertZodLockScope(original, candidateFixture(original, release), release)
  assert.equal(JSON.stringify(original), before)
})

test("source prerequisites preserve prior fixes and the exact three existing Zod records", () => {
  const lock = lockFixture()
  for (const [path, field, value] of [
    ["node_modules/body-parser", "version", "1.20.8"],
    ["node_modules/body-parser", "dev", false],
    ["node_modules/undici", "version", "8.11.0"],
    ["node_modules/undici", "dev", false],
    ["node_modules/zod", "version", "4.6.7"],
    ["node_modules/zod", "dev", true],
    ...nested.map((path) => [path, "version", "4.6.7"]),
    ...nested.map((path) => [path, "dev", false]),
  ]) {
    const changed = structuredClone(lock)
    changed.packages[path][field] = value
    assert.throws(() => assertSourceLockPrerequisites(changed))
  }
  const extra = structuredClone(lock)
  extra.packages["node_modules/other/node_modules/zod"] = { version: "3.25.76" }
  assert.throws(() => assertSourceLockPrerequisites(extra))
  assertSourceLockPrerequisites(lock)
})

test("temporary override targets existing Zod 4.6.5 without adding an application dependency", () => {
  const manifest = {
    dependencies: { valibot: "^1.3.0" },
    devDependencies: { knip: "6.2.0" },
    overrides: {
      undici: ">=8.10.2",
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
    },
  }
  const before = JSON.stringify(manifest)
  assert.deepEqual(prepareTemporaryManifest(manifest), {
    ...manifest,
    overrides: { ...manifest.overrides, "zod@4.6.5": "4.6.7" },
  })
  assert.equal(JSON.stringify(manifest), before)
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    const changed = structuredClone(manifest)
    changed[section] = { ...changed[section], zod: "^4.6.5" }
    assert.throws(() => prepareTemporaryManifest(changed))
  }
  for (const key of ["zod", "zod@4.6.5", "zod@^3"]) {
    const changed = structuredClone(manifest)
    changed.overrides[key] = "4.6.7"
    assert.throws(() => prepareTemporaryManifest(changed))
  }
})

test("module import is inert while direct execution fails closed before network on absent workspace", () => {
  const url = new URL("./generate-zod-root-lock-candidate.mjs", import.meta.url)
  const env = { GITHUB_WORKSPACE: "/zod-generator-test-does-not-exist" }
  const direct = spawnSync(process.execPath, [fileURLToPath(url)], {
    env,
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 4096,
  })
  assert.equal(direct.status, 1)
  assert.equal(direct.stdout, "")
  assert.equal(direct.stderr, "Zod candidate rejected at stage: preflight\n")
  const imported = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", "import " + JSON.stringify(url.href)],
    { env, encoding: "utf8", timeout: 10000, maxBuffer: 4096 }
  )
  assert.equal(imported.status, 0)
  assert.equal(imported.stdout, "")
  assert.equal(imported.stderr, "")
})
