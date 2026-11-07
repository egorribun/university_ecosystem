import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import test from "node:test"
import { fileURLToPath } from "node:url"

const frontendRoot = new URL("../", import.meta.url)
const require = createRequire(import.meta.url)
const semver = require("semver")
const auditedTools = ["@babel/core", "jsdom"]
const expectedNodeRange = "^24.15.0 || >=26.0.0"

async function readJson(relativePath) {
  return JSON.parse(await readFile(new URL(relativePath, frontendRoot), "utf8"))
}

function assertRangeSubset(declaredRange, supportedRange, label) {
  assert.equal(typeof declaredRange, "string", `AUD-162 ${label}: missing declared Node range`)
  assert.notEqual(declaredRange.trim(), "", `AUD-162 ${label}: empty declared Node range`)
  assert.equal(typeof supportedRange, "string", `AUD-162 ${label}: missing Node engine`)
  assert.notEqual(supportedRange.trim(), "", `AUD-162 ${label}: empty Node engine`)
  assert.ok(semver.validRange(declaredRange), `AUD-162 ${label}: invalid declared Node range`)
  assert.ok(semver.validRange(supportedRange), `AUD-162 ${label}: missing or invalid Node engine`)
  assert.ok(
    semver.subset(declaredRange, supportedRange),
    `AUD-162 ${label}: ${declaredRange} permits Node versions outside ${supportedRange}`
  )
}

test("AUD-162 manifest and lock declare the same bounded Node range with engine-strict enabled", async () => {
  const manifest = await readJson("package.json")
  const lock = await readJson("package-lock.json")
  const npmConfig = await readFile(new URL(".npmrc", frontendRoot), "utf8")
  const declaredRange = manifest.engines.node

  assert.equal(lock.packages[""].engines.node, declaredRange)
  assertRangeSubset(declaredRange, expectedNodeRange, "manifest")
  assertRangeSubset(expectedNodeRange, declaredRange, "expected contract")
  const engineStrictSettings = npmConfig
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter((line) => /^engine-strict\s*=/u.test(line))
  assert.deepEqual(engineStrictSettings, ["engine-strict=true"])

  for (const [version, accepted] of [
    ["24.0.0", false],
    ["24.10.0", false],
    ["24.14.9", false],
    ["24.15.0", true],
    ["24.21.0", true],
    ["25.0.0", false],
    ["25.99.99", false],
    ["26.0.0", true],
    ["27.0.0", true],
    ["24.15.0-rc.1", false],
    ["26.0.0-rc.1", false],
  ]) {
    assert.equal(semver.satisfies(version, declaredRange), accepted, `AUD-162 Node ${version}`)
  }
})

for (const name of auditedTools) {
  test(`AUD-162 ${name} locked and installed engines cover the declared Node range`, async () => {
    const manifest = await readJson("package.json")
    const lock = await readJson("package-lock.json")
    const packagePath = `node_modules/${name}`
    const locked = lock.packages[packagePath]
    const installed = await readJson(`${packagePath}/package.json`)
    assert.ok(manifest.devDependencies[name], `AUD-162 ${name} must remain a direct tool`)
    assert.ok(locked, `AUD-162 ${name} must be locked`)
    assert.equal(installed.name, name)
    assert.equal(installed.version, locked.version)
    assert.equal(installed.engines.node, locked.engines.node)
    assertRangeSubset(manifest.engines.node, locked.engines.node, name)
  })
}

test("AUD-162 non-optional locked Node engine declarations cover the declared range", async () => {
  const manifest = await readJson("package.json")
  const lock = await readJson("package-lock.json")
  const requiredEngines = Object.entries(lock.packages).filter(
    ([packagePath, metadata]) =>
      packagePath && !metadata.optional && Object.hasOwn(metadata.engines ?? {}, "node")
  )
  assert.ok(requiredEngines.length > 0, "AUD-162 must inspect required lock entries")
  for (const [packagePath, metadata] of requiredEngines) {
    assertRangeSubset(manifest.engines.node, metadata.engines.node, packagePath)
  }
})

test("AUD-162 the former Node range exposes the original Babel and jsdom counterexamples", async () => {
  const lock = await readJson("package-lock.json")
  const formerRange = ">=24.0.0"

  for (const [name, versions] of [
    ["@babel/core", ["24.0.0", "24.10.0"]],
    ["jsdom", ["24.0.0", "24.10.0", "24.14.9", "25.0.0"]],
  ]) {
    const supportedRange = lock.packages[`node_modules/${name}`].engines.node
    assert.throws(() => assertRangeSubset(formerRange, supportedRange, name), {
      name: "AssertionError",
    })
    for (const version of versions) {
      assert.equal(
        semver.satisfies(version, formerRange),
        true,
        `former contract admits ${version}`
      )
      assert.equal(semver.satisfies(version, supportedRange), false, `${name} rejects ${version}`)
    }
  }
})

test("AUD-162 semver comparison uses the frontend's locked installation", async () => {
  const lock = await readJson("package-lock.json")
  const installed = await readJson("node_modules/semver/package.json")
  const expectedEntry = fileURLToPath(new URL("node_modules/semver/index.js", frontendRoot))
  assert.equal(require.resolve("semver"), expectedEntry)
  assert.equal(installed.name, "semver")
  assert.equal(installed.version, lock.packages["node_modules/semver"].version)
})

test("AUD-162 rejects absent, malformed, and narrower engine ranges", () => {
  for (const supportedRange of [undefined, "", "not-a-range", ">=26.0.0"]) {
    assert.throws(() => assertRangeSubset(expectedNodeRange, supportedRange, "control"), {
      name: "AssertionError",
    })
  }
})
