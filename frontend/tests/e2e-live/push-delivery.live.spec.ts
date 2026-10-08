import { randomUUID } from "node:crypto"
import type { BrowserContext, Page } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
  test,
} from "./fixtures"

interface PermissionAuditEntry {
  isActive: boolean
}

interface NotificationRow {
  id: string
  title: string
  type: string | null
  url: string | null
  body: string | null
  topic?: string | null
  metadata?: Record<string, unknown>
  read: boolean
}

interface NotificationListResponse {
  items: NotificationRow[]
}

interface AdminUserRow {
  id: string
  email: string
  full_name: string | null
}

interface PushSubscriptionReceipt {
  endpoint?: unknown
}

interface LiveUserIdentity {
  id: string
  email?: string
  full_name: string | null
}

interface LiveGroupIdentity {
  id: string
  chat_type: string
  name: string | null
  created_by: string | null
  participants: { id: string }[]
}

interface LiveGroupList {
  items: LiveGroupIdentity[]
  has_more: boolean
  next_cursor: string | null
}

const readPermissionAudit = (page: Page): Promise<PermissionAuditEntry[]> =>
  page.evaluate(() => {
    try {
      return JSON.parse(
        sessionStorage.getItem("ue-push-permission-audit") ?? "[]"
      ) as PermissionAuditEntry[]
    } catch {
      return []
    }
  })

const installPermissionAudit = async (page: Page): Promise<void> => {
  await page.addInitScript(() => {
    if (typeof Notification === "undefined") return

    const nativeRequestPermission = Notification.requestPermission
    Object.defineProperty(Notification, "requestPermission", {
      configurable: true,
      value: (...args: Parameters<typeof Notification.requestPermission>) => {
        const raw = sessionStorage.getItem("ue-push-permission-audit")
        const entries = raw ? (JSON.parse(raw) as { isActive: boolean }[]) : []
        entries.push({ isActive: navigator.userActivation.isActive })
        sessionStorage.setItem("ue-push-permission-audit", JSON.stringify(entries))
        return nativeRequestPermission.apply(Notification, args)
      },
    })
  })
}

const registerSyntheticAccount = async (
  page: Page,
  fullName: string,
  email: string,
  password: string,
  markRegistrationAttempted: () => void
): Promise<void> => {
  await stubBreachedPasswordLookup(page)
  await page.goto("/register")
  await page.getByLabel("Имя", { exact: true }).fill(fullName)
  await page.getByRole("textbox", { name: "E-mail" }).fill(email)
  await page.getByLabel("Пароль", { exact: true }).fill(password)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(password)
  markRegistrationAttempted()
  await page.getByRole("button", { name: "Зарегистрироваться" }).click()
  await expect(page).toHaveURL(/\/login$/u)
  await loginWith(page, email, password)
}

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  fullName: string
): Promise<void> => {
  const query = new URLSearchParams({ search: fullName, limit: "200" })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  expect(response.status(), "admin locates the synthetic account for exact cleanup").toBe(200)

  const users = (await response.json()) as AdminUserRow[]
  const matches = users.filter((entry) => entry.email === email && entry.full_name === fullName)
  expect(
    matches.length,
    "cleanup resolves at most one exact synthetic identity"
  ).toBeLessThanOrEqual(1)
  const [match] = matches
  if (!match) return

  const deletion = await adminPage.evaluate(async (userId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, deleted: false }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const result = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await result.json().catch(() => null)) as { deleted?: boolean } | null
    return { status: result.status, deleted: body?.deleted === true }
  }, match.id)
  expect(deletion.status, "cleanup uses the CSRF-protected admin endpoint").toBe(200)
  expect(deletion.deleted, "cleanup deletes only the located synthetic account id").toBe(true)
}

