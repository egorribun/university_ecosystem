import { randomUUID } from "node:crypto"
import type { BrowserContext, Page } from "@playwright/test"
import { expect, freshPassword, loginAs, loginWith, stubBreachedPasswordLookup } from "./fixtures"
import { test } from "./native-push-profile-fixtures"

const expandPushAccordion = async (page: Page): Promise<void> => {
  const accordion = page.getByRole("button", { name: /Push notifications|Push-уведомления/u })
  if ((await accordion.getAttribute("aria-expanded")) !== "true") {
    await accordion.click()
  }
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
}

test.use({ channel: "chromium" })
test.use({ nativePushChannel: "chromium" })

const DELIVERY_TOPICS = [
  "news.published",
  "events.published",
  "schedule.changed",
  "system.release",
] as const
type DeliveryTopic = (typeof DELIVERY_TOPICS)[number]

const RECIPIENT_TOPICS = [...DELIVERY_TOPICS]
const SCHEDULE_GROUP_NAME = "University Ecosystem live notification delivery"
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu
const PAGE_SIZE = 200

interface UserRow {
  id: string
  is_active: boolean
}

interface TopicPreferences {
  user_id: string
  topics: string[]
  allowed_topics: string[]
  updated_at: string | null
}

interface GroupRow {
  id: string
  name: string
}

interface ScheduleRow {
  id: string
  group_id: string
  subject: string
  teacher: string | null
  room: string | null
  weekday: string
  start_time: string
  end_time: string
  parity: string | null
  lesson_type: string | null
}

interface NewsRecoveryExpectation {
  title: string
  contentMarker: string
}

interface EventRecoveryExpectation {
  title: string
  descriptionMarker: string
  location: string
  eventType: string
  startsAt: string
  endsAt: string
  ownerId: string
}

interface ScheduleRecoveryExpectation {
  groupId: string
  subject: string
  teacher: string
  room: string
  weekday: string
  startTime: string
  endTime: string
  parity: string
  lessonType: string
}

interface NotificationRow {
  id: string
  title: string
  body: string | null
  type: string | null
  topic: string | null
  url: string | null
  read: boolean
}

interface NotificationListResponse {
  items: NotificationRow[]
  has_more: boolean
  next_cursor: string | null
}

interface ApiMutationResult {
  status: number
  body: unknown
}

interface NativeNotification {
  count: number
  title: string | null
  body: string | null
  tag: string | null
  notificationId: string | null
  topic: string | null
  type: string | null
  url: string | null
  entityId: string | null
}

type NativeNotificationMarkerKey = "newsId" | "eventId" | "lessonId" | "version"

interface NativeNotificationMarker {
  key: NativeNotificationMarkerKey
  value: string
}

interface ScenarioNotificationCleanup {
  newsId: string | null
  newsTitle: string
  newsContentMarker: string
  eventId: string | null
  eventTitle: string
  eventDescriptionMarker: string
  scheduleId: string | null
  scheduleSubject: string
  releaseVersion: string | null
}

const expectUuid = (value: unknown, description: string): string => {
  if (typeof value !== "string" || !UUID_PATTERN.test(value)) {
    throw new Error(`${description} did not return a valid UUID`)
  }
  return value
}

const readJson = async <T>(page: Page, path: string, description: string): Promise<T> => {
  const response = await page.request.get(path)
  expect(response.status(), description).toBe(200)
  return (await response.json()) as T
}

const readCurrentUserId = async (
  page: Page,
  expectedRole: "admin" | "teacher"
): Promise<string> => {
  const profile = await readJson<{ id: unknown; role: unknown }>(
    page,
    "/api/v1/users/me",
    `the authenticated ${expectedRole} resolves its exact cleanup identity`
  )
  expect(profile.role, "the producer session has the expected role").toBe(expectedRole)
  return expectUuid(profile.id, `${expectedRole} producer identity`)
}

/** Use the authenticated same-origin session and its double-submit CSRF token. */
const mutate = async (
  page: Page,
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  payload?: Record<string, unknown>
): Promise<ApiMutationResult> =>
  page.evaluate(
    async ({ requestPath, requestMethod, requestBody }) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return { status: 0, body: null }

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const headers: Record<string, string> = { "X-CSRF-Token": csrfToken }
      if (requestBody !== null) headers["Content-Type"] = "application/json"
      const response = await fetch(requestPath, {
        method: requestMethod,
        credentials: "same-origin",
        headers,
        ...(requestBody === null ? {} : { body: JSON.stringify(requestBody) }),
      })
      return {
        status: response.status,
        body: await response.json().catch(() => null),
      }
    },
    { requestPath: path, requestMethod: method, requestBody: payload ?? null }
  )

const listUsersCompletely = async (adminPage: Page, groupId?: string): Promise<UserRow[]> => {
  const allUsers: UserRow[] = []
  const seenIds = new Set<string>()
  let afterId: string | null = null

  for (let pageNumber = 0; pageNumber < 10_000; pageNumber += 1) {
    const query = new URLSearchParams({ limit: String(PAGE_SIZE) })
    if (groupId) query.set("group_id", groupId)
    if (afterId) query.set("after_id", afterId)
    const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
    expect(response.status(), "admin can enumerate every recipient page").toBe(200)
    const pageUsers = (await response.json()) as UserRow[]
    if (!Array.isArray(pageUsers) || pageUsers.length > PAGE_SIZE) {
      throw new Error("recipient pagination returned an invalid page")
    }

    for (const user of pageUsers) {
      expectUuid(user.id, "recipient enumeration")
      if (typeof user.is_active !== "boolean") {
        throw new Error("recipient enumeration omitted active state")
      }
      if (seenIds.has(user.id)) {
        throw new Error("recipient pagination returned a duplicate identity")
      }
      seenIds.add(user.id)
      allUsers.push(user)
    }

    if (pageUsers.length < PAGE_SIZE) return allUsers
    const lastId = pageUsers.at(-1)?.id
    if (!lastId || lastId === afterId) {
      throw new Error("recipient pagination did not advance its keyset cursor")
    }
    afterId = lastId
  }

  throw new Error("recipient enumeration exceeded its bounded page count")
}

const readAdminTopicPreferences = async (
  adminPage: Page,
  userId: string
): Promise<TopicPreferences> =>
  readJson<TopicPreferences>(
    adminPage,
    `/api/v1/push/admin/topics/${encodeURIComponent(userId)}`,
    "admin can read the exact recipient topic preferences"
  )

