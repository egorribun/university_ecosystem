import { randomUUID } from "node:crypto"
import { devices, type BrowserContext, type Locator, type Page } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
  test,
} from "./fixtures"

const LIVE_BASE_URL = process.env.LIVE_BASE_URL
if (!LIVE_BASE_URL) {
  throw new Error("LIVE_BASE_URL must be set to the endpoint printed by scripts/live_stand.py")
}

type JsonRecord = Record<string, unknown>
type SyntheticAccount = {
  id: string | null
  email: string
  fullName: string
  password: string
  registrationAttempted: boolean
}
type ReceivedMessage = {
  chatId: string
  id: string
  senderId: string
  content: string
  sequence: number | null
  replayed: boolean
}
type RoomJoin = { room: string; hasResumeToken: boolean }
type SocketSession = {
  roomJoins: RoomJoin[]
  messages: ReceivedMessage[]
  closed: boolean
}
type SocketObservation = { sessions: SocketSession[] }
type CreatedLiveMessage = { id: string; content: string }

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function parseFrame(frame: { payload: string | Buffer }): unknown {
  try {
    const payload = frame.payload
    return JSON.parse(typeof payload === "string" ? payload : payload.toString("utf8")) as unknown
  } catch {
    return null
  }
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
    typeof payload.message.sender_id === "string" &&
    typeof payload.message.content === "string"
  ) {
    return [
      {
        chatId: payload.chat_id,
        id: payload.message.id,
        senderId: payload.message.sender_id,
        content: payload.message.content,
        sequence: typeof value.seq === "number" ? value.seq : null,
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
    socket.on("framesent", (frame) => session.roomJoins.push(...findRoomJoins(parseFrame(frame))))
    socket.on("framereceived", (frame) =>
      session.messages.push(...findNewMessages(parseFrame(frame)))
    )
    socket.on("close", () => {
      session.closed = true
    })
  })
  return observation
}

function receivedForChat(observation: SocketObservation, chatId: string): ReceivedMessage[] {
  return observation.sessions
    .flatMap((session) => session.messages)
    .filter((message) => message.chatId === chatId)
}

async function registerSyntheticUser(page: Page, account: SyntheticAccount): Promise<void> {
  await stubBreachedPasswordLookup(page)
  await page.goto("/register")
  await page.getByLabel("Имя", { exact: true }).fill(account.fullName)
  await page.getByRole("textbox", { name: "E-mail" }).fill(account.email)
  await page.getByLabel("Пароль", { exact: true }).fill(account.password)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(account.password)

  const registrationResponsePromise = page.waitForResponse((response) => {
    const request = response.request()
    return (
      request.method() === "POST" && new URL(response.url()).pathname.endsWith("/auth/register")
    )
  })
  account.registrationAttempted = true
  await page.getByRole("button", { name: "Зарегистрироваться" }).click()
  const registrationResponse = await registrationResponsePromise
  expect(registrationResponse.ok(), "the unique synthetic account registers in the live app").toBe(
    true
  )
  const registration = (await registrationResponse.json()) as { id?: unknown }
  if (typeof registration.id !== "string" || registration.id.length === 0) {
    throw new Error("Synthetic messenger account registration returned no account id")
  }
  account.id = registration.id

  await expect(page).toHaveURL(/\/login$/u)
  await loginWith(page, account.email, account.password)
  const identityResponse = await page.request.get("/api/v1/users/me")
  expect(identityResponse.ok()).toBe(true)
  const identity = (await identityResponse.json()) as { id: string; role: string }
  expect(identity.id).toBe(account.id)
  expect(identity.role).toBe("student")
}

