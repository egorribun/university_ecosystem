import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { randomBytes } from "node:crypto"
import { mkdtemp, mkdir, readFile, realpath, rm, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath, pathToFileURL } from "node:url"
import {
  assertNoLiveE2EOutputOverride,
  resolveLiveE2EOutputDirectory,
} from "./live-e2e-output-dir.mjs"
import {
  liveAuditCaseIds,
  selectLiveAuditCases,
  selectLiveAuditCasesFromEnvironment,
} from "./live-audit-case-selection.mjs"

test("live audit case selection maps exact files, titles, and projects", () => {
  const selection = selectLiveAuditCases([
    "aud154-realtime",
    "aud454-membership-revocation",
    "aud375-service-worker",
    "aud321-rate-limit-ux",
  ])
  assert.deepEqual(selection.files, [
    "tests/e2e-live/messenger-realtime.live.spec.ts",
    "tests/e2e-live/messenger-membership-revocation.live.spec.ts",
    "tests/e2e/audit375-service-worker.spec.ts",
    "tests/e2e/rate-limit-ux.spec.ts",
  ])
  assert.deepEqual(selection.projects, ["desktop"])
  assert.deepEqual(
    selection.grep.map(({ source }) => source),
    [
      "a message is delivered, edited, and tombstoned in the other authenticated session",
      "a removed member loses detail, history, reactor, attachment, send, and live access",
      "AUD-375 real service-worker replay",
      "Rate limit UX",
    ]
  )
  assert.deepEqual(liveAuditCaseIds, [
    "aud154-realtime",
    "aud154-enter-sent-confirmation",
    "aud454-membership-revocation",
    "aud375-service-worker",
    "aud321-rate-limit-ux",
    "aud432-login-lockout",
    "aud432-registration",
    "aud501-hidden-clock",
  ])
})

test("AUD-154 Enter selection preserves the separate button path and both projects", () => {
  const selection = selectLiveAuditCases(["aud154-enter-sent-confirmation"])
  assert.deepEqual(selection.files, ["tests/e2e-live/messenger-realtime.live.spec.ts"])
  assert.deepEqual(selection.projects, ["desktop", "mobile"])
  assert.deepEqual(
    selection.grep.map(({ source }) => source),
    ["shows sent confirmation after the server accepts the message"]
  )
  assert.deepEqual(selectLiveAuditCases(["aud154-realtime"]).projects, ["desktop"])
  assert.throws(
    () =>
      selectLiveAuditCases(["aud154-enter-sent-confirmation", "aud154-enter-sent-confirmation"]),
    TypeError
  )
})

test("live audit selection rejects raw paths, raw grep, empty, unknown, and duplicate IDs", () => {
  for (const invalid of [
    [],
    ["aud164"],
    ["aud154-realtime", "aud154-realtime"],
    ["../tests/e2e-live/secret.spec.ts"],
    [".*"],
  ]) {
    assert.throws(() => selectLiveAuditCases(invalid), TypeError)
  }
  assert.throws(() => selectLiveAuditCasesFromEnvironment(""), TypeError)
  assert.throws(
    () => selectLiveAuditCasesFromEnvironment("aud154-realtime,../unreviewed.spec.ts"),
    TypeError
  )
  assert.throws(
    () => selectLiveAuditCasesFromEnvironment("aud154-realtime,aud154-realtime"),
    TypeError
  )
  assert.throws(() => selectLiveAuditCasesFromEnvironment("x".repeat(513)), TypeError)
  assert.equal(selectLiveAuditCasesFromEnvironment(undefined), undefined)
})

test("AUD-432 lockout and registration retain desktop and mobile projects", () => {
  assert.deepEqual(selectLiveAuditCases(["aud432-login-lockout"]).projects, ["desktop", "mobile"])
  assert.deepEqual(selectLiveAuditCases(["aud432-registration"]).projects, ["desktop", "mobile"])
})

test("AUD-501 selects only the seeded story clock case on desktop and mobile", () => {
  const selection = selectLiveAuditCases(["aud501-hidden-clock"])
  assert.deepEqual(selection.files, ["tests/e2e-live/story-viewer-keyboard.live.spec.ts"])
  assert.deepEqual(selection.projects, ["desktop", "mobile"])
  assert.deepEqual(
    selection.grep.map(({ source }) => source),
    ["a seeded story preserves elapsed playback across a clock-controlled hidden tab"]
  )
})

