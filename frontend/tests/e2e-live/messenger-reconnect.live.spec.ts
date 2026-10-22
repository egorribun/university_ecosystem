import { devices, type BrowserContext, type Locator, type Page } from "@playwright/test"
import {
  expect,
  GROUP_CHAT_ACCOUNTS,
  LIVE_GROUP_CHAT_NAME,
  loginAs,
  loginWith,
  test,
} from "./fixtures"

const LIVE_BASE_URL = process.env.LIVE_BASE_URL
if (!LIVE_BASE_URL) {
  throw new Error("LIVE_BASE_URL must be set to the endpoint printed by scripts/live_stand.py")
}

type JsonRecord = Record<string, unknown>

type RoomJoin = { room: string; hasResumeToken: boolean }
type ReceivedMessage = {
  chatId: string
  messageId: string
  content: string
  sequence: number | null
  hasResumeToken: boolean
  replayed: boolean
}
type SocketSession = {
  roomJoins: RoomJoin[]
  messages: ReceivedMessage[]
  closed: boolean
}
type SocketObservation = { sessions: SocketSession[] }
type LiveUser = { id: string; full_name: string | null; role: string }
type LiveGroup = {
  id: string
  chat_type: string
  name: string | null
  created_by: string | null
  participants: { id: string }[]
}
type LiveChatPage = {
  items: LiveGroup[]
  has_more: boolean
  next_cursor: string | null
}

