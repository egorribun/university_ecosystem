import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import { runInNewContext } from "node:vm"
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
const notificationsApiUrl = new URL("../../../app/api/notifications.py", import.meta.url)
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
    notificationsApi,
    notificationHelpers,
    liveCompose,
  ] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(serviceWorkerUrl, "utf8"),
    readFile(chatNotificationUrl, "utf8"),
    readFile(deliveryUrl, "utf8"),
    readFile(notificationContractUrl, "utf8"),
    readFile(notificationSchemaUrl, "utf8"),
    readFile(notificationsApiUrl, "utf8"),
    readFile(notificationHelpersUrl, "utf8"),
    readFile(liveComposeUrl, "utf8"),
  ])

  assert.match(spec, /permission is requested only after the explicit settings action/u)
  assert.match(spec, /chat message reaches Chromium through its real push subscription/u)
  const chromiumChannelSetup = spec.indexOf('test.use({ channel: "chromium" })')
  const firstNativePushTest = spec.indexOf(
    'test("permission is requested only after the explicit settings action"'
  )
  assert.ok(
    chromiumChannelSetup >= 0 && chromiumChannelSetup < firstNativePushTest,
    "native push scenarios select full Chromium locally before declaring tests"
  )
  assert.doesNotMatch(
    config,
    /channel:\s*["']chromium["']/u,
    "full Chromium remains scoped to the native push spec"
  )
  assert.match(spec, /browserName !== "chromium"/u)
  assert.match(spec, /navigator\.userActivation\.isActive/u)
  assert.match(spec, /Notification\.requestPermission/u)
  assert.match(spec, /registration\.pushManager\.getSubscription\(\)/u)
  assert.match(spec, /registration\.getNotifications\(\)/u)
  assert.match(spec, /interface NotificationRow[\s\S]*?read: boolean/u)
  assert.match(
    spec,
    /interface NotificationListResponse[\s\S]*?has_more: boolean[\s\S]*?next_cursor: string \| null/u,
    "notification cleanup consumes the API's cursor-page contract"
  )
  assert.match(notificationsApi, /has_more=has_more,[\s\S]*?next_cursor=next_cursor/u)
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
    /const endpoint = subscription\?\.endpoint \?\? fallbackEndpoint\s+if \(!endpoint\) return false/u,
    "cleanup must fail closed when an attempted subscription has no deletable endpoint"
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
  assert.match(
    spec,
    /const listNotifications = async[\s\S]*?query\.set\("cursor", cursor\)/u,
    "notification reads can advance with the server-provided cursor"
  )
  assert.match(
    spec,
    /const listNotificationIdsMatching = async[\s\S]*?while \(true\)[\s\S]*?notificationPage\.has_more[\s\S]*?notificationPage\.next_cursor/u,
    "shared notification traversal walks all pages and rejects incomplete cursors"
  )
  assert.match(
    spec,
    /const listTestGroupNotificationIds = \(page: Page, path: string\)[\s\S]*?listNotificationIdsMatching/u,
    "group cleanup keeps its chat-path and message/reply filter on shared pagination"
  )
  assert.match(
    spec,
    /const findOnlyTestMessageNotificationId = async[\s\S]*?item\.type === "chat\.message" && item\.url === path && item\.body === message[\s\S]*?matches\.length > 1/u,
    "DM fallback requires the exact chat path, unique body, and chat.message type"
  )
  const directMessageCleanupStart = spec.indexOf("const deleteOnlyTestNotification")
  const directMessageCleanupEnd = spec.indexOf(
    "\n\nconst unsubscribeOnlyNativeSubscription",
    directMessageCleanupStart
  )
  const directMessageCleanup = spec.slice(directMessageCleanupStart, directMessageCleanupEnd)
  assert.match(
    directMessageCleanup,
    /if \(!notificationId\)[\s\S]*?findOnlyTestMessageNotificationId\(page, path, message\)[\s\S]*?if \(!notificationId\) return[\s\S]*?method: "DELETE"[\s\S]*?"X-CSRF-Token"/u,
    "DM cleanup deletes only the unique fallback ID with the owner page CSRF token"
  )
  assert.doesNotMatch(
    directMessageCleanup,
    /for \([^)]*notificationId of|DELETE[^\n]*notifications\/?\*|deleteAll/u,
    "DM cleanup never bulk-deletes shared-chat notifications"
  )
  const groupCleanupStart = spec.indexOf("const deleteOnlyTestGroupNotifications")
  const groupCleanupEnd = spec.indexOf("const listNotifications", groupCleanupStart)
  const groupCleanupFlow = spec.slice(groupCleanupStart, groupCleanupEnd)
  const collectGroupNotificationIds = groupCleanupFlow.indexOf(
    "const notificationIds = await listTestGroupNotificationIds(page, path)"
  )
  const deleteGroupNotifications = groupCleanupFlow.indexOf(
    "for (const notificationId of notificationIds)"
  )
  const verifyGroupNotifications = groupCleanupFlow.indexOf(
    "await listTestGroupNotificationIds(page, path)",
    deleteGroupNotifications
  )
  assert.ok(
    collectGroupNotificationIds >= 0 &&
      collectGroupNotificationIds < deleteGroupNotifications &&
      verifyGroupNotifications > deleteGroupNotifications,
    "cleanup snapshots all matching IDs before deleting and verifies none remain afterward"
  )
  const groupPaginationStart = spec.indexOf(
    "const listTestGroupNotificationIds = (page: Page, path: string)"
  )
  const groupPaginationEnd = spec.indexOf(
    "\n\nconst findOnlyTestMessageNotificationId",
    groupPaginationStart
  )
  const groupPaginationHelper = spec.slice(groupPaginationStart, groupPaginationEnd)
  assert.match(
    groupPaginationHelper,
    /item\.url === path[\s\S]*?item\.type === "chat\.message" \|\| item\.type === "chat\.reply"/u,
    "group pagination only targets chat-specific message and reply notifications"
  )
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

  assert.match(
    chatNotification,
    /if chat_type == "group":[\s\S]*?notif_title = chat_name or "Group"[\s\S]*?f"\{sender_name\}: \{body_preview\}"/u
  )
  assert.match(
    chatNotification,
    /type="chat\.reply"[\s\S]*?topic="chat\.message\.created"[\s\S]*?push_via_outbox_only=True/u
  )
  assert.match(notificationContract, /"chat\.": "chat\.message\.created"/u)
  assert.match(notificationsApi, /topic = infer_notification_topic\(type_raw\)/u)
  assert.match(notificationSchema, /topic: SanitizedInput/u)

  const groupReplyStart = spec.indexOf(
    'test("quoted group author gets one chat.reply push with group context and no generic duplicate'
  )
  assert.ok(groupReplyStart >= 0, "the real group-reply Web Push scenario must be registered")
  const groupReplyFlow = spec.slice(groupReplyStart)
  assert.match(groupReplyFlow, /getByRole\("tab", \{ name: "Группа", exact: true \}\)/u)
  assert.match(groupReplyFlow, /participantIds[\s\S]*?expectedMemberIds = participantIds/u)
  assert.match(groupReplyFlow, /new Set\(participantIds\)/u)
  const responseGroupId = groupReplyFlow.indexOf("chatId = group.id")
  assert.ok(
    responseGroupId >= 0,
    "the candidate ID is captured only after validating the create response"
  )
  for (const identityCheck of [
    'if (typeof group.id !== "string"',
    'expect(group.chat_type).toBe("group")',
    "expect(group.name).toBe(groupName)",
    "expect(group.created_by).toBe(owner.id)",
    "expect(group.participants).toHaveLength(3)",
    "expect(new Set(group.participants.map((participant) => participant.id)))",
  ]) {
    const checkIndex = groupReplyFlow.indexOf(identityCheck)
    assert.ok(
      checkIndex >= 0 && checkIndex < responseGroupId,
      `group identity check precedes cleanup ID capture: ${identityCheck}`
    )
  }
  assert.match(
    spec,
    /const findOnlyOwnedGroup = async[\s\S]*?expect\(group\.participants\)\.toHaveLength\(expectedMemberIds\.length\)[\s\S]*?new Set\(expectedMemberIds\)/u,
    "cleanup ownership requires exact participant count and membership"
  )
  const cleanupStart = groupReplyFlow.indexOf("const cleanupGroup:")
  const cleanupRevalidation = groupReplyFlow.indexOf("findOnlyOwnedGroup(", cleanupStart)
  const cleanupNotifications = groupReplyFlow.lastIndexOf(
    "deleteOnlyTestGroupNotifications(memberPage, ownedCleanupGroupId)"
  )
  const cleanupChat = groupReplyFlow.lastIndexOf(
    "deleteOnlyTestChat(adminPage!, ownedCleanupGroupId)"
  )
  assert.ok(
    cleanupRevalidation >= 0 &&
      cleanupRevalidation < cleanupNotifications &&
      cleanupRevalidation < cleanupChat,
    "cleanup re-resolves the unique owner-controlled group before deleting notifications or the chat"
  )
  assert.match(groupReplyFlow, /if \(chatId && resolvedGroupId !== chatId\)/u)
  assert.match(groupReplyFlow, /reply_to\?\.id[\s\S]*?quotedMessageId/u)
  assert.match(groupReplyFlow, /quotedAuthorReplies[\s\S]*?toHaveLength\(1\)/u)
  assert.match(groupReplyFlow, /quotedAuthorGenericReplies[\s\S]*?toHaveLength\(0\)/u)
  const finalGenericStart = groupReplyFlow.indexOf("const thirdMemberNotifications =")
  const thirdReplyStart = groupReplyFlow.indexOf(
    "const thirdMemberReplyNotifications",
    finalGenericStart
  )
  assert.ok(finalGenericStart >= 0 && thirdReplyStart > finalGenericStart)
  const finalGenericAssertions = groupReplyFlow.slice(finalGenericStart, thirdReplyStart)
  assert.match(
    finalGenericAssertions,
    /const thirdMemberGenericNotifications = thirdMemberNotifications\.filter\([\s\S]*?item\.type === "chat\.message"[\s\S]*?item\.url === chatPath[\s\S]*?item\.body === expectedReplyBody/u
  )
  assert.match(
    finalGenericAssertions,
    /expect\(\s*thirdMemberGenericNotifications[\s\S]*?toHaveLength\(1\)/u,
    "the final read after the poll still has exactly one generic notification"
  )
  const thirdReplyFilterEnd = groupReplyFlow.indexOf("    expect(", thirdReplyStart)
  assert.ok(thirdReplyFilterEnd > thirdReplyStart)
  const thirdReplyFilter = groupReplyFlow.slice(thirdReplyStart, thirdReplyFilterEnd)
  assert.match(
    thirdReplyFilter,
    /item\.type === "chat\.reply" && item\.url === chatPath/u,
    "the third-member exclusion scans every reply notification for the chat"
  )
  assert.doesNotMatch(
    thirdReplyFilter,
    /item\.(?:title|body)/u,
    "reply exclusion cannot hide notifications with unexpected title or body"
  )
  assert.match(
    groupReplyFlow.slice(thirdReplyFilterEnd),
    /thirdMemberReplyNotifications[\s\S]*?toHaveLength\(0\)/u,
    "the third member must not receive a reply-specific notification"
  )
  assert.match(groupReplyFlow, /inAppReply\?\.topic[\s\S]*?chat\.message\.created/u)
  assert.match(groupReplyFlow, /nativeReply\?\.notificationId[\s\S]*?expectedNotificationId/u)
  assert.match(groupReplyFlow, /nativeReply\?\.topic[\s\S]*?chat\.message\.created/u)
  assert.match(groupReplyFlow, /nativeReply\?\.repliedToMessageId[\s\S]*?quotedMessageId/u)
  assert.match(groupReplyFlow, /nativeReply\?\.replyingMessageId[\s\S]*?replyMessageId/u)
  assert.match(
    groupReplyFlow,
    /deleteOnlyTestGroupNotifications\(memberPage, ownedCleanupGroupId\)/u
  )
  assert.match(groupReplyFlow, /deleteOnlyTestChat\(adminPage!, ownedCleanupGroupId\)/u)
  assert.doesNotMatch(
    groupReplyFlow,
    /routeWebSocket|PushManager\.prototype|ServiceWorkerRegistration\.prototype|vi\.mock/u
  )
})

test("notification cleanup traverses all pages and keeps the DM fallback unique", async () => {
  const spec = await readFile(specUrl, "utf8")
  const helperStart = spec.indexOf("const listNotificationIdsMatching = async")
  const helperEnd = spec.indexOf("\n\nconst deleteOnlyTestNotification", helperStart)
  assert.ok(helperStart >= 0 && helperEnd > helperStart, "shared pagination helpers are present")

  const typescriptModule = await import("typescript")
  const typescript = typescriptModule.default ?? typescriptModule
  const compiled = typescript.transpileModule(spec.slice(helperStart, helperEnd), {
    compilerOptions: {
      target: typescript.ScriptTarget.ES2022,
      module: typescript.ModuleKind.None,
    },
  })
  const path = "/messenger/owned-chat"
  const calls = []
  const pages = new Map([
    [
      null,
      {
        items: [
          { id: "owned-group-message", url: path, type: "chat.message", body: "group body" },
          {
            id: "other-chat-same-body",
            url: "/messenger/other",
            type: "chat.message",
            body: "dm body",
          },
          { id: "same-chat-reply", url: path, type: "chat.reply", body: "dm body" },
          { id: "same-chat-other-body", url: path, type: "chat.message", body: "other body" },
        ],
        has_more: true,
        next_cursor: "cursor-1",
      },
    ],
    [
      "cursor-1",
      {
        items: [
          { id: "owned-group-reply", url: path, type: "chat.reply", body: "reply body" },
          { id: "dm-match-on-later-page", url: path, type: "chat.message", body: "dm body" },
          { id: "unrelated-type", url: path, type: "system", body: "dm body" },
        ],
        has_more: false,
        next_cursor: null,
      },
    ],
  ])
  const helpersFor = (listNotifications) =>
    runInNewContext(
      `${compiled.outputText}\n({ listTestGroupNotificationIds, findOnlyTestMessageNotificationId })`,
      { listNotifications }
    )
  const listNotifications = async (_page, cursor) => {
    calls.push(cursor)
    assert.ok(pages.has(cursor), "the helper requests only known continuation pages")
    return pages.get(cursor)
  }
  const helpers = helpersFor(listNotifications)

  assert.deepEqual(Array.from(await helpers.listTestGroupNotificationIds({}, path)), [
    "owned-group-message",
    "same-chat-reply",
    "same-chat-other-body",
    "owned-group-reply",
    "dm-match-on-later-page",
  ])
  assert.deepEqual(calls, [null, "cursor-1"])

  calls.length = 0
  assert.equal(
    await helpers.findOnlyTestMessageNotificationId({}, path, "dm body"),
    "dm-match-on-later-page"
  )
  assert.deepEqual(calls, [null, "cursor-1"])

  const duplicate = helpersFor(async (_page, cursor) => ({
    items: [
      {
        id: cursor ? "duplicate-two" : "duplicate-one",
        url: path,
        type: "chat.message",
        body: "dm body",
      },
    ],
    has_more: cursor === null,
    next_cursor: cursor === null ? "cursor-1" : null,
  }))
  await assert.rejects(
    () => duplicate.findOnlyTestMessageNotificationId({}, path, "dm body"),
    /multiple exact message notifications/u,
    "ambiguous cleanup fails closed instead of deleting multiple shared-chat notifications"
  )

  const incompletePage = helpersFor(async () => ({ items: [], next_cursor: null }))
  await assert.rejects(
    () => incompletePage.findOnlyTestMessageNotificationId({}, path, "dm body"),
    /omitted its continuation flag/u,
    "cleanup fails closed when a page omits has_more"
  )

  const brokenCursor = helpersFor(async (_page, cursor) => ({
    items: [],
    has_more: true,
    next_cursor: cursor ?? "repeat",
  }))
  await assert.rejects(
    () => brokenCursor.findOnlyTestMessageNotificationId({}, path, "dm body"),
    /invalid continuation cursor/u,
    "a repeated cursor fails closed instead of looping or leaving notifications behind"
  )

  const noMatch = helpersFor(async () => ({
    items: [],
    has_more: false,
    next_cursor: null,
  }))
  assert.equal(await noMatch.findOnlyTestMessageNotificationId({}, path, "missing"), null)
})