const deleteOnlyTestChat = async (adminPage: Page, chatId: string): Promise<void> => {
  const deletion = await adminPage.evaluate(async (createdChatId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, resourceStatus: null as string | null }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch(`/api/v1/chats/${encodeURIComponent(createdChatId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await response.json().catch(() => null)) as { status?: string } | null
    return { status: response.status, resourceStatus: body?.status ?? null }
  }, chatId)
  expect(deletion.status, "cleanup deletes the exact test-created chat").toBe(200)
  expect(deletion.resourceStatus).toBe("deleted")
}

const getLiveUserIdentity = async (page: Page): Promise<LiveUserIdentity> => {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.status(), "the live participant session resolves to its own identity").toBe(200)
  return (await response.json()) as LiveUserIdentity
}

const selectGroupMember = async (page: Page, fullName: string): Promise<void> => {
  const search = page.getByRole("textbox", { name: "Поиск пользователей" })
  await search.fill(fullName)
  const option = page.getByRole("option").filter({ hasText: fullName })
  await expect(option).toHaveCount(1)
  await option.click()
}

const findOnlyOwnedGroup = async (
  ownerPage: Page,
  name: string,
  ownerId: string,
  expectedMemberIds: string[]
): Promise<string | null> => {
  const matches: LiveGroupIdentity[] = []
  let cursor: string | null = null

  do {
    const query = new URLSearchParams({ limit: "100" })
    if (cursor) query.set("cursor", cursor)
    const response = await ownerPage.request.get("/api/v1/chats?" + query.toString())
    expect(response.status(), "cleanup resolves only chats visible to the group owner").toBe(200)
    const pageBody = (await response.json()) as LiveGroupList
    matches.push(...pageBody.items.filter((chat) => chat.name === name))
    if (!pageBody.has_more) break
    expect(pageBody.next_cursor).toBeTruthy()
    cursor = pageBody.next_cursor
  } while (cursor)

  expect(
    matches.length,
    "the random group name resolves to at most one created chat"
  ).toBeLessThanOrEqual(1)
  const [group] = matches
  if (!group) return null
  if (typeof group.id !== "string" || group.id.length === 0) {
    throw new Error("the owned group response did not include a valid id")
  }
  expect(group.participants).toHaveLength(expectedMemberIds.length)
  expect(group.chat_type).toBe("group")
  expect(group.created_by).toBe(ownerId)
  expect(new Set(group.participants.map((participant) => participant.id))).toEqual(
    new Set(expectedMemberIds)
  )
  return group.id
}

const deleteOnlyTestGroupNotifications = async (page: Page, chatId: string): Promise<void> => {
  const path = "/messenger/" + chatId
  const notificationIds = (await listNotifications(page)).items
    .filter(
      (item) => item.url === path && (item.type === "chat.message" || item.type === "chat.reply")
    )
    .map((item) => item.id)

  for (const notificationId of notificationIds) {
    const deletion = await page.evaluate(async (createdNotificationId) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return { status: 0, ok: false }

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const response = await fetch(
        "/api/v1/notifications/" + encodeURIComponent(createdNotificationId),
        {
          method: "DELETE",
          credentials: "same-origin",
          headers: { "X-CSRF-Token": csrfToken },
        }
      )
      const body = (await response.json().catch(() => null)) as { ok?: boolean } | null
      return { status: response.status, ok: body?.ok === true }
    }, notificationId)
    expect(deletion.status, "cleanup removes a notification found only under this test chat").toBe(
      200
    )
    expect(deletion.ok).toBe(true)
  }
}

const listNotifications = async (page: Page): Promise<NotificationListResponse> => {
  const response = await page.request.get("/api/v1/notifications?limit=100")
  expect(response.status(), "the signed-in owner can read in-app notifications").toBe(200)
  return (await response.json()) as NotificationListResponse
}

const deleteOnlyTestNotification = async (
  page: Page,
  chatId: string,
  message: string,
  knownId: string | null
): Promise<void> => {
  let notificationId = knownId
  if (!notificationId) {
    const notifications = await listNotifications(page)
    const matches = notifications.items.filter(
      (item) =>
        item.type === "chat.message" && item.url === `/messenger/${chatId}` && item.body === message
    )
    expect(
      matches.length,
      "cleanup resolves at most one exact message notification"
    ).toBeLessThanOrEqual(1)
    notificationId = matches[0]?.id ?? null
  }
  if (!notificationId) return

  const deletion = await page.evaluate(async (createdNotificationId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, ok: false }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch(
      `/api/v1/notifications/${encodeURIComponent(createdNotificationId)}`,
      {
        method: "DELETE",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrfToken },
      }
    )
    const body = (await response.json().catch(() => null)) as { ok?: boolean } | null
    return { status: response.status, ok: body?.ok === true }
  }, notificationId)
  expect(deletion.status, "cleanup deletes the exact test-owned notification").toBe(200)
  expect(deletion.ok).toBe(true)
}

const unsubscribeOnlyNativeSubscription = async (
  page: Page,
  knownEndpoint: string | null
): Promise<boolean> =>
  page.evaluate(async (fallbackEndpoint) => {
    const registration = await navigator.serviceWorker.getRegistration()
    const subscription = await registration?.pushManager.getSubscription()
    const endpoint = subscription?.endpoint ?? fallbackEndpoint
    if (!endpoint) return !subscription

    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((cookiePart) => cookiePart.startsWith("csrf_token="))
    if (!csrfCookie) {
      if (subscription) await subscription.unsubscribe()
      return false
    }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch("/api/v1/push/unsubscribe", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({ endpoint }),
    })
    const browserUnsubscribed = subscription ? await subscription.unsubscribe() : true
    return response.ok && browserUnsubscribed
  }, knownEndpoint)

const closeContexts = async (contexts: BrowserContext[]): Promise<void> => {
  await Promise.all(contexts.map((context) => context.close()))
}

test("permission is requested only after the explicit settings action", async ({
  page,
  browser,
  browserName,
}, testInfo) => {
  test.skip(browserName !== "chromium", "native Notifications and PushManager require Chromium")

  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = randomUUID()
  const email = `live-push-permission-${testInfo.project.name}-${identity}@university.dev`
  const fullName = `Live Push Permission ${testInfo.project.name} ${identity}`
  const password = freshPassword()
  let registrationAttempted = false
  let adminContext: BrowserContext | null = null
  let adminPage: Page | null = null

  try {
    adminContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    adminPage = await adminContext.newPage()
    await loginAs(adminPage, "admin")
    await installPermissionAudit(page)
    await registerSyntheticAccount(page, fullName, email, password, () => {
      registrationAttempted = true
    })

    const beforeSettings = await page.evaluate(async () => {
      const supported =
        "serviceWorker" in navigator &&
        "PushManager" in window &&
        typeof Notification !== "undefined"
      if (!supported) return { supported, permission: "unsupported", hasSubscription: false }
      const registration = await navigator.serviceWorker.ready
      return {
        supported,
        permission: Notification.permission,
        hasSubscription: (await registration.pushManager.getSubscription()) !== null,
      }
    })
    expect(beforeSettings.supported, "Chromium exposes its native push APIs").toBe(true)
    expect(beforeSettings.permission, "the isolated browser starts undecided").toBe("default")
    expect(beforeSettings.hasSubscription, "the synthetic account starts unsubscribed").toBe(false)

    let subscribeRequests = 0
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/api/v1/push/subscribe"
      ) {
        subscribeRequests += 1
      }
    })

    await page.goto("/settings?tab=3")
    const pushSwitch = page.getByRole("switch", { name: "Включить уведомления" })
    await expect(pushSwitch).toBeVisible()
    await expect(pushSwitch).not.toBeChecked()

    const requestsBeforeAction = await readPermissionAudit(page)
    const subscriptionsBeforeAction = subscribeRequests
    expect(requestsBeforeAction).toHaveLength(0)
    expect(subscriptionsBeforeAction).toBe(0)

    await pushSwitch.click()
    await expect.poll(async () => (await readPermissionAudit(page)).length).toBe(1)
    const requestsAfterAction = await readPermissionAudit(page)
    expect(requestsAfterAction[0]?.isActive, "the native permission call has a user gesture").toBe(
      true
    )
  } finally {
    if (registrationAttempted && adminPage) {
      await deleteOnlyCreatedAccount(adminPage, email, fullName)
    }
    if (adminContext) await adminContext.close()
  }
})

test("chat message reaches Chromium through its real push subscription", async ({
  page,
  browser,
  browserName,
}, testInfo) => {
  test.skip(browserName !== "chromium", "native Notifications and PushManager require Chromium")

  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = randomUUID()
  const email = `live-push-delivery-${testInfo.project.name}-${identity}@university.dev`
  const fullName = `Live Web Push Recipient ${testInfo.project.name} ${identity}`
  const message = `live-webpush-${identity}`
  const password = freshPassword()
  let registrationAttempted = false
  let subscriptionMayExist = false
  let subscriptionEndpoint: string | null = null
  let chatId: string | null = null
  let notificationId: string | null = null
  const contexts: BrowserContext[] = []
  let testFailure: unknown
  let testFailed = false

  try {
    const origin = new URL(liveBaseUrl).origin
    await page.context().grantPermissions(["notifications"], { origin })

    const adminContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    contexts.push(adminContext)
    const adminPage = await adminContext.newPage()
    await loginAs(adminPage, "admin")

    const senderContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    contexts.push(senderContext)
    const senderPage = await senderContext.newPage()
    await loginAs(senderPage, "student")

    await registerSyntheticAccount(page, fullName, email, password, () => {
      registrationAttempted = true
    })
    const identityResponse = await page.request.get("/api/v1/users/me")
    expect(identityResponse.status(), "the push recipient is authenticated as itself").toBe(200)
    const identityBody = (await identityResponse.json()) as { email?: string }
    expect(identityBody.email).toBe(email)

    const initialPushState = await page.evaluate(async () => {
      const supported =
        "serviceWorker" in navigator &&
        "PushManager" in window &&
        typeof Notification !== "undefined"
      if (!supported) return { supported, permission: "unsupported", hasSubscription: false }
      const registration = await navigator.serviceWorker.ready
      return {
        supported,
        permission: Notification.permission,
        hasSubscription: (await registration.pushManager.getSubscription()) !== null,
      }
    })
    expect(initialPushState.supported).toBe(true)
    expect(initialPushState.permission).toBe("granted")
    expect(initialPushState.hasSubscription).toBe(false)

    await page.goto("/settings?tab=3")
    const pushSwitch = page.getByRole("switch", { name: "Включить уведомления" })
    await expect(pushSwitch).toBeVisible()
    await expect(pushSwitch).not.toBeChecked()

    const subscribePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/push/subscribe"
    )
    subscriptionMayExist = true
    await pushSwitch.click()
    const subscribeResponse = await subscribePromise
    expect(subscribeResponse.status(), "the explicit opt-in stores a real browser endpoint").toBe(
      200
    )
    const subscriptionReceipt = (await subscribeResponse.json()) as PushSubscriptionReceipt
    if (typeof subscriptionReceipt.endpoint !== "string") {
      throw new Error("the server push binding did not include its endpoint")
    }
    subscriptionEndpoint = subscriptionReceipt.endpoint

    const subscribed = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()
      if (!subscription) return { endpoint: null, providerIssued: false }
      const endpoint = new URL(subscription.endpoint)
      return {
        endpoint: subscription.endpoint,
        providerIssued: endpoint.protocol === "https:" && endpoint.hostname !== location.hostname,
      }
    })
    expect(
      subscribed.providerIssued,
      "the service worker owns a provider-issued HTTPS subscription"
    ).toBe(true)
    expect(
      subscribed.endpoint,
      "the persisted server binding belongs to this native browser endpoint"
    ).toBe(subscriptionEndpoint)
    await expect(pushSwitch).toBeChecked()

    await senderPage.goto("/messenger")
    await senderPage.getByRole("button", { name: "Новый чат", exact: true }).click()
    await senderPage.getByRole("textbox", { name: "Поиск пользователей" }).fill(fullName)
    const recipientOption = senderPage.getByRole("option").filter({ hasText: fullName })
    await expect(recipientOption).toHaveCount(1)

    const chatResponsePromise = senderPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/chats"
    )
    await recipientOption.click()
    const chatResponse = await chatResponsePromise
    expect(chatResponse.status(), "the seeded sender creates a live direct chat").toBe(200)
    const createdChat = (await chatResponse.json()) as { id?: unknown }
    if (typeof createdChat.id !== "string" || createdChat.id.length === 0) {
      throw new Error("the live chat response did not include its created id")
    }
    chatId = createdChat.id

    await expect(senderPage).toHaveURL(/\/messenger\/[^/]+\/?$/u)
    await expect(senderPage.locator("#chat-message-input")).toBeVisible()
    const messageResponsePromise = senderPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages`
    )
    await senderPage.locator("#chat-message-input").fill(message)
    await senderPage.locator("#chat-send-btn").click()
    const messageResponse = await messageResponsePromise
    expect(messageResponse.status(), "the seeded sender posts a real message").toBe(200)

    await expect
      .poll(
        async () => {
          const notifications = await listNotifications(page)
          const matches = notifications.items.filter(
            (item) =>
              item.type === "chat.message" &&
              item.url === `/messenger/${chatId}` &&
              item.body === message
          )
          if (matches.length === 1) notificationId = matches[0]?.id ?? null
          return matches.length
        },
        { timeout: 45_000, message: "the message event creates one in-app notification" }
      )
      .toBe(1)

    const persistedNotification = (await listNotifications(page)).items.find(
      (item) => item.id === notificationId
    )
    expect(
      persistedNotification?.read,
      "Web Push delivery leaves its in-app notification unread"
    ).toBe(false)
    const expectedNotificationId = notificationId
    if (!expectedNotificationId) {
      throw new Error("the persisted test notification did not have an identity")
    }

    await expect
      .poll(
        async () =>
          page.evaluate(async (expectedId) => {
            const registration = await navigator.serviceWorker.ready
            const activeNotifications = await registration.getNotifications()
            return activeNotifications.filter((notification) => notification.tag === expectedId)
              .length
          }, expectedNotificationId),
        {
          timeout: 60_000,
          message: "a real Web Push shows a notification tagged with its persisted identity",
        }
      )
      .toBe(1)

    const notificationsWithTag = await page.evaluate(async (expectedId) => {
      const registration = await navigator.serviceWorker.ready
      const activeNotifications = await registration.getNotifications()
      return activeNotifications
        .filter((notification) => notification.tag === expectedId)
        .map((notification) => {
          const rawData = notification.data
          const data =
            rawData && typeof rawData === "object" ? (rawData as Record<string, unknown>) : {}
          return {
            body: notification.body,
            tag: notification.tag,
            notificationId: typeof data.notificationId === "string" ? data.notificationId : null,
            url: typeof data.url === "string" ? data.url : null,
          }
        })
    }, expectedNotificationId)
    expect(
      notificationsWithTag,
      "duplicate pushes share one native notification identity"
    ).toHaveLength(1)
    const deliveredNotification = notificationsWithTag[0]
    expect(deliveredNotification?.body).toBe(message)
    expect(deliveredNotification?.tag).toBe(expectedNotificationId)
    expect(deliveredNotification?.notificationId).toBe(expectedNotificationId)
    expect(deliveredNotification?.url).toBe(`/messenger/${chatId}`)
  } catch (error) {
    testFailure = error
    testFailed = true
  }

  {
    const adminContext = contexts[0]
    const adminPage = adminContext?.pages()[0] ?? null
    const cleanupErrors: unknown[] = []
    const attemptCleanup = async (action: () => Promise<void>) => {
      try {
        await action()
      } catch (error) {
        cleanupErrors.push(error)
      }
    }

    if (subscriptionMayExist) {
      await attemptCleanup(async () => {
        expect(
          await unsubscribeOnlyNativeSubscription(page, subscriptionEndpoint),
          "cleanup removes only this context's exact browser endpoint and server binding"
        ).toBe(true)
      })
    }
    if (chatId) {
      await attemptCleanup(() => deleteOnlyTestNotification(page, chatId!, message, notificationId))
      if (adminPage) await attemptCleanup(() => deleteOnlyTestChat(adminPage, chatId!))
    }
    if (registrationAttempted && adminPage) {
      await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage, email, fullName))
    }
    try {
      await closeContexts(contexts)
    } catch (error) {
      cleanupErrors.push(error)
    }
    if (testFailed && cleanupErrors.length > 0) {
      throw new AggregateError(
        [testFailure, ...cleanupErrors],
        "live Web Push acceptance and exact-resource cleanup both failed"
      )
    }
    if (testFailed) throw testFailure
    if (cleanupErrors.length > 0)
      throw new AggregateError(
        cleanupErrors,
        "test-owned Web Push resources were not fully cleaned"
      )
  }
})

