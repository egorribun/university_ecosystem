import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { randomBytes } from "node:crypto"
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import {
  assertNoLiveE2EOutputOverride,
  resolveLiveE2EOutputDirectory,
} from "./live-e2e-output-dir.mjs"

test("live admin fixture requires a runtime password and has no static admin fallback", async () => {
  const fixture = await readFile(new URL("../tests/e2e-live/fixtures.ts", import.meta.url), "utf8")
  const adminRole = fixture.match(/admin:\s*\{[^}]*\}/su)?.[0]
  assert.ok(adminRole, "the live admin role must remain defined")
  assert.match(adminRole, /password:\s*requireLiveAdminPassword\(\)/u)
  assert.doesNotMatch(adminRole, /password:\s*["']/u)
})

test("live admin password resolver fails closed when TEST_PASSWORD is missing or blank", async () => {
  const { requireLiveAdminPassword } = await import("./live-e2e-credentials.mjs")
  assert.throws(() => requireLiveAdminPassword({}), /TEST_PASSWORD/u)
  assert.throws(() => requireLiveAdminPassword({ TEST_PASSWORD: " \t " }), /TEST_PASSWORD/u)

  const runtimePassword = `${randomBytes(32).toString("base64url")}!Aa0`
  if (requireLiveAdminPassword({ TEST_PASSWORD: runtimePassword }) !== runtimePassword) {
    assert.fail("the live fixture must preserve the caller's per-run password")
  }
})

test("live Playwright fails CI runs that pass only after retrying and disables retained artifacts", async () => {
  const config = await readFile(new URL("../playwright.live.config.ts", import.meta.url), "utf8")
  assert.match(config, /failOnFlakyTests:\s*Boolean\(process\.env\.CI\)/u)
  assert.match(config, /reporter:\s*["']list["']/u)
  assert.doesNotMatch(config, /["']html["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(config, /outputDir:\s*resolveLiveE2EOutputDirectory\(\)/u)

  for (const file of [
    "../tests/e2e-live/auth-roles.live.spec.ts",
    "../tests/e2e-live/messenger-group-isolation.live.spec.ts",
    "../tests/e2e-live/messenger-realtime.live.spec.ts",
    "../tests/e2e-live/password-reset.live.spec.ts",
    "../tests/e2e-live/search-dialog-keyboard.live.spec.ts",
    "../tests/e2e-live/settings-radio-focus.live.spec.ts",
  ]) {
    const spec = await readFile(new URL(file, import.meta.url), "utf8")
    assert.doesNotMatch(spec, /trace:\s*["'](?:on|retain-on-failure)["']/u)
    assert.doesNotMatch(spec, /screenshot:\s*["']only-on-failure["']/u)
  }
})

test("live Playwright output paths are bounded for both environment overrides", async (t) => {
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), "ue-live-e2e-contract-"))
  t.after(() => rm(temporaryRoot, { recursive: true, force: true }))

  const frontendRoot = path.join(temporaryRoot, "repo", "frontend")
  await mkdir(frontendRoot, { recursive: true })

  const ownedTemporaryRoot = await mkdtemp(path.join(tmpdir(), "ue-live-playwright-"))
  t.after(() => rm(ownedTemporaryRoot, { recursive: true, force: true }))
  const outputDirectory = path.join(ownedTemporaryRoot, "playwright-output")
  await mkdir(outputDirectory)
  await writeFile(
    path.join(ownedTemporaryRoot, ".ue-live-e2e-output-owner"),
    "ue-live-playwright-output-v1\n",
    { flag: "wx" }
  )
  for (const configName of ["npm-userconfig", "npm-globalconfig"]) {
    await writeFile(path.join(ownedTemporaryRoot, configName), "", { flag: "wx" })
  }

  const ownedEnvironment = {
    LIVE_E2E_OUTPUT_DIR: outputDirectory,
    PLAYWRIGHT_TEST_OUTPUT_DIR: outputDirectory,
    NPM_CONFIG_USERCONFIG: path.join(ownedTemporaryRoot, "npm-userconfig"),
    NPM_CONFIG_GLOBALCONFIG: path.join(ownedTemporaryRoot, "npm-globalconfig"),
  }
  assert.equal(
    resolveLiveE2EOutputDirectory({
      environment: ownedEnvironment,
      frontendRoot,
      temporaryRoot: tmpdir(),
    }),
    outputDirectory
  )

  const externalDirectory = path.join(temporaryRoot, "arbitrary-external-output")
  await mkdir(externalDirectory)
  for (const variableName of ["LIVE_E2E_OUTPUT_DIR", "PLAYWRIGHT_TEST_OUTPUT_DIR"]) {
    assert.throws(
      () =>
        resolveLiveE2EOutputDirectory({
          environment: { [variableName]: externalDirectory },
          frontendRoot,
          temporaryRoot: tmpdir(),
        }),
      /owned temporary output|repository test-results/u,
      `${variableName} must not authorize an arbitrary cleanup path`
    )
  }

  assert.throws(
    () =>
      resolveLiveE2EOutputDirectory({
        environment: {
          ...ownedEnvironment,
          PLAYWRIGHT_TEST_OUTPUT_DIR: externalDirectory,
        },
        frontendRoot,
        temporaryRoot: tmpdir(),
      }),
    /must resolve to the same directory/u
  )
  assert.equal(
    resolveLiveE2EOutputDirectory({ environment: {}, frontendRoot }),
    path.join(frontendRoot, "test-results")
  )
  for (const variableName of ["LIVE_E2E_OUTPUT_DIR", "PLAYWRIGHT_TEST_OUTPUT_DIR"]) {
    assert.equal(
      resolveLiveE2EOutputDirectory({
        environment: { [variableName]: path.join(frontendRoot, "test-results") },
        frontendRoot,
      }),
      path.join(frontendRoot, "test-results"),
      `${variableName} may select only the repository's ignored output directory`
    )
  }
})

test("live Playwright rejects CLI output flags that bypass validated environment paths", () => {
  for (const args of [["--output", "C:/outside"], ["--output=C:/outside"], ["-o", "C:/outside"]]) {
    assert.throws(() => assertNoLiveE2EOutputOverride(args), /cannot be overridden/u)
  }
  assert.doesNotThrow(() => assertNoLiveE2EOutputOverride(["--grep", "live smoke"]))
})

test("live messenger acceptance observes edit and delete frames over a second real WebSocket", async () => {
  const spec = await readFile(
    new URL("../tests/e2e-live/messenger-realtime.live.spec.ts", import.meta.url),
    "utf8"
  )

  assert.match(spec, /browser\.newContext\(/u)
  assert.match(spec, /receiverPage\.on\(["']websocket["']/u)
  assert.match(spec, /socket\.on\(["']framereceived["']/u)
  assert.match(spec, /message_edited/u)
  assert.match(spec, /message_deleted/u)
  assert.match(spec, /editedAt|edited_at/u)
  assert.match(spec, /deletedAt|deleted_at/u)
  assert.doesNotMatch(spec, /routeWebSocket|WebSocket\s*=\s*new\s+Mock/u)
})

test("live messenger reactions reach another user and persist as viewer-specific history", async () => {
  const spec = await readFile(
    new URL("../tests/e2e-live/messenger-realtime.live.spec.ts", import.meta.url),
    "utf8"
  )

  assert.match(
    spec,
    /test\("a receiver reaction is delivered to the sender over the live WebSocket"/u
  )
  assert.match(spec, /senderReactions/u)
  assert.match(spec, /const senderHistoryResponse = await page\.request\.get/u)
  assert.match(spec, /const receiverHistoryResponse = await receiverPage\.request\.get/u)
  assert.match(spec, /reacted_by_me: false/u)
  assert.match(spec, /reacted_by_me: true/u)
  assert.match(spec, /count: 1/u)
  assert.doesNotMatch(spec, /routeWebSocket|WebSocket\s*=\s*new\s+Mock/u)
})

test("live group messenger acceptance checks member delivery and non-member isolation", async () => {
  const spec = await readFile(
    new URL("../tests/e2e-live/messenger-group-isolation.live.spec.ts", import.meta.url),
    "utf8"
  )

  assert.match(spec, /browser\.newContext\(/u)
  assert.match(spec, /findReusableGroup\(page, LIVE_GROUP_CHAT_NAME\)/u)
  assert.match(spec, /expect\(group\.created_by\)\.toBe\(ownerId\)/u)
  assert.match(spec, /matches\.length\)\.toBeLessThanOrEqual\(1\)/u)
  assert.doesNotMatch(spec, /live-group-\$\{crypto\.randomUUID/u)
  assert.match(spec, /socket\.on\(["']framesent["']/u)
  assert.match(spec, /socket\.on\(["']framereceived["']/u)
  assert.match(spec, /nonMemberSocket\.roomJoins/u)
  assert.match(spec, /deniedChatResponse\.status\(\)\)\.toBe\(403\)/u)
  assert.match(spec, /message_edited/u)
  assert.match(spec, /message_deleted/u)
  assert.match(
    spec,
    /eventsForMessage\(nonMemberSocket, chatId, sentMessage\.id\)\)\.toEqual\(\[\]\)/u
  )
  const outsiderJoinAttempt = spec.indexOf("nonMemberSocket.roomJoins")
  const messageSent = spec.indexOf("const message =")
  const outsiderDeliveryAssertion = spec.indexOf(
    "eventsForMessage(nonMemberSocket, chatId, sentMessage.id)"
  )
  assert.ok(outsiderJoinAttempt >= 0 && outsiderJoinAttempt < messageSent)
  assert.ok(outsiderDeliveryAssertion > messageSent)
  assert.match(spec, /trace:\s*["']off["']/u)
  assert.match(spec, /screenshot:\s*["']off["']/u)
  assert.doesNotMatch(
    spec,
    /loginAs\([^\n]*["']admin["']|routeWebSocket|WebSocket\s*=\s*new\s+Mock/u
  )
})

test("live Playwright collection has a closed source inventory", async (t) => {
  const requireCollection = (condition) => {
    if (!condition) throw new Error("Live Playwright collection contract failed")
  }
  const isRecord = (value) => typeof value === "object" && value !== null && !Array.isArray(value)

  let phase = "versions"
  let ownedRoot
  let summary
  let failure
  try {
    const frontendRoot = await realpath(fileURLToPath(new URL("../", import.meta.url)))
    const liveRoot = path.join(frontendRoot, "tests", "e2e-live")
    const suppliedSha = process.env.GITHUB_SHA
    const sourceSha = suppliedSha === undefined ? "unverified" : suppliedSha
    requireCollection(sourceSha === "unverified" || /^[0-9a-f]{40}$/u.test(sourceSha))
    requireCollection(!process.env.CI || sourceSha !== "unverified")

    const require = createRequire(import.meta.url)
    const packagePath = require.resolve("playwright/package.json")
    const playwrightPackage = JSON.parse(await readFile(packagePath, "utf8"))
    const testPackage = JSON.parse(
      await readFile(require.resolve("@playwright/test/package.json"), "utf8")
    )
    requireCollection(playwrightPackage.version === "1.63.0" && testPackage.version === "1.63.0")
    const cli = path.join(path.dirname(packagePath), "cli.js")

    phase = "inventory"
    const launcher = await readFile(
      path.join(frontendRoot, "..", "scripts", "live_stand.py"),
      "utf8"
    )
    const inventory = launcher.match(
      /^_PLAYWRIGHT_FAILURE_DECLARATION_SOURCES = \(\n([\s\S]*?)^\)/mu
    )
    requireCollection(inventory !== null)
    const reviewed = new Set()
    for (const line of inventory[1].trimEnd().split("\n")) {
      const entry = line.match(/^ {4}"(tests\/e2e-live\/[a-z0-9-]+\.live\.spec\.ts)",$/u)
      requireCollection(entry !== null)
      requireCollection(!reviewed.has(entry[1]))
      reviewed.add(entry[1])
    }
    requireCollection(reviewed.size > 0 && reviewed.size <= 256)

    const expectedCount = Number(
      launcher.match(/^_PLAYWRIGHT_SKIP_IDENTITY_LIMIT = ([1-9][0-9]*)$/mu)?.[1]
    )
    requireCollection(Number.isSafeInteger(expectedCount) && expectedCount > 0)
    requireCollection(expectedCount <= 10_000)

    phase = "spawn"
    ownedRoot = await mkdtemp(path.join(tmpdir(), "ue-live-playwright-"))
    const outputDirectory = path.join(ownedRoot, "playwright-output")
    await mkdir(outputDirectory)
    await writeFile(
      path.join(ownedRoot, ".ue-live-e2e-output-owner"),
      "ue-live-playwright-output-v1\n",
      { flag: "wx" }
    )
    for (const name of ["npm-userconfig", "npm-globalconfig"]) {
      await writeFile(path.join(ownedRoot, name), "", { flag: "wx" })
    }

    const environment = {
      CI: "true",
      HOME: ownedRoot,
      PATH: path.dirname(process.execPath),
      TMPDIR: tmpdir(),
      TMP: tmpdir(),
      TEMP: tmpdir(),
      LANG: "C.UTF-8",
      LC_ALL: "C.UTF-8",
      LIVE_BASE_URL: "http://localhost:20000",
      LIVE_MAILPIT_URL: "http://127.0.0.1:20001",
      TEST_PASSWORD: randomBytes(32).toString("base64url"),
      LIVE_E2E_OUTPUT_DIR: outputDirectory,
      PLAYWRIGHT_TEST_OUTPUT_DIR: outputDirectory,
      NPM_CONFIG_USERCONFIG: path.join(ownedRoot, "npm-userconfig"),
      NPM_CONFIG_GLOBALCONFIG: path.join(ownedRoot, "npm-globalconfig"),
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1",
    }
    if (process.platform === "win32") {
      requireCollection(
        typeof process.env.SYSTEMROOT === "string" && process.env.SYSTEMROOT.length > 0
      )
      environment.SYSTEMROOT = process.env.SYSTEMROOT
    }

    const collected = spawnSync(
      process.execPath,
      [cli, "test", "--list", "--reporter=json", "--config=playwright.live.config.ts"],
      {
        cwd: frontendRoot,
        env: environment,
        shell: false,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        encoding: "utf8",
        timeout: 60_000,
        killSignal: "SIGKILL",
        maxBuffer: 8 * 1024 * 1024,
      }
    )
    requireCollection(
      collected.error === undefined &&
        collected.signal === null &&
        collected.status === 0 &&
        typeof collected.stdout === "string" &&
        collected.stdout.length > 0
    )

    phase = "report-root"
    const report = JSON.parse(collected.stdout)
    requireCollection(isRecord(report))
    requireCollection(Array.isArray(report.errors) && report.errors.length === 0)
    requireCollection(isRecord(report.config))
    requireCollection(
      typeof report.config.rootDir === "string" && path.resolve(report.config.rootDir) === liveRoot
    )
    requireCollection(Array.isArray(report.suites))

    phase = "projects"
    requireCollection(Array.isArray(report.config.projects) && report.config.projects.length === 2)
    const projectNames = report.config.projects.map((project) => {
      requireCollection(isRecord(project))
      requireCollection(project.name === "desktop" || project.name === "mobile")
      requireCollection(project.repeatEach === 1)
      return project.name
    })
    requireCollection(new Set(projectNames).size === 2)

    const counts = { desktop: 0, mobile: 0 }
    const seenFiles = { desktop: new Set(), mobile: new Set() }
    const identities = new Set()
    const pending = [...report.suites]
    let visited = 0
    while (pending.length > 0) {
      phase = "spec-path"
      visited += 1
      requireCollection(visited <= 10_000)
      const suite = pending.pop()
      requireCollection(isRecord(suite))
      requireCollection(Array.isArray(suite.specs))
      if (suite.suites !== undefined) {
        requireCollection(Array.isArray(suite.suites))
        requireCollection(pending.length + suite.suites.length <= 10_000)
        pending.push(...suite.suites)
      }
      for (const spec of suite.specs) {
        phase = "spec-path"
        requireCollection(isRecord(spec))
        requireCollection(
          typeof spec.file === "string" && /^[a-z0-9-]+\.live\.spec\.ts$/u.test(spec.file)
        )
        const source = `tests/e2e-live/${spec.file}`
        requireCollection(reviewed.has(source))
        requireCollection(
          typeof spec.id === "string" && spec.id.length > 0 && spec.id.length <= 256
        )
        requireCollection(
          Number.isSafeInteger(spec.line) &&
            spec.line > 0 &&
            Number.isSafeInteger(spec.column) &&
            spec.column > 0
        )

        phase = "instances"
        requireCollection(Array.isArray(spec.tests) && spec.tests.length > 0)
        for (const instance of spec.tests) {
          requireCollection(isRecord(instance))
          const project = instance.projectName
          requireCollection(project === "desktop" || project === "mobile")
          requireCollection(Array.isArray(instance.results) && instance.results.length === 0)
          const identity = JSON.stringify([project, source, spec.id])
          requireCollection(!identities.has(identity))
          identities.add(identity)
          requireCollection(identities.size <= 10_000)
          counts[project] += 1
          seenFiles[project].add(source)
        }
      }
    }

    phase = "coverage"
    for (const project of ["desktop", "mobile"]) {
      requireCollection(counts[project] > 0)
      requireCollection(seenFiles[project].size === reviewed.size)
      for (const source of reviewed) {
        requireCollection(seenFiles[project].has(source))
      }
    }
    phase = "collection-count"
    requireCollection(identities.size === expectedCount)
    summary =
      `live collection source_sha=${sourceSha} files=${reviewed.size} projects=2 ` +
      `desktop=${counts.desktop} mobile=${counts.mobile} total=${identities.size}`
  } catch {
    // Phase is assigned only fixed literals, never captured child or report data.
    failure = new Error(`Live Playwright collection unavailable or invalid phase=${phase}`)
  } finally {
    if (ownedRoot !== undefined) {
      try {
        await rm(ownedRoot, { recursive: true, force: true })
      } catch {
        failure = new Error("Live Playwright collection temporary cleanup failed")
      }
    }
  }
  if (failure) throw failure
  t.diagnostic(summary)
})
