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
