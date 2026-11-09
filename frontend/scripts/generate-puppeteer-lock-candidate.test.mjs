import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { test } from "node:test"
import { fileURLToPath } from "node:url"

import {
  assertPuppeteerLockScope,
  assertPuppeteerSourceLock,
  preparePuppeteerManifest,
  puppeteerNpmCommand,
  puppeteerTargets,
  validatePuppeteerMetadata,
  verifyPuppeteerArchive,
} from "./generate-puppeteer-lock-candidate.mjs"

const DAY = 86_400_000
const NOW = Date.parse("2026-10-24T00:00:00.000Z")
const TARGETS = [
  ["puppeteer-core", "25.11.0", "25.13.0", "node_modules/puppeteer-core"],
  ["@puppeteer/browsers", "3.2.2", "3.2.4", "node_modules/@puppeteer/browsers"],
  ["chromium-bidi", "17.0.2", "157.0.8090-0", "node_modules/chromium-bidi"],
  [
    "devtools-protocol",
    "0.0.1680125",
    "0.0.1696802",
    "node_modules/puppeteer-core/node_modules/devtools-protocol",
  ],
  ["typed-query-selector", "2.12.2", "2.12.3", "node_modules/typed-query-selector"],
  ["webdriver-bidi-protocol", "0.4.3", "1.0.1", "node_modules/webdriver-bidi-protocol"],
].map(([name, from, to, path]) => ({ name, from, to, path }))
const REMOVED = "node_modules/chromium-bidi/node_modules/zod"
const TRANSPORT = [
  "--registry=https://registry.npmjs.org/",
  "--fetch-retries=0",
  "--fetch-timeout=30000",
  "--ignore-scripts",
  "--min-release-age=7",
]
const clone = (value) => JSON.parse(JSON.stringify(value))
const bytesFor = (name) => Buffer.from("synthetic archive fixture for " + name)
const archiveFor = (name, version) =>
  "https://registry.npmjs.org/" + name + "/-/" + name.split("/").at(-1) + "-" + version + ".tgz"

function metadata(target) {
  const bytes = bytesFor(target.name)
  const data = {
    name: target.name,
    version: target.to,
    time: { [target.to]: new Date(NOW - 8 * DAY).toISOString() },
    dist: {
      tarball: archiveFor(target.name, target.to),
      integrity: "sha512-" + createHash("sha512").update(bytes).digest("base64"),
      shasum: createHash("sha1").update(bytes).digest("hex"),
    },
    license: "Apache-2.0",
  }
  if (target.name === "puppeteer-core") {
    data.dependencies = {
      "@puppeteer/browsers": "3.2.4",
      "chromium-bidi": "157.0.8090-0",
      "devtools-protocol": "0.0.1696802",
      "typed-query-selector": "^2.12.3",
      "webdriver-bidi-protocol": "1.0.1",
      ws: "^8.21.3",
    }
    data.engines = { node: ">=22.12.0" }
  } else if (target.name === "@puppeteer/browsers") {
    data.dependencies = { "modern-tar": "^0.8.5", yargs: "^18.0.0" }
    data.bin = { browsers: "lib/main-cli.js" }
    data.engines = { node: ">=22.12.0" }
    data.peerDependencies = { "proxy-agent": ">=8.0.1", yauzl: "^2.10.0 || ^3.4.0" }
    data.peerDependenciesMeta = { "proxy-agent": { optional: true }, yauzl: { optional: true } }
  } else if (target.name === "chromium-bidi") {
    data.dependencies = { mitt: "^3.0.1", zod: "^4.6.5" }
    data.engines = { node: ">=20.19.0 <22.0.0 || >=22.12.0" }
    data.peerDependencies = { "devtools-protocol": "*" }
  } else if (target.name === "devtools-protocol") {
    data.license = "BSD-3-Clause"
  } else if (target.name === "typed-query-selector") {
    data.license = "MIT"
  }
  return data
}

function lockRecord(data) {
  const record = {
    version: data.version,
    resolved: data.dist.tarball,
    integrity: data.dist.integrity,
    dev: true,
    license: data.license,
  }
  for (const key of [
    "dependencies",
    "bin",
    "engines",
    "peerDependencies",
    "peerDependenciesMeta",
  ]) {
    if (Object.hasOwn(data, key)) record[key] = clone(data[key])
  }
  return record
}