/**
 * News, event, schedule and release producers can address every active account.
 * Fail before each producer call unless every other active account has an
 * explicit saved preference excluding all four tested topics.
 */
const requireProducerIsolation = async (adminPage: Page, recipientId?: string): Promise<void> => {
  const activeUsers = (await listUsersCompletely(adminPage)).filter((user) => user.is_active)
  let recipientSeen = recipientId === undefined

  for (const user of activeUsers) {
    const preferences = await readAdminTopicPreferences(adminPage, user.id)
    if (
      preferences.user_id !== user.id ||
      typeof preferences.updated_at !== "string" ||
      preferences.updated_at.length === 0
    ) {
      throw new Error(
        "global producer precondition failed: an active account has no saved topic preferences"
      )
    }
    if (
      !Array.isArray(preferences.topics) ||
      preferences.topics.some((topic) => typeof topic !== "string")
    ) {
      throw new Error("global producer precondition failed: topic preferences are malformed")
    }

    if (user.id === recipientId) {
      recipientSeen = true
      const actual = new Set(preferences.topics)
      const expected = new Set(RECIPIENT_TOPICS)
      expect(actual, "the synthetic recipient has only the explicitly selected topics").toEqual(
        expected
      )
      continue
    }

    const eligibleTopic = DELIVERY_TOPICS.find((topic) => preferences.topics.includes(topic))
    if (eligibleTopic) {
      throw new Error(
        "global producer precondition failed: another active account is eligible for a tested topic"
      )
    }
  }

  if (!recipientSeen) {
    throw new Error("global producer precondition failed: the synthetic recipient is not active")
  }
}

const resolveEmptyScheduleGroup = async (adminPage: Page): Promise<string> => {
  const configuredGroupId = process.env.LIVE_NOTIFICATION_SCHEDULE_GROUP_ID
  if (configuredGroupId !== undefined && !UUID_PATTERN.test(configuredGroupId)) {
    throw new Error("LIVE_NOTIFICATION_SCHEDULE_GROUP_ID must be a UUID")
  }

  const groups = await readJson<GroupRow[]>(
    adminPage,
    "/api/v1/groups",
    "the owned stand exposes its schedule test group"
  )
  if (!Array.isArray(groups)) throw new Error("schedule group listing is malformed")

  const matches = configuredGroupId
    ? groups.filter((group) => group.id.toLowerCase() === configuredGroupId.toLowerCase())
    : groups.filter((group) => group.name === SCHEDULE_GROUP_NAME)
  if (matches.length !== 1 || matches[0]?.name !== SCHEDULE_GROUP_NAME) {
    throw new Error("the dedicated notification schedule group is missing or ambiguous")
  }
  const groupId = expectUuid(matches[0].id, "schedule group lookup")

  const schedules = await readJson<ScheduleRow[]>(
    adminPage,
    `/api/v1/schedule/${encodeURIComponent(groupId)}`,
    "admin can inspect the dedicated schedule group"
  )
  if (!Array.isArray(schedules) || schedules.length !== 0) {
    throw new Error("the dedicated notification schedule group must start without lessons")
  }
  const activeMembers = (await listUsersCompletely(adminPage, groupId)).filter(
    (user) => user.is_active
  )
  if (activeMembers.length !== 0) {
    throw new Error("the dedicated notification schedule group must start without active members")
  }
  return groupId
}

