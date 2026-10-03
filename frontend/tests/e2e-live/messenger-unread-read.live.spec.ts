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
type ReadFrame = { chatId: string; userId: string; readAt: string | null }
type SocketSession = { roomJoins: string[]; readFrames: ReadFrame[] }
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

function findRoomJoins(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(findRoomJoins)
  if (!isRecord(value)) return []

  const rooms = value.type === "join" && typeof value.room === "string" ? [value.room] : []
  return [...rooms, ...Object.values(value).flatMap(findRoomJoins)]
}

function findReadFrames(value: unknown): ReadFrame[] {
  if (Array.isArray(value)) return value.flatMap(findReadFrames)
  if (!isRecord(value)) return []

  const payload = isRecord(value.payload) ? value.payload : value
  if (
    payload.type === "read" &&
    typeof payload.chat_id === "string" &&
    typeof payload.user_id === "string" &&
    (typeof payload.read_at === "string" || payload.read_at === null)
  ) {
    return [{ chatId: payload.chat_id, userId: payload.user_id, readAt: payload.read_at }]
  }
  return Object.values(value).flatMap(findReadFrames)
}

function observeSocket(page: Page): SocketObservation {
  const observation: SocketObservation = { sessions: [] }
  page.on("websocket", (socket) => {
    const session: SocketSession = { roomJoins: [], readFrames: [] }
    observation.sessions.push(session)
    socket.on("framesent", (frame) => session.roomJoins.push(...findRoomJoins(parseFrame(frame))))
    socket.on("framereceived", (frame) =>
      session.readFrames.push(...findReadFrames(parseFrame(frame)))
    )
  })
  return observation
}

function readFramesForChat(observation: SocketObservation, chatId: string): ReadFrame[] {
  return observation.sessions
    .flatMap((session) => session.readFrames)
    .filter((frame) => {
      return frame.chatId === chatId
    })
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
    throw new Error("Synthetic Messenger account registration returned no account id")
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
): Promise<{ id: string; chatType: string; participantIds: string[] }> {
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
  expect(chatResponse.ok(), "the sender creates a direct chat with the generated receiver").toBe(
    true
  )
  const createdChat = (await chatResponse.json()) as {
    id?: unknown
    chat_type?: unknown
    participants?: Array<{ id?: unknown }>
  }
  if (typeof createdChat.id === "string" && createdChat.id.length > 0) onCreated(createdChat.id)
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
  const message = (await response.json()) as { id?: unknown }
  if (typeof message.id !== "string" || message.id.length === 0) {
    throw new Error("Live message creation returned an invalid message id")
  }
  return { id: message.id, content }
}

type LiveChatListItem = { id: string; unread_count: number }
type LiveMessage = { id: string; read_status: boolean; read_at?: string | null }

async function getChatListItem(page: Page, chatId: string): Promise<LiveChatListItem | null> {
  const response = await page.request.get("/api/v1/chats?limit=100")
  expect(response.ok(), "the receiver can read its own live chat list").toBe(true)
  const body = (await response.json()) as { items?: LiveChatListItem[] }
  if (!Array.isArray(body.items)) throw new Error("Chat list returned no item collection")
  return body.items.find((item) => item.id === chatId) ?? null
}

