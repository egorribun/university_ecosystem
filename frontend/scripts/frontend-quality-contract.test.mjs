import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import strykerConfig from "../stryker.config.mjs"

const frontendRoot = new URL("../", import.meta.url)
const repositoryRoot = new URL("../../", import.meta.url)

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf8"))
}

test("the production-only Vitest command uses the supported single-worker flag", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  const command = packageJson.scripts["test:client-production"]

  assert.match(command, /--maxWorkers=1(?:\s|$)/u)
  assert.doesNotMatch(command, /--minWorkers(?:=|\s)/u)
})

test("Stryker mutation scope is derived from the complete frontend coverage denominator", async () => {
  const sourcePolicy = await readJson(
    new URL("quality/coverage-source-policy.json", repositoryRoot)
  )
  const expected = [
    ...sourcePolicy.frontend.include,
    ...sourcePolicy.frontend.exclude.map((pattern) => `!${pattern}`),
  ]

  assert.deepEqual(strykerConfig.mutate, expected)
  assert.equal(
    strykerConfig.coverageAnalysis,
    "perTest",
    "Full-source mutation must use per-test coverage to select relevant tests and expose NoCoverage"
  )
  assert.equal(
    Object.hasOwn(strykerConfig, "testFiles"),
    false,
    "Stryker must discover the complete Vitest suite instead of a hand-picked test allow-list"
  )
  assert.deepEqual(strykerConfig.mutator, { plugins: null, excludedMutations: [] })
  assert.deepEqual(strykerConfig.ignorers, [])
  assert.equal(strykerConfig.incremental, false)
  assert.ok(
    Number.isInteger(strykerConfig.concurrency) &&
      strykerConfig.concurrency >= 1 &&
      strykerConfig.concurrency <= 4,
    "Mutation concurrency must remain explicitly bounded"
  )
  assert.equal(
    strykerConfig.dryRunTimeoutMinutes,
    15,
    "Stryker's initial test run deadline must be explicit and long enough for the full suite"
  )
})

test("the mutation command always validates the fail-closed source inventory", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  assert.equal(packageJson.scripts["test:mutation"], "node ./scripts/run-stryker.mjs")
  assert.equal(
    packageJson.scripts["test:mutation:verify"],
    "node ./scripts/verify-stryker-evidence.mjs"
  )
})

test("canonical test:ci executes the frontend quality contract tests", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  assert.match(
    packageJson.scripts["test:ci"],
    /--maxWorkers=4(?:\s|$)/u,
    "The full coverage run must not exhaust the host with an unbounded worker pool"
  )
  const command = packageJson.scripts["test:wasm"]
  assert.match(command, /scripts\/frontend-quality-contract\.test\.mjs/u)
  assert.match(command, /scripts\/stryker-inventory\.test\.mjs/u)
  assert.match(command, /scripts\/run-stryker\.test\.mjs/u)
  assert.match(command, /scripts\/verify-stryker-evidence\.test\.mjs/u)
  assert.match(command, /scripts\/server-response-stream\.test\.mjs/u)
  assert.match(command, /scripts\/server-readiness\.test\.mjs/u)
  assert.match(command, /scripts\/visual-smoke-auth\.test\.mjs/u)
  assert.match(command, /scripts\/visual-smoke-contract\.test\.mjs/u)
  assert.match(command, /scripts\/lhci-route-policy\.test\.mjs/u)
})

test("Lighthouse configuration keeps SEO route-aware and invokes the privacy policy", async () => {
  const rootConfig = await readFile(new URL("../.lighthouserc.js", frontendRoot), "utf8")
  const runner = await readFile(new URL("./scripts/run-lhci.mjs", frontendRoot), "utf8")
  const policyConfig = await readFile(
    new URL("./scripts/lhci-route-policy-config.cjs", frontendRoot),
    "utf8"
  )

  assert.match(rootConfig, /assertMatrix/u)
  assert.match(rootConfig, /publicSeoUrlPattern/u)
  assert.doesNotMatch(
    rootConfig,
    /"categories:seo":\s*\["error",\s*\{\s*minScore:\s*0\.9/u,
    "Protected routes must not inherit a global SEO assertion"
  )
  assert.match(runner, /assertLhciRoutePolicy/u)
  assert.match(runner, /expectedPaths/u)
  assert.match(runner, /fetchRemoteRobots/u)
  assert.match(runner, /redirect: "error"/u)
  assert.match(policyConfig, /protectedRoutePrefixes/u)
  assert.match(policyConfig, /defaultLhciPaths/u)
})

test("dependency install scripts use a reviewed fail-closed allow-list", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  const npmConfig = await readFile(new URL(".npmrc", frontendRoot), "utf8")

  assert.deepEqual(packageJson.allowScripts, {
    "@sentry/cli@2.58.6": true,
    "esbuild@0.28.1": true,
    "core-js": false,
    "fsevents@2.3.2": false,
    "fsevents@2.3.3": false,
    msw: false,
  })
  assert.match(npmConfig, /^strict-allow-scripts=true$/mu)
})

test("the transitive glob override is the supported non-deprecated release", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  const packageLock = await readJson(new URL("package-lock.json", frontendRoot))
  const installedGlobEntries = Object.entries(packageLock.packages)
    .filter(([packagePath]) => packagePath.endsWith("node_modules/glob"))
    .map(([packagePath, metadata]) => ({ packagePath, version: metadata.version }))

  assert.equal(packageJson.overrides.glob, "13.0.6")
  assert.deepEqual(installedGlobEntries, [{ packagePath: "node_modules/glob", version: "13.0.6" }])
  assert.equal(packageJson.overrides["chrome-launcher"], "1.2.1")
  assert.equal(
    Object.keys(packageLock.packages).some((packagePath) =>
      packagePath.endsWith("node_modules/rimraf")
    ),
    false,
    "LHCI must not retain rimraf@3, whose callback-era glob contract is incompatible with glob@13"
  )
})
