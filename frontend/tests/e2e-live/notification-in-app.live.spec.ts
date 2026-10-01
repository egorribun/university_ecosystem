import { randomUUID } from "node:crypto"
import type { Page } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
  test,
} from "./fixtures"

interface NotificationRow {
  id: string
  type: string | null
  url: string | null
  body: string | null
  read: boolean
}

interface NotificationListResponse {
  items: NotificationRow[]
  unread_count: number
}

interface AdminUserRow {
  id: string
  email: string
  full_name: string | null
}

const registerAndLogin = async (
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

const readNotifications = async (page: Page): Promise<NotificationListResponse> => {
  const response = await page.request.get("/api/v1/notifications?limit=100")
  expect(response.status(), "the owner can read their in-app notifications").toBe(200)
  return (await response.json()) as NotificationListResponse
}

const waitForProfileUpdate = (page: Page) =>
  page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/users/me" &&
      response.request().method() === "PUT"
  )

const enableAllDayQuietHours = async (page: Page): Promise<void> => {
  await page.goto("/settings?tab=3")
  const quietHours = page.getByRole("switch", { name: "Включить тихий период", exact: true })
  await expect(quietHours).toBeVisible()
  if (!(await quietHours.isChecked())) {
    const enabled = waitForProfileUpdate(page)
    await quietHours.click()
    const response = await enabled
    expect(response.status(), "the owner enables quiet hours in settings").toBe(200)
  }

  const startTime = page.getByLabel("С", { exact: true })
  const endTime = page.getByLabel("До", { exact: true })
  await expect(startTime).toBeEnabled()
  await expect(endTime).toBeEnabled()
  const startSave = waitForProfileUpdate(page)
  await startTime.fill("00:00")
  await startTime.press("Tab")
  expect((await startSave).status(), "the all-day quiet-hours start persists").toBe(200)
  const endSave = waitForProfileUpdate(page)
  await endTime.fill("00:00")
  await endTime.press("Tab")
  expect((await endSave).status(), "the all-day quiet-hours end persists").toBe(200)

  const profileResponse = await page.request.get("/api/v1/users/me")
  expect(profileResponse.status(), "the owner can verify its quiet-hours profile").toBe(200)
  const quietHoursProfile = (await profileResponse.json()) as {
    dnd_enabled?: boolean
    dnd_start?: string | null
    dnd_end?: string | null
  }
  expect(quietHoursProfile.dnd_enabled).toBe(true)
  expect(quietHoursProfile.dnd_start).toMatch(/^00:00/u)
  expect(quietHoursProfile.dnd_end).toMatch(/^00:00/u)
}

const expectUnreadIndicator = async (page: Page, unreadCount: number): Promise<void> => {
  const trigger = page.locator("#global-notifications-btn")
  await expect(trigger).toBeVisible()
  if (unreadCount > 0) {
    await expect(trigger).toHaveAttribute("data-unread", "")
  } else {
    await expect(trigger).not.toHaveAttribute("data-unread")
  }
}

const findTestNotification = (
  notifications: NotificationListResponse,
  chatId: string,
  message: string
): NotificationRow[] =>
  notifications.items.filter(
    (item) =>
      item.type === "chat.message" && item.url === `/messenger/${chatId}` && item.body === message
  )

const deleteWithCurrentBrowserCsrf = async (
  page: Page,
  route: string
): Promise<{ status: number; ok: boolean; deleted: boolean; resourceStatus: string | null }> =>
  page.evaluate(async (deleteRoute) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, ok: false, deleted: false, resourceStatus: null }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch(deleteRoute, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await response.json().catch(() => null)) as {
      ok?: boolean
      deleted?: boolean
      status?: string
    } | null
    return {
      status: response.status,
      ok: body?.ok === true,
      deleted: body?.deleted === true,
      resourceStatus: typeof body?.status === "string" ? body.status : null,
    }
  }, route)

const deleteOnlyTestNotification = async (
  ownerPage: Page,
  chatId: string,
  message: string,
  knownNotificationId: string | null
): Promise<void> => {
  let notificationId = knownNotificationId
  if (!notificationId) {
    const notifications = await readNotifications(ownerPage)
    const matches = findTestNotification(notifications, chatId, message)
    expect(
      matches.length,
      "cleanup resolves at most the exact message notification"
    ).toBeLessThanOrEqual(1)
    notificationId = matches[0]?.id ?? null
  }
  if (!notificationId) return

  const deletion = await deleteWithCurrentBrowserCsrf(
    ownerPage,
    `/api/v1/notifications/${encodeURIComponent(notificationId)}`
  )
  expect(deletion.status, "cleanup deletes the exact test-owned notification").toBe(200)
  expect(deletion.ok).toBe(true)
}

