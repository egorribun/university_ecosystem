import assert from "node:assert/strict"
import { randomBytes } from "node:crypto"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"
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

test("live Playwright disables reports and attachments that could retain credentials", async () => {
  const config = await readFile(new URL("../playwright.live.config.ts", import.meta.url), "utf8")
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
