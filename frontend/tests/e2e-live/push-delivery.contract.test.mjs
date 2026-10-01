import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./push-delivery.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const serviceWorkerUrl = new URL("../../src/sw/push.ts", import.meta.url)
const chatNotificationUrl = new URL(
  "../../../app/services/chat/notification_service.py",
  import.meta.url
)
const deliveryUrl = new URL("../../../app/services/notifications/delivery.py", import.meta.url)
const notificationContractUrl = new URL(
  "../../../app/core/notification_contract.py",
  import.meta.url
)
const notificationSchemaUrl = new URL(
  "../../../app/schemas/notification_delivery.py",
  import.meta.url
)
const notificationHelpersUrl = new URL("../../src/push/notification-helpers.ts", import.meta.url)
const liveComposeUrl = new URL("../../../docker-compose.live.yml", import.meta.url)

test("live Chromium proves post-action permission and real service-worker Web Push delivery", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the live push delivery acceptance scenario must exist")
  }

  const [
    config,
    serviceWorker,
    chatNotification,
    delivery,
    notificationContract,
    notificationSchema,
    notificationHelpers,
    liveCompose,
  ] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(serviceWorkerUrl, "utf8"),
    readFile(chatNotificationUrl, "utf8"),
    readFile(deliveryUrl, "utf8"),
    readFile(notificationContractUrl, "utf8"),
    readFile(notificationSchemaUrl, "utf8"),
    readFile(notificationHelpersUrl, "utf8"),
    readFile(liveComposeUrl, "utf8"),
  ])

  assert.match(spec, /permission is requested only after the explicit settings action/u)
  assert.match(spec, /chat message reaches Chromium through its real push subscription/u)
  assert.match(spec, /browserName !== "chromium"/u)
  assert.match(spec, /navigator\.userActivation\.isActive/u)
  assert.match(spec, /Notification\.requestPermission/u)
  assert.match(spec, /registration\.pushManager\.getSubscription\(\)/u)
  assert.match(spec, /registration\.getNotifications\(\)/u)
  assert.match(spec, /interface NotificationRow[\s\S]*?read: boolean/u)
  assert.match(spec, /persistedNotification\?\.read[\s\S]*?\.toBe\(false\)/u)
  assert.match(spec, /notification\.tag[\s\S]*?expectedNotificationId/u)
  assert.match(spec, /data\.notificationId[\s\S]*?expectedNotificationId/u)
  assert.match(spec, /notificationsWithTag[\s\S]*?\.toHaveLength\(\s*1\s*\)/u)
  assert.match(spec, /await page\.context\(\)\.grantPermissions\(\["notifications"\]/u)
  assert.match(spec, /await stubBreachedPasswordLookup\(page\)/u)
  assert.match(
    spec,
    /const installPermissionAudit = async[\s\S]*?page\.addInitScript\([\s\S]*?nativeRequestPermission\.apply/u
  )
  assert.match(spec, /loginAs\(senderPage, "student"\)/u)
  assert.match(spec, /getByRole\("button", \{ name: "Новый чат", exact: true \}\)/u)
  assert.match(spec, /\/api\/v1\/chats/u)
  assert.match(spec, /\/api\/v1\/chats\/\$\{chatId\}\/messages/u)
  assert.match(spec, /await expect\.poll\([\s\S]*?getNotifications\(\)[\s\S]*?message/u)
  assert.match(spec, /\/api\/v1\/push\/unsubscribe/u)
  assert.match(spec, /subscription\.unsubscribe\(\)/u)
  assert.match(spec, /interface PushSubscriptionReceipt[\s\S]*?endpoint\?: unknown/u)
  assert.match(spec, /let subscriptionEndpoint: string \| null = null/u)
  assert.match(
    spec,
    /subscription\?\.endpoint \?\? fallbackEndpoint/u,
    "cleanup must use the captured server endpoint if browser subscription state disappeared"
  )
  assert.match(
    spec,
    /if \(!csrfCookie\) \{\s*if \(subscription\) await subscription\.unsubscribe\(\)/u,
    "cleanup must fail closed without dereferencing an absent browser subscription"
  )
  assert.match(
    spec,
    /unsubscribeOnlyNativeSubscription\(page, subscriptionEndpoint\)/u,
    "failure cleanup must revoke only the exact endpoint created by this test"
  )
  assert.match(
    spec,
    /subscribed\.endpoint[\s\S]*?toBe\(subscriptionEndpoint\)/u,
    "the stored server binding must match the native browser endpoint"
  )
  assert.match(spec, /const deleteOnlyTestChat/u)
  assert.match(spec, /const deleteOnlyCreatedAccount/u)
  assert.match(spec, /entry\.email === email && entry\.full_name === fullName/u)
  assert.match(config, /name: "desktop"/u)
  assert.match(config, /name: "mobile"/u)
  assert.match(serviceWorker, /self\.addEventListener\("push"/u)
  assert.match(serviceWorker, /self\.registration\.showNotification\(title, options\)/u)
  assert.match(notificationHelpers, /tag: payload\.tag/u)
  assert.match(delivery, /payload_for_subscription\["tag"\] = str\(notification_id\)/u)
  assert.match(notificationContract, /"notificationId": str\(notification_id\)/u)
  assert.match(notificationSchema, /class NotificationOut[\s\S]*?read: bool/u)
  assert.match(chatNotification, /topic="chat\.message\.created"/u)
  assert.match(chatNotification, /push_via_outbox_only=True/u)
  assert.match(delivery, /webpush_module\._send_push_async\(subscription, prepared\)/u)
  assert.match(liveCompose, /VAPID_PRIVATE_KEY: \$\{LIVE_VAPID_PRIVATE_KEY/u)

  const permissionFlowStart = spec.indexOf(
    'test("permission is requested only after the explicit settings action'
  )
  const deliveryFlowStart = spec.indexOf(
    'test("chat message reaches Chromium through its real push subscription'
  )
  assert.ok(permissionFlowStart >= 0 && deliveryFlowStart > permissionFlowStart)
  const permissionFlow = spec.slice(permissionFlowStart, deliveryFlowStart)
  assert.match(permissionFlow, /Notification\.permission[\s\S]*?"default"/u)
  assert.match(permissionFlow, /await installPermissionAudit\(page\)/u)
  assert.match(permissionFlow, /requestsBeforeAction[\s\S]*?\.toHaveLength\(0\)/u)
  assert.match(
    permissionFlow,
    /pushSwitch\.click\(\)[\s\S]*?requestsAfterAction\[0\]\?\.isActive[\s\S]*?\.toBe\(\s*true\s*\)/u
  )
  assert.doesNotMatch(
    permissionFlow,
    /grantPermissions|page\.route|PushManager\.prototype|vi\.mock/u
  )

  assert.doesNotMatch(
    spec,
    /routeWebSocket|PushManager\.prototype|ServiceWorkerRegistration\.prototype|vi\.mock/u
  )
  assert.doesNotMatch(spec, /\/api\/v1\/push\/send|\/api\/v1\/notifications\/broadcast/u)
  assert.match(
    spec,
    /const subscribePromise = page\.waitForResponse\([\s\S]*?\/api\/v1\/push\/subscribe/u
  )
  assert.match(spec, /deleteOnlyCreatedAccount\(adminPage, email, fullName\)/u)
})