function parseFrame(frame: { payload: string | Buffer }): unknown {
  try {
    const payload = frame.payload
    return JSON.parse(typeof payload === "string" ? payload : payload.toString("utf8")) as unknown
  } catch {
    return null
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function findRoomJoins(value: unknown): RoomJoin[] {
  if (Array.isArray(value)) return value.flatMap(findRoomJoins)
  if (!isRecord(value)) return []

  const joins: RoomJoin[] = []
  if (value.type === "join" && typeof value.room === "string") {
    joins.push({ room: value.room, hasResumeToken: typeof value.resume_token === "string" })
  }
  return [...joins, ...Object.values(value).flatMap(findRoomJoins)]
}

function findNewMessages(value: unknown): ReceivedMessage[] {
  if (Array.isArray(value)) return value.flatMap(findNewMessages)
  if (!isRecord(value)) return []

  const payload = isRecord(value.payload) ? value.payload : value
  if (
    payload.type === "new_message" &&
    typeof payload.chat_id === "string" &&
    isRecord(payload.message) &&
    typeof payload.message.id === "string" &&
    typeof payload.message.content === "string"
  ) {
    return [
      {
        chatId: payload.chat_id,
        messageId: payload.message.id,
        content: payload.message.content,
        sequence: typeof value.seq === "number" ? value.seq : null,
        hasResumeToken: typeof value.resume_token === "string",
        replayed: value.replayed === true,
      },
    ]
  }

  return Object.values(value).flatMap(findNewMessages)
}

function observeSocket(page: Page): SocketObservation {
  const observation: SocketObservation = { sessions: [] }
  page.on("websocket", (socket) => {
    const session: SocketSession = { roomJoins: [], messages: [], closed: false }
    observation.sessions.push(session)
    socket.on("framesent", (frame) => {
      session.roomJoins.push(...findRoomJoins(parseFrame(frame)))
    })
    socket.on("framereceived", (frame) => {
      session.messages.push(...findNewMessages(parseFrame(frame)))
    })
    socket.on("close", () => {
      session.closed = true
    })
  })
  return observation
}

function receivedMessages(
  observation: SocketObservation,
  chatId: string,
  messageId: string
): ReceivedMessage[] {
  return observation.sessions
    .flatMap((session) => session.messages)
    .filter((message) => message.chatId === chatId && message.messageId === messageId)
}

async function getCurrentUser(page: Page): Promise<LiveUser> {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.ok()).toBe(true)
  return (await response.json()) as LiveUser
}

async function findReusableGroup(page: Page): Promise<LiveGroup | null> {
  const matches: LiveGroup[] = []
  let cursor: string | null = null

  do {
    const parameters = new URLSearchParams({ limit: "100" })
    if (cursor) parameters.set("cursor", cursor)
    const response = await page.request.get(`/api/v1/chats?${parameters.toString()}`)
    expect(response.ok()).toBe(true)
    const chatPage = (await response.json()) as LiveChatPage
    matches.push(...chatPage.items.filter((chat) => chat.name === LIVE_GROUP_CHAT_NAME))
    if (!chatPage.has_more) break
    expect(chatPage.next_cursor).toBeTruthy()
    cursor = chatPage.next_cursor
  } while (cursor)

  expect(matches.length).toBeLessThanOrEqual(1)
  return matches[0] ?? null
}

async function selectGroupMember(page: Page, fullName: string): Promise<void> {
  const search = page.getByRole("textbox", { name: "Поиск пользователей" })
  await search.fill(fullName)
  const option = page.getByRole("option").filter({ hasText: fullName })
  await expect(option).toHaveCount(1)
  await option.click()
}

function expectGroupOwnedByMembers(group: LiveGroup, ownerId: string, memberIds: string[]): void {
  expect(group.chat_type).toBe("group")
  expect(group.name).toBe(LIVE_GROUP_CHAT_NAME)
  expect(group.created_by).toBe(ownerId)
  expect(new Set(group.participants.map((participant) => participant.id))).toEqual(
    new Set(memberIds)
  )
}

async function resolveAcceptanceGroup(
  ownerPage: Page,
  owner: LiveUser,
  receiver: LiveUser,
  secondMember: LiveUser
): Promise<LiveGroup> {
  const existing = await findReusableGroup(ownerPage)
  if (existing) {
    expectGroupOwnedByMembers(existing, owner.id, [owner.id, receiver.id, secondMember.id])
    return existing
  }

  await ownerPage.goto("/messenger")
  await ownerPage.getByRole("button", { name: "Новый чат", exact: true }).click()
  await ownerPage.getByRole("tab", { name: "Группа", exact: true }).click()
  await ownerPage.getByRole("textbox", { name: "Название группы" }).fill(LIVE_GROUP_CHAT_NAME)
  await selectGroupMember(ownerPage, receiver.full_name!)
  await selectGroupMember(ownerPage, secondMember.full_name!)

  const createResponsePromise = ownerPage.waitForResponse((response) => {
    const request = response.request()
    return (
      request.method() === "POST" && new URL(response.url()).pathname === "/api/v1/chats/groups"
    )
  })
  await ownerPage.getByRole("button", { name: "Создать группу", exact: true }).click()
  const createResponse = await createResponsePromise
  expect(createResponse.ok()).toBe(true)
  const group = (await createResponse.json()) as LiveGroup
  expectGroupOwnedByMembers(group, owner.id, [owner.id, receiver.id, secondMember.id])
  return group
}

async function sendMessage(page: Page, chatId: string, content: string): Promise<{ id: string }> {
  const responsePromise = page.waitForResponse((response) => {
    const request = response.request()
    return (
      request.method() === "POST" &&
      new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages`
    )
  })
  await page.locator("#chat-message-input").fill(content)
  await page.locator("#chat-send-btn").click()
  const response = await responsePromise
  expect(response.ok()).toBe(true)
  return (await response.json()) as { id: string }
}

async function deleteOwnMessage(page: Page, log: Locator, content: string): Promise<void> {
  const message = log.getByText(content, { exact: true })
  if ((await message.count()) === 0) return
  const row = message.locator(
    "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
  )
  const deleteButton = row.getByRole("button", { name: "Удалить сообщение", exact: true })
  if ((await deleteButton.count()) === 0) return
  await deleteButton.click()
  const dialog = page.getByRole("alertdialog", { name: "Удалить сообщение" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Удалить", exact: true }).click()
  await expect(message).toHaveCount(0)
}

function eventsForRoom(
  observation: SocketObservation,
  chatId: string,
  messageId: string
): ReceivedMessage[] {
  return receivedMessages(observation, chatId, messageId)
}

// Live traces and screenshots can retain credentials and private chat payloads.
test.use({ trace: "off", screenshot: "off" })

test.describe("live messenger reconnect", () => {
  test("reconnect replays a missed message once in sequence and receives the next live message", async ({
    browser,
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === "mobile"
    const contextOptions = {
      ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
      baseURL: LIVE_BASE_URL,
      locale: "ru-RU",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    }
    const contexts: BrowserContext[] = []
    let ownerLog: Locator | undefined
    const createdMessages: string[] = []

    try {
      const receiverContext = await browser.newContext(contextOptions)
      contexts.push(receiverContext)
      const secondMemberContext = await browser.newContext(contextOptions)
      contexts.push(secondMemberContext)
      const receiverPage = await receiverContext.newPage()
      const secondMemberPage = await secondMemberContext.newPage()
      const receiverSocket = observeSocket(receiverPage)
      const secondMemberSocket = observeSocket(secondMemberPage)

      await loginAs(page, "student")
      await loginAs(receiverPage, "teacher")
      await loginWith(
        secondMemberPage,
        GROUP_CHAT_ACCOUNTS.secondMember.email,
        GROUP_CHAT_ACCOUNTS.secondMember.password
      )

      const owner = await getCurrentUser(page)
      const receiver = await getCurrentUser(receiverPage)
      const secondMember = await getCurrentUser(secondMemberPage)
      expect(owner.role).toBe("student")
      expect(receiver.role).toBe("teacher")
      expect(secondMember.role).toBe("student")
      expect(new Set([owner.id, receiver.id, secondMember.id]).size).toBe(3)
      expect(receiver.full_name).toBeTruthy()
      expect(secondMember.full_name).toBeTruthy()

      const group = await resolveAcceptanceGroup(page, owner, receiver, secondMember)
      const chatId = group.id
      await page.goto(`/messenger/${chatId}`)
      await receiverPage.goto(`/messenger/${chatId}`)
      await secondMemberPage.goto(`/messenger/${chatId}`)
      const senderLog = page.getByRole("log", { name: /Сообщения чата/i })
      const receiverLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
      const secondMemberLog = secondMemberPage.getByRole("log", { name: /Сообщения чата/i })
      ownerLog = senderLog
      await expect(senderLog).toBeVisible()
      await expect(receiverLog).toBeVisible()
      await expect(secondMemberLog).toBeVisible()
      await expect
        .poll(() =>
          receiverSocket.sessions.some((session) =>
            session.roomJoins.some((join) => join.room === chatId)
          )
        )
        .toBe(true)
      await expect
        .poll(() =>
          secondMemberSocket.sessions.some((session) =>
            session.roomJoins.some((join) => join.room === chatId)
          )
        )
        .toBe(true)

      const beforeReconnectContent = `live-reconnect-before-${crypto.randomUUID()}`
      const beforeReconnectMessage = await sendMessage(page, chatId, beforeReconnectContent)
      createdMessages.push(beforeReconnectContent)
      await expect
        .poll(() => eventsForRoom(receiverSocket, chatId, beforeReconnectMessage.id).length)
        .toBe(1)
      const initialDelivery = eventsForRoom(receiverSocket, chatId, beforeReconnectMessage.id)[0]!
      expect(initialDelivery.sequence ?? 0).toBeGreaterThan(0)
      expect(initialDelivery.hasResumeToken).toBe(true)
      await expect(receiverLog.getByText(beforeReconnectContent, { exact: true })).toHaveCount(1)

      const activeSession = [...receiverSocket.sessions]
        .reverse()
        .find((session) => session.roomJoins.some((join) => join.room === chatId))
      expect(activeSession).toBeDefined()
      const previousSessionCount = receiverSocket.sessions.length
      await receiverContext.setOffline(true)
      await expect.poll(() => activeSession?.closed ?? false).toBe(true)
      await expect.poll(() => receiverPage.evaluate(() => navigator.onLine)).toBe(false)

      const missedWhileOfflineContent = `live-reconnect-missed-${crypto.randomUUID()}`
      const missedWhileOfflineMessage = await sendMessage(page, chatId, missedWhileOfflineContent)
      createdMessages.push(missedWhileOfflineContent)
      await expect
        .poll(() => eventsForRoom(secondMemberSocket, chatId, missedWhileOfflineMessage.id).length)
        .toBe(1)
      const observerDelivery = eventsForRoom(
        secondMemberSocket,
        chatId,
        missedWhileOfflineMessage.id
      )[0]!
      expect(observerDelivery.sequence ?? 0).toBeGreaterThan(initialDelivery.sequence ?? 0)
      await expect(
        secondMemberLog.getByText(missedWhileOfflineContent, { exact: true })
      ).toHaveCount(1)

      const historyRefetchPromise = receiverPage.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "GET" &&
          new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages`
        )
      })
      await receiverContext.setOffline(false)
      await expect
        .poll(() =>
          receiverSocket.sessions
            .slice(previousSessionCount)
            .some((session) =>
              session.roomJoins.some((join) => join.room === chatId && join.hasResumeToken)
            )
        )
        .toBe(true)
      const historyRefetch = await historyRefetchPromise
      expect(historyRefetch.ok()).toBe(true)

      await expect
        .poll(() => eventsForRoom(receiverSocket, chatId, missedWhileOfflineMessage.id).length)
        .toBe(1)
      const missedDelivery = eventsForRoom(receiverSocket, chatId, missedWhileOfflineMessage.id)[0]!
      expect(missedDelivery.replayed).toBe(true)
      expect(missedDelivery.sequence ?? 0).toBeGreaterThan(initialDelivery.sequence ?? 0)
      await expect(receiverLog.getByText(missedWhileOfflineContent, { exact: true })).toHaveCount(1)

      await expect
        .poll(() => eventsForRoom(receiverSocket, chatId, beforeReconnectMessage.id).length)
        .toBe(1)
      await expect(receiverLog.getByText(beforeReconnectContent, { exact: true })).toHaveCount(1)

      const afterReconnectContent = `live-reconnect-after-${crypto.randomUUID()}`
      const afterReconnectMessage = await sendMessage(page, chatId, afterReconnectContent)
      createdMessages.push(afterReconnectContent)
      await expect
        .poll(() => eventsForRoom(receiverSocket, chatId, afterReconnectMessage.id).length)
        .toBe(1)
      const afterReconnectDelivery = eventsForRoom(
        receiverSocket,
        chatId,
        afterReconnectMessage.id
      )[0]!
      expect(afterReconnectDelivery.sequence ?? 0).toBeGreaterThan(missedDelivery.sequence ?? 0)
      await expect(receiverLog.getByText(afterReconnectContent, { exact: true })).toHaveCount(1)
    } finally {
      if (ownerLog) {
        for (const content of createdMessages) {
          try {
            await deleteOwnMessage(page, ownerLog, content)
          } catch {
            // Best-effort cleanup uses only the seeded sender's own messages.
          }
        }
      }
      await Promise.all(contexts.map((context) => context.close()))
    }
  })
})