const requireOnlyActiveScheduleRecipient = async (
  adminPage: Page,
  groupId: string,
  recipientId: string
): Promise<void> => {
  const activeMembers = (await listUsersCompletely(adminPage, groupId)).filter(
    (user) => user.is_active
  )
  expect(
    activeMembers.map((user) => user.id),
    "the isolated schedule group contains only this scenario's synthetic student"
  ).toEqual([recipientId])
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

const listAllNotifications = async (page: Page): Promise<NotificationRow[]> => {
  const allRows: NotificationRow[] = []
  const seenIds = new Set<string>()
  const seenCursors = new Set<string>()
  let cursor: string | null = null

  for (let pageNumber = 0; pageNumber < 10_000; pageNumber += 1) {
    const query = new URLSearchParams({ limit: "100" })
    if (cursor) query.set("cursor", cursor)
    const response = await page.request.get(`/api/v1/notifications?${query.toString()}`)
    expect(response.status(), "the recipient can read its in-app notification pages").toBe(200)
    const body = (await response.json()) as NotificationListResponse
    if (!Array.isArray(body.items) || typeof body.has_more !== "boolean") {
      throw new Error("notification pagination returned an invalid page")
    }
    for (const row of body.items) {
      expectUuid(row.id, "notification list")
      if (seenIds.has(row.id)) throw new Error("notification pagination repeated an identity")
      seenIds.add(row.id)
      allRows.push(row)
    }
    if (!body.has_more) return allRows
    const nextCursor = body.next_cursor
    if (
      typeof nextCursor !== "string" ||
      nextCursor.length === 0 ||
      nextCursor === cursor ||
      seenCursors.has(nextCursor)
    ) {
      throw new Error("notification pagination returned an invalid continuation cursor")
    }
    seenCursors.add(nextCursor)
    cursor = nextCursor
  }
  throw new Error("notification enumeration exceeded its bounded page count")
}

const waitForOnePersistedNotification = async (
  page: Page,
  matches: (row: NotificationRow) => boolean,
  description: string
): Promise<NotificationRow> => {
  let matchingRows: NotificationRow[] = []
  await expect
    .poll(
      async () => {
        matchingRows = (await listAllNotifications(page)).filter(matches)
        return matchingRows.length
      },
      { timeout: 45_000, message: description }
    )
    .toBe(1)
  const [row] = matchingRows
  if (!row) throw new Error("the persisted notification disappeared after polling")
  return row
}

const inspectNativeNotification = async (
  page: Page,
  notificationId: string,
  entityKey: string
): Promise<NativeNotification> =>
  page.evaluate(
    async ({ expectedId, expectedEntityKey }) => {
      const registration = await navigator.serviceWorker.ready
      const active = await registration.getNotifications()
      const matches = active.filter((notification) => notification.tag === expectedId)
      const notification = matches[0]
      const rawData = notification?.data
      const data =
        rawData && typeof rawData === "object" ? (rawData as Record<string, unknown>) : {}
      const asString = (value: unknown): string | null => (typeof value === "string" ? value : null)
      return {
        count: matches.length,
        title: notification?.title ?? null,
        body: notification?.body ?? null,
        tag: notification?.tag ?? null,
        notificationId: asString(data.notificationId),
        topic: asString(data.topic),
        type: asString(data.type),
        url: asString(data.url),
        entityId: asString(data[expectedEntityKey]),
      }
    },
    { expectedId: notificationId, expectedEntityKey: entityKey }
  )

const waitForNativeNotification = async (
  page: Page,
  notificationId: string,
  entityKey: string
): Promise<NativeNotification> => {
  await expect
    .poll(async () => (await inspectNativeNotification(page, notificationId, entityKey)).count, {
      timeout: 60_000,
      message:
        "the native Chromium service worker receives a push tagged with the persisted notification id",
    })
    .toBe(1)
  return inspectNativeNotification(page, notificationId, entityKey)
}

const assertActualDelivery = async (
  page: Page,
  notificationRow: NotificationRow,
  expected: {
    topic: DeliveryTopic
    type: string
    url: string
    entityKey: string
    entityId: string
  }
): Promise<void> => {
  expect(notificationRow.topic).toBe(expected.topic)
  expect(notificationRow.type).toBe(expected.type)
  expect(notificationRow.url).toBe(expected.url)
  expect(notificationRow.read, "new in-app notifications remain unread").toBe(false)

  const native = await waitForNativeNotification(page, notificationRow.id, expected.entityKey)
  expect(native.count, "a persisted identity owns one native notification tag").toBe(1)
  expect(native.tag).toBe(notificationRow.id)
  expect(native.notificationId).toBe(notificationRow.id)
  expect(native.topic).toBe(expected.topic)
  expect(native.type).toBe(expected.type)
  expect(native.url).toBe(expected.url)
  expect(native.entityId).toBe(expected.entityId)
}

const savePushOptInAndTopics = async (
  page: Page,
  adminPage: Page,
  expectedEmail: string
): Promise<{ recipientId: string; subscriptionEndpoint: string }> => {
  const profileResponse = await page.request.get("/api/v1/users/me")
  expect(profileResponse.status(), "the registered recipient reads its own profile").toBe(200)
  const profile = (await profileResponse.json()) as {
    id?: unknown
    email?: unknown
    role?: unknown
  }
  const recipientId = expectUuid(profile.id, "synthetic recipient profile")
  expect(profile.email).toBe(expectedEmail)
  expect(profile.role).toBe("student")

  const initialBrowserState = await page.evaluate(async () => {
    const supported =
      "serviceWorker" in navigator && "PushManager" in window && typeof Notification !== "undefined"
    if (!supported) return { supported, permission: "unsupported", hasSubscription: false }
    const registration = await navigator.serviceWorker.ready
    return {
      supported,
      permission: Notification.permission,
      hasSubscription: (await registration.pushManager.getSubscription()) !== null,
    }
  })
  expect(initialBrowserState.supported, "Chromium has native service worker push APIs").toBe(true)
  expect(initialBrowserState.permission).toBe("granted")
  expect(initialBrowserState.hasSubscription).toBe(false)

  await page.goto("/settings?tab=3")
  await expandPushAccordion(page)
  const pushSwitch = page.getByRole("switch", { name: "Включить уведомления", exact: true })
  const chatTopicSwitch = page.getByRole("switch", { name: "Сообщения чата", exact: true })
  await expect(pushSwitch).toBeVisible()
  await expect(pushSwitch).not.toBeChecked()
  await expect(chatTopicSwitch).toBeChecked()
  await chatTopicSwitch.click()
  await expect(chatTopicSwitch).not.toBeChecked()

  const subscriptionSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/push/subscribe"
  )
  const topicsSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      new URL(response.url()).pathname === "/api/v1/push/subscribe/topics"
  )
  await pushSwitch.click()
  const subscriptionResponse = await subscriptionSaved
  expect(
    subscriptionResponse.status(),
    "the explicit Settings action saves native push opt-in"
  ).toBe(200)
  const topicsResponse = await topicsSaved
  expect(topicsResponse.status(), "the selected delivery topics persist for the endpoint").toBe(200)
  await expect(pushSwitch).toBeChecked()

  const subscriptionReceipt = (await subscriptionResponse.json()) as { endpoint?: unknown }
  if (typeof subscriptionReceipt.endpoint !== "string") {
    throw new Error("the server did not return the test-owned push endpoint")
  }
  const nativeEndpoint = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    if (!subscription) return null
    const endpointUrl = new URL(subscription.endpoint)
    if (endpointUrl.protocol !== "https:" || endpointUrl.hostname === location.hostname) {
      return null
    }
    return subscription.endpoint
  })
  expect(nativeEndpoint, "the browser owns a real provider HTTPS subscription").toBe(
    subscriptionReceipt.endpoint
  )
  if (!nativeEndpoint) throw new Error("the browser endpoint was not provider-issued HTTPS")

  const savedPreferences = await readAdminTopicPreferences(adminPage, recipientId)
  expect(
    savedPreferences.updated_at,
    "recipient topic preferences are explicit and persisted"
  ).not.toBeNull()
  expect(new Set(savedPreferences.topics)).toEqual(new Set(RECIPIENT_TOPICS))
  expect(new Set(savedPreferences.allowed_topics)).toEqual(
    new Set([...RECIPIENT_TOPICS, "chat.message.created"])
  )
  return { recipientId, subscriptionEndpoint: nativeEndpoint }
}

const removeOnlyNotification = async (page: Page, notificationId: string): Promise<void> => {
  const result = await mutate(
    page,
    `/api/v1/notifications/${encodeURIComponent(notificationId)}`,
    "DELETE"
  )
  expect(result.status, "cleanup deletes only an exact notification owned by this recipient").toBe(
    200
  )
  expect((result.body as { ok?: unknown } | null)?.ok).toBe(true)
}

const findNativeNotificationIds = async (
  page: Page,
  markers: NativeNotificationMarker[]
): Promise<Set<string>> => {
  if (markers.length === 0) return new Set()
  const notificationIds = await page.evaluate(async (expectedMarkers) => {
    const registration = await navigator.serviceWorker.getRegistration()
    if (!registration) return []
    const notifications = await registration.getNotifications()
    const ids: string[] = []
    for (const notification of notifications) {
      const rawData = notification.data
      const data =
        rawData && typeof rawData === "object" ? (rawData as Record<string, unknown>) : {}
      const notificationId = data.notificationId
      const hasExactMarker = expectedMarkers.some(({ key, value }) => data[key] === value)
      if (
        hasExactMarker &&
        typeof notification.tag === "string" &&
        notificationId === notification.tag
      ) {
        ids.push(notification.tag)
      }
    }
    return ids
  }, markers)
  return new Set(notificationIds.map((id) => expectUuid(id, "test-marked native notification")))
}