test("project-scoped selection rejects cases assigned to the other project", () => {
  const desktop = selectLiveAuditCases(["aud154-realtime", "aud432-registration"], "desktop")
  const mobile = selectLiveAuditCases(["aud432-registration", "aud501-hidden-clock"], "mobile")
  assert.deepEqual(desktop.projects, ["desktop"])
  assert.deepEqual(mobile.projects, ["mobile"])
  assert.throws(() => selectLiveAuditCases(["aud154-realtime"], "mobile"), TypeError)
  assert.throws(() => selectLiveAuditCases(["aud154-realtime"], "backend"), TypeError)
})

test("audit Playwright config discovers only the closed case map's exact files", async () => {
  const config = await readFile(
    new URL("../playwright.live-audit.config.ts", import.meta.url),
    "utf8"
  )
  assert.match(config, /process\.env\.LIVE_AUDIT_CASE_IDS/u)
  assert.match(config, /process\.env\.LIVE_AUDIT_PROJECT/u)
  assert.match(config, /testMatch:\s*exactTestFiles/u)
  assert.match(config, /grep:\s*selection\.grep/u)
  assert.doesNotMatch(config, /new RegExp/u)
  assert.match(config, /projects:\s*selectedProjects/u)
  assert.doesNotMatch(config, /\*\*\/e2e-live|\.\*\.live/u)
})