async function createDirectChat(
  page: Page,
  receiverName: string,
  onCreated: (chatId: string) => void
): Promise<{ id: string; chatType: string; createdBy: string | null; participantIds: string[] }> {
  await page.goto("/messenger")
  await page.getByRole("button", { name: "Новый чат", exact: true }).click()
  await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(receiverName)
  const receiverOption = page.getByRole("option").filter({ hasText: receiverName })
  await expect(receiverOption).toHaveCount(1)

  const chatResponsePromise = page.waitForResponse((response) => {
    const request = response.request()
    return request.method() === "POST" && new URL(response.url()).pathname === "/api/v1/chats"
  })
  await receiverOption.click()
  const chatResponse = await chatResponsePromise
  expect(
    chatResponse.ok(),
    "the sender creates a new direct chat with the generated receiver"
  ).toBe(true)
  const createdChat = (await chatResponse.json()) as {
    id?: unknown
    chat_type?: unknown
    created_by?: unknown
    participants?: Array<{ id?: unknown }>
  }
  if (typeof createdChat.id === "string" && createdChat.id.length > 0) {
    onCreated(createdChat.id)
  }
  if (
    typeof createdChat.id !== "string" ||
    createdChat.id.length === 0 ||
    typeof createdChat.chat_type !== "string" ||
    !Array.isArray(createdChat.participants)
  ) {
    throw new Error("Synthetic direct chat creation returned no chat id")
  }
  return {
    id: createdChat.id,
    chatType: createdChat.chat_type,
    createdBy: typeof createdChat.created_by === "string" ? createdChat.created_by : null,
    participantIds: createdChat.participants.flatMap((participant) =>
      typeof participant.id === "string" ? [participant.id] : []
    ),
  }
}

async function sendLiveMessage(
  page: Page,
  chatId: string,
  content: string
): Promise<CreatedLiveMessage> {
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
  const created = (await response.json()) as { id?: unknown; content?: unknown }
  if (typeof created.id !== "string" || created.id.length === 0) {
    throw new Error("Live message creation returned an invalid message")
  }
  return { id: created.id, content }
}