const deleteOnlyTestChat = async (adminPage: Page, chatId: string): Promise<void> => {
  const deletion = await deleteWithCurrentBrowserCsrf(
    adminPage,
    `/api/v1/chats/${encodeURIComponent(chatId)}`
  )
  expect(deletion.status, "admin cleanup targets only the chat created in this test").toBe(200)
  expect(deletion.resourceStatus).toBe("deleted")
}

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  fullName: string
): Promise<void> => {
  const query = new URLSearchParams({ search: fullName, limit: "200" })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  expect(response.status(), "admin can locate the test-owned synthetic account").toBe(200)
  const users = (await response.json()) as AdminUserRow[]
  const matches = users.filter((entry) => entry.email === email && entry.full_name === fullName)
  expect(
    matches.length,
    "account cleanup requires one exact generated identity"
  ).toBeLessThanOrEqual(1)
  const [match] = matches
  if (!match) return

  const deletion = await deleteWithCurrentBrowserCsrf(
    adminPage,
    `/api/v1/users/${encodeURIComponent(match.id)}`
  )
  expect(deletion.status, "cleanup deletes only the exact generated account id").toBe(200)
  expect(deletion.deleted).toBe(true)
}

test.use({ trace: "off", screenshot: "off" })

test("chat message creates one in-app notification during quiet hours and remains read and unique after reload", async ({
  page,
  browser,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = randomUUID()
  const senderName = `Live Notification Sender ${testInfo.project.name} ${identity}`
  const recipientName = `Live Notification Recipient ${testInfo.project.name} ${identity}`
  const senderEmail = `live-notification-sender-${testInfo.project.name}-${identity}@university.dev`
  const recipientEmail = `live-notification-recipient-${testInfo.project.name}-${identity}@university.dev`
  const message = `live-in-app-${identity}`
  const senderPassword = freshPassword()
  const recipientPassword = freshPassword()
  let senderRegistrationAttempted = false
  let recipientRegistrationAttempted = false
  let chatId: string | null = null
  let testNotificationId: string | null = null

  const recipientContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const recipientPage = await recipientContext.newPage()
  const adminPage = await adminContext.newPage()
  let testFailure: unknown
  let testFailed = false

  try {
    await loginAs(adminPage, "admin")
    await registerAndLogin(page, senderName, senderEmail, senderPassword, () => {
      senderRegistrationAttempted = true
    })
    await registerAndLogin(recipientPage, recipientName, recipientEmail, recipientPassword, () => {
      recipientRegistrationAttempted = true
    })

    const initialNotifications = await readNotifications(recipientPage)
    const initialUnreadCount = initialNotifications.unread_count
    await expect(recipientPage.locator("#global-notifications-btn")).toBeVisible()
    await enableAllDayQuietHours(recipientPage)
    expect((await readNotifications(recipientPage)).unread_count).toBe(initialUnreadCount)

    await page.goto("/messenger")
    await page.getByRole("button", { name: "Новый чат", exact: true }).click()
    await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(recipientName)
    const recipientOption = page.getByRole("option").filter({ hasText: recipientName })
    await expect(recipientOption).toHaveCount(1)

    const chatResponsePromise = page.waitForResponse((response) => {
      return (
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/chats"
      )
    })
    await recipientOption.click()
    const chatResponse = await chatResponsePromise
    const createdChat = (await chatResponse.json()) as { id?: unknown }
    if (typeof createdChat.id !== "string" || createdChat.id.length === 0) {
      throw new Error("the live chat creation response did not include its exact id")
    }
    chatId = createdChat.id
    expect(chatResponse.status(), "the sender creates a real direct chat").toBe(200)

    await expect(page).toHaveURL(/\/messenger\/[^/]+\/?$/u)
    await expect(page.locator("#chat-message-input")).toBeVisible()
    const messageResponsePromise = page.waitForResponse((response) => {
      return (
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages`
      )
    })
    await page.locator("#chat-message-input").fill(message)
    await page.locator("#chat-send-btn").click()
    const messageResponse = await messageResponsePromise
    expect(messageResponse.status(), "the sender posts a real chat message").toBe(200)

    await expect
      .poll(
        async () =>
          findTestNotification(await readNotifications(recipientPage), chatId!, message).length,
        { timeout: 30_000, message: "the message notification is persisted for its recipient" }
      )
      .toBe(1)
    const createdNotifications = await readNotifications(recipientPage)
    const [createdNotification] = findTestNotification(createdNotifications, chatId, message)
    if (!createdNotification) {
      throw new Error("the synthetic chat message did not create its expected notification")
    }
    // Quiet hours suppress the Web Push presentation only. The durable in-app
    // notification and its unread count remain available to the signed-in user.
    expect(createdNotification.read).toBe(false)
    expect(createdNotifications.unread_count).toBe(initialUnreadCount + 1)
    const notificationId = createdNotification.id
    testNotificationId = notificationId

    await recipientPage.reload()
    await expect
      .poll(async () => {
        const state = await readNotificationsForState(recipientPage, chatId!, message)
        return {
          count: state.matches.length,
          id: state.matches[0]?.id,
          read: state.matches[0]?.read,
          unreadCount: state.unreadCount,
        }
      })
      .toEqual({ count: 1, id: notificationId, read: false, unreadCount: initialUnreadCount + 1 })
    await expectUnreadIndicator(recipientPage, initialUnreadCount + 1)
    await recipientPage.locator("#global-notifications-btn").click()
    const notificationDialog = recipientPage.locator("#notifications-center")
    await expect(notificationDialog).toBeVisible()
    const notificationCard = notificationDialog
      .locator(".relative.group")
      .filter({ hasText: message })
    await expect(notificationCard).toHaveCount(1)
    await expect(notificationCard.getByTitle("Прочитано", { exact: true })).toBeVisible()

    const markReadResponsePromise = recipientPage.waitForResponse((response) => {
      return (
        response.request().method() === "PATCH" &&
        new URL(response.url()).pathname === `/api/v1/notifications/${notificationId}/read`
      )
    })
    await notificationCard.getByTitle("Прочитано", { exact: true }).click()
    const markReadResponse = await markReadResponsePromise
    expect(markReadResponse.status(), "the owner marks the in-app notification as read").toBe(200)

    await expect
      .poll(async () => {
        const state = await readNotificationsForState(recipientPage, chatId!, message)
        return {
          count: state.matches.length,
          id: state.matches[0]?.id,
          read: state.matches[0]?.read,
          unreadCount: state.unreadCount,
        }
      })
      .toEqual({ count: 1, id: notificationId, read: true, unreadCount: initialUnreadCount })
    await expect(notificationCard.getByTitle("Прочитано", { exact: true })).toHaveCount(0)
    await expectUnreadIndicator(recipientPage, initialUnreadCount)

    await recipientPage.reload()
    await expect
      .poll(async () => {
        const state = await readNotificationsForState(recipientPage, chatId!, message)
        return {
          count: state.matches.length,
          id: state.matches[0]?.id,
          read: state.matches[0]?.read,
          unreadCount: state.unreadCount,
        }
      })
      .toEqual({ count: 1, id: notificationId, read: true, unreadCount: initialUnreadCount })
    await recipientPage.locator("#global-notifications-btn").click()
    await expect(notificationDialog).toBeVisible()
    await expect(
      notificationDialog.locator(".relative.group").filter({ hasText: message })
    ).toHaveCount(1)
    await expect(
      notificationDialog
        .locator(".relative.group")
        .filter({ hasText: message })
        .getByTitle("Прочитано", { exact: true })
    ).toHaveCount(0)
    await expectUnreadIndicator(recipientPage, initialUnreadCount)
  } catch (error) {
    testFailure = error
    testFailed = true
  }

  const cleanupErrors: unknown[] = []
  const attemptCleanup = async (action: () => Promise<void>) => {
    try {
      await action()
    } catch (error) {
      cleanupErrors.push(error)
    }
  }

  if (chatId && recipientRegistrationAttempted) {
    await attemptCleanup(() =>
      deleteOnlyTestNotification(recipientPage, chatId!, message, testNotificationId)
    )
  }
  if (chatId) await attemptCleanup(() => deleteOnlyTestChat(adminPage, chatId!))
  if (recipientRegistrationAttempted) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage, recipientEmail, recipientName))
  }
  if (senderRegistrationAttempted) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage, senderEmail, senderName))
  }

  try {
    await Promise.all([recipientContext.close(), adminContext.close()])
  } catch (error) {
    cleanupErrors.push(error)
  }

  if (testFailed && cleanupErrors.length > 0) {
    throw new AggregateError([testFailure, ...cleanupErrors], "test and owned-data cleanup failed")
  }
  if (testFailed) throw testFailure
  if (cleanupErrors.length > 0) {
    throw new AggregateError(cleanupErrors, "test-owned notification data cleanup failed")
  }
})

async function readNotificationsForState(
  page: Page,
  chatId: string,
  message: string
): Promise<{ matches: NotificationRow[]; unreadCount: number }> {
  const notifications = await readNotifications(page)
  return {
    matches: findTestNotification(notifications, chatId, message),
    unreadCount: notifications.unread_count,
  }
}