async function getMessage(
  page: Page,
  chatId: string,
  messageId: string
): Promise<LiveMessage | null> {
  const response = await page.request.get(`/api/v1/chats/${chatId}/messages?limit=100`)
  expect(response.ok(), "the receiver can read messages in its own direct chat").toBe(true)
  const body = (await response.json()) as { items?: LiveMessage[] }
  if (!Array.isArray(body.items)) throw new Error("Message history returned no item collection")
  return body.items.find((item) => item.id === messageId) ?? null
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
  expect(response.ok(), "sender cleanup deletes only its exact generated message").toBe(true)
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
  expect(deletion.status, "cleanup deletes only the generated direct chat").toBe(200)
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
    "generated email and name identify at most one account"
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

test.use({ trace: "off", screenshot: "off", video: "off" })

test("a real DM read receipt clears only that chat's unread state", async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(210_000)
  const identity = randomUUID()
  const sender: SyntheticAccount = {
    id: null,
    email: `live-messenger-unread-sender-${testInfo.project.name}-${identity}@university.dev`,
    fullName: `Live Messenger Unread Sender ${testInfo.project.name} ${identity}`,
    password: freshPassword(),
    registrationAttempted: false,
  }
  const receiver: SyntheticAccount = {
    id: null,
    email: `live-messenger-unread-receiver-${testInfo.project.name}-${identity}@university.dev`,
    fullName: `Live Messenger Unread Receiver ${testInfo.project.name} ${identity}`,
    password: freshPassword(),
    registrationAttempted: false,
  }
  const peer: SyntheticAccount = {
    id: null,
    email: `live-messenger-unread-peer-${testInfo.project.name}-${identity}@university.dev`,
    fullName: `Live Messenger Unread Peer ${testInfo.project.name} ${identity}`,
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
  let peerContext: BrowserContext | null = null
  let adminContext: BrowserContext | null = null
  let adminPage: Page | null = null
  let peerPage: Page | null = null
  let adminReady = false
  let chatId: string | null = null
  let secondChatId: string | null = null
  let senderLog: Locator | null = null
  let peerLog: Locator | null = null
  const createdMessages: CreatedLiveMessage[] = []
  const peerMessages: CreatedLiveMessage[] = []
  let testFailure: unknown
  let testFailed = false

  try {
    const currentReceiverContext = await browser.newContext(contextOptions)
    receiverContext = currentReceiverContext
    const receiverPage = await currentReceiverContext.newPage()
    const currentPeerContext = await browser.newContext(contextOptions)
    peerContext = currentPeerContext
    const currentPeerPage = await currentPeerContext.newPage()
    peerPage = currentPeerPage
    const currentAdminContext = await browser.newContext({
      baseURL: LIVE_BASE_URL,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    adminContext = currentAdminContext
    const currentAdminPage = await currentAdminContext.newPage()
    adminPage = currentAdminPage
    await loginAs(currentAdminPage, "admin")
    adminReady = true

    const senderSocket = observeSocket(page)
    const peerSocket = observeSocket(currentPeerPage)
    await registerSyntheticUser(page, sender)
    await registerSyntheticUser(receiverPage, receiver)
    await registerSyntheticUser(currentPeerPage, peer)
    expect(sender.id).toBeTruthy()
    expect(receiver.id).toBeTruthy()
    expect(peer.id).toBeTruthy()
    expect(new Set([sender.id, receiver.id, peer.id]).size).toBe(3)

    const createdChat = await createDirectChat(page, receiver.fullName, (createdId) => {
      chatId = createdId
    })
    const activeChatId = createdChat.id
    expect(createdChat.chatType).toBe("dm")
    expect(new Set(createdChat.participantIds)).toEqual(new Set([sender.id, receiver.id]))
    await expect.poll(() => new URL(page.url()).pathname).toBe(`/messenger/${activeChatId}`)
    const senderMessageLog = page.getByRole("log", { name: /Сообщения чата/i })
    senderLog = senderMessageLog
    await expect(senderMessageLog).toBeVisible()
    await expect
      .poll(() => senderSocket.sessions.some((session) => session.roomJoins.includes(activeChatId)))
      .toBe(true)

    // Keep the receiver outside the conversation. Loading the DM must be the action
    // that clears its unread state, not delivery-time background work.
    await receiverPage.goto("/dashboard")
    const message = await sendLiveMessage(page, activeChatId, `live-unread-message-${identity}`)
    createdMessages.push(message)
    await expect(senderMessageLog.getByText(message.content, { exact: true })).toHaveCount(1)

    await expect
      .poll(async () => (await getChatListItem(receiverPage, activeChatId))?.unread_count ?? null)
      .toBe(1)
    await expect
      .poll(
        async () => (await getMessage(receiverPage, activeChatId, message.id))?.read_status ?? null
      )
      .toBe(false)

    const secondChat = await createDirectChat(receiverPage, peer.fullName, (createdId) => {
      secondChatId = createdId
    })
    const activeSecondChatId = secondChat.id
    expect(secondChat.chatType).toBe("dm")
    expect(new Set(secondChat.participantIds)).toEqual(new Set([receiver.id, peer.id]))
    await expect
      .poll(() => new URL(receiverPage.url()).pathname)
      .toBe(`/messenger/${activeSecondChatId}`)
    await receiverPage.goto("/dashboard")

    await currentPeerPage.goto(`/messenger/${activeSecondChatId}`)
    const peerMessageLog = currentPeerPage.getByRole("log", { name: /Сообщения чата/i })
    peerLog = peerMessageLog
    await expect(peerMessageLog).toBeVisible()
    await expect
      .poll(() =>
        peerSocket.sessions.some((session) => session.roomJoins.includes(activeSecondChatId))
      )
      .toBe(true)
    const secondMessage = await sendLiveMessage(
      currentPeerPage,
      activeSecondChatId,
      `live-unread-peer-message-${identity}`
    )
    peerMessages.push(secondMessage)
    await expect(peerMessageLog.getByText(secondMessage.content, { exact: true })).toHaveCount(1)
    await expect
      .poll(async () => (await getChatListItem(receiverPage, activeChatId))?.unread_count ?? null)
      .toBe(1)
    await expect
      .poll(
        async () => (await getChatListItem(receiverPage, activeSecondChatId))?.unread_count ?? null
      )
      .toBe(1)
    await expect
      .poll(
        async () =>
          (await getMessage(receiverPage, activeSecondChatId, secondMessage.id))?.read_status ??
          null
      )
      .toBe(false)

    // Reload the receiver so the list and accessible unread badge come from the persisted
    // server state rather than a prior React Query cache entry. Both DMs must stay independent.
    await receiverPage.reload()
    await receiverPage.goto("/messenger")
    const receiverChatRow = receiverPage.locator(`#messenger-contact-${activeChatId}`)
    const secondReceiverChatRow = receiverPage.locator(`#messenger-contact-${activeSecondChatId}`)
    await expect(receiverChatRow).toBeVisible()
    await expect(receiverChatRow.getByLabel(/1 непрочитано/u)).toHaveCount(1)
    await expect(secondReceiverChatRow).toBeVisible()
    await expect(secondReceiverChatRow.getByLabel(/1 непрочитано/u)).toHaveCount(1)

    const markReadResponsePromise = receiverPage.waitForResponse((response) => {
      const request = response.request()
      return (
        request.method() === "POST" &&
        new URL(response.url()).pathname === `/api/v1/chats/${activeChatId}/read`
      )
    })
    await receiverChatRow.click()
    const markReadResponse = await markReadResponsePromise
    expect(markReadResponse.ok(), "opening the generated DM persists its read state").toBe(true)

    const markReadBody = (await markReadResponse.json()) as { status?: unknown }
    expect(markReadBody.status).toBe("ok")
    await expect
      .poll(async () => (await getChatListItem(receiverPage, activeChatId))?.unread_count ?? null)
      .toBe(0)
    await expect
      .poll(
        async () => (await getMessage(receiverPage, activeChatId, message.id))?.read_status ?? null
      )
      .toBe(true)
    await expect
      .poll(
        async () => (await getChatListItem(receiverPage, activeSecondChatId))?.unread_count ?? null
      )
      .toBe(1)
    await expect
      .poll(
        async () =>
          (await getMessage(receiverPage, activeSecondChatId, secondMessage.id))?.read_status ??
          null
      )
      .toBe(false)
    await expect(secondReceiverChatRow.getByLabel(/1 непрочитано/u)).toHaveCount(1)

    await expect
      .poll(() => readFramesForChat(senderSocket, activeChatId))
      .toContainEqual(expect.objectContaining({ userId: receiver.id }))
    await expect
      .poll(() =>
        senderMessageLog.getByRole("img", { name: "Прочитано получателем", exact: true }).count()
      )
      .toBe(1)

    const secondMarkReadResponsePromise = receiverPage.waitForResponse((response) => {
      const request = response.request()
      return (
        request.method() === "POST" &&
        new URL(response.url()).pathname === `/api/v1/chats/${activeSecondChatId}/read`
      )
    })
    await secondReceiverChatRow.click()
    const secondMarkReadResponse = await secondMarkReadResponsePromise
    expect(secondMarkReadResponse.ok(), "the second DM has its own read transition").toBe(true)
    await expect
      .poll(
        async () => (await getChatListItem(receiverPage, activeSecondChatId))?.unread_count ?? null
      )
      .toBe(0)
    await expect
      .poll(
        async () =>
          (await getMessage(receiverPage, activeSecondChatId, secondMessage.id))?.read_status ??
          null
      )
      .toBe(true)
    await expect
      .poll(() => readFramesForChat(peerSocket, activeSecondChatId))
      .toContainEqual(expect.objectContaining({ userId: receiver.id }))
    await expect
      .poll(() =>
        peerMessageLog.getByRole("img", { name: "Прочитано получателем", exact: true }).count()
      )
      .toBe(1)
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
  if (secondChatId && peerLog && peerPage) {
    for (const message of [...peerMessages].reverse()) {
      await attemptCleanup(() =>
        deleteOwnedLiveMessage(peerPage!, peerLog!, secondChatId!, message)
      )
    }
  }
  if (chatId && adminPage && adminReady) {
    await attemptCleanup(() => deleteOnlyCreatedChat(adminPage!, chatId!))
  }
  if (secondChatId && adminPage && adminReady) {
    await attemptCleanup(() => deleteOnlyCreatedChat(adminPage!, secondChatId!))
  }

  if (receiverContext) {
    const contextToClose = receiverContext
    await attemptCleanup(() => contextToClose.close())
  }
  if (peerContext) {
    const contextToClose = peerContext
    await attemptCleanup(() => contextToClose.close())
  }
  if (adminPage && adminReady && sender.registrationAttempted) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage!, sender))
  }
  if (adminPage && adminReady && receiver.registrationAttempted) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage!, receiver))
  }
  if (adminPage && adminReady && peer.registrationAttempted) {
    await attemptCleanup(() => deleteOnlyCreatedAccount(adminPage!, peer))
  }
  if (adminContext) {
    const contextToClose = adminContext
    await attemptCleanup(() => contextToClose.close())
  }

  if (testFailed && cleanupErrors.length > 0) {
    throw new AggregateError(
      [testFailure, ...cleanupErrors],
      "Messenger acceptance and cleanup failed"
    )
  }
  if (testFailed) throw testFailure
  if (cleanupErrors.length > 0) {
    throw new AggregateError(cleanupErrors, "Messenger acceptance cleanup failed")
  }
})