const assertNativeScenarioIdentity = async (
  page: Page,
  expected: {
    entityKey: "newsId" | "eventId" | "lessonId"
    entityId: string
    marker: string
    topic: string
    type: string
    url: string
  }
): Promise<void> => {
  const evidence = await page.evaluate(async ({ entityKey, marker }) => {
    const registration = await navigator.serviceWorker.getRegistration()
    if (!registration) return []
    const notifications = await registration.getNotifications()
    return notifications
      .filter((notification) =>
        `${notification.title}\n${notification.body ?? ""}`.includes(marker)
      )
      .map((notification) => {
        const rawData = notification.data
        const data = rawData && typeof rawData === "object" ? rawData : {}
        const asString = (value: unknown): string | null =>
          typeof value === "string" ? value : null
        return {
          tag: notification.tag ?? null,
          title: notification.title,
          body: notification.body ?? null,
          notificationId: asString(data.notificationId),
          topic: asString(data.topic),
          type: asString(data.type),
          url: asString(data.url),
          entityId: asString(data[entityKey]),
        }
      })
  }, expected)

  for (const marker of evidence) {
    const notificationId = expectUuid(
      marker.notificationId,
      "scenario native notification identity"
    )
    if (
      marker.tag !== notificationId ||
      marker.topic !== expected.topic ||
      marker.type !== expected.type ||
      marker.url !== expected.url ||
      marker.entityId !== expected.entityId
    ) {
      throw new Error("refusing cleanup because a native scenario marker conflicts with its entity")
    }
  }
}

const closeNativeNotifications = async (
  page: Page,
  markers: NativeNotificationMarker[]
): Promise<void> => {
  if (markers.length === 0) return
  await page.evaluate(async (expectedMarkers) => {
    const registration = await navigator.serviceWorker.getRegistration()
    if (!registration) return
    const notifications = await registration.getNotifications()
    for (const notification of notifications) {
      const rawData = notification.data
      const data =
        rawData && typeof rawData === "object" ? (rawData as Record<string, unknown>) : {}
      const hasExactMarker = expectedMarkers.some(({ key, value }) => data[key] === value)
      if (
        hasExactMarker &&
        notification.tag &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu.test(
          notification.tag
        ) &&
        data.notificationId === notification.tag
      ) {
        notification.close()
      }
    }
  }, markers)
}

const unsubscribeOnlyNativeEndpoint = async (
  page: Page,
  knownEndpoint: string | null
): Promise<void> => {
  const result = await page.evaluate(async (fallbackEndpoint) => {
    const registration = await navigator.serviceWorker.getRegistration()
    const subscription = await registration?.pushManager.getSubscription()
    const endpoint = subscription?.endpoint ?? fallbackEndpoint
    if (!endpoint) return { serverRemoved: true, browserRevoked: true }

    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { serverRemoved: false, browserRevoked: false }
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
    const body = (await response.json().catch(() => null)) as { removed?: unknown } | null
    const browserRevoked = subscription ? await subscription.unsubscribe() : true
    return {
      serverRemoved: response.ok && body?.removed === true,
      browserRevoked,
    }
  }, knownEndpoint)
  expect(result.serverRemoved, "cleanup removes only the recipient's exact server endpoint").toBe(
    true
  )
  expect(result.browserRevoked, "cleanup revokes only the recipient's native subscription").toBe(
    true
  )
}

const findOnlyCreatedAccountId = async (
  adminPage: Page,
  email: string,
  fullName: string
): Promise<string | null> => {
  const query = new URLSearchParams({ search: fullName, limit: String(PAGE_SIZE) })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  expect(response.status(), "admin resolves the generated account for exact cleanup").toBe(200)
  const users = (await response.json()) as Array<{
    id: string
    email: string
    full_name: string | null
  }>
  const exactMatches = users.filter((user) => user.email === email && user.full_name === fullName)
  if (exactMatches.length > 1) throw new Error("generated account cleanup was ambiguous")
  const match = exactMatches[0]
  return match ? expectUuid(match.id, "generated account cleanup lookup") : null
}

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  fullName: string,
  knownUserId: string | null
): Promise<void> => {
  const userId = knownUserId ?? (await findOnlyCreatedAccountId(adminPage, email, fullName))
  if (!userId) return
  const result = await mutate(adminPage, `/api/v1/users/${encodeURIComponent(userId)}`, "DELETE")
  expect(result.status, "cleanup deletes only the recorded synthetic recipient id").toBe(200)
  expect((result.body as { deleted?: unknown } | null)?.deleted).toBe(true)
}

const findOnlyCreatedNewsId = async (
  adminPage: Page,
  expected: NewsRecoveryExpectation
): Promise<string> => {
  const response = await adminPage.request.get("/api/v1/news?limit=100")
  expect(response.status(), "admin inspects the bounded newest-news page for cleanup").toBe(200)
  const body = (await response.json()) as {
    items?: Array<{ id?: unknown; title?: unknown; content?: unknown }>
    has_more?: unknown
  }
  if (!Array.isArray(body.items) || typeof body.has_more !== "boolean") {
    throw new Error("news cleanup lookup returned a malformed bounded page")
  }
  if (body.has_more) {
    throw new Error("refusing news cleanup because the bounded marker page is incomplete")
  }

  // NewsOut does not expose author_id, and the create route itself is admin-only.
  // The authenticated admin session plus both random request markers are the
  // available ownership evidence for this record.
  const exactMatches = body.items.filter(
    (item) =>
      item.title === expected.title &&
      typeof item.content === "string" &&
      item.content.includes(expected.contentMarker)
  )
  if (exactMatches.length !== 1) {
    throw new Error(
      exactMatches.length === 0
        ? "refusing news cleanup because the exact admin-created marker is missing"
        : "refusing news cleanup because the exact admin-created marker is ambiguous"
    )
  }
  return expectUuid(exactMatches[0]?.id, "exact admin-created news cleanup lookup")
}

const sameInstant = (left: unknown, right: string): boolean =>
  typeof left === "string" &&
  Number.isFinite(Date.parse(left)) &&
  Date.parse(left) === Date.parse(right)

