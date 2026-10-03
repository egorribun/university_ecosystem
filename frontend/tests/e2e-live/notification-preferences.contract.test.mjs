import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./notification-preferences.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const packageUrl = new URL("../../package.json", import.meta.url)
const quietHoursUrl = new URL("../../../app/services/notifications/quiet_hours.py", import.meta.url)
const frontendTopicsUrl = new URL("../../src/notifications/contract.ts", import.meta.url)
const backendTopicsUrl = new URL("../../../app/core/notification_contract.py", import.meta.url)
const notificationRouterUrl = new URL("../../../app/routers/notifications.py", import.meta.url)
const preferencesHookUrl = new URL("../../src/hooks/usePushPreferences.ts", import.meta.url)
const notificationsApiUrl = new URL("../../src/api/notifications.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)

test("live notification acceptance uses an owned account and cleans up only that account", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the live notification-preferences browser scenario must exist")
  }
  const [config, quietHours, fixtures] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(quietHoursUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
  ])

  assert.match(spec, /notification topics and quiet hours persist across reload and opt-out/u)
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /loginWith\(page, email, password\)/u)
  assert.match(spec, /loginAs\(adminPage, "admin"\)/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /dnd_enabled/u)
  assert.match(spec, /dnd_start/u)
  assert.match(spec, /dnd_end/u)
  assert.match(
    spec,
    /const equalStartSave = waitForProfileUpdate\(page\)[\s\S]*?startTime\.fill\("00:00"\)[\s\S]*?const equalEndSave = waitForProfileUpdate\(page\)[\s\S]*?endTime\.fill\("00:00"\)/u,
    "the UI saves the equal-midnight boundary through the profile form"
  )
  assert.match(
    spec,
    /equalBoundaryProfile = await readProfile\(page\)[\s\S]*?dnd_start[\s\S]*?00:00[\s\S]*?dnd_end[\s\S]*?00:00/u,
    "the live profile read verifies both equal boundary values persisted"
  )
  assert.match(
    quietHours,
    /if start == end:\s*return True/u,
    "the boundary is the documented all-day quiet-hours sentinel"
  )
  assert.match(spec, /PUT/u)
  const disableFlowStart = spec.indexOf("const disableSave = waitForProfileUpdate(page)")
  assert.ok(disableFlowStart >= 0, "quiet-hours opt-out must be exercised through the UI")
  const disableFlow = spec.slice(disableFlowStart)
  assert.match(disableFlow, /await quietHours\.click\(\)[\s\S]*?disabledResponse/u)
  assert.match(disableFlow, /await page\.reload\(\)[\s\S]*?quietHoursAfterOptOut/u)
  assert.match(disableFlow, /dnd_enabled\)\.toBe\(false\)/u)
  assert.match(disableFlow, /dnd_start\)\.toBeNull\(\)/u)
  assert.match(disableFlow, /dnd_end\)\.toBeNull\(\)/u)
  assert.ok(
    spec.includes('page.request.get("/api/v1/users/me")'),
    "the browser scenario must verify persisted state from the authenticated profile API"
  )
  assert.match(spec, /entry\.email === email && entry\.full_name === fullName/u)
  assert.match(
    spec,
    /fetch\(`\/api\/v1\/users\/\$\{encodeURIComponent\(userId\)\}`,[\s\S]*?method:\s*["']DELETE["']/u,
    "cleanup must delete the exact synthetic account through the same-origin CSRF-protected API"
  )
  assert.match(spec, /document\.cookie[\s\S]*?csrf_token=/u)
  assert.match(spec, /headers:\s*\{\s*["']X-CSRF-Token["']:\s*csrfToken\s*\}/u)
  assert.doesNotMatch(
    spec,
    /adminPage\.request\.delete\(/u,
    "APIRequestContext cleanup must not bypass the browser CSRF header"
  )
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|vi\.mock|push\/test/u,
    "the live preference scenario must use real backend APIs without delivery mocks"
  )
  assert.match(spec, /stubBreachedPasswordLookup\(page\)/u)
  assert.equal(
    (fixtures.match(/page\.route\(/gu) ?? []).length,
    1,
    "the shared fixture may intercept only the external breached-password lookup"
  )
  assert.match(fixtures, /await page\.route\(["']https:\/\/api\.pwnedpasswords\.com\/\*\*["']/u)
  assert.doesNotMatch(
    fixtures,
    /page\.route\(["'][^"']*\/api(?:\/|["'])/u,
    "the synthetic account setup must not mock application APIs"
  )
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
})

test("live notification preferences cover every topic, owner scope, and post-reload opt-out", async () => {
  const [
    spec,
    config,
    packageJson,
    frontendTopics,
    backendTopics,
    notificationRouter,
    preferencesHook,
    notificationsApi,
  ] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(packageUrl, "utf8"),
    readFile(frontendTopicsUrl, "utf8"),
    readFile(backendTopicsUrl, "utf8"),
    readFile(notificationRouterUrl, "utf8"),
    readFile(preferencesHookUrl, "utf8"),
    readFile(notificationsApiUrl, "utf8"),
  ])

  const frontendList = frontendTopics.match(
    /CANONICAL_NOTIFICATION_TOPICS\s*=\s*\[([\s\S]*?)\]\s*as const/u
  )?.[1]
  const backendList = backendTopics.match(
    /CANONICAL_NOTIFICATION_TOPICS:\s*Final\[tuple\[str, \.\.\.\]\]\s*=\s*\(([\s\S]*?)\)/u
  )?.[1]
  assert.ok(frontendList, "the frontend canonical topic contract must remain explicit")
  assert.ok(backendList, "the backend canonical topic contract must remain explicit")
  const topicsFrom = (source) =>
    [...source.matchAll(/["']([^"']+)["']/gu)].map(([, value]) => value)
  const expectedTopics = topicsFrom(frontendList)
  assert.deepEqual(
    topicsFrom(backendList),
    expectedTopics,
    "frontend and backend topic catalogs agree"
  )
  assert.equal(expectedTopics.length, 5, "MVP currently defines five notification topics")
  const liveTopics = spec.match(/const TOPICS = \[([\s\S]*?)\] as const/u)?.[1]
  assert.ok(liveTopics, "the live scenario must explicitly map topics to visible controls")
  const liveTopicKeys = [...liveTopics.matchAll(/key:\s*["']([^"']+)["']/gu)].map(([, key]) => key)
  assert.deepEqual(liveTopicKeys, expectedTopics, "each canonical topic maps to one UI control")

  assert.match(
    packageJson,
    /test:e2e:live:contract[^\n]*notification-preferences\.contract\.test\.mjs/u
  )
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)

  assert.match(spec, /grantPermissions\(\[["']notifications["']\]/u)
  assert.match(spec, /navigator\.serviceWorker\.ready/u)
  assert.match(spec, /pushManager\.getSubscription\(\)/u)
  assert.ok(spec.includes("/api/v1/push/subscribe/topics"))
  assert.ok(spec.includes("/api/v1/push/topics"))
  assert.ok(spec.includes("/api/v1/push/admin/topics"))
  for (const topic of expectedTopics) {
    assert.ok(spec.includes(topic), `live scenario must exercise the ${topic} preference`)
  }
  assert.match(spec, /createdProfile\.role[\s\S]*?\.toBe\(\s*["']student["']/u)
  assert.match(spec, /studentAdminRead\.status[\s\S]*?\.toBe\(403\)/u)
  assert.match(spec, /admin can inspect the exact target[\s\S]*?\.toBe\(200\)/u)
  assert.match(spec, /topics\)\.toEqual\(\[\]\)/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /const pushOptOut = waitForPushAction[\s\S]*?\/api\/v1\/push\/unsubscribe/u)
  assert.match(spec, /optedOutTopicsAfterReload = await readTopicPreferences\(page\)/u)
  assert.match(spec, /optedOutAdminTopics = await readAdminTopicPreferences/u)
  assert.match(spec, /topicPatchRequests\)\.toBe\(1 \+ SELECTED_TOPICS\.length\)/u)
  assert.match(
    spec,
    /optedOutTopicsAfterReload = await readTopicPreferences\(page\)[\s\S]*?const optedOutPushRebind = waitForPushAction\(page, "\/api\/v1\/push\/subscribe", "POST"\)[\s\S]*?const reboundTopics = await readTopicPreferences\(page\)[\s\S]*?reboundTopics\.has_preferences\)\.toBe\(true\)[\s\S]*?reboundTopics\.topics\)\.toEqual\(\[\]\)[\s\S]*?await page\.reload\(\)[\s\S]*?expectTopicSelection\(page, \[\]\)/u,
    "re-enabling the endpoint must preserve an explicit empty topic opt-out across reload"
  )
  assert.match(
    spec,
    /const topicPatchRequestsBeforeRebind = topicPatchRequests[\s\S]*?topicPatchRequests\)\.toBe\(topicPatchRequestsBeforeRebind\)/u,
    "re-binding an endpoint must not silently overwrite canonical topic preferences"
  )
  const topicReloadStart = spec.indexOf("await page.reload()")
  const selectedTopicsAfterReload = spec.indexOf(
    "await expectTopicSelection(page, SELECTED_TOPICS)",
    topicReloadStart
  )
  const canonicalTopicsAfterReload = spec.indexOf(
    "expect((await readTopicPreferences(page)).topics).toEqual(SELECTED_TOPICS)",
    selectedTopicsAfterReload
  )
  const selectedTopicOptOutStart = spec.indexOf(
    "for (const topic of TOPICS.filter((entry) => SELECTED_TOPICS.includes(entry.key)))",
    canonicalTopicsAfterReload
  )
  assert.ok(
    topicReloadStart >= 0 &&
      selectedTopicsAfterReload > topicReloadStart &&
      canonicalTopicsAfterReload > selectedTopicsAfterReload &&
      selectedTopicOptOutStart > canonicalTopicsAfterReload,
    "all five UI topic controls and the owner API restore the selected subset before opt-out"
  )
  assert.match(spec, /dnd_enabled/u)
  assert.match(spec, /dnd_start/u)
  assert.match(spec, /dnd_end/u)
  const endTimeSaveStart = spec.indexOf("const endSave = waitForProfileUpdate(page)")
  const quietHoursReloadStart = spec.indexOf("await page.reload()", endTimeSaveStart)
  const quietHoursReloadEnd = spec.indexOf("const equalStartSave", quietHoursReloadStart)
  const quietHoursReload = spec.slice(quietHoursReloadStart, quietHoursReloadEnd)
  assert.ok(endTimeSaveStart >= 0 && quietHoursReloadStart > endTimeSaveStart)
  assert.match(
    quietHoursReload,
    /getByRole\("switch", \{ name: "Включить тихий период" \}\)\)\.toBeChecked\(\)/u
  )
  assert.match(quietHoursReload, /getByLabel\("С", \{ exact: true \}\)\)\.toHaveValue\("21:35"\)/u)
  assert.match(quietHoursReload, /getByLabel\("До", \{ exact: true \}\)\)\.toHaveValue\("06:45"\)/u)
  assert.match(quietHoursReload, /persistedProfile = await readProfile\(page\)/u)
  assert.match(quietHoursReload, /persistedProfile\.dnd_enabled\)\.toBe\(true\)/u)
  assert.match(quietHoursReload, /persistedProfile\.dnd_start\)\.toMatch\(\/\^21:35/u)
  assert.match(quietHoursReload, /persistedProfile\.dnd_end\)\.toMatch\(\/\^06:45/u)
  assert.match(
    notificationRouter,
    /@router\.patch\(["']\/subscribe\/topics["'][\s\S]*?PushSubscription\.user_id == user\.id/u,
    "topic mutations must target a subscription owned by the authenticated user"
  )
  assert.match(
    preferencesHook,
    /updatePushTopics\(subscription\.endpoint, pendingTopics\)[\s\S]*?updatePushTopics\(pushSubscription\.endpoint, topicsToSend\)/u,
    "pending and enabled topic choices persist through the real preferences hook"
  )
  assert.match(
    notificationsApi,
    /updateSubscriptionTopicsApiV1PushSubscribeTopicsPatch/u,
    "the preferences client uses the generated topic PATCH endpoint"
  )
  assert.match(
    notificationRouter,
    /@router\.get\(["']\/topics["'][\s\S]*?UserPushTopic\.user_id == user\.id/u,
    "the canonical preference read must be scoped to the authenticated user"
  )
  const adminRead = notificationRouter
    .split(/(?=^@router\.)/mu)
    .find((route) => /^@router\.get\(["']\/admin\/topics\/\{user_id\}["']/u.test(route))
  assert.ok(adminRead, "the admin topic read endpoint must exist")
  const adminReadSignature = adminRead.match(
    /^async def admin_get_user_topics\(([\s\S]*?)^\)/mu
  )?.[1]
  assert.ok(adminReadSignature, "the admin topic read must have an explicit dependency signature")
  assert.match(
    adminReadSignature,
    /user:\s*Annotated\[User, Depends\(get_current_admin_user_from_dishka\)\]/u,
    "only an administrator may inspect a selected user's canonical topics"
  )
  assert.match(
    adminRead,
    /target = \([\s\S]*?select\(User\)[\s\S]*?\.where\(User\.id == user_id\)/u,
    "the authorized admin read must target the requested user"
  )
  assert.ok(
    adminRead.indexOf("target =") >
      adminRead.indexOf(adminReadSignature) + adminReadSignature.length,
    "admin authorization resolves before target lookup in the endpoint body"
  )
  assert.match(spec, /subscriptionMayExist/u)
  assert.match(spec, /subscription\.unsubscribe\(\)/u)
  assert.match(spec, /entry\.email === email && entry\.full_name === fullName/u)
  assert.match(spec, /encodeURIComponent\(userId\)/u)
  assert.match(spec, /X-CSRF-Token/u)
  assert.doesNotMatch(spec, /page\.route\(|vi\.mock|push\/test|sendTest\(/u)
  assert.doesNotMatch(spec, /asyncpg|sqlalchemy|direct database|direct DB/u)
})