function fixture() {
  const releases = TARGETS.map(metadata)
  const source = {
    name: "synthetic-frontend",
    version: "1.0.0",
    lockfileVersion: 3,
    requires: true,
    packages: {
      "": { name: "synthetic-frontend", version: "1.0.0" },
      "node_modules/lighthouse": {
        version: "13.5.0",
        dev: true,
        dependencies: { "puppeteer-core": "^25.9.0" },
      },
      "node_modules/zod": { version: "4.6.7", license: "MIT" },
      "node_modules/body-parser": { version: "1.20.9", dev: true },
      "node_modules/undici": { version: "8.12.2", dev: true },
      "node_modules/ws": { version: "8.22.0" },
      "node_modules/devtools-protocol": { version: "0.0.1687809", dev: true },
      "node_modules/modern-tar": { version: "0.8.5", dev: true },
      "node_modules/@puppeteer/browsers/node_modules/string-width": {
        version: "8.2.2",
        dev: true,
      },
      "node_modules/@puppeteer/browsers/node_modules/cliui/node_modules/string-width": {
        version: "7.2.0",
        dev: true,
      },
      "node_modules/msw/node_modules/string-width": { version: "8.3.0", dev: true },
      "node_modules/@puppeteer/browsers/node_modules/yargs": {
        version: "18.2.0",
        dev: true,
      },
      "node_modules/eslint-plugin-react-compiler": {
        version: "19.1.0-rc.2",
        dev: true,
      },
      "node_modules/eslint-plugin-react-compiler/node_modules/zod": {
        version: "3.25.76",
        dev: true,
      },
      [REMOVED]: { version: "3.25.76", dev: true },
    },
  }
  for (const [index, target] of TARGETS.entries()) {
    source.packages[target.path] = {
      ...lockRecord(releases[index]),
      version: target.from,
      resolved: archiveFor(target.name, target.from),
      integrity:
        "sha512-" +
        createHash("sha512")
          .update("old " + target.name)
          .digest("base64"),
    }
  }
  source.packages["node_modules/puppeteer-core"].dependencies = {
    "@puppeteer/browsers": "3.2.2",
    "chromium-bidi": "17.0.2",
    "devtools-protocol": "0.0.1680125",
    "typed-query-selector": "^2.12.2",
    "webdriver-bidi-protocol": "0.4.3",
    ws: "^8.21.3",
  }
  source.packages["node_modules/@puppeteer/browsers"].dependencies["modern-tar"] = "^0.8.4"
  source.packages["node_modules/chromium-bidi"].dependencies.zod = "^3.24.1"
  const candidate = clone(source)
  for (const [index, target] of TARGETS.entries()) {
    candidate.packages[target.path] = lockRecord(releases[index])
  }
  delete candidate.packages[REMOVED]
  return { source, candidate, releases }
}

test("targets are exactly six consumer-compatible releases at fixed lock paths", () => {
  assert.deepEqual(puppeteerTargets(), TARGETS)
})

test("every target requires its own mature registry identity and archive metadata", () => {
  for (const target of TARGETS) {
    const data = metadata(target)
    const before = clone(data)
    assert.deepEqual(validatePuppeteerMetadata(data, target, NOW), {
      data,
      published: data.time[target.to],
      timestamp: NOW - 8 * DAY,
    })
    assert.deepEqual(data, before)
  }
})

test("seven-day boundary is inclusive and younger or invalid timestamps are rejected", () => {
  for (const target of TARGETS) {
    const data = metadata(target)
    data.time[target.to] = new Date(NOW - 7 * DAY).toISOString()
    assert.equal(validatePuppeteerMetadata(data, target, NOW)?.timestamp, NOW - 7 * DAY)
    for (const published of [
      new Date(NOW - 7 * DAY + 1).toISOString(),
      new Date(NOW + DAY).toISOString(),
      "2026-02-30T00:00:00.000Z",
      "not-a-date",
      "2026-10-01",
      undefined,
    ]) {
      data.time[target.to] = published
      assert.throws(() => validatePuppeteerMetadata(data, target, NOW))
    }
    assert.throws(() => validatePuppeteerMetadata(metadata(target), target, NaN))
  }
})

test("metadata rejects wrong names, versions and targets including unapproved prereleases", () => {
  const target = TARGETS[0]
  for (const mutate of [
    (data) => (data.name = "puppeteer"),
    (data) => (data.version = "25.14.0"),
    (data) => (data.version = "25.13.0-next.1"),
  ]) {
    const data = metadata(target)
    mutate(data)
    assert.throws(() => validatePuppeteerMetadata(data, target, NOW))
  }
  for (const changed of [
    { ...target, to: "25.13.0-next.1" },
    { ...TARGETS[2], to: "158.0.0-0" },
    { ...target, path: "node_modules/unrelated" },
  ]) {
    assert.throws(() => validatePuppeteerMetadata(metadata(changed), changed, NOW))
  }
})