const findOnlyCreatedEventId = async (
  teacherPage: Page,
  expected: EventRecoveryExpectation
): Promise<string> => {
  const query = new URLSearchParams({ search: expected.title, limit: "100" })
  const response = await teacherPage.request.get(`/api/v1/events?${query.toString()}`)
  expect(response.status(), "teacher inspects the title-filtered event page for cleanup").toBe(200)
  const body = (await response.json()) as {
    items?: Array<{
      id?: unknown
      title?: unknown
      description?: unknown
      location?: unknown
      event_type?: unknown
      starts_at?: unknown
      ends_at?: unknown
      created_by?: unknown
      is_active?: unknown
    }>
    has_more?: unknown
  }
  if (!Array.isArray(body.items) || typeof body.has_more !== "boolean") {
    throw new Error("event cleanup lookup returned a malformed bounded page")
  }
  if (body.has_more) {
    throw new Error("refusing event cleanup because the title-filtered marker page is incomplete")
  }

  const exactMatches = body.items.filter(
    (item) =>
      item.title === expected.title &&
      typeof item.description === "string" &&
      item.description.includes(expected.descriptionMarker) &&
      item.location === expected.location &&
      item.event_type === expected.eventType &&
      sameInstant(item.starts_at, expected.startsAt) &&
      sameInstant(item.ends_at, expected.endsAt) &&
      typeof item.created_by === "string" &&
      item.created_by.toLowerCase() === expected.ownerId.toLowerCase() &&
      item.is_active === true
  )
  if (exactMatches.length !== 1) {
    throw new Error(
      exactMatches.length === 0
        ? "refusing event cleanup because the exact teacher-owned marker is missing"
        : "refusing event cleanup because the exact teacher-owned marker is ambiguous"
    )
  }
  return expectUuid(exactMatches[0]?.id, "exact teacher-owned event cleanup lookup")
}

const findOnlyCreatedScheduleId = async (
  teacherPage: Page,
  expected: ScheduleRecoveryExpectation
): Promise<string> => {
  const schedules = await readJson<ScheduleRow[]>(
    teacherPage,
    `/api/v1/schedule/${encodeURIComponent(expected.groupId)}`,
    "teacher inspects only the dedicated test group for schedule cleanup"
  )
  if (!Array.isArray(schedules))
    throw new Error("schedule cleanup lookup returned a malformed list")
  const exactMatches = schedules.filter(
    (item) =>
      item.group_id.toLowerCase() === expected.groupId.toLowerCase() &&
      item.subject === expected.subject &&
      item.teacher === expected.teacher &&
      item.room === expected.room &&
      item.weekday === expected.weekday &&
      sameInstant(item.start_time, expected.startTime) &&
      sameInstant(item.end_time, expected.endTime) &&
      item.parity === expected.parity &&
      item.lesson_type === expected.lessonType
  )
  if (exactMatches.length !== 1) {
    throw new Error(
      exactMatches.length === 0
        ? "refusing schedule cleanup because the exact group-scoped marker is missing"
        : "refusing schedule cleanup because the exact group-scoped marker is ambiguous"
    )
  }
  return expectUuid(exactMatches[0]?.id, "exact group-scoped schedule cleanup lookup")
}

const findScheduleNotifications = async (
  recipientPage: Page,
  uniqueSubject: string
): Promise<NotificationRow[]> =>
  (await listAllNotifications(recipientPage)).filter(
    (row) =>
      row.topic === "schedule.changed" &&
      row.type === "schedule.change" &&
      row.url === "/schedule" &&
      `${row.title}\n${row.body ?? ""}`.includes(uniqueSubject)
  )

const isOwnedScenarioNotification = (
  row: NotificationRow,
  scenario: ScenarioNotificationCleanup,
  nativeNotificationIds: ReadonlySet<string>
): boolean => {
  const rowText = `${row.title}\n${row.body ?? ""}`
  if (
    scenario.newsId &&
    row.topic === "news.published" &&
    row.type === "news.new" &&
    row.url === `/news/${scenario.newsId}` &&
    rowText.includes(scenario.newsTitle) &&
    rowText.includes(scenario.newsContentMarker)
  ) {
    return true
  }
  if (
    scenario.eventId &&
    row.topic === "events.published" &&
    row.type === "events.new" &&
    row.url === `/events/${scenario.eventId}` &&
    rowText.includes(scenario.eventTitle) &&
    rowText.includes(scenario.eventDescriptionMarker)
  ) {
    return true
  }

  if (
    scenario.scheduleId &&
    row.topic === "schedule.changed" &&
    row.type === "schedule.change" &&
    row.url === "/schedule" &&
    (nativeNotificationIds.has(row.id) || rowText.includes(scenario.scheduleSubject))
  ) {
    return true
  }
  return Boolean(
    scenario.releaseVersion &&
    row.topic === "system.release" &&
    row.type === "system.message" &&
    row.url === "/" &&
    (nativeNotificationIds.has(row.id) || row.title.includes(scenario.releaseVersion))
  )
}

const assertMutationStatus = (
  result: ApiMutationResult,
  expectedStatus: number,
  description: string
): Record<string, unknown> => {
  expect(result.status, description).toBe(expectedStatus)
  if (result.body === null || typeof result.body !== "object") {
    throw new Error(`${description} returned a malformed response`)
  }
  return result.body as Record<string, unknown>
}

