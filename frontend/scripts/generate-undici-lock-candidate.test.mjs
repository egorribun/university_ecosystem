import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import { spawnSync } from "node:child_process"
import test from "node:test"
import { fileURLToPath } from "node:url"
import {
  assertSourceLockPrerequisites,
  assertNpmCommand,
  assertUndiciLockScope,
  NPM_TRANSPORT_ARGS,
  npmCommand,
  validateRegistryMetadata,
  verifyArchiveBytes,
} from "./generate-undici-lock-candidate.mjs"

const now = Date.parse("2026-10-24T00:00:00.000Z")
const age = 7 * 86400000
const archive = Buffer.from("Synthetic archive bytes for isolated guard tests")
const paths = { prefix: "/tmp/undici-test/tool", archive: "/tmp/undici-test/npm-11.17.0.tgz" }
const generatorUrl = new URL("./generate-undici-lock-candidate.mjs", import.meta.url)

function metadata(name = "undici", published = new Date(now - age).toISOString()) {
  const version = name === "undici" ? "8.12.2" : "11.17.0"
  return {
    name,
    version,
    license: "MIT",
    engines: { node: ">=22.19.0" },
    scripts: { prepare: "husky && node ./scripts/platform-shell.js" },
    time: { [version]: published },
    dist: {
      tarball: `https://registry.npmjs.org/${name}/-/${name}-${version}.tgz`,
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
      "node_modules/undici": {
        version: "8.11.0",
        resolved: "https://registry.npmjs.org/undici/-/undici-8.11.0.tgz",
        integrity: "old-fixture-integrity",
        dev: true,
        license: "MIT",
        engines: { node: ">=22.19.0" },
      },
      "node_modules/body-parser": { version: "1.20.9", dev: true },
    },
  }
}

function candidateFixture(original, release) {
  const candidate = structuredClone(original)
  Object.assign(candidate.packages["node_modules/undici"], {
    version: release.version,
    resolved: release.dist.tarball,
    integrity: release.dist.integrity,
  })
  return candidate
}

test("network npm argv are frozen, scripts-disabled and bounded with zero retries", () => {
  assert(Object.isFrozen(NPM_TRANSPORT_ARGS))
  assert.deepEqual(NPM_TRANSPORT_ARGS, [
    "--registry=https://registry.npmjs.org/",
    "--fetch-retries=0",
    "--fetch-timeout=30000",
    "--ignore-scripts",
    "--min-release-age=7",
  ])
  for (const operation of ["toolMetadata", "targetMetadata", "toolInstall", "targetUpdate"]) {
    const args = npmCommand(operation, paths)
    assert(Object.isFrozen(args))
    assertNpmCommand(operation, args, paths)
    for (const flag of NPM_TRANSPORT_ARGS) {
      assert.equal(args.filter((arg) => arg === flag).length, 1)
    }
    assert.throws(() => args.push("--fetch-retries=1"), TypeError)
  }
  assert.deepEqual(npmCommand("version"), ["--version"])
  assert.deepEqual(npmCommand("targetMetadata").slice(0, 3), ["view", "undici@8.12.2", "--json"])
  assert.deepEqual(npmCommand("toolMetadata").slice(0, 3), ["view", "npm@11.17.0", "--json"])
  assert.deepEqual(npmCommand("targetUpdate").slice(0, 5), [
    "update",
    "undici",
    "--package-lock-only",
    "--no-audit",
    "--no-fund",
  ])
})