test("registry tarball URLs reject alternate origins, credentials and suffixes", () => {
  for (const target of TARGETS) {
    for (const tarball of [
      archiveFor(target.name, target.to).replace("https:", "http:"),
      archiveFor(target.name, target.to).replace("registry.npmjs.org", "example.invalid"),
      archiveFor(target.name, target.to).replace("registry.npmjs.org", "registry.npmjs.org:443"),
      archiveFor(target.name, target.to).replace("https://", "https://user@"),
      archiveFor(target.name, target.to) + "?download=1",
      archiveFor(target.name, target.to) + "#fragment",
      archiveFor(target.name, target.from),
    ]) {
      const data = metadata(target)
      data.dist.tarball = tarball
      assert.throws(() => validatePuppeteerMetadata(data, target, NOW))
    }
  }
})

test("registry integrity and shasum are mandatory canonical digest encodings", () => {
  const target = TARGETS[0]
  for (const [field, value] of [
    ["integrity", ""],
    ["integrity", "sha1-invalid"],
    ["integrity", "sha512-" + "A".repeat(86) + "== trailing"],
    ["shasum", "A".repeat(40)],
    ["shasum", "a".repeat(39)],
    ["shasum", undefined],
  ]) {
    const data = metadata(target)
    data.dist[field] = value
    assert.throws(() => validatePuppeteerMetadata(data, target, NOW))
  }
})

test("deprecated releases and install-time lifecycle hooks are rejected", () => {
  const target = TARGETS[0]
  const deprecated = metadata(target)
  deprecated.deprecated = "synthetic retired release"
  assert.throws(() => validatePuppeteerMetadata(deprecated, target, NOW))
  for (const phase of [
    "preinstall",
    "install",
    "postinstall",
    "prepublish",
    "preprepare",
    "prepare",
    "postprepare",
  ]) {
    const data = metadata(target)
    data.scripts = { [phase]: "synthetic-command" }
    assert.throws(() => validatePuppeteerMetadata(data, target, NOW))
  }
})

test("verified archives must match both hashes and a bounded nonempty byte buffer", () => {
  const data = metadata(TARGETS[0])
  const bytes = bytesFor(data.name)
  assert.equal(verifyPuppeteerArchive(data, bytes, 1024), true)
  for (const [input, limit] of [
    [Buffer.from("different"), 1024],
    [Buffer.alloc(0), 1024],
    [bytes, bytes.length - 1],
    [bytes, 0],
    [bytes, 16 * 1024 * 1024 + 1],
    ["not a buffer", 1024],
  ]) {
    assert.throws(() => verifyPuppeteerArchive(data, input, limit))
  }
  const altered = clone(data)
  altered.dist.shasum = createHash("sha1").update("different").digest("hex")
  assert.throws(() => verifyPuppeteerArchive(altered, bytes, 1024))
})

test("source prerequisites accept the fixed Lighthouse consumer and protected patches", () => {
  const { source } = fixture()
  const before = clone(source)
  assert.equal(assertPuppeteerSourceLock(source), true)
  assert.deepEqual(source, before)
})

test("wrong source versions, runtime flags and consumer ranges fail closed", () => {
  for (const target of TARGETS) {
    for (const [field, value] of [
      ["version", target.to],
      ["dev", false],
    ]) {
      const { source } = fixture()
      source.packages[target.path][field] = value
      assert.throws(() => assertPuppeteerSourceLock(source))
    }
    const { source } = fixture()
    delete source.packages[target.path]
    assert.throws(() => assertPuppeteerSourceLock(source))
  }
  for (const mutate of [
    (lock) => (lock.lockfileVersion = 2),
    (lock) => (lock.packages["node_modules/zod"].version = "4.6.5"),
    (lock) => (lock.packages["node_modules/zod"].dev = true),
    (lock) => (lock.packages["node_modules/body-parser"].version = "1.20.8"),
    (lock) => (lock.packages["node_modules/undici"].version = "8.11.0"),
    (lock) => (lock.packages["node_modules/body-parser"].dev = false),
    (lock) => (lock.packages["node_modules/undici"].dev = false),
    (lock) => (lock.packages["node_modules/modern-tar"].version = "0.8.6"),
    (lock) => {
      lock.packages["node_modules/@puppeteer/browsers/node_modules/string-width"].version = "8.3.0"
    },
    (lock) => (lock.packages["node_modules/puppeteer-core"].version = "25.12.0"),
    (lock) => (lock.packages["node_modules/chromium-bidi"].dev = false),
    (lock) => (lock.packages[REMOVED].version = "3.25.75"),
    (lock) => (lock.packages[REMOVED].dev = false),
    (lock) => (lock.packages["node_modules/lighthouse"].dev = false),
    (lock) => (lock.packages["node_modules/lighthouse"].version = "13.4.0"),
    (lock) => (lock.packages["node_modules/lighthouse"].dependencies["puppeteer-core"] = "^24"),
  ]) {
    const { source } = fixture()
    mutate(source)
    assert.throws(() => assertPuppeteerSourceLock(source))
  }
})