test("news, events, schedule changes and system releases reach the opted-in Chromium recipient", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(360_000)
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = randomUUID()
  const email = `live-topic-delivery-${testInfo.project.name}-${identity}@university.dev`
  const fullName = `Live Topic Delivery ${testInfo.project.name} ${identity}`
  const password = freshPassword()
  const uniqueMarker = identity
  const newsTitle = `Live topic news ${uniqueMarker}`
  const newsContent = `Owned live notification news ${uniqueMarker}`
  const eventTitle = `Live topic event ${uniqueMarker}`
  const eventDescription = `Owned live notification event ${uniqueMarker}`
  const scheduleSubject = `Live topic schedule ${uniqueMarker}`
  const releaseVersion = `1.0.0-live${identity.replaceAll("-", "").slice(0, 12)}`
  const releaseNotes = `Owned live release notification ${uniqueMarker}`

  let registrationAttempted = false
  let recipientId: string | null = null
  let subscriptionMayExist = false
  let subscriptionEndpoint: string | null = null
  let groupId: string | null = null
  let groupAssignmentMayExist = false
  let newsId: string | null = null
  let newsMayExist = false
  let eventId: string | null = null
  let eventMayExist = false
  let scheduleId: string | null = null
  let scheduleMayExist = false
  let eventRecoveryExpectation: EventRecoveryExpectation | null = null
  let scheduleRecoveryExpectation: ScheduleRecoveryExpectation | null = null
  let scheduleUpdateSucceeded = false
  let scheduleDeleteSucceeded = false
  let releaseAnnouncementMayExist = false
  const ownedNotificationIds = new Set<string>()
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

    const teacherContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    contexts.push(teacherContext)
    const teacherPage = await teacherContext.newPage()
    await loginAs(teacherPage, "teacher")
    const teacherOwnerId = await readCurrentUserId(teacherPage, "teacher")

    // This read-only preflight prevents producers that target every active user
    // from notifying any unrelated account. It must pass before synthetic setup.
    await requireProducerIsolation(adminPage)
    groupId = await resolveEmptyScheduleGroup(adminPage)

    await registerSyntheticAccount(page, fullName, email, password, () => {
      registrationAttempted = true
    })
    subscriptionMayExist = true
    const optIn = await savePushOptInAndTopics(page, adminPage, email)
    recipientId = optIn.recipientId
    subscriptionEndpoint = optIn.subscriptionEndpoint
    await requireProducerIsolation(adminPage, recipientId)

    const exactRecipientQuery = new URLSearchParams({ search: fullName, limit: String(PAGE_SIZE) })
    const exactRecipientResponse = await adminPage.request.get(
      `/api/v1/users?${exactRecipientQuery.toString()}`
    )
    expect(exactRecipientResponse.status(), "admin can resolve the exact synthetic recipient").toBe(
      200
    )
    const exactRecipients = (
      (await exactRecipientResponse.json()) as Array<{ id: string; email: string }>
    ).filter((user) => user.id === recipientId && user.email === email)
    expect(exactRecipients).toHaveLength(1)

    groupAssignmentMayExist = true
    const assign = await mutate(
      adminPage,
      `/api/v1/users/${encodeURIComponent(recipientId)}`,
      "PATCH",
      { group_id: groupId }
    )
    const assignedUser = assertMutationStatus(
      assign,
      200,
      "admin assigns the exact synthetic student"
    )
    expect(assignedUser.id).toBe(recipientId)
    expect(assignedUser.group_id).toBe(groupId)
    await requireOnlyActiveScheduleRecipient(adminPage, groupId, recipientId)
    const initialSchedule = await readJson<ScheduleRow[]>(
      adminPage,
      `/api/v1/schedule/${encodeURIComponent(groupId)}`,
      "assigned recipient group still has no lessons before this test"
    )
    expect(initialSchedule).toEqual([])

    // News producer: POST /api/v1/news -> real notification queue/outbox -> persisted row + SW.
    await requireProducerIsolation(adminPage, recipientId)
    newsMayExist = true
    const createdNews = assertMutationStatus(
      await mutate(adminPage, "/api/v1/news", "POST", {
        title: newsTitle,
        content: newsContent,
      }),
      200,
      "admin creates the unique owned news article"
    )
    newsId = expectUuid(createdNews.id, "created news resource")
    const newsNotification = await waitForOnePersistedNotification(
      page,
      (row) =>
        row.topic === "news.published" && row.type === "news.new" && row.url === `/news/${newsId}`,
      "real news publication persists one recipient notification"
    )
    ownedNotificationIds.add(newsNotification.id)
    await assertActualDelivery(page, newsNotification, {
      topic: "news.published",
      type: "news.new",
      url: `/news/${newsId}`,
      entityKey: "newsId",
      entityId: newsId,
    })

    // Events producer: POST /api/v1/events -> real notification queue/outbox.
    await requireProducerIsolation(adminPage, recipientId)
    const startsAt = new Date(Date.now() + 48 * 60 * 60 * 1000)
    startsAt.setUTCMinutes(0, 0, 0)
    const endsAt = new Date(startsAt.getTime() + 60 * 60 * 1000)
    const eventLocation = `Live room ${uniqueMarker}`
    eventRecoveryExpectation = {
      title: eventTitle,
      descriptionMarker: eventDescription,
      location: eventLocation,
      eventType: "acceptance",
      startsAt: startsAt.toISOString(),
      endsAt: endsAt.toISOString(),
      ownerId: teacherOwnerId,
    }
    eventMayExist = true
    const createdEvent = assertMutationStatus(
      await mutate(teacherPage, "/api/v1/events", "POST", {
        title: eventTitle,
        description: eventDescription,
        location: eventLocation,
        event_type: "acceptance",
        starts_at: eventRecoveryExpectation.startsAt,
        ends_at: eventRecoveryExpectation.endsAt,
      }),
      200,
      "teacher creates the unique owned event"
    )
    eventId = expectUuid(createdEvent.id, "created event resource")
    const eventNotification = await waitForOnePersistedNotification(
      page,
      (row) =>
        row.topic === "events.published" &&
        row.type === "events.new" &&
        row.url === `/events/${eventId}`,
      "real event publication persists one recipient notification"
    )
    ownedNotificationIds.add(eventNotification.id)
    await assertActualDelivery(page, eventNotification, {
      topic: "events.published",
      type: "events.new",
      url: `/events/${eventId}`,
      entityKey: "eventId",
      entityId: eventId,
    })

    // Schedule creation is audit-only; the following real room change emits the topic.
    await requireProducerIsolation(adminPage, recipientId)
    const weekdayNames = [
      "sunday",
      "monday",
      "tuesday",
      "wednesday",
      "thursday",
      "friday",
      "saturday",
    ]
    const scheduleStart = new Date(Date.now() + 8 * 24 * 60 * 60 * 1000)
    scheduleStart.setUTCHours(10, 0, 0, 0)
    const scheduleEnd = new Date(scheduleStart.getTime() + 50 * 60 * 1000)
    const scheduleTeacher = `Live teacher ${uniqueMarker}`
    const scheduleRoom = `Old room ${uniqueMarker}`
    if (!groupId) throw new Error("the dedicated schedule group was not verified")
    scheduleRecoveryExpectation = {
      groupId,
      subject: scheduleSubject,
      teacher: scheduleTeacher,
      room: scheduleRoom,
      weekday: weekdayNames[scheduleStart.getUTCDay()] ?? "",
      startTime: scheduleStart.toISOString(),
      endTime: scheduleEnd.toISOString(),
      parity: "both",
      lessonType: "lecture",
    }
    scheduleMayExist = true
    const createdSchedule = assertMutationStatus(
      await mutate(teacherPage, "/api/v1/schedule", "POST", {
        group_id: groupId,
        subject: scheduleSubject,
        teacher: scheduleRecoveryExpectation.teacher,
        room: scheduleRecoveryExpectation.room,
        weekday: scheduleRecoveryExpectation.weekday,
        start_time: scheduleStart.toISOString(),
        end_time: scheduleEnd.toISOString(),
        parity: "both",
        lesson_type: "lecture",
      }),
      200,
      "teacher creates one lesson in the verified empty group"
    )
    scheduleId = expectUuid(createdSchedule.id, "created schedule resource")

    await requireProducerIsolation(adminPage, recipientId)
    const updatedSchedule = assertMutationStatus(
      await mutate(teacherPage, `/api/v1/schedule/${encodeURIComponent(scheduleId)}`, "PATCH", {
        room: `Updated room ${uniqueMarker}`,
      }),
      200,
      "teacher changes the exact owned schedule room"
    )
    scheduleUpdateSucceeded = true
    expect(updatedSchedule.id).toBe(scheduleId)
    const scheduleNotification = await waitForOnePersistedNotification(
      page,
      (row) =>
        row.topic === "schedule.changed" &&
        row.type === "schedule.change" &&
        row.url === "/schedule" &&
        `${row.title}\n${row.body ?? ""}`.includes(scheduleSubject),
      "the changed lesson creates one recipient notification"
    )
    ownedNotificationIds.add(scheduleNotification.id)
    await assertActualDelivery(page, scheduleNotification, {
      topic: "schedule.changed",
      type: "schedule.change",
      url: "/schedule",
      entityKey: "lessonId",
      entityId: scheduleId,
    })

    // The only release route used here is the unique-semver announcement API, never broadcast.
    await requireProducerIsolation(adminPage, recipientId)
    const releasePayload = { version: releaseVersion, notes_ru: releaseNotes }
    releaseAnnouncementMayExist = true
    const releaseResult = assertMutationStatus(
      await mutate(adminPage, "/api/v1/push/admin/releases", "POST", releasePayload),
      200,
      "admin announces this test's unique semantic version"
    )
    expect(releaseResult.version).toBe(releaseVersion)
    expect(releaseResult.created).toBe(1)
    expect(releaseResult.already_announced).toBe(false)
    const releaseNotification = await waitForOnePersistedNotification(
      page,
      (row) =>
        row.topic === "system.release" &&
        row.type === "system.message" &&
        row.url === "/" &&
        (row.body ?? "").includes(releaseNotes),
      "the release creates one persisted in-app notification for the opted-in recipient"
    )
    ownedNotificationIds.add(releaseNotification.id)
    await assertActualDelivery(page, releaseNotification, {
      topic: "system.release",
      type: "system.message",
      url: "/",
      entityKey: "version",
      entityId: releaseVersion,
    })

    await requireProducerIsolation(adminPage, recipientId)
    const repeatedRelease = assertMutationStatus(
      await mutate(adminPage, "/api/v1/push/admin/releases", "POST", releasePayload),
      200,
      "retrying the exact release version is idempotent"
    )
    expect(repeatedRelease.created).toBe(0)
    expect(repeatedRelease.already_announced).toBe(true)
    expect(
      (await listAllNotifications(page)).filter(
        (row) =>
          row.topic === "system.release" &&
          row.type === "system.message" &&
          row.url === "/" &&
          (row.body ?? "").includes(releaseNotes)
      )
    ).toHaveLength(1)
  } catch (error) {
    testFailure = error
    testFailed = true
  }

  const adminPage = contexts[0]?.pages()[0] ?? null
  const teacherPage = contexts[1]?.pages()[0] ?? null
  const cleanupErrors: unknown[] = []
  const attemptCleanup = async (action: () => Promise<void>): Promise<void> => {
    try {
      await action()
    } catch (error) {
      cleanupErrors.push(error)
    }
  }

  // A producer may commit before its response is lost or malformed. Recover
  // only from a bounded GET that matches the scenario's random marker and its
  // expected owner/group; ambiguous and missing identities stay undeleted.
  if (newsMayExist && !newsId && adminPage) {
    await attemptCleanup(async () => {
      newsId = await findOnlyCreatedNewsId(adminPage, {
        title: newsTitle,
        contentMarker: uniqueMarker,
      })
    })
  }
  if (eventMayExist && !eventId && teacherPage && eventRecoveryExpectation) {
    await attemptCleanup(async () => {
      eventId = await findOnlyCreatedEventId(teacherPage, eventRecoveryExpectation!)
    })
  }
  if (scheduleMayExist && !scheduleId && teacherPage && scheduleRecoveryExpectation) {
    await attemptCleanup(async () => {
      scheduleId = await findOnlyCreatedScheduleId(teacherPage, scheduleRecoveryExpectation!)
    })
  }

  // Delete the schedule first: this intentionally emits one cancellation row.
  // The notification IDs are discovered only by their unique subject and exact topic/type/url.
  if (scheduleId && teacherPage && adminPage && page && groupId && recipientId) {
    await attemptCleanup(async () => {
      // Schedule deletion emits a cancellation. Recheck both the global saved
      // topic fence and the group-scoped audience before that mutation.
      await requireProducerIsolation(adminPage, recipientId)
      await requireOnlyActiveScheduleRecipient(adminPage, groupId, recipientId)
      const deletion = await mutate(
        teacherPage,
        `/api/v1/schedule/${encodeURIComponent(scheduleId!)}`,
        "DELETE"
      )
      expect(deletion.status, "cleanup deletes only this test's schedule UUID").toBe(200)
      expect((deletion.body as { ok?: unknown } | null)?.ok).toBe(true)
      scheduleDeleteSucceeded = true
    })
  }

  if (scheduleId && scheduleDeleteSucceeded && page) {
    await attemptCleanup(async () => {
      let rows: NotificationRow[] = []
      const expectedCount = scheduleUpdateSucceeded ? 2 : 1
      await expect
        .poll(
          async () => {
            rows = await findScheduleNotifications(page, scheduleSubject)
            return rows.length
          },
          {
            timeout: 45_000,
            message: "schedule update and exact cancellation rows reach the owned recipient",
          }
        )
        .toBe(expectedCount)
      for (const row of rows) {
        ownedNotificationIds.add(row.id)
        expect(row.read, "schedule notifications remain unread before cleanup").toBe(false)
        const native = await waitForNativeNotification(page, row.id, "lessonId")
        expect(native.notificationId).toBe(row.id)
        expect(native.topic).toBe("schedule.changed")
        expect(native.type).toBe("schedule.change")
        expect(native.url).toBe("/schedule")
        expect(native.entityId).toBe(scheduleId)
      }
    })
  }

  const scenarioCleanup: ScenarioNotificationCleanup = {
    newsId,
    newsTitle,
    newsContentMarker: uniqueMarker,
    eventId,
    eventTitle,
    eventDescriptionMarker: uniqueMarker,
    scheduleId,
    scheduleSubject,
    releaseVersion: releaseAnnouncementMayExist ? releaseVersion : null,
  }
  const nativeMarkers: NativeNotificationMarker[] = []
  if (scenarioCleanup.newsId) {
    nativeMarkers.push({ key: "newsId", value: scenarioCleanup.newsId })
  }
  if (scenarioCleanup.eventId) {
    nativeMarkers.push({ key: "eventId", value: scenarioCleanup.eventId })
  }
  if (scenarioCleanup.scheduleId) {
    nativeMarkers.push({ key: "lessonId", value: scenarioCleanup.scheduleId })
  }
  if (scenarioCleanup.releaseVersion) {
    nativeMarkers.push({ key: "version", value: scenarioCleanup.releaseVersion })
  }

  // A wait may fail after the producer persisted/sent a notification but
  // before its ID reaches ownedNotificationIds. Recover only this recipient's
  // rows by exact entity routes/version or the exact schedule marker before
  // deleting any producer entity or the synthetic account.
  if (page) {
    let recoveredRows: NotificationRow[] = []
    await attemptCleanup(async () => {
      recoveredRows = await listAllNotifications(page)
    })
    let nativeNotificationIds = new Set<string>()
    await attemptCleanup(async () => {
      nativeNotificationIds = await findNativeNotificationIds(page, nativeMarkers)
    })
    for (const row of recoveredRows) {
      if (isOwnedScenarioNotification(row, scenarioCleanup, nativeNotificationIds)) {
        ownedNotificationIds.add(row.id)
      }
    }
    for (const [marker, expected] of [
      [
        newsTitle,
        newsId ? { topic: "news.published", type: "news.new", url: `/news/${newsId}` } : null,
      ],
      [
        eventTitle,
        eventId
          ? { topic: "events.published", type: "events.new", url: `/events/${eventId}` }
          : null,
      ],
      [
        scheduleSubject,
        scheduleId
          ? { topic: "schedule.changed", type: "schedule.change", url: "/schedule" }
          : null,
      ],
    ] as const) {
      if (!expected) continue
      await attemptCleanup(async () => {
        for (const row of recoveredRows.filter((item) =>
          `${item.title}\n${item.body ?? ""}`.includes(marker)
        )) {
          if (
            row.topic !== expected.topic ||
            row.type !== expected.type ||
            row.url !== expected.url
          ) {
            throw new Error(
              "refusing notification cleanup because a unique scenario marker has a conflicting route"
            )
          }
        }
      })
    }
    for (const notificationId of nativeNotificationIds) {
      ownedNotificationIds.add(notificationId)
    }
    if (newsId) {
      await attemptCleanup(() =>
        assertNativeScenarioIdentity(page, {
          entityKey: "newsId",
          entityId: newsId!,
          marker: newsTitle,
          topic: "news.published",
          type: "news.new",
          url: `/news/${newsId}`,
        })
      )
    }
    if (eventId) {
      await attemptCleanup(() =>
        assertNativeScenarioIdentity(page, {
          entityKey: "eventId",
          entityId: eventId!,
          marker: eventTitle,
          topic: "events.published",
          type: "events.new",
          url: `/events/${eventId}`,
        })
      )
    }
    if (scheduleId) {
      await attemptCleanup(() =>
        assertNativeScenarioIdentity(page, {
          entityKey: "lessonId",
          entityId: scheduleId!,
          marker: scheduleSubject,
          topic: "schedule.changed",
          type: "schedule.change",
          url: "/schedule",
        })
      )
    }
    await attemptCleanup(() => closeNativeNotifications(page, nativeMarkers))
  }

  if (newsId && adminPage) {
    await attemptCleanup(async () => {
      const deletion = await mutate(
        adminPage,
        `/api/v1/news/${encodeURIComponent(newsId!)}`,
        "DELETE"
      )
      expect(deletion.status, "cleanup deletes only this test's news UUID").toBe(200)
      expect((deletion.body as { ok?: unknown } | null)?.ok).toBe(true)
    })
  }
  if (eventId && teacherPage) {
    await attemptCleanup(async () => {
      const deletion = await mutate(
        teacherPage,
        `/api/v1/events/${encodeURIComponent(eventId!)}`,
        "DELETE"
      )
      expect(deletion.status, "cleanup deletes only this test's event UUID").toBe(200)
      expect((deletion.body as { ok?: unknown } | null)?.ok).toBe(true)
    })
  }

  if (page) {
    for (const notificationId of ownedNotificationIds) {
      await attemptCleanup(() => removeOnlyNotification(page, notificationId))
    }
    await attemptCleanup(() => closeNativeNotifications(page, nativeMarkers))

    if (subscriptionMayExist) {
      await attemptCleanup(() => unsubscribeOnlyNativeEndpoint(page, subscriptionEndpoint))
    }
  }

  if (groupAssignmentMayExist && recipientId && adminPage) {
    await attemptCleanup(async () => {
      const unassign = await mutate(
        adminPage,
        `/api/v1/users/${encodeURIComponent(recipientId!)}`,
        "PATCH",
        { group_id: null }
      )
      const unassigned = assertMutationStatus(
        unassign,
        200,
        "cleanup removes only the test recipient from its assigned schedule group"
      )
      expect(unassigned.group_id ?? null).toBeNull()
    })
  }

  if (groupId && adminPage) {
    await attemptCleanup(async () => {
      const remainingSchedules = await readJson<ScheduleRow[]>(
        adminPage,
        `/api/v1/schedule/${encodeURIComponent(groupId!)}`,
        "cleanup verifies the dedicated group has no remaining lessons"
      )
      expect(remainingSchedules).toEqual([])
      const remainingMembers = (await listUsersCompletely(adminPage, groupId)).filter(
        (user) => user.is_active
      )
      expect(remainingMembers.map((user) => user.id)).toEqual([])
    })
  }

  if (registrationAttempted && adminPage) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage, email, fullName, recipientId))
  }
  try {
    await Promise.all(contexts.map((context) => context.close()))
  } catch (error) {
    cleanupErrors.push(error)
  }

  if (testFailed && cleanupErrors.length > 0) {
    throw new AggregateError(
      [testFailure, ...cleanupErrors],
      "notification-topic delivery acceptance and exact-resource cleanup both failed"
    )
  }
  if (testFailed) throw testFailure
  if (cleanupErrors.length > 0) {
    throw new AggregateError(
      cleanupErrors,
      "test-owned notification resources were not fully cleaned"
    )
  }
})