test("audit Playwright collection binds the eight cases to exact files and projects", async (t) => {
  const frontendRoot = await realpath(fileURLToPath(new URL("../", import.meta.url)))
  const require = createRequire(import.meta.url)
  const cli = path.join(path.dirname(require.resolve("playwright/package.json")), "cli.js")
  const ownedRoot = await mkdtemp(path.join(tmpdir(), "ue-live-playwright-audit-selection-"))
  t.after(() => rm(ownedRoot, { recursive: true, force: true }))

  const outputDirectory = path.join(ownedRoot, "playwright-output")
  const npmUserConfig = path.join(ownedRoot, "npm-userconfig")
  const npmGlobalConfig = path.join(ownedRoot, "npm-globalconfig")
  await mkdir(outputDirectory)
  await writeFile(
    path.join(ownedRoot, ".ue-live-e2e-output-owner"),
    "ue-live-playwright-output-v1\n",
    { flag: "wx" }
  )
  for (const configPath of [npmUserConfig, npmGlobalConfig]) {
    await writeFile(configPath, "", { flag: "wx" })
  }

  const expectedRows = {
    desktop: [
      [
        "e2e/audit375-service-worker.spec.ts",
        "an abandoned worker's lease blocks its successor until forced expiry, then the successor drains the row",
      ],
      [
        "e2e/audit375-service-worker.spec.ts",
        "forwards the cookie proof and deletes a terminal 403 while two active workers contend",
      ],
      [
        "e2e/rate-limit-ux.spec.ts",
        "a persistent 429 shows a load error and manual retry recovers",
      ],
      [
        "e2e/rate-limit-ux.spec.ts",
        "retries a 429 after Retry-After and renders the successful response",
      ],
      [
        "e2e-live/auth-login-lockout.live.spec.ts",
        "synthetic account reaches account lockout after the configured failed-login threshold",
      ],
      [
        "e2e-live/messenger-membership-revocation.live.spec.ts",
        "a removed member loses detail, history, reactor, attachment, send, and live access",
      ],
      [
        "e2e-live/messenger-realtime.live.spec.ts",
        "a message is delivered, edited, and tombstoned in the other authenticated session",
      ],
      [
        "e2e-live/messenger-realtime.live.spec.ts",
        "shows sent confirmation after the server accepts the message",
      ],
      [
        "e2e-live/register-double-submit.live.spec.ts",
        "rapid double submit on a 360px registration form creates one account",
      ],
      [
        "e2e-live/story-viewer-keyboard.live.spec.ts",
        "a seeded story preserves elapsed playback across a clock-controlled hidden tab",
      ],
    ],
    mobile: [
      [
        "e2e-live/auth-login-lockout.live.spec.ts",
        "synthetic account reaches account lockout after the configured failed-login threshold",
      ],
      [
        "e2e-live/messenger-realtime.live.spec.ts",
        "shows sent confirmation after the server accepts the message",
      ],
      [
        "e2e-live/register-double-submit.live.spec.ts",
        "rapid double submit on a 360px registration form creates one account",
      ],
      [
        "e2e-live/story-viewer-keyboard.live.spec.ts",
        "a seeded story preserves elapsed playback across a clock-controlled hidden tab",
      ],
    ],
  }

  const projectCases = {
    desktop: liveAuditCaseIds,
    mobile: [
      "aud154-enter-sent-confirmation",
      "aud432-login-lockout",
      "aud432-registration",
      "aud501-hidden-clock",
    ],
  }
  for (const project of ["desktop", "mobile"]) {
    const environment = {
      CI: "true",
      HOME: ownedRoot,
      PATH: path.dirname(process.execPath),
      TMPDIR: tmpdir(),
      TMP: tmpdir(),
      TEMP: tmpdir(),
      LIVE_AUDIT_CASE_IDS: projectCases[project].join(","),
      LIVE_AUDIT_PROJECT: project,
      LIVE_BASE_URL: "http://localhost:20000",
      LIVE_MAILPIT_URL: "http://127.0.0.1:20001",
      TEST_PASSWORD: `${randomBytes(32).toString("base64url")}!Aa0`,
      LIVE_E2E_OUTPUT_DIR: outputDirectory,
      PLAYWRIGHT_TEST_OUTPUT_DIR: outputDirectory,
      NPM_CONFIG_USERCONFIG: npmUserConfig,
      NPM_CONFIG_GLOBALCONFIG: npmGlobalConfig,
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1",
    }
    if (process.platform === "win32") {
      assert.equal(typeof process.env.SYSTEMROOT, "string")
      environment.SYSTEMROOT = process.env.SYSTEMROOT
    }

    const collected = spawnSync(
      process.execPath,
      [cli, "test", "--list", "--reporter=json", "--config=playwright.live-audit.config.ts"],
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
    assert.equal(collected.error, undefined, `Playwright ${project} collection must start`)
    assert.equal(collected.signal, null, `Playwright ${project} collection must finish bounded`)
    assert.equal(
      collected.status,
      0,
      `Playwright ${project} collection must succeed: ${collected.stderr}`
    )
    const report = JSON.parse(collected.stdout)
    assert.deepEqual(report.errors, [])
    assert.equal(path.resolve(report.config.rootDir), path.join(frontendRoot, "tests"))
    assert.deepEqual(
      report.config.projects.map(({ name }) => name),
      [project]
    )

    const rows = []
    const pending = [...report.suites]
    while (pending.length > 0) {
      const suite = pending.pop()
      assert.ok(suite.suites === undefined || Array.isArray(suite.suites))
      assert.ok(Array.isArray(suite.specs))
      pending.push(...(suite.suites ?? []))
      for (const spec of suite.specs) {
        assert.equal(typeof spec.file, "string")
        for (const instance of spec.tests) {
          assert.equal(instance.projectName, project)
          rows.push([spec.file.replaceAll("\\", "/"), spec.title])
        }
      }
    }
    const normalizeRows = (values) =>
      values.toSorted(([leftFile, leftTitle], [rightFile, rightTitle]) =>
        `${leftFile}\0${leftTitle}`.localeCompare(`${rightFile}\0${rightTitle}`)
      )
    assert.deepEqual(normalizeRows(rows), normalizeRows(expectedRows[project]))

    const realtime = spawnSync(
      process.execPath,
      [
        cli,
        "test",
        "--list",
        "--reporter=json",
        "--config=playwright.live.config.ts",
        `--project=${project}`,
        "tests/e2e-live/messenger-realtime.live.spec.ts",
        "tests/e2e-live/messenger-reconnect-ordering.live.spec.ts",
        "tests/e2e-live/messenger-unread-read.live.spec.ts",
      ],
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
    assert.equal(realtime.error, undefined)
    assert.equal(realtime.signal, null)
    assert.equal(realtime.status, 0, realtime.stderr)
    const realtimeReport = JSON.parse(realtime.stdout)
    assert.deepEqual(realtimeReport.errors, [])
    const realtimeRows = []
    const realtimePending = [...realtimeReport.suites]
    while (realtimePending.length > 0) {
      const suite = realtimePending.pop()
      realtimePending.push(...(suite.suites ?? []))
      for (const spec of suite.specs) {
        for (const instance of spec.tests) {
          assert.equal(instance.projectName, project)
          assert.equal(instance.expectedStatus, "passed")
          assert.deepEqual(instance.annotations, [])
          realtimeRows.push([spec.file.replaceAll("\\", "/"), spec.title])
        }
      }
    }
    assert.deepEqual(
      normalizeRows(realtimeRows),
      normalizeRows([
        ...[
          "shows sent confirmation after the server accepts the message",
          "a message is delivered, edited, and tombstoned in the other authenticated session",
          "direct-message replay stays ordered and exactly once across receiver reconnect",
          "a receiver reaction is delivered to the sender over the live WebSocket",
          "a sender reply preserves its parent identity and reaches the receiver",
          "forwarding through the current-chat modal preserves attribution and reaches the receiver",
          "a peer typing indicator appears and expires over the live socket",
        ].map((title) => ["messenger-realtime.live.spec.ts", title]),
        [
          "messenger-reconnect-ordering.live.spec.ts",
          "two synthetic users receive ordered, exactly-once messages sent during a real reconnect",
        ],
        [
          "messenger-unread-read.live.spec.ts",
          "a real DM read receipt clears only that chat's unread state",
        ],
      ])
    )
  }
})

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
  assert.match(config, /reporter:\s*\[\["list"\], \["\.\/scripts\/live-aud154-reporter\.mjs"\]\]/u)
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
    requireCollection(playwrightPackage.version === "1.64.1" && testPackage.version === "1.64.1")
    const cli = path.join(path.dirname(packagePath), "cli.js")

    phase = "inventory"
    const launcher = await readFile(
      path.join(frontendRoot, "..", "scripts", "live_stand.py"),
      "utf8"
    )
    const evidence = await readFile(
      path.join(frontendRoot, "..", "scripts", "live_stand_playwright_evidence.py"),
      "utf8"
    )
    requireCollection(
      /^from scripts\.live_stand_playwright_evidence import \(\s+_PLAYWRIGHT_FAILURE_DECLARATION_SOURCES as _PLAYWRIGHT_FAILURE_DECLARATION_SOURCES,\s*\)$/mu.test(
        launcher
      )
    )
    requireCollection(
      /^from scripts\.live_stand_playwright_evidence import \(\s+_PLAYWRIGHT_FULL_COLLECTION_COUNT as _PLAYWRIGHT_FULL_COLLECTION_COUNT,\s*\)$/mu.test(
        launcher
      )
    )
    const inventory = evidence.match(
      /^_PLAYWRIGHT_FAILURE_DECLARATION_SOURCES = \(\n([\s\S]*?)^\)/mu
    )
    requireCollection(inventory !== null)
    const declarations = new Set()
    const reviewed = new Set()
    const auditCaseSources = new Set()
    const expectedAuditCaseSources = new Set([
      "tests/e2e/audit375-service-worker.spec.ts",
      "tests/e2e/rate-limit-ux.spec.ts",
    ])
    for (const line of inventory[1].trimEnd().split("\n")) {
      const entry = line.match(/^ {4}"(tests\/[^"]+)",$/u)
      requireCollection(entry !== null)
      requireCollection(!declarations.has(entry[1]))
      if (/^tests\/e2e-live\/[a-z0-9-]+\.live\.spec\.ts$/u.test(entry[1])) {
        // Existing live-suite sources remain tied to tracked live spec files.
        reviewed.add(entry[1])
      } else {
        requireCollection(expectedAuditCaseSources.has(entry[1]))
        auditCaseSources.add(entry[1])
      }
      declarations.add(entry[1])
    }
    requireCollection(reviewed.size > 0 && reviewed.size <= 256)
    requireCollection(
      auditCaseSources.size === expectedAuditCaseSources.size &&
        [...expectedAuditCaseSources].every((source) => auditCaseSources.has(source))
    )

    const expectedCount = Number(
      evidence.match(/^_PLAYWRIGHT_FULL_COLLECTION_COUNT = ([1-9][0-9]*)$/mu)?.[1]
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

test("ordinary Playwright rejects focused tests in CI during collection", async (t) => {
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), "ue-focused-test-contract-"))
  t.after(() => rm(temporaryRoot, { recursive: true, force: true }))
  const fixtureDirectory = path.join(temporaryRoot, "specs")
  await mkdir(fixtureDirectory)

  const frontendRoot = await realpath(fileURLToPath(new URL("../", import.meta.url)))
  const require = createRequire(import.meta.url)
  const cli = path.join(path.dirname(require.resolve("playwright/package.json")), "cli.js")
  const testEntry = require.resolve("@playwright/test")
  const ordinaryConfig = pathToFileURL(path.join(frontendRoot, "playwright.config.ts")).href
  const wrapper = path.join(temporaryRoot, "playwright.config.mjs")
  const focusCall = ["test", "only"].join(".")
  await writeFile(
    path.join(fixtureDirectory, "runtime.spec.cjs"),
    `const { test } = require(${JSON.stringify(testEntry)});\n` +
      `${focusCall}("owned focused fixture", () => {});\n`,
    { flag: "wx" }
  )
  await writeFile(
    wrapper,
    `import baseConfig from ${JSON.stringify(ordinaryConfig)};\n` +
      `export default { ...baseConfig, testDir: ${JSON.stringify(fixtureDirectory)} };\n`,
    { flag: "wx" }
  )

  for (const ci of [false, true]) {
    const environment = { SKIP_WEBSERVER: "true", ...(ci ? { CI: "true" } : {}) }
    if (process.platform === "win32") {
      assert.equal(typeof process.env.SYSTEMROOT, "string")
      environment.SYSTEMROOT = process.env.SYSTEMROOT
    }
    const collected = spawnSync(
      process.execPath,
      [cli, "test", "--config", wrapper, "--list", "--project=chromium"],
      {
        cwd: frontendRoot,
        env: environment,
        shell: false,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        encoding: "utf8",
        timeout: 30_000,
        killSignal: "SIGKILL",
        maxBuffer: 1024 * 1024,
      }
    )
    assert.equal(collected.error, undefined)
    assert.equal(collected.signal, null)
    const output = String(collected.stdout) + String(collected.stderr)
    if (ci) {
      assert.notEqual(collected.status, 0, output)
      assert.match(output, /forbidOnly/u)
    } else {
      assert.equal(collected.status, 0, output)
      assert.match(output, /owned focused fixture/u)
    }
  }
})