test("temporary targeting freezes browser descendants without mutating source", () => {
  const manifest = {
    name: "synthetic-frontend",
    devDependencies: { lighthouse: "13.5.0" },
    overrides: { "existing-package": "1.0.0" },
  }
  const before = clone(manifest)
  assert.deepEqual(preparePuppeteerManifest(manifest), {
    ...before,
    overrides: {
      ...before.overrides,
      "puppeteer-core@25.11.0": "25.13.0",
      "@puppeteer/browsers@3.2.4": {
        "modern-tar@0.8.5": "0.8.5",
        "string-width@8.2.2": "8.2.2",
      },
    },
  })
  assert.deepEqual(manifest, before)
})

test("direct dependencies and existing Puppeteer override policies are not replaced", () => {
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    assert.throws(() => preparePuppeteerManifest({ [section]: { "puppeteer-core": "25.11.0" } }))
  }
  for (const overrides of [
    { "puppeteer-core": "25.11.0" },
    { "puppeteer-core@25.11.0": "25.13.0" },
    { lighthouse: { "puppeteer-core": "25.11.0" } },
    { "@puppeteer/browsers": "3.2.4" },
    { "@puppeteer/browsers@3.2.4": { "modern-tar": "0.8.5" } },
    { lighthouse: { "@puppeteer/browsers": "3.2.4" } },
  ]) {
    assert.throws(() => preparePuppeteerManifest({ overrides }))
  }
})

test("the only accepted lock change is six exact releases and obsolete nested Zod removal", () => {
  const { source, candidate, releases } = fixture()
  const before = clone({ source, candidate, releases })
  assert.equal(assertPuppeteerLockScope(source, candidate, releases), true)
  assert.deepEqual({ source, candidate, releases }, before)
})

test("whole-lock validation preserves unrelated package records and root metadata", () => {
  for (const mutate of [
    (lock) => (lock.name = "changed"),
    (lock) => (lock.version = "2.0.0"),
    (lock) => (lock.lockfileVersion = 2),
    (lock) => (lock.requires = false),
    (lock) => (lock.packages[""].devDependencies = { "puppeteer-core": "25.13.0" }),
    (lock) => (lock.packages["node_modules/ws"].version = "8.23.0"),
    (lock) => (lock.packages["node_modules/ws"].dev = true),
    (lock) => (lock.packages["node_modules/zod"].version = "4.6.8"),
    (lock) => (lock.packages["node_modules/body-parser"].version = "1.20.8"),
    (lock) => (lock.packages["node_modules/undici"].version = "8.11.0"),
    (lock) => (lock.packages["node_modules/devtools-protocol"].version = "0.0.1696802"),
    (lock) => (lock.packages["node_modules/modern-tar"].version = "0.8.6"),
    (lock) => {
      lock.packages["node_modules/@puppeteer/browsers/node_modules/string-width"].version = "8.3.0"
    },
    (lock) => (lock.packages["node_modules/msw/node_modules/string-width"].version = "8.2.2"),
    (lock) => {
      const path = "node_modules/@puppeteer/browsers/node_modules/cliui/node_modules/string-width"
      lock.packages[path].version = "8.2.2"
    },
    (lock) => delete lock.packages["node_modules/eslint-plugin-react-compiler/node_modules/zod"],
    (lock) => (lock.packages["node_modules/unrelated"] = { version: "1.0.0" }),
    (lock) => delete lock.packages["node_modules/modern-tar"],
    (lock) => delete lock.packages["node_modules/puppeteer-core"],
    (lock) => (lock.packages[REMOVED] = { version: "3.25.76", dev: true }),
  ]) {
    const { source, candidate, releases } = fixture()
    mutate(candidate)
    assert.throws(() => assertPuppeteerLockScope(source, candidate, releases))
  }
})

