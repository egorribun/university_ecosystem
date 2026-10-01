import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

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
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /loginAs\(adminPage,\s*["']admin["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/register["']\)/u)
  assert.match(spec, /loginWith\(page,\s*email,\s*password\)/u)
  assert.match(spec, /registrationAttempted = true/u)
  assert.match(spec, /const foreignIdentity = randomUUID\(\)/u)
  assert.match(spec, /foreignRegistrationAttempted = true/u)
  assert.match(spec, /loginWith\(secondPage, foreignEmail, foreignPassword\)/u)
  assert.match(spec, /foreignProfile\.email === foreignEmail/u)
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