test("AUD-154 live Enter acceptance binds real POST, sender visibility, status, peer and cleanup", async () => {
  const source = await readFile(
    new URL("../tests/e2e-live/messenger-realtime.live.spec.ts", import.meta.url),
    "utf8"
  )
  const title = 'test("shows sent confirmation after the server accepts the message"'
  const start = source.indexOf(title)
  assert.ok(start >= 0, "the independent non-skipped Enter acceptance must exist")
  const next = source.indexOf('\n  test("', start + title.length)
  const body = source.slice(start, next < 0 ? source.length : next)
  assert.match(body, /\.press\("Enter"\)/u)
  assert.doesNotMatch(body, /#chat-send-btn|test\.skip|test\.fixme|route\.fulfill/u)
  assert.match(body, /waitForResponse/u)
  assert.match(body, /method\(\) === "POST"/u)
  assert.match(body, /\/api\/v1\/chats\/\$\{[^}]+\}\/messages/u)
  assert.match(body, /expect\([^\n]*\.ok\(\)\)\.toBe\(true\)/u)
  assert.match(body, /expect\(created\.id\)\.toBeTruthy\(\)/u)
  assert.match(body, /expect\(created\.content\)\.toBe\(message\)/u)
  assert.match(body, /expect\(senderText\)\.toHaveCount\(1\)/u)
  assert.match(body, /expect\(senderText\)\.toBeVisible\(\)/u)
  assert.match(body, /senderRow\.getByRole\("img",/u)
  assert.match(body, /Отправлено\|Прочитано получателем/u)
  assert.match(body, /frame\.message\.id === created\.id/u)
  assert.match(body, /receiverLog\.getByText\(message, \{ exact: true \}\)/u)
  assert.match(body, /finally/u)
  assert.match(body, /deleteOwnedLiveMessage/u)
  assert.match(body, /receiverContext\.close\(\)/u)
})