test("changed records match release metadata without extra fields or runtime promotion", () => {
  for (const target of TARGETS) {
    for (const mutate of [
      (record) => (record.version = target.from),
      (record) => (record.resolved = archiveFor(target.name, target.from)),
      (record) => (record.integrity = "invalid"),
      (record) => delete record.dev,
      (record) => (record.hasInstallScript = true),
      (record) => (record.dependencies = { unexpected: "1.0.0" }),
    ]) {
      const { source, candidate, releases } = fixture()
      mutate(candidate.packages[target.path])
      assert.throws(() => assertPuppeteerLockScope(source, candidate, releases))
    }
  }
})

test("release sets cannot omit, duplicate or expand the six verified targets", () => {
  for (const mutate of [
    (releases) => releases.pop(),
    (releases) => releases.push(clone(releases[0])),
    (releases) => (releases[0].version = "25.14.0"),
    (releases) => (releases[0].dependencies["chromium-bidi"] = "17.0.2"),
    (releases) => (releases[2].dependencies.zod = "^3.24.1"),
    (releases) => (releases[0].dependencies.unexpected = "1.0.0"),
  ]) {
    const { source, candidate, releases } = fixture()
    mutate(releases)
    assert.throws(() => assertPuppeteerLockScope(source, candidate, releases))
  }
})

test("coherent registry and candidate drift cannot broaden the reviewed dependency set", () => {
  for (const mutate of [
    (releases) => (releases[0].dependencies["chromium-bidi"] = "17.0.2"),
    (releases) => (releases[2].dependencies.zod = "^3.24.1"),
    (releases) => (releases[0].dependencies.ws = "^9.0.0"),
    (releases) => (releases[1].dependencies.unexpected = "1.0.0"),
    (releases) => (releases[4].dependencies = { unexpected: "1.0.0" }),
  ]) {
    const { source, candidate, releases } = fixture()
    mutate(releases)
    for (const [index, target] of TARGETS.entries()) {
      candidate.packages[target.path] = lockRecord(releases[index])
    }
    assert.throws(() => assertPuppeteerLockScope(source, candidate, releases))
  }
})

test("already-staged compiler records remain opaque and unchanged", () => {
  const { source, candidate, releases } = fixture()
  const staged = {
    "node_modules/patched-zod": { version: "4.6.7", dev: true, name: "zod" },
    "node_modules/react-compiler-zod-compat": {
      resolved: "scripts/react-compiler-zod-compat",
      link: true,
    },
    "scripts/react-compiler-zod-compat": {
      name: "@university-ecosystem/react-compiler-zod-compat",
      version: "1.0.0",
      dev: true,
      dependencies: { "patched-zod": "npm:zod@4.6.7" },
    },
  }
  Object.assign(source.packages, clone(staged))
  Object.assign(candidate.packages, clone(staged))
  assert.equal(assertPuppeteerLockScope(source, candidate, releases), true)
  candidate.packages["node_modules/patched-zod"].version = "4.6.8"
  assert.throws(() => assertPuppeteerLockScope(source, candidate, releases))
})

test("npm commands retain cooldown, no scripts and finite target scope", () => {
  assert.deepEqual(puppeteerNpmCommand("update"), [
    "update",
    "puppeteer-core",
    "--package-lock-only",
    "--no-audit",
    "--no-fund",
    ...TRANSPORT,
  ])
  for (const target of TARGETS) {
    assert.deepEqual(puppeteerNpmCommand("metadata", target), [
      "view",
      target.name + "@" + target.to,
      "--json",
      ...TRANSPORT,
    ])
  }
  assert.throws(() => puppeteerNpmCommand("install"))
  assert.throws(() => puppeteerNpmCommand("metadata", { ...TARGETS[0], to: "latest" }))
})

test("CLI without immutable hosted source fails before network or candidate evidence", () => {
  const modulePath = fileURLToPath(
    new URL("./generate-puppeteer-lock-candidate.mjs", import.meta.url)
  )
  const result = spawnSync(process.execPath, [modulePath], {
    env: {},
    encoding: "utf8",
    timeout: 5000,
    maxBuffer: 4096,
    shell: false,
  })
  assert.equal(result.error, undefined)
  assert.equal(result.signal, null)
  assert.equal(result.status, 1)
  assert.equal(result.stdout, "")
  assert.equal(result.stderr, "Puppeteer candidate rejected at stage: preflight\n")
})