test("argv guard rejects positive, missing, malformed, duplicate and aliased retries", () => {
  const args = [...npmCommand("targetUpdate")]
  for (const replacement of ["--fetch-retries=1", "--fetch-retries=-1", "--fetch-retries=no"]) {
    assert.throws(() =>
      assertNpmCommand(
        "targetUpdate",
        args.map((arg) => (arg === "--fetch-retries=0" ? replacement : arg))
      )
    )
  }
  assert.throws(() =>
    assertNpmCommand(
      "targetUpdate",
      args.filter((arg) => arg !== "--fetch-retries=0")
    )
  )
  for (const extra of [
    "--fetch-retries=0",
    "--fetchRetries=1",
    "--fetch-retries",
    "--ignore-scripts=false",
    "--min-release-age=0",
    "--min-release-age-exclude=undici",
    "--registry=https://example.test/",
    "--fetch-timeout=0",
    "body-parser",
  ]) {
    assert.throws(() => assertNpmCommand("targetUpdate", [...args, extra]))
  }
  assert.throws(() => npmCommand("auditFix"))
  assert.throws(() => npmCommand("toolInstall", { ...paths, prefix: "relative/tool" }))
  assert.throws(() =>
    npmCommand("toolInstall", { ...paths, archive: "/tmp/other/npm-11.17.0.tgz" })
  )
  assert.throws(() =>
    npmCommand("toolInstall", { ...paths, archive: "/tmp/undici-test/other.tgz" })
  )
})

test("metadata admits the exact seven-day boundary but no younger or missing publication", () => {
  for (const name of ["undici", "npm"]) {
    const release = metadata(name)
    assert.equal(validateRegistryMetadata(release, name, release.version, now).timestamp, now - age)
    for (const published of [
      new Date(now - age + 1).toISOString(),
      new Date(now + 1).toISOString(),
      "not-a-date",
    ]) {
      assert.throws(() =>
        validateRegistryMetadata(metadata(name, published), name, release.version, now)
      )
    }
    const missing = metadata(name)
    delete missing.time[missing.version]
    assert.throws(() => validateRegistryMetadata(missing, name, missing.version, now))
  }
})

test("metadata rejects alternate identity, registry, hashes and lifecycle scripts", () => {
  const mutations = [
    (value) => {
      value.name = "other"
    },
    (value) => {
      value.version = "8.12.3"
    },
    (value) => {
      value.deprecated = "Do not use"
    },
    (value) => {
      value.dist.tarball = "https://example.test/undici-8.12.2.tgz"
    },
    (value) => {
      value.dist.integrity = "sha512-invalid"
    },
    (value) => {
      value.dist.shasum = "invalid"
    },
    (value) => {
      value.scripts.prepare = "unexpected command"
    },
    ...["preinstall", "install", "postinstall"].map((phase) => (value) => {
      value.scripts[phase] = "unexpected command"
    }),
  ]
  for (const mutate of mutations) {
    const value = metadata()
    mutate(value)
    assert.throws(() => validateRegistryMetadata(value, "undici", "8.12.2", now))
  }
  assert.throws(() => validateRegistryMetadata(metadata(), "undici", "8.12.3", now))
})

test("archive validation requires both hashes and a positive bounded byte count", () => {
  const release = metadata()
  verifyArchiveBytes(release, archive, archive.length)
  assert.throws(() => verifyArchiveBytes(release, Buffer.alloc(0), 1024))
  assert.throws(() => verifyArchiveBytes(release, archive, archive.length - 1))
  assert.throws(() => verifyArchiveBytes(release, archive, 16 * 1024 * 1024 + 1))
  for (const field of ["integrity", "shasum"]) {
    const altered = structuredClone(release)
    altered.dist[field] = "mismatched-test-digest"
    assert.throws(() => verifyArchiveBytes(altered, archive, 1024))
  }
  assert.throws(() => verifyArchiveBytes(release, Buffer.from("altered"), 1024))
})

test("whole-lock guard permits exactly three Undici artifact fields without mutating input", () => {
  const original = lockFixture()
  const before = JSON.stringify(original)
  const release = metadata()
  assertUndiciLockScope(original, candidateFixture(original, release), release)
  assert.equal(JSON.stringify(original), before)
})

