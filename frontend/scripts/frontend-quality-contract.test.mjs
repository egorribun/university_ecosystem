import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import { createRequire } from "node:module"
import test from "node:test"
import { fileURLToPath } from "node:url"

import strykerConfig, { mutationRunnerReuse, mutationThresholds } from "../stryker.config.mjs"

const frontendRoot = new URL("../", import.meta.url)
const repositoryRoot = new URL("../../", import.meta.url)
const liveSetupUrl = new URL("./playwright-live-global-setup.mjs", import.meta.url).href
const require = createRequire(import.meta.url)

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf8"))
}

function runLiveStandSetup(environmentOverrides = {}) {
  const environment = { ...process.env }
  delete environment.LIVE_BASE_URL
  delete environment.LIVE_MAILPIT_URL
  Object.assign(environment, environmentOverrides)

  return spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `const { default: setup } = await import(${JSON.stringify(liveSetupUrl)}); await setup()`,
    ],
    {
      cwd: fileURLToPath(frontendRoot),
      encoding: "utf8",
      env: environment,
      timeout: 30_000,
    }
  )
}

test("frontend is explicitly a private application package", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))

  assert.equal(packageJson.private, true)
})

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
  // ADR-040: exactly one governed ignore policy, loaded from the repository.
  assert.deepEqual(strykerConfig.ignorers, ["presentation-class-names"])
  assert.deepEqual(strykerConfig.plugins, [
    "@stryker-mutator/*",
    "./scripts/stryker-presentation-ignorer.mjs",
  ])
  assert.equal(strykerConfig.incremental, false)
  assert.equal(
    strykerConfig.vitest?.related,
    true,
    "Stryker must use Vitest related mode so each shard executes only tests that cover its assigned source"
  )
  assert.ok(
    Number.isInteger(strykerConfig.concurrency) &&
      strykerConfig.concurrency >= 1 &&
      strykerConfig.concurrency <= 4,
    "Mutation concurrency must remain explicitly bounded"
  )
  assert.ok(
    strykerConfig.ignorePatterns?.includes("/dist/**"),
    "Generated production output must not be copied into the mutation sandbox"
  )
  for (const generatedPattern of ["/storybook-static/**", "/test-results/**", "/coverage-*/**"]) {
    assert.ok(
      strykerConfig.ignorePatterns?.includes(generatedPattern),
      `${generatedPattern} must stay outside mutation sandboxes`
    )
  }
  assert.equal(
    strykerConfig.dryRunTimeoutMinutes,
    30,
    "Stryker's initial test run deadline must be explicit and long enough for the full suite"
  )
})

test("Stryker reuses workers indefinitely on CI while retaining the Windows leak guard", () => {
  assert.equal(
    mutationRunnerReuse({}, "linux"),
    0,
    "Linux CI should avoid restarting Vitest workers between every few mutants"
  )
  assert.equal(
    mutationRunnerReuse({}, "win32"),
    4,
    "Windows keeps the bounded reuse default for native-handle stability"
  )
  assert.equal(mutationRunnerReuse({ STRYKER_MAX_TEST_RUNNER_REUSE: "8" }, "linux"), 8)
  assert.throws(
    () => mutationRunnerReuse({ STRYKER_MAX_TEST_RUNNER_REUSE: "-1" }, "linux"),
    /non-negative integer/u
  )
})

test("only the shard producer disables its local break threshold", () => {
  assert.deepEqual(mutationThresholds(true), { high: 100, low: 100, break: null })
  assert.deepEqual(mutationThresholds(false), { high: 100, low: 100, break: 100 })
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

test("canonical Node gates exercise the non-release progress reporter contracts", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  assert.match(packageJson.scripts["test:wasm"], /scripts\/stryker-progress-reporter\.test\.mjs/u)
})

test("canonical Node gates retain the real test CSS pipeline contract", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  assert.match(packageJson.scripts["test:wasm"], /scripts\/vitest-css-pipeline\.test\.mjs/u)
})

test("canonical Node gates exercise the bounded progress monitor contracts", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  assert.match(packageJson.scripts["test:wasm"], /scripts\/stryker-progress-monitor\.test\.mjs/u)
  assert.match(packageJson.scripts["test:wasm"], /scripts\/stryker-progress-diagnostic\.test\.mjs/u)
})

