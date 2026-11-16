import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"
import {
  removeBeforeCleanupDeadline,
  withVerifiedNativePushBrowserExit,
} from "./native-push-profile-cleanup.ts"

test("an initially disconnected Browser cannot synthesize disconnect evidence", async () => {
  const [fixtureSource, baseFixtureSource] = await Promise.all([
    readFile(new URL("./native-push-profile-fixtures.ts", import.meta.url), "utf8"),
    readFile(new URL("./fixtures.ts", import.meta.url), "utf8"),
  ])
  const branch = fixtureSource.match(/if \(!ownedBrowser\.isConnected\(\)\) \{([^}]*)\}/)

  assert.ok(branch, "initial-disconnected guard must remain explicit")
  assert.match(branch[1], /throw new Error\(/)
  assert.doesNotMatch(branch[1], /disconnectObserved\s*=/)
  assert.doesNotMatch(branch[1], /resolveDisconnected\s*\(/)

  assert.match(fixtureSource, /import \{ lstatSync, rmSync, type Stats \} from "node:fs"/u)
  assert.match(fixtureSource, /function identityOf\(stat: Stats\): DirectoryIdentity/u)
  assert.match(fixtureSource, /lstat\(canonicalProfilePath, \{ bigint: false \}\)/u)
  assert.match(fixtureSource, /lstat\(canonicalPath, \{ bigint: false \}\)/u)
  assert.doesNotMatch(fixtureSource, /Number\(stat\.(?:dev|ino|birthtimeMs)\)/u)

  const cleanupOverrideStart = fixtureSource.indexOf("  ownedSessionCleanup:")
  const pageFixtureStart = fixtureSource.indexOf("  page:", cleanupOverrideStart)
  const cleanupOverride = fixtureSource.slice(cleanupOverrideStart, pageFixtureStart)
  assert.match(cleanupOverride, /ownedSessionCleanup: async/u)
  assert.match(cleanupOverride, /void nativePushProfiles/u)
  assert.match(cleanupOverride, /await provideFixture\(ownedSessionCleanup\)/u)
  assert.doesNotMatch(cleanupOverride, /auto\s*:/u)

  const inheritedCleanupStart = baseFixtureSource.indexOf("  ownedSessionCleanup:")
  const pageErrorsStart = baseFixtureSource.indexOf("  pageErrors:", inheritedCleanupStart)
  const inheritedCleanup = baseFixtureSource.slice(inheritedCleanupStart, pageErrorsStart)
  assert.match(
    inheritedCleanup,
    /\{ auto: true, timeout: LIVE_OWNED_SESSION_CLEANUP_TIMEOUT_MS \}/u
  )
})

test("closes a recorded context before refusing a missing Browser owner", async () => {
  let closeCalls = 0
  let verifiedCleanupCalls = 0

  await assert.rejects(
    withVerifiedNativePushBrowserExit(
      {
        context: {
          close: async () => {
            closeCalls += 1
          },
        },
        browser: undefined,
        disconnected: Promise.resolve(),
        disconnectObserved: () => false,
        withTimeout: async (operation) => operation,
        timeoutMs: 10,
      },
      async () => {
        verifiedCleanupCalls += 1
      }
    ),
    /browser identity is unavailable/
  )

  assert.equal(closeCalls, 1)
  assert.equal(verifiedCleanupCalls, 0)
})

test("does not enter profile cleanup without a Browser disconnect observation", async () => {
  let verifiedCleanupCalls = 0

  await assert.rejects(
    withVerifiedNativePushBrowserExit(
      {
        context: { close: async () => undefined },
        browser: { isConnected: () => false },
        disconnected: Promise.resolve(),
        disconnectObserved: () => false,
        withTimeout: async (operation) => operation,
        timeoutMs: 10,
      },
      async () => {
        verifiedCleanupCalls += 1
      }
    ),
    /browser exit was not verified/
  )

  assert.equal(verifiedCleanupCalls, 0)
})

test("allows verification only after the explicit Browser disconnect event", async () => {
  const result = await withVerifiedNativePushBrowserExit(
    {
      context: { close: async () => undefined },
      browser: { isConnected: () => false },
      disconnected: Promise.resolve(),
      disconnectObserved: () => true,
      withTimeout: async (operation) => operation,
      timeoutMs: 10,
    },
    async () => "verified"
  )

  assert.equal(result, "verified")
})

test("runs the synchronous profile removal only before its absolute deadline", () => {
  let removalCalls = 0
  const remove = () => {
    removalCalls += 1
    return "removed"
  }

  assert.throws(
    () => removeBeforeCleanupDeadline(100, remove, () => 100),
    /cleanup deadline expired/
  )
  assert.equal(removalCalls, 0)
  assert.equal(
    removeBeforeCleanupDeadline(100, remove, () => 99),
    "removed"
  )
  assert.equal(removalCalls, 1)
})

test("native push profiles default to persistent branded Google Chrome, never off-the-record Chromium", async () => {
  const fixtureSource = await readFile(
    new URL("./native-push-profile-fixtures.ts", import.meta.url),
    "utf8"
  )

  assert.match(fixtureSource, /export const NATIVE_PUSH_BROWSER_CHANNEL = "chrome"/u)
  assert.match(
    fixtureSource,
    /nativePushChannel: \[NATIVE_PUSH_BROWSER_CHANNEL, \{ option: true \}\]/u,
    "the fixture must default to the Chrome channel that owns a real push service"
  )
  assert.doesNotMatch(fixtureSource, /nativePushChannel: \[undefined/u)
  assert.match(fixtureSource, /\.launchPersistentContext\(canonicalProfilePath, /u)
  assert.match(
    fixtureSource,
    /export const NATIVE_PUSH_BROWSER_ARGS = \["--disable-features=NativeNotifications"\] as const/u,
    "automated Chrome closes system notifications at once; keep Chrome's own notification centre"
  )
  assert.match(fixtureSource, /args: \[\.\.\.NATIVE_PUSH_BROWSER_ARGS\],/u)
  assert.doesNotMatch(
    fixtureSource,
    /browser\.newContext\(/u,
    "native push profiles must not be created as off-the-record contexts"
  )
})

test("a native Push test budget holds the bounded FCM steps it declares", async () => {
  const [fixtureSource, configSource] = await Promise.all([
    readFile(new URL("./native-push-profile-fixtures.ts", import.meta.url), "utf8"),
    readFile(new URL("../../playwright.live.config.ts", import.meta.url), "utf8"),
  ])
  const stepBudget = Number(
    fixtureSource
      .match(/export const PUSH_SUBSCRIBE_SAVE_TIMEOUT_MS = ([0-9_]+)/u)?.[1]
      .replaceAll("_", "")
  )
  const testBudget = Number(
    fixtureSource
      .match(/export const NATIVE_PUSH_TEST_TIMEOUT_MS = ([0-9_]+)/u)?.[1]
      .replaceAll("_", "")
  )
  const suiteBudget = Number(
    configSource.match(/^ {2}timeout: ([0-9_]+),$/mu)?.[1].replaceAll("_", "")
  )
  assert.equal(stepBudget, 60_000)
  assert.equal(suiteBudget, 60_000)
  // Two FCM-bound steps plus the ordinary suite budget for setup and cleanup.
  assert.ok(testBudget >= 2 * stepBudget + suiteBudget, "the test budget must hold its steps")

  const fixtureStart = fixtureSource.indexOf("  nativePushProfiles: async (")
  const profileCreation = fixtureSource.indexOf("await createOwnedProfile(", fixtureStart)
  const raise = fixtureSource.indexOf(
    "testInfo.setTimeout(NATIVE_PUSH_TEST_TIMEOUT_MS)",
    fixtureStart
  )
  assert.ok(fixtureStart > 0 && raise > fixtureStart && profileCreation > raise)
  // Only a smaller, bounded budget is raised; an unbounded (0) or larger one is kept.
  assert.match(
    fixtureSource.slice(fixtureStart, raise),
    /if \(testInfo\.timeout !== 0 && testInfo\.timeout < NATIVE_PUSH_TEST_TIMEOUT_MS\) \{\s*$/u
  )
})
