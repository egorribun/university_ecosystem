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
  type: string | null
  url: string | null
  body: string | null
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