test("canonical Node gates exercise the Stryker factory adapter contracts", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  assert.match(packageJson.scripts["test:wasm"], /scripts\/stryker-progress-plugin\.test\.mjs/u)
})

test("canonical Node gates execute the runner-owned progress context contracts exactly once", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  const argumentsList = packageJson.scripts["test:wasm"].split(/\s+/u)
  assert.equal(
    argumentsList.filter((argument) => argument === "scripts/stryker-progress-context.test.mjs")
      .length,
    1
  )
})

test("profile bootstrap keeps the LHCI branch compile-time tree-shakeable", async () => {
  const profileSyncSource = await readFile(
    new URL("src/hooks/auth/useProfileSync.ts", frontendRoot),
    "utf8"
  )
  const hookStart = profileSyncSource.indexOf("export const useProfileSync")
  assert.ok(hookStart >= 0, "useProfileSync export must remain discoverable")
  const initializerStart = profileSyncSource.indexOf("useState<UserState>", hookStart)
  const initializerEnd = profileSyncSource.indexOf("const [pendingMfaState", initializerStart)
  assert.ok(initializerStart >= 0 && initializerEnd > initializerStart)
  const initializer = profileSyncSource.slice(initializerStart, initializerEnd)

  assert.match(
    initializer,
    /if \(import\.meta\.env\.VITE_LHCI === "true"\)/u,
    "the production initializer must expose a static VITE_LHCI guard"
  )
  assert.match(
    initializer,
    /resolveInitialUserStateWithoutLhci\(/u,
    "the non-LHCI initializer must delegate to the covered cache resolver"
  )
  assert.doesNotMatch(
    initializer,
    /resolveInitialUserState\(/u,
    "the production initializer must not route through a runtime LHCI boolean"
  )

  const initializingStart = profileSyncSource.indexOf("const [initializing", initializerEnd)
  const initializingEnd = profileSyncSource.indexOf("const [authOperation", initializingStart)
  assert.ok(initializingStart >= 0 && initializingEnd > initializingStart)
  const initializingInitializer = profileSyncSource.slice(initializingStart, initializingEnd)
  assert.match(
    initializingInitializer,
    /if \(import\.meta\.env\.VITE_LHCI === "true"\)/u,
    "the loading initializer must expose a static VITE_LHCI guard"
  )
  assert.match(
    initializingInitializer,
    /resolveInitialInitializingStateWithoutLhci\(/u,
    "the non-LHCI loading initializer must delegate to the covered resolver"
  )
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

test("LHCI binary setup skips Unix symlink operations on Windows only", async () => {
  const { runSetupForPlatform } = require("./setup-lhci-binaries.cjs")
  const invoked = []

  await runSetupForPlatform("win32", async () => invoked.push("win32"))
  assert.deepEqual(invoked, [])

  await runSetupForPlatform("linux", async () => invoked.push("linux"))
  assert.deepEqual(invoked, ["linux"])
})

test("Knip analyzes frontend tests as export consumers", async () => {
  const knipConfig = await readJson(new URL("knip.json", frontendRoot))

  assert.equal(
    knipConfig.treatConfigHintsAsErrors,
    true,
    "Knip configuration hints must fail the quality gate instead of remaining advisory"
  )

  // Only patterns that match real files: Knip reports unmatched entries as
  // configuration hints, which this gate treats as errors.
  for (const pattern of ["src/**/*.test.ts", "src/**/*.test.tsx"]) {
    assert.ok(knipConfig.entry.includes(pattern), `Missing Knip test entry: ${pattern}`)
  }
})

test("live Playwright config can be imported without a running stand", () => {
  const configUrl = new URL("../playwright.live.config.ts", import.meta.url).href
  const setupPath = "./scripts/playwright-live-global-setup.mjs"
  const environment = { ...process.env }
  delete environment.LIVE_BASE_URL
  delete environment.LIVE_MAILPIT_URL

  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `const { default: config } = await import(${JSON.stringify(configUrl)}); ` +
        `if (config.globalSetup !== ${JSON.stringify(setupPath)}) { ` +
        "throw new Error('Live stand validation must run in Playwright global setup') }",
    ],
    {
      cwd: fileURLToPath(frontendRoot),
      encoding: "utf8",
      env: environment,
      timeout: 30_000,
    }
  )

  assert.equal(
    result.status,
    0,
    `Config import unexpectedly required the live stand:\n${result.stderr}`
  )
})

test("live Playwright global setup requires the owned stand endpoints", () => {
  const missingBaseUrl = runLiveStandSetup()
  assert.notEqual(missingBaseUrl.status, 0)
  assert.match(missingBaseUrl.stderr, /LIVE_BASE_URL must be set/u)

  const missingMailpitUrl = runLiveStandSetup({ LIVE_BASE_URL: "http://localhost:32494" })
  assert.notEqual(missingMailpitUrl.status, 0)
  assert.match(missingMailpitUrl.stderr, /LIVE_MAILPIT_URL must be set/u)
})

test("live Playwright global setup verifies endpoints against the signed owner marker", async () => {
  const { createLiveStandSetup } = await import(liveSetupUrl)
  const calls = []
  const runtimeEnvironment = {
    PATH: process.env.PATH,
    HOME: "C:/test/live-setup-home",
    CHROMATIC_PROJECT_TOKEN: "must-not-reach-the-verifier",
  }
  const setup = createLiveStandSetup({
    environment: {
      LIVE_BASE_URL: "http://localhost:24123",
      LIVE_MAILPIT_URL: "http://127.0.0.1:24124",
      CHROMATIC_PROJECT_TOKEN: "never-an-argument",
    },
    runtimeEnvironment,
    runner: (...args) => {
      calls.push(args)
      return { error: null, status: 0 }
    },
  })

  await setup()

  assert.equal(calls.length, 1)
  const [command, args, options] = calls[0]
  assert.equal(command, "uv")
  assert.deepEqual(args, [
    "run",
    "--frozen",
    "python",
    "scripts/live_stand.py",
    "verify-endpoints",
    "--base-url",
    "http://localhost:24123",
    "--mailpit-url",
    "http://127.0.0.1:24124",
  ])
  assert.equal(options.shell, false)
  assert.equal(options.stdio, "ignore")
  assert.equal(options.cwd, fileURLToPath(repositoryRoot))
  assert.deepEqual(options.env, {
    PATH: process.env.PATH,
    HOME: "C:/test/live-setup-home",
  })
  assert.doesNotMatch(JSON.stringify(args), /CHROMATIC_PROJECT_TOKEN|never-an-argument/u)
})

test("live Playwright setup reports only a generic verifier failure", async () => {
  const { createLiveStandSetup } = await import(liveSetupUrl)
  const setup = createLiveStandSetup({
    environment: {
      LIVE_BASE_URL: "http://localhost:24123",
      LIVE_MAILPIT_URL: "http://127.0.0.1:24124",
    },
    runtimeEnvironment: { PATH: process.env.PATH },
    runner: () => ({ error: null, status: 2 }),
  })

  await assert.rejects(setup(), {
    message: "live stand endpoint ownership verification failed",
  })
})

test("live Playwright setup rejects unsafe URL components before spawning the verifier", async () => {
  const { createLiveStandSetup } = await import(liveSetupUrl)
  const invalidEndpoints = [
    {
      LIVE_BASE_URL: "https://localhost:24123",
      LIVE_MAILPIT_URL: "http://127.0.0.1:24124",
    },
    {
      LIVE_BASE_URL: "http://example.com:24123",
      LIVE_MAILPIT_URL: "http://127.0.0.1:24124",
    },
    {
      LIVE_BASE_URL: "http://localhost:24123",
      LIVE_MAILPIT_URL: "http://localhost:24124",
    },
    {
      LIVE_BASE_URL: "http://localhost:24123",
      LIVE_MAILPIT_URL: "https://127.0.0.1:24124",
    },
    {
      LIVE_BASE_URL: "http://userinfo@localhost:24123",
      LIVE_MAILPIT_URL: "http://127.0.0.1:24124",
    },
  ]

  for (const environment of invalidEndpoints) {
    let spawned = false
    const setup = createLiveStandSetup({
      environment,
      runtimeEnvironment: { PATH: process.env.PATH },
      runner: () => {
        spawned = true
        return { error: null, status: 0 }
      },
    })

    await assert.rejects(setup(), /must be a valid live-stand loopback URL/u)
    assert.equal(spawned, false)
  }
})

test("dependency install scripts use a reviewed fail-closed allow-list", async () => {
  const packageJson = await readJson(new URL("package.json", frontendRoot))
  const npmConfig = await readFile(new URL(".npmrc", frontendRoot), "utf8")

  assert.deepEqual(packageJson.allowScripts, {
    "esbuild@0.28.2": true,
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
