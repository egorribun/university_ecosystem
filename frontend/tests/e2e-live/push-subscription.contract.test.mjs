import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import {
  lstatSync,
  mkdirSync,
  mkdtempSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { readFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { basename, dirname, join } from "node:path"
import process from "node:process"
import { fileURLToPath, URL } from "node:url"
import test from "node:test"
import { runInNewContext } from "node:vm"
import ts from "typescript"

const specUrl = new URL("./push-subscription.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const packageUrl = new URL("../../package.json", import.meta.url)
const sourceContractUrl = new URL("./push-opt-in.contract.test.mjs", import.meta.url)
const hookUrl = new URL("../../src/hooks/usePushPreferences.ts", import.meta.url)
const pushClientUrl = new URL("../../src/push/subscribe.ts", import.meta.url)
const appEntryUrl = new URL("../../src/main.tsx", import.meta.url)
const apiRouterUrl = new URL("../../../app/routers/notifications.py", import.meta.url)
const modelUrl = new URL("../../../app/models/notifications.py", import.meta.url)
const composeUrl = new URL("../../../docker-compose.live.yml", import.meta.url)
const standUrl = new URL("../../../scripts/live_stand.py", import.meta.url)

test("live Web Push acceptance is selected and stays inside native opt-in and subscription APIs", async () => {
  const [
    spec,
    config,
    packageJson,
    sourceContract,
    hook,
    pushClient,
    appEntry,
    apiRouter,
    model,
    compose,
    stand,
  ] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(packageUrl, "utf8"),
    readFile(sourceContractUrl, "utf8"),
    readFile(hookUrl, "utf8"),
    readFile(pushClientUrl, "utf8"),
    readFile(appEntryUrl, "utf8"),
    readFile(apiRouterUrl, "utf8"),
    readFile(modelUrl, "utf8"),
    readFile(composeUrl, "utf8"),
    readFile(standUrl, "utf8"),
  ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(packageJson, /test:e2e:live:contract[^\n]*push-opt-in\.contract\.test\.mjs/u)
  assert.match(packageJson, /test:e2e:live:contract[^\n]*push-subscription\.contract\.test\.mjs/u)
  assert.match(
    spec,
    /Chromium push opt-in persists one native subscription and removes it on opt-out/u
  )
  assert.match(spec, /randomUUID\(\)/u)
  assert.match(spec, /test\.use\(\{ channel: "chromium" \}\)/u)
  assert.match(spec, /test\.use\(\{ nativePushChannel: "chrome" \}\)/u)
  assert.doesNotMatch(spec, /nativePushChannel: "chromium"/u)
  assert.doesNotMatch(
    spec,
    /browser\.newContext\([\s\S]{0,400}?pushManager\.subscribe/u,
    "no off-the-record context may subscribe to Web Push"
  )
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /loginAs\(adminPage,\s*["']admin["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/register["']\)/u)
  assert.match(spec, /loginWith\(page,\s*email,\s*password\)/u)
  assert.match(spec, /registrationAttempted = true/u)
  assert.match(spec, /const foreignIdentity = randomUUID\(\)/u)
  assert.match(spec, /foreignRegistrationAttempted = true/u)
  assert.match(spec, /loginWith\(secondPage, foreignEmail, foreignPassword\)/u)
  assert.match(spec, /foreignIdentityProfile\.email === foreignEmail/u)
  assert.match(spec, /entry\.email === email && entry\.full_name === fullName/u)
  assert.match(spec, /encodeURIComponent\(userId\)/u)
  assert.match(spec, /X-CSRF-Token/u)
  assert.match(spec, /grantPermissions\(\[["']notifications["']\],\s*\{\s*origin\s*\}/u)
  assert.match(spec, /navigator\.serviceWorker\.ready/u)
  assert.match(spec, /registration\.pushManager\.getSubscription\(\)/u)
  assert.match(spec, /pushSwitch\.click\(\)/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /\/api\/v1\/push\/subscribe/u)
  assert.match(spec, /\/api\/v1\/push\/unsubscribe/u)
  assert.match(spec, /sameRecord/u)
  assert.match(spec, /unsubscribeBody\.removed === true/u)
  assert.match(spec, /second synthetic owner creates a real browser subscription/u)
  assert.match(
    spec,
    /foreignEndpoint[\s\S]*?authenticated foreign account cannot remove/u,
    "a different authenticated owner must not unsubscribe another user's endpoint"
  )
  assert.match(
    spec,
    /foreignSubscriptionAfterReload[\s\S]*?\.toBe\(true\)/u,
    "the subscription must remain owned and persisted after the foreign unsubscribe attempt"
  )
  const failureCleanupStart = spec.indexOf("if (subscriptionMayExist)")
  const accountCleanupStart = spec.indexOf("if (registrationAttempted)", failureCleanupStart)
  assert.ok(
    failureCleanupStart >= 0 && accountCleanupStart > failureCleanupStart,
    "failed runs must clean up the test-owned browser subscription before its account"
  )
  const failureCleanup = spec.slice(failureCleanupStart, accountCleanupStart)
  assert.match(
    failureCleanup,
    /cleanupOwnedBrowserSubscription\(page, ownEndpoint\)/u,
    "cleanup can revoke the exact owner endpoint even if the browser loses its local subscription"
  )
  assert.match(failureCleanup, /expect\(\s*ownSubscriptionCleaned,[\s\S]*?\.toBe\(true\)/u)
  assert.match(
    failureCleanup,
    /cleanupOwnedBrowserSubscription\(\s*foreignPage,\s*foreignEndpoint\s*\)/u
  )
  assert.match(failureCleanup, /expect\(\s*foreignSubscriptionCleaned,[\s\S]*?\.toBe\(true\)/u)
  assert.match(spec, /deleteOnlyCreatedAccount\(adminPage, foreignEmail, foreignFullName\)/u)
  const optOutStart = spec.indexOf("const unsubscribePromise")
  const optOutEnd = spec.indexOf("subscriptionMayExist = false", optOutStart)
  assert.ok(optOutStart >= 0 && optOutEnd > optOutStart, "the opt-out flow must remain bounded")
  const optOutFlow = spec.slice(optOutStart, optOutEnd)
  assert.match(
    optOutFlow,
    /await page\.reload\(\)[\s\S]*?pushSwitchAfterOptOut[\s\S]*?await expect\(pushSwitchAfterOptOut\)\.not\.toBeChecked\(\)/u
  )
  assert.match(optOutFlow, /await expect\(pushSwitchAfterOptOut\)\.toBeEnabled\(\)/u)
  assert.match(optOutFlow, /const nativeSubscriptionAfterOptOutReload = await page\.evaluate/u)
  assert.match(optOutFlow, /nativeSubscriptionAfterOptOutReload,[\s\S]*?\.toBe\(false\)/u)
  assert.match(
    sourceContract,
    /explicit notifications switch owns permission and subscription requests/u
  )
  assert.match(
    sourceContract,
    /loading notification settings only reads the owned browser subscription/u
  )

  assert.match(hook, /Notification\.requestPermission\(\)/u)
  assert.match(hook, /ensurePushSubscription\(/u)
  assert.match(pushClient, /reg\.pushManager\.subscribe\(/u)
  assert.match(pushClient, /getVapidPublicKey\(\)/u)
  assert.match(pushClient, /deleteSubscription\(endpoint\)/u)
  assert.match(appEntry, /syncPushForConfirmedIdentity\(\{ registration \}\)/u)

  assert.match(apiRouter, /@router\.post\(["']\/subscribe["']/u)
  assert.match(apiRouter, /@router\.post\(["']\/unsubscribe["']/u)
  assert.match(apiRouter, /PushSubscription\.endpoint == endpoint/u)
  assert.match(apiRouter, /PushSubscription\.user_id == user\.id/u)
  const unsubscribeStart = apiRouter.indexOf('@router.post("/unsubscribe")')
  const topicsStart = apiRouter.indexOf('@router.get("/topics")', unsubscribeStart)
  const unsubscribeSource = apiRouter.slice(unsubscribeStart, topicsStart)
  assert.match(
    unsubscribeSource,
    /PushSubscription\.endpoint == endpoint,[\s\S]*?PushSubscription\.user_id == user\.id/u,
    "the unsubscribe lookup requires both the requested endpoint and authenticated owner"
  )
  assert.match(
    unsubscribeSource,
    /if not existing:[\s\S]*?return \{"ok": True, "removed": False\}/u,
    "foreign endpoints return a non-mutating not-removed result"
  )
  assert.match(apiRouter, /return \{"ok": True, "removed": True\}/u)
  assert.match(
    model,
    /endpoint: Mapped\[str\] = mapped_column\(Text, nullable=False, index=True, unique=True\)/u
  )

  assert.match(compose, /VAPID_PUBLIC_KEY: \$\{LIVE_VAPID_PUBLIC_KEY/u)
  assert.match(compose, /VAPID_PRIVATE_KEY: \$\{LIVE_VAPID_PRIVATE_KEY/u)
  assert.match(stand, /generate_vapid_keys\(/u)
  assert.match(stand, /env\["LIVE_VAPID_PUBLIC_KEY"\]/u)
  assert.match(stand, /env\["LIVE_VAPID_PRIVATE_KEY"\]/u)

  const composeServices = [...compose.matchAll(/^ {2}([a-z][a-z0-9_-]*):\s*$/gmu)].map(
    ([, service]) => service
  )
  assert.equal(
    composeServices.some((service) => /push/i.test(service)),
    false,
    "the owned live Compose stack has no local push-delivery service; this acceptance must not claim delivery"
  )

  assert.doesNotMatch(spec, /page\.route\([^)]*(?:push|notifications)/iu)
  assert.doesNotMatch(
    spec,
    /routeWebSocket|vi\.mock|PushManager\.prototype|push\/test|sendTest\(/iu
  )
  assert.doesNotMatch(spec, /asyncpg|sqlalchemy|direct database|direct DB/iu)
})

async function runSyntheticPushCleanup(failures = {}, enabled = true) {
  const source = await readFile(specUrl, "utf8")
  const testStart = source.indexOf('test("Chromium push opt-in persists one native subscription')
  const bodyEnd = source.indexOf("    subscriptionMayExist = false\n", testStart)
  const cleanupStart = source.indexOf("\n  }", bodyEnd)
  const cleanupEnd = source.indexOf("\n})", cleanupStart)
  assert.ok(
    testStart >= 0 && bodyEnd > testStart && cleanupStart > bodyEnd && cleanupEnd > cleanupStart
  )

  const code = ts.transpileModule(
    `async function run(state) {
      let testFailure: unknown
      let testFailed = false
      const { page, ownEndpoint, foreignPage, foreignEndpoint, adminPage, adminContext,
        foreignEmail, foreignFullName, email, fullName, expect,
        cleanupOwnedBrowserSubscription, deleteOnlyCreatedAccount } = state
      const subscriptionMayExist = state.enabled
      const foreignSubscriptionMayExist = state.enabled
      const foreignRegistrationAttempted = state.enabled
      const registrationAttempted = state.enabled
      try { await state.body()${source.slice(cleanupStart, cleanupEnd)}
    }`,
    { compilerOptions: { target: ts.ScriptTarget.ES2022 } }
  ).outputText
  const run = runInNewContext(`${code}\nrun`, { AggregateError, Promise })
  const calls = []
  const page = {}
  const foreignPage = {}
  const capture = (name) => {
    calls.push(name)
    if (Object.hasOwn(failures, name)) throw failures[name]
  }
  const state = {
    enabled,
    page,
    foreignPage,
    ownEndpoint: "own",
    foreignEndpoint: "foreign",
    adminPage: {},
    email: "own",
    fullName: "own",
    foreignEmail: "foreign",
    foreignFullName: "foreign",
    body: async () => {
      if (Object.hasOwn(failures, "body")) throw failures.body
    },
    cleanupOwnedBrowserSubscription: async (owner) => {
      const name = owner === page ? "ownSubscription" : "foreignSubscription"
      capture(name)
      return failures[`${name}Result`] !== false
    },
    deleteOnlyCreatedAccount: async (_admin, email) => {
      capture(email === "own" ? "ownAccount" : "foreignAccount")
    },
    adminContext: { close: async () => capture("close") },
    expect: (value) => ({ toBe: (expected) => assert.equal(value, expected) }),
  }
  let threw = false
  let error
  try {
    await run(state)
  } catch (failure) {
    threw = true
    error = failure
  }
  return { calls, threw, error }
}

test("push subscription retains its body and every cleanup failure in order", async () => {
  const names = [
    "body",
    "ownSubscription",
    "foreignSubscription",
    "foreignAccount",
    "ownAccount",
    "close",
  ]
  const failures = Object.fromEntries(names.map((name) => [name, new Error(`synthetic ${name}`)]))
  const result = await runSyntheticPushCleanup(failures)
  assert.deepEqual(result.calls, names.slice(1))
  assert.equal(result.threw, true)
  assert.ok(result.error instanceof AggregateError)
  assert.deepEqual(
    Array.from(result.error.errors),
    names.map((name) => failures[name])
  )
})

test("push subscription keeps isolated failures and clean success failing or passing", async () => {
  const body = new Error("synthetic body")
  const bodyOnly = await runSyntheticPushCleanup({ body })
  assert.equal(bodyOnly.threw, true)
  assert.equal(bodyOnly.error, body)

  const cleanup = new Error("synthetic cleanup")
  const cleanupOnly = await runSyntheticPushCleanup({ foreignAccount: cleanup })
  assert.equal(cleanupOnly.threw, true)
  assert.ok(cleanupOnly.error instanceof AggregateError)
  assert.deepEqual(Array.from(cleanupOnly.error.errors), [cleanup])
  assert.deepEqual(cleanupOnly.calls, [
    "ownSubscription",
    "foreignSubscription",
    "foreignAccount",
    "ownAccount",
    "close",
  ])

  const falseyBody = await runSyntheticPushCleanup({ body: undefined })
  assert.equal(falseyBody.threw, true)
  assert.equal(falseyBody.error, undefined)

  const cleanupAssertion = await runSyntheticPushCleanup({ ownSubscriptionResult: false })
  assert.equal(cleanupAssertion.threw, true)
  assert.ok(cleanupAssertion.error instanceof AggregateError)
  assert.equal(cleanupAssertion.error.errors[0].code, "ERR_ASSERTION")
  assert.deepEqual(cleanupAssertion.calls, [
    "ownSubscription",
    "foreignSubscription",
    "foreignAccount",
    "ownAccount",
    "close",
  ])

  const clean = await runSyntheticPushCleanup({}, false)
  assert.equal(clean.threw, false)
  assert.deepEqual(clean.calls, ["close"])
})

function removeVerifiedFormatterFixture(root, temporaryRoot) {
  const resolved = realpathSync(root)
  if (dirname(resolved) !== temporaryRoot || !basename(resolved).startsWith("ue-push-format-")) {
    throw new Error("unsafe temporary Playwright fixture path")
  }
  rmSync(resolved, { recursive: true, force: true })
}

test("real Playwright aggregate frames remain bounded by the live redactor", () => {
  const temporaryRoot = realpathSync(tmpdir())
  const root = mkdtempSync(join(temporaryRoot, "ue-push-format-"))
  try {
    const frontendRoot = fileURLToPath(new URL("../..", import.meta.url))
    const workspaceRoot = fileURLToPath(new URL("../../..", import.meta.url))
    const moduleLink = join(root, "node_modules")
    symlinkSync(
      join(frontendRoot, "node_modules"),
      moduleLink,
      process.platform === "win32" ? "junction" : "dir"
    )
    assert.equal(lstatSync(moduleLink).isSymbolicLink(), true)
    const directory = join(root, "tests", "e2e-live")
    mkdirSync(directory, { recursive: true })
    writeFileSync(
      join(directory, "push-subscription.live.spec.ts"),
      [
        "import { test } from '@playwright/test'",
        "test('synthetic only', async () => {",
        "  const failures = []",
        "  try {",
        "    throw new Error('synthetic-private-body')",
        "  } catch (error) { failures.push(error) }",
        "  try {",
        "    throw new Error('synthetic-private-cleanup')",
        "  } catch (error) { failures.push(error) }",
        "  throw new AggregateError(failures, 'synthetic-private-aggregate')",
        "})",
        "",
      ].join("\n")
    )
    const config = join(root, "playwright.config.cjs")
    writeFileSync(
      config,
      "module.exports = { testDir: './tests/e2e-live', reporter: 'list', workers: 1, " +
        "retries: 0, projects: [{ name: 'desktop' }] }\n"
    )
    const playwrightEnv = { ...process.env, CI: "1", FORCE_COLOR: "0" }
    delete playwrightEnv.NO_COLOR
    const playwright = spawnSync(
      process.execPath,
      [join(frontendRoot, "node_modules", "@playwright", "test", "cli.js"), "test", "-c", config],
      {
        cwd: root,
        encoding: "utf8",
        timeout: 30000,
        env: playwrightEnv,
      }
    )
    assert.equal(playwright.error, undefined)
    assert.equal(playwright.status, 1)
    assert.equal(playwright.stderr, "")
    assert.match(playwright.stdout, /synthetic-private-body/u)
    assert.match(playwright.stdout, /synthetic-private-cleanup/u)

    const python = spawnSync(
      process.platform === "win32" ? "python" : "python3",
      [
        "-c",
        "import json,sys; from pathlib import Path; from scripts.live_stand_playwright_evidence import _live_playwright_failure_locations; print(json.dumps(_live_playwright_failure_locations(sys.stdin.read(), cwd=Path(sys.argv[1]))))",
        root,
      ],
      {
        cwd: workspaceRoot,
        input: playwright.stdout,
        encoding: "utf8",
        timeout: 10000,
        env: { ...process.env, PYTHONUTF8: "1", PYTHONDONTWRITEBYTECODE: "1" },
      }
    )
    assert.equal(python.error, undefined)
    assert.equal(python.status, 0)
    assert.equal(python.stderr, "")
    const locations = JSON.parse(python.stdout)
    assert.ok(
      locations.some(
        ([project, source, line, kind]) =>
          project === "desktop" &&
          source === "tests/e2e-live/push-subscription.live.spec.ts" &&
          line === 2 &&
          kind === "declaration"
      )
    )
    assert.deepEqual(
      locations
        .filter(([, , , kind]) => kind === "frame")
        .map(([, , line]) => line)
        .sort((a, b) => a - b),
      [5, 8, 10]
    )
    assert.doesNotMatch(python.stdout, /synthetic-private/u)
  } finally {
    removeVerifiedFormatterFixture(root, temporaryRoot)
  }
})