test("whole-lock guard rejects unrelated graph and Undici metadata churn", () => {
  const original = lockFixture()
  const release = metadata()
  const mutations = [
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
      delete value.packages["node_modules/body-parser"]
    },
    (value) => {
      value.packages["node_modules/unrelated"] = { version: "1.0.0" }
    },
    (value) => {
      value.packages["node_modules/undici"].dev = false
    },
    (value) => {
      value.packages["node_modules/undici"].license = "changed"
    },
    (value) => {
      value.packages["node_modules/undici"].dependencies = { surprise: "1.0.0" }
    },
    (value) => {
      value.packages["node_modules/undici"].version = "8.12.3"
    },
    (value) => {
      value.packages["node_modules/undici"].integrity = "wrong"
    },
  ]
  for (const mutate of mutations) {
    const candidate = candidateFixture(original, release)
    mutate(candidate)
    assert.throws(() => assertUndiciLockScope(original, candidate, release))
  }
  const changedRelease = structuredClone(release)
  changedRelease.dependencies = { surprise: "1.0.0" }
  assert.throws(() =>
    assertUndiciLockScope(original, candidateFixture(original, release), changedRelease)
  )
  const duplicate = structuredClone(original)
  duplicate.packages["node_modules/example/node_modules/undici"] =
    original.packages["node_modules/undici"]
  assert.throws(() =>
    assertUndiciLockScope(duplicate, candidateFixture(duplicate, release), release)
  )
})

test("source prerequisites preserve body-parser fix and targeted Undici version", () => {
  const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url)))
  assertSourceLockPrerequisites(lock)
  for (const [name, field, value] of [
    ["body-parser", "version", "1.20.8"],
    ["body-parser", "dev", false],
    ["undici", "version", "8.12.2"],
    ["undici", "dev", false],
  ]) {
    const changed = structuredClone(lock)
    changed.packages["node_modules/" + name][field] = value
    assert.throws(() => assertSourceLockPrerequisites(changed))
  }
})

test("import has no side effects; direct execution fails closed on absent workspace", () => {
  const env = { GITHUB_WORKSPACE: "/undici-generator-test-does-not-exist" }
  const imported = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", `import ${JSON.stringify(generatorUrl.href)}`],
    { env, encoding: "utf8", timeout: 10000, maxBuffer: 4096 }
  )
  assert.equal(imported.status, 0)
  assert.equal(imported.stdout, "")
  assert.equal(imported.stderr, "")
  const direct = spawnSync(process.execPath, [fileURLToPath(generatorUrl)], {
    env,
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 4096,
  })
  assert.equal(direct.status, 1)
  assert.equal(direct.stdout, "")
  assert.equal(direct.stderr, "Undici candidate rejected at stage: preflight\n")
})

test("workflow runs guards and protects executable inputs without weakening audit", () => {
  const root = new URL("../../", import.meta.url)
  const workflow = readFileSync(
    new URL(".github/workflows/reusable-security-audit.yml", root),
    "utf8"
  )
  const immutable = readFileSync(
    new URL(".github/workflows/security-policy-integrity.yml", root),
    "utf8"
  )
  const policy = workflow.slice(
    workflow.indexOf("  policy-integrity:"),
    workflow.indexOf("  pip-audit:")
  )
  const protectedCase = immutable.split('case "$path" in')[1].split('protected_paths+=("$path")')[0]
  for (const path of [
    "frontend/scripts/generate-undici-lock-candidate.mjs",
    "frontend/scripts/generate-undici-lock-candidate.test.mjs",
  ]) {
    assert(policy.includes(`"${path}"`))
    assert(protectedCase.includes(path))
  }
  assert(workflow.includes("run: node --test scripts/generate-undici-lock-candidate.test.mjs"))
  assert(workflow.includes("run: node scripts/generate-undici-lock-candidate.mjs"))
  assert(workflow.includes("npm ci --ignore-scripts --no-audit --no-fund"))
  assert(workflow.includes("--npm frontend"))
})