async function deleteOwnedLiveMessage(
  page: Page,
  log: Locator,
  chatId: string,
  message: CreatedLiveMessage
): Promise<void> {
  const renderedMessage = log.getByText(message.content, { exact: true })
  if ((await renderedMessage.count()) === 0) return

  const row = renderedMessage.locator(
    "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
  )
  const deleteButton = row.getByRole("button", { name: "Удалить сообщение", exact: true })
  if ((await deleteButton.count()) === 0) return

  const responsePromise = page.waitForResponse((response) => {
    const request = response.request()
    return (
      request.method() === "DELETE" &&
      new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages/${message.id}`
    )
  })
  await deleteButton.click()
  const dialog = page.getByRole("alertdialog", { name: "Удалить сообщение" })
  await expect(dialog).toBeVisible()
  await dialog.getByRole("button", { name: "Удалить", exact: true }).click()
  const response = await responsePromise
  expect(response.ok(), "sender cleanup deletes only its exact test message").toBe(true)
  await expect(renderedMessage).toHaveCount(0)
}

async function deleteWithCurrentBrowserCsrf(
  page: Page,
  route: string
): Promise<{ status: number; deleted: boolean; resourceStatus: string | null }> {
  return page.evaluate(async (deleteRoute) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, deleted: false, resourceStatus: null }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch(deleteRoute, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await response.json().catch(() => null)) as {
      deleted?: boolean
      status?: string
    } | null
    return {
      status: response.status,
      deleted: body?.deleted === true,
      resourceStatus: typeof body?.status === "string" ? body.status : null,
    }
  }, route)
}

async function deleteOnlyCreatedChat(adminPage: Page, chatId: string): Promise<void> {
  const deletion = await deleteWithCurrentBrowserCsrf(
    adminPage,
    `/api/v1/chats/${encodeURIComponent(chatId)}`
  )
  expect(deletion.status, "cleanup deletes only the direct chat created in this test").toBe(200)
  expect(deletion.resourceStatus).toBe("deleted")
}

async function deleteOnlyCreatedAccount(adminPage: Page, account: SyntheticAccount): Promise<void> {
  if (!account.registrationAttempted) return

  const query = new URLSearchParams({ search: account.fullName, limit: "200" })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  expect(response.ok(), "admin resolves generated accounts for exact cleanup").toBe(true)
  const users = (await response.json()) as Array<{
    id: string
    email: string
    full_name: string | null
  }>
  const matches = users.filter(
    (user) => user.email === account.email && user.full_name === account.fullName
  )
  expect(
    matches.length,
    "generated email and full name identify at most one account"
  ).toBeLessThanOrEqual(1)
  const [match] = matches
  if (!match) return
  if (account.id) expect(match.id).toBe(account.id)

  const deletion = await deleteWithCurrentBrowserCsrf(
    adminPage,
    `/api/v1/users/${encodeURIComponent(match.id)}`
  )
  expect(deletion.status, "cleanup deletes only the generated account id").toBe(200)
  expect(deletion.deleted).toBe(true)
}

test.use({ trace: "off", screenshot: "off" })

test("two synthetic users receive ordered, exactly-once messages sent during a real reconnect", async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(150_000)
  const identity = randomUUID()
  const sender: SyntheticAccount = {
    id: null,
    email: `live-messenger-reconnect-sender-${testInfo.project.name}-${identity}@university.dev`,
    fullName: `Live Messenger Reconnect Sender ${testInfo.project.name} ${identity}`,
    password: freshPassword(),
    registrationAttempted: false,
  }
  const receiver: SyntheticAccount = {
    id: null,
    email: `live-messenger-reconnect-receiver-${testInfo.project.name}-${identity}@university.dev`,
    fullName: `Live Messenger Reconnect Receiver ${testInfo.project.name} ${identity}`,
    password: freshPassword(),
    registrationAttempted: false,
  }
  const mobile = testInfo.project.name === "mobile"
  const contextOptions = {
    ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
    baseURL: LIVE_BASE_URL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
    viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
  }
  let receiverContext: BrowserContext | null = null
  let adminContext: BrowserContext | null = null
  let adminPage: Page | null = null
  let chatId: string | null = null
  let senderLog: Locator | null = null
  const createdMessages: CreatedLiveMessage[] = []
  let testFailure: unknown
  let testFailed = false

  try {
    const currentReceiverContext = await browser.newContext(contextOptions)
    receiverContext = currentReceiverContext
    const receiverPage = await currentReceiverContext.newPage()
    const receiverSocket = observeSocket(receiverPage)
    const currentAdminContext = await browser.newContext({
      baseURL: LIVE_BASE_URL,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    adminContext = currentAdminContext
    const currentAdminPage = await currentAdminContext.newPage()
    adminPage = currentAdminPage
    await loginAs(currentAdminPage, "admin")

    await registerSyntheticUser(page, sender)
    await registerSyntheticUser(receiverPage, receiver)
    expect(sender.id).toBeTruthy()
    expect(receiver.id).toBeTruthy()
    expect(new Set([sender.id, receiver.id]).size).toBe(2)

    const createdChat = await createDirectChat(page, receiver.fullName, (createdId) => {
      chatId = createdId
    })
    const activeChatId = createdChat.id
    expect(createdChat.chatType).toBe("dm")
    expect(createdChat.createdBy).toBeNull()
    expect(new Set(createdChat.participantIds)).toEqual(new Set([sender.id, receiver.id]))
    await expect.poll(() => new URL(page.url()).pathname).toBe(`/messenger/${activeChatId}`)
    const senderMessageLog = page.getByRole("log", { name: /Сообщения чата/i })
    senderLog = senderMessageLog
    const receiverLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
    await expect(senderMessageLog).toBeVisible()
    await receiverPage.goto(`/messenger/${activeChatId}`)
    await expect(receiverLog).toBeVisible()
    await expect
      .poll(() =>
        receiverSocket!.sessions.some((session) =>
          session.roomJoins.some((join) => join.room === activeChatId)
        )
      )
      .toBe(true)

    const baseline = await sendLiveMessage(page, activeChatId, `live-reconnect-anchor-${identity}`)
    createdMessages.push(baseline)
    await expect
      .poll(() =>
        receivedForChat(receiverSocket, activeChatId).filter((event) => event.id === baseline.id)
      )
      .toHaveLength(1)
    await expect(receiverLog.getByText(baseline.content, { exact: true })).toHaveCount(1)
    const baselineFrame = receivedForChat(receiverSocket, activeChatId).find(
      (event) => event.id === baseline.id
    )
    expect(baselineFrame?.sequence ?? 0).toBeGreaterThan(0)

    const activeSession = [...receiverSocket.sessions]
      .reverse()
      .find((session) => session.roomJoins.some((join) => join.room === activeChatId))
    expect(activeSession).toBeDefined()
    const previousSessionCount = receiverSocket.sessions.length
    await currentReceiverContext.setOffline(true)
    await expect.poll(() => activeSession?.closed ?? false).toBe(true)
    await expect.poll(() => receiverPage.evaluate(() => navigator.onLine)).toBe(false)

    const offlineMessages = [
      await sendLiveMessage(page, activeChatId, `live-reconnect-offline-first-${identity}`),
      await sendLiveMessage(page, activeChatId, `live-reconnect-offline-second-${identity}`),
    ]
    createdMessages.push(...offlineMessages)
    const offlineMessageIds = offlineMessages.map((message) => message.id)
    expect(
      receivedForChat(receiverSocket, activeChatId).filter((event) =>
        offlineMessageIds.includes(event.id)
      )
    ).toEqual([])
    for (const message of offlineMessages) {
      await expect(senderMessageLog.getByText(message.content, { exact: true })).toHaveCount(1)
    }

    const historyRefetchPromise = receiverPage.waitForResponse((response) => {
      const request = response.request()
      return (
        request.method() === "GET" &&
        new URL(response.url()).pathname === `/api/v1/chats/${activeChatId}/messages`
      )
    })
    await currentReceiverContext.setOffline(false)
    await expect
      .poll(() =>
        receiverSocket!.sessions
          .slice(previousSessionCount)
          .some((session) =>
            session.roomJoins.some((join) => join.room === activeChatId && join.hasResumeToken)
          )
      )
      .toBe(true)
    const historyRefetch = await historyRefetchPromise
    expect(historyRefetch.ok()).toBe(true)

    const receivedOfflineMessages = () =>
      receivedForChat(receiverSocket, activeChatId).filter((message) =>
        offlineMessageIds.includes(message.id)
      )
    await expect.poll(() => receivedOfflineMessages()).toHaveLength(offlineMessages.length)
    const replayedFrames = receivedOfflineMessages()
    expect(replayedFrames.map((message) => message.id)).toEqual(offlineMessageIds)
    expect(new Set(replayedFrames.map((message) => message.id)).size).toBe(offlineMessageIds.length)
    expect(replayedFrames.every((message) => message.replayed)).toBe(true)

    const baselineSequence = baselineFrame?.sequence
    const replaySequences = replayedFrames.map((message) => message.sequence)
    if (
      typeof baselineSequence !== "number" ||
      replaySequences.some((sequence) => typeof sequence !== "number")
    ) {
      throw new Error("Reconnect delivery omitted its ordered WebSocket sequence")
    }
    expect(baselineSequence).toBeLessThan(replaySequences[0]!)
    expect(replaySequences[0]!).toBeLessThan(replaySequences[1]!)

    for (const message of offlineMessages) {
      await expect(receiverLog.getByText(message.content, { exact: true })).toHaveCount(1)
    }

    const afterReconnect = await sendLiveMessage(
      page,
      activeChatId,
      `live-reconnect-after-${identity}`
    )
    createdMessages.push(afterReconnect)
    await expect
      .poll(() =>
        receivedForChat(receiverSocket, activeChatId).filter(
          (event) => event.id === afterReconnect.id
        )
      )
      .toHaveLength(1)
    const afterReconnectFrame = receivedForChat(receiverSocket, activeChatId).find(
      (event) => event.id === afterReconnect.id
    )
    expect(afterReconnectFrame?.sequence ?? 0).toBeGreaterThan(replaySequences[1]!)
    await expect(receiverLog.getByText(afterReconnect.content, { exact: true })).toHaveCount(1)

    const expectedMessageIds = [...createdMessages.map((message) => message.id)]
    const allTestDeliveries = receivedForChat(receiverSocket, activeChatId).filter((message) =>
      expectedMessageIds.includes(message.id)
    )
    expect(allTestDeliveries.map((message) => message.id)).toEqual(expectedMessageIds)
    expect(allTestDeliveries).toHaveLength(expectedMessageIds.length)
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

  if (chatId && senderLog) {
    for (const message of [...createdMessages].reverse()) {
      await attemptCleanup(() => deleteOwnedLiveMessage(page, senderLog!, chatId!, message))
    }
  }
  if (chatId && adminPage) {
    await attemptCleanup(() => deleteOnlyCreatedChat(adminPage!, chatId!))
  }

  if (receiverContext) {
    const contextToClose = receiverContext
    receiverContext = null
    await attemptCleanup(() => contextToClose.close())
  }
  if (adminPage && sender.registrationAttempted) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage!, sender))
  }
  if (adminPage && receiver.registrationAttempted) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage!, receiver))
  }

  await Promise.all(
    [adminContext, receiverContext]
      .filter((context): context is BrowserContext => context !== null)
      .map((context) => context.close().catch((error: unknown) => cleanupErrors.push(error)))
  )

  if (testFailed && cleanupErrors.length > 0) {
    throw new AggregateError([testFailure, ...cleanupErrors], "test and owned-data cleanup failed")
  }
  if (testFailed) throw testFailure
  if (cleanupErrors.length > 0) {
    throw new AggregateError(cleanupErrors, "test-owned messenger data cleanup failed")
  }
})