test("quoted group author gets one chat.reply push with group context and no generic duplicate", async ({
  page,
  browser,
  browserName,
}, testInfo) => {
  test.skip(browserName !== "chromium", "native Notifications and PushManager require Chromium")

  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = randomUUID()
  const email = "live-group-push-" + testInfo.project.name + "-" + identity + "@university.dev"
  const fullName = "Live Group Push Author " + testInfo.project.name + " " + identity
  const groupName = "Live Web Push Reply Group " + testInfo.project.name + " " + identity
  const quotedText = "live-group-quoted-" + identity
  const replyText = "live-group-reply-" + identity
  const password = freshPassword()
  let registrationAttempted = false
  let subscriptionMayExist = false
  let subscriptionEndpoint: string | null = null
  let chatId: string | null = null
  let groupCreationAttempted = false
  let expectedMemberIds: string[] | null = null
  let ownerId: string | null = null
  let adminPage: Page | null = null
  let ownerPage: Page | null = null
  let thirdMemberPage: Page | null = null
  const contexts: BrowserContext[] = []
  let testFailure: unknown
  let testFailed = false

  try {
    const origin = new URL(liveBaseUrl).origin
    await page.context().grantPermissions(["notifications"], { origin })

    const adminContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    contexts.push(adminContext)
    adminPage = await adminContext.newPage()
    await loginAs(adminPage, "admin")

    const ownerContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    contexts.push(ownerContext)
    const groupOwnerPage = await ownerContext.newPage()
    ownerPage = groupOwnerPage
    await loginAs(groupOwnerPage, "student")

    const thirdMemberContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    contexts.push(thirdMemberContext)
    const groupThirdMemberPage = await thirdMemberContext.newPage()
    thirdMemberPage = groupThirdMemberPage
    await loginAs(groupThirdMemberPage, "teacher")

    await registerSyntheticAccount(page, fullName, email, password, () => {
      registrationAttempted = true
    })
    const quotedAuthor = await getLiveUserIdentity(page)
    expect(quotedAuthor.email).toBe(email)
    expect(quotedAuthor.full_name).toBeTruthy()

    const owner = await getLiveUserIdentity(groupOwnerPage)
    const thirdMember = await getLiveUserIdentity(groupThirdMemberPage)
    ownerId = owner.id
    if (typeof owner.full_name !== "string" || owner.full_name.length === 0) {
      throw new Error("the group reply sender has no display name")
    }
    const ownerName = owner.full_name
    expect(thirdMember.full_name).toBeTruthy()
    const participantIds = [quotedAuthor.id, owner.id, thirdMember.id]
    expectedMemberIds = participantIds
    expect(new Set(participantIds).size, "the group has three distinct real users").toBe(3)

    const initialPushState = await page.evaluate(async () => {
      const supported =
        "serviceWorker" in navigator &&
        "PushManager" in window &&
        typeof Notification !== "undefined"
      if (!supported) return { supported, permission: "unsupported", hasSubscription: false }
      const registration = await navigator.serviceWorker.ready
      return {
        supported,
        permission: Notification.permission,
        hasSubscription: (await registration.pushManager.getSubscription()) !== null,
      }
    })
    expect(initialPushState.supported).toBe(true)
    expect(initialPushState.permission).toBe("granted")
    expect(initialPushState.hasSubscription).toBe(false)

    await page.goto("/settings?tab=3")
    const pushSwitch = page.getByRole("switch", {
      name: "Включить уведомления",
    })
    await expect(pushSwitch).toBeVisible()
    await expect(pushSwitch).not.toBeChecked()

    const subscribePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/push/subscribe"
    )
    subscriptionMayExist = true
    await pushSwitch.click()
    const subscribeResponse = await subscribePromise
    expect(subscribeResponse.status(), "explicit opt-in stores a real browser endpoint").toBe(200)
    const subscriptionReceipt = (await subscribeResponse.json()) as PushSubscriptionReceipt
    if (typeof subscriptionReceipt.endpoint !== "string") {
      throw new Error("the server push binding did not include its endpoint")
    }
    subscriptionEndpoint = subscriptionReceipt.endpoint

    const subscribed = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()
      if (!subscription) return { endpoint: null, providerIssued: false }
      const endpoint = new URL(subscription.endpoint)
      return {
        endpoint: subscription.endpoint,
        providerIssued: endpoint.protocol === "https:" && endpoint.hostname !== location.hostname,
      }
    })
    expect(subscribed.providerIssued, "Chromium owns a provider-issued HTTPS subscription").toBe(
      true
    )
    expect(subscribed.endpoint).toBe(subscriptionEndpoint)
    await expect(pushSwitch).toBeChecked()

    await groupOwnerPage.goto("/messenger")
    await groupOwnerPage.getByRole("button", { name: "Новый чат", exact: true }).click()
    await groupOwnerPage.getByRole("tab", { name: "Группа", exact: true }).click()
    await groupOwnerPage.getByRole("textbox", { name: "Название группы" }).fill(groupName)
    await selectGroupMember(groupOwnerPage, quotedAuthor.full_name!)
    await selectGroupMember(groupOwnerPage, thirdMember.full_name!)

    const createGroupPromise = groupOwnerPage.waitForResponse((response) => {
      return (
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/chats/groups"
      )
    })
    groupCreationAttempted = true
    await groupOwnerPage.getByRole("button", { name: "Создать группу", exact: true }).click()
    const createGroupResponse = await createGroupPromise
    expect(
      createGroupResponse.status(),
      "the owner creates a real group with all three members"
    ).toBe(200)
    const group = (await createGroupResponse.json()) as LiveGroupIdentity
    if (typeof group.id !== "string" || group.id.length === 0)
      throw new Error("the created group response did not include its id")
    expect(group.chat_type).toBe("group")
    expect(group.name).toBe(groupName)
    expect(group.created_by).toBe(owner.id)
    expect(group.participants).toHaveLength(3)
    expect(new Set(group.participants.map((participant) => participant.id))).toEqual(
      new Set(participantIds)
    )
    chatId = group.id

    await page.goto("/messenger/" + chatId)
    await groupOwnerPage.goto("/messenger/" + chatId)
    const quotedAuthorInput = page.locator("#chat-message-input")
    await expect(quotedAuthorInput).toBeVisible()

    const quotedMessageResponsePromise = page.waitForResponse((response) => {
      return (
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/chats/" + chatId + "/messages"
      )
    })
    await quotedAuthorInput.fill(quotedText)
    await page.locator("#chat-send-btn").click()
    const quotedMessageResponse = await quotedMessageResponsePromise
    expect(quotedMessageResponse.status(), "the quoted author posts a real group message").toBe(200)
    const quotedMessage = (await quotedMessageResponse.json()) as {
      id?: unknown
      content?: unknown
    }
    if (typeof quotedMessage.id !== "string" || quotedMessage.id.length === 0) {
      throw new Error("the quoted message response did not include its id")
    }
    expect(quotedMessage.content).toBe(quotedText)
    const quotedMessageId = quotedMessage.id

    const ownerLog = groupOwnerPage.getByRole("log", { name: /Сообщения чата/i })
    await expect(ownerLog.getByText(quotedText, { exact: true })).toBeVisible()
    const quotedMessageRow = ownerLog
      .getByText(quotedText, { exact: true })
      .locator(
        "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
      )
    await quotedMessageRow.getByRole("button", { name: "Ответить", exact: true }).click()

    const replyMessageResponsePromise = groupOwnerPage.waitForResponse((response) => {
      return (
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/chats/" + chatId + "/messages"
      )
    })
    await groupOwnerPage.locator("#chat-message-input").fill(replyText)
    await groupOwnerPage.locator("#chat-send-btn").click()
    const replyMessageResponse = await replyMessageResponsePromise
    expect(replyMessageResponse.status(), "the group reply is submitted through the real UI").toBe(
      200
    )
    const replyMessage = (await replyMessageResponse.json()) as {
      id?: unknown
      content?: unknown
      reply_to?: { id?: unknown } | null
    }
    if (typeof replyMessage.id !== "string" || replyMessage.id.length === 0) {
      throw new Error("the reply response did not include its id")
    }
    expect(replyMessage.content).toBe(replyText)
    expect(replyMessage.reply_to?.id, "the posted message quotes the synthetic author").toBe(
      quotedMessageId
    )
    const replyMessageId = replyMessage.id
    const chatPath = "/messenger/" + chatId
    const expectedReplyBody = ownerName + ": " + replyText

    let replyNotificationId: string | null = null
    await expect
      .poll(
        async () => {
          const notifications = await listNotifications(page)
          const matches = notifications.items.filter(
            (item) =>
              item.type === "chat.reply" &&
              item.url === chatPath &&
              item.title === groupName &&
              item.body === expectedReplyBody
          )
          if (matches.length === 1) replyNotificationId = matches[0]?.id ?? null
          return matches.length
        },
        {
          timeout: 45_000,
          message: "the quoted author gets one persisted group reply notification",
        }
      )
      .toBe(1)

    const quotedAuthorNotifications = await listNotifications(page)
    const quotedAuthorReplies = quotedAuthorNotifications.items.filter(
      (item) =>
        item.type === "chat.reply" &&
        item.url === chatPath &&
        item.title === groupName &&
        item.body === expectedReplyBody
    )
    expect(quotedAuthorReplies).toHaveLength(1)
    const inAppReply = quotedAuthorReplies[0]
    expect(inAppReply?.read, "the reply notification remains unread").toBe(false)
    expect(inAppReply?.topic).toBe("chat.message.created")
    expect(inAppReply?.metadata).toMatchObject({
      notificationId: replyNotificationId,
      topic: "chat.message.created",
      type: "chat.reply",
      url: chatPath,
    })
    const quotedAuthorGenericReplies = quotedAuthorNotifications.items.filter(
      (item) =>
        item.type === "chat.message" &&
        item.url === chatPath &&
        item.title === groupName &&
        item.body === expectedReplyBody
    )
    expect(
      quotedAuthorGenericReplies,
      "the quoted author is not also sent the generic message notification"
    ).toHaveLength(0)

    let thirdMemberGenericId: string | null = null
    await expect
      .poll(
        async () => {
          const notifications = await listNotifications(groupThirdMemberPage)
          const matches = notifications.items.filter(
            (item) =>
              item.type === "chat.message" &&
              item.url === chatPath &&
              item.title === groupName &&
              item.body === expectedReplyBody
          )
          if (matches.length === 1) thirdMemberGenericId = matches[0]?.id ?? null
          return matches.length
        },
        {
          timeout: 45_000,
          message: "the other member keeps one generic group notification",
        }
      )
      .toBe(1)
    const thirdMemberNotifications = (await listNotifications(groupThirdMemberPage)).items
    const thirdMemberGenericNotifications = thirdMemberNotifications.filter(
      (item) =>
        item.type === "chat.message" &&
        item.url === chatPath &&
        item.title === groupName &&
        item.body === expectedReplyBody
    )
    expect(
      thirdMemberGenericNotifications,
      "the other member has one final generic group notification after delivery settles"
    ).toHaveLength(1)
    const thirdMemberReplyNotification = thirdMemberGenericNotifications[0]
    expect(thirdMemberReplyNotification?.id).toBe(thirdMemberGenericId)
    expect(thirdMemberReplyNotification?.topic).toBe("chat.message.created")
    expect(thirdMemberReplyNotification?.read).toBe(false)
    expect(thirdMemberReplyNotification?.title).toBe(groupName)
    expect(thirdMemberReplyNotification?.body).toBe(expectedReplyBody)

    const thirdMemberReplyNotifications = (
      await listNotifications(groupThirdMemberPage)
    ).items.filter((item) => item.type === "chat.reply" && item.url === chatPath)
    expect(
      thirdMemberReplyNotifications,
      "the unquoted member does not receive reply-specific notification"
    ).toHaveLength(0)

    const expectedNotificationId = replyNotificationId
    if (!expectedNotificationId) {
      throw new Error("the persisted group reply notification did not have an identity")
    }
    await expect
      .poll(
        async () =>
          page.evaluate(async (expectedId) => {
            const registration = await navigator.serviceWorker.ready
            const activeNotifications = await registration.getNotifications()
            return activeNotifications.filter((notification) => notification.tag === expectedId)
              .length
          }, expectedNotificationId),
        {
          timeout: 60_000,
          message: "the native reply push is tagged with the persisted notification identity",
        }
      )
      .toBe(1)

    const nativeReplyNotifications = await page.evaluate(async (expectedId) => {
      const registration = await navigator.serviceWorker.ready
      const activeNotifications = await registration.getNotifications()
      return activeNotifications
        .filter((notification) => notification.tag === expectedId)
        .map((notification) => {
          const rawData = notification.data
          const data =
            rawData && typeof rawData === "object" ? (rawData as Record<string, unknown>) : {}
          return {
            title: notification.title,
            body: notification.body,
            tag: notification.tag,
            notificationId: typeof data.notificationId === "string" ? data.notificationId : null,
            topic: typeof data.topic === "string" ? data.topic : null,
            type: typeof data.type === "string" ? data.type : null,
            url: typeof data.url === "string" ? data.url : null,
            chatId: typeof data.chatId === "string" ? data.chatId : null,
            repliedToMessageId:
              typeof data.repliedToMessageId === "string" ? data.repliedToMessageId : null,
            replyingMessageId:
              typeof data.replyingMessageId === "string" ? data.replyingMessageId : null,
            senderId: typeof data.senderId === "string" ? data.senderId : null,
          }
        })
    }, expectedNotificationId)
    expect(
      nativeReplyNotifications,
      "duplicate delivery replaces the same persisted native notification identity"
    ).toHaveLength(1)
    const nativeReply = nativeReplyNotifications[0]
    expect(nativeReply?.title).toBe(groupName)
    expect(nativeReply?.body).toBe(expectedReplyBody)
    expect(nativeReply?.tag).toBe(expectedNotificationId)
    expect(nativeReply?.notificationId).toBe(expectedNotificationId)
    expect(nativeReply?.topic).toBe("chat.message.created")
    expect(nativeReply?.type).toBe("chat.reply")
    expect(nativeReply?.url).toBe(chatPath)
    expect(nativeReply?.chatId).toBe(chatId)
    expect(nativeReply?.repliedToMessageId).toBe(quotedMessageId)
    expect(nativeReply?.replyingMessageId).toBe(replyMessageId)
    expect(nativeReply?.senderId).toBe(owner.id)
  } catch (error) {
    testFailure = error
    testFailed = true
  }

  {
    const cleanupErrors: unknown[] = []
    const attemptCleanup = async (action: () => Promise<void>) => {
      try {
        await action()
      } catch (error) {
        cleanupErrors.push(error)
      }
    }

    if (subscriptionMayExist) {
      await attemptCleanup(async () => {
        expect(
          await unsubscribeOnlyNativeSubscription(page, subscriptionEndpoint),
          "cleanup removes only this test's exact push endpoint and server binding"
        ).toBe(true)
      })
    }

    const cleanupGroup: { id: string | null } = { id: null }
    if (groupCreationAttempted && ownerPage && ownerId && expectedMemberIds) {
      await attemptCleanup(async () => {
        const resolvedGroupId = await findOnlyOwnedGroup(
          ownerPage!,
          groupName,
          ownerId!,
          expectedMemberIds!
        )
        if (!resolvedGroupId) return
        if (chatId && resolvedGroupId !== chatId) {
          throw new Error("the owned group id changed before cleanup")
        }
        cleanupGroup.id = resolvedGroupId
      })
    }
    const ownedCleanupGroupId = cleanupGroup.id
    if (ownedCleanupGroupId) {
      for (const memberPage of [page, ownerPage, thirdMemberPage]) {
        if (memberPage) {
          await attemptCleanup(() =>
            deleteOnlyTestGroupNotifications(memberPage, ownedCleanupGroupId)
          )
        }
      }
      if (adminPage) await attemptCleanup(() => deleteOnlyTestChat(adminPage!, ownedCleanupGroupId))
    }
    if (registrationAttempted && adminPage) {
      await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage!, email, fullName))
    }
    try {
      await closeContexts(contexts)
    } catch (error) {
      cleanupErrors.push(error)
    }

    if (testFailed && cleanupErrors.length > 0) {
      throw new AggregateError(
        [testFailure, ...cleanupErrors],
        "group Web Push acceptance and exact-resource cleanup both failed"
      )
    }
    if (testFailed) throw testFailure
    if (cleanupErrors.length > 0) {
      throw new AggregateError(
        cleanupErrors,
        "test-owned group, notifications, account, and push subscription were not fully cleaned"
      )
    }
  }
})
