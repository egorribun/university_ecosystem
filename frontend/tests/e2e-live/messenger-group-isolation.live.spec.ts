import { devices, type BrowserContext, type Page } from "@playwright/test"
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

type GroupMessageEvent = {
  type: "new_message" | "message_edited" | "message_deleted"
  chatId: string
  messageId: string
  content?: string
  editedAt?: string
  deletedAt?: string
}

type SocketObservation = {
  roomJoins: string[]
  groupEvents: GroupMessageEvent[]
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

function findRoomJoins(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(findRoomJoins)
  if (!isRecord(value)) return []

  const rooms: string[] = []
  if (value.type === "join" && typeof value.room === "string") rooms.push(value.room)
  return [...rooms, ...Object.values(value).flatMap(findRoomJoins)]
}

function findGroupMessageEvents(value: unknown, chatId?: string): GroupMessageEvent[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => findGroupMessageEvents(item, chatId))
  }
  if (!isRecord(value)) return []

  const events: GroupMessageEvent[] = []
  const frameChatId = typeof value.chat_id === "string" ? value.chat_id : null
  const matchesChat = frameChatId !== null && (chatId === undefined || frameChatId === chatId)
  if (matchesChat && value.type === "new_message" && isRecord(value.message)) {
    if (typeof value.message.id === "string" && typeof value.message.content === "string") {
      events.push({
        type: "new_message",
        chatId: frameChatId,
        messageId: value.message.id,
        content: value.message.content,
      })
    }
  } else if (
    matchesChat &&
    value.type === "message_edited" &&
    typeof value.message_id === "string" &&
    typeof value.content === "string" &&
    typeof value.edited_at === "string"
  ) {
    events.push({
      type: "message_edited",
      chatId: frameChatId,
      messageId: value.message_id,
      content: value.content,
      editedAt: value.edited_at,
    })
  } else if (
    matchesChat &&
    value.type === "message_deleted" &&
    typeof value.message_id === "string" &&
    typeof value.deleted_at === "string"
  ) {
    events.push({
      type: "message_deleted",
      chatId: frameChatId,
      messageId: value.message_id,
      deletedAt: value.deleted_at,
    })
  }

  return [
    ...events,
    ...Object.values(value).flatMap((nested) => findGroupMessageEvents(nested, chatId)),
  ]
}

function observeSocket(page: Page): SocketObservation {
  const observation: SocketObservation = { roomJoins: [], groupEvents: [] }
  page.on("websocket", (socket) => {
    socket.on("framesent", (frame) => {
      observation.roomJoins.push(...findRoomJoins(parseFrame(frame)))
    })
    socket.on("framereceived", (frame) => {
      observation.groupEvents.push(...findGroupMessageEvents(parseFrame(frame)))
    })
  })
  return observation
}

function eventsForMessage(
  observation: SocketObservation,
  chatId: string,
  messageId: string
): GroupMessageEvent[] {
  return observation.groupEvents.filter(
    (event) => event.chatId === chatId && event.messageId === messageId
  )
}

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
type LiveMessagePage = {
  items: { content: string }[]
  has_more: boolean
  next_cursor: string | null
}

async function getCurrentUser(page: Page): Promise<LiveUser> {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.ok()).toBe(true)
  return (await response.json()) as LiveUser
}

async function findReusableGroup(page: Page, name: string): Promise<LiveGroup | null> {
  const matches: LiveGroup[] = []
  let cursor: string | null = null

  do {
    const parameters = new URLSearchParams({ limit: "100" })
    if (cursor) parameters.set("cursor", cursor)
    const response = await page.request.get(`/api/v1/chats?${parameters.toString()}`)
    expect(response.ok()).toBe(true)
    const chatPage = (await response.json()) as LiveChatPage
    matches.push(...chatPage.items.filter((chat) => chat.name === name))
    if (!chatPage.has_more) break
    expect(chatPage.next_cursor).toBeTruthy()
    cursor = chatPage.next_cursor
  } while (cursor)

  expect(matches.length).toBeLessThanOrEqual(1)
  return matches[0] ?? null
}

async function memberHistoryContains(
  page: Page,
  chatId: string,
  content: string
): Promise<boolean> {
  let cursor: string | null = null

  do {
    const parameters = new URLSearchParams({ limit: "100" })
    if (cursor) parameters.set("cursor", cursor)
    const response = await page.request.get(
      `/api/v1/chats/${chatId}/messages?${parameters.toString()}`
    )
    expect(response.ok()).toBe(true)
    const history = (await response.json()) as LiveMessagePage
    if (history.items.some((message) => message.content === content)) return true
    if (!history.has_more) return false
    expect(history.next_cursor).toBeTruthy()
    cursor = history.next_cursor
  } while (cursor)

  return false
}

function expectGroupOwnedByMembers(group: LiveGroup, ownerId: string, memberIds: string[]): void {
  expect(group.chat_type).toBe("group")
  expect(group.name).toBe(LIVE_GROUP_CHAT_NAME)
  expect(group.created_by).toBe(ownerId)
  expect(new Set(group.participants.map((participant) => participant.id))).toEqual(
    new Set(memberIds)
  )
}

async function selectGroupMember(page: Page, fullName: string): Promise<void> {
  const search = page.getByRole("textbox", { name: "Поиск пользователей" })
  await search.fill(fullName)
  const option = page.getByRole("option").filter({ hasText: fullName })
  await expect(option).toHaveCount(1)
  await option.click()
}

// Live traces and screenshots can retain credentials and private chat payloads.
test.use({ trace: "off", screenshot: "off" })

test.describe("live messenger group isolation", () => {
  test("group events reach both members and never reach an authenticated non-member", async ({
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

    try {
      const teacherContext = await browser.newContext(contextOptions)
      contexts.push(teacherContext)
      const secondMemberContext = await browser.newContext(contextOptions)
      contexts.push(secondMemberContext)
      const nonMemberContext = await browser.newContext(contextOptions)
      contexts.push(nonMemberContext)
      const teacherPage = await teacherContext.newPage()
      const secondMemberPage = await secondMemberContext.newPage()
      const nonMemberPage = await nonMemberContext.newPage()

      const teacherSocket = observeSocket(teacherPage)
      const secondMemberSocket = observeSocket(secondMemberPage)
      const nonMemberSocket = observeSocket(nonMemberPage)

      await loginAs(page, "student")
      await loginAs(teacherPage, "teacher")
      await loginWith(
        secondMemberPage,
        GROUP_CHAT_ACCOUNTS.secondMember.email,
        GROUP_CHAT_ACCOUNTS.secondMember.password
      )
      await loginWith(
        nonMemberPage,
        GROUP_CHAT_ACCOUNTS.nonMember.email,
        GROUP_CHAT_ACCOUNTS.nonMember.password
      )

      const owner = await getCurrentUser(page)
      const teacher = await getCurrentUser(teacherPage)
      const secondMember = await getCurrentUser(secondMemberPage)
      const outsider = await getCurrentUser(nonMemberPage)
      expect(owner.role).toBe("student")
      expect(teacher.role).toBe("teacher")
      expect(secondMember.role).toBe("student")
      expect(outsider.role).toBe("teacher")
      expect(new Set([owner.id, teacher.id, secondMember.id, outsider.id]).size).toBe(4)
      expect(teacher.full_name).toBeTruthy()
      expect(secondMember.full_name).toBeTruthy()

      let group = await findReusableGroup(page, LIVE_GROUP_CHAT_NAME)
      if (group) {
        expectGroupOwnedByMembers(group, owner.id, [owner.id, teacher.id, secondMember.id])
      } else {
        await page.goto("/messenger")
        await page.getByRole("button", { name: "Новый чат", exact: true }).click()
        await page.getByRole("tab", { name: "Группа", exact: true }).click()
        await page.getByRole("textbox", { name: "Название группы" }).fill(LIVE_GROUP_CHAT_NAME)
        await selectGroupMember(page, teacher.full_name!)
        await selectGroupMember(page, secondMember.full_name!)

        const createGroupResponsePromise = page.waitForResponse((response) => {
          const request = response.request()
          return (
            request.method() === "POST" &&
            new URL(response.url()).pathname === "/api/v1/chats/groups"
          )
        })
        await page.getByRole("button", { name: "Создать группу", exact: true }).click()
        const createGroupResponse = await createGroupResponsePromise
        expect(createGroupResponse.ok()).toBe(true)
        group = (await createGroupResponse.json()) as LiveGroup
        expectGroupOwnedByMembers(group, owner.id, [owner.id, teacher.id, secondMember.id])
      }

      const chatId = group.id
      expect(chatId).toBeTruthy()

      await page.goto(`/messenger/${chatId}`)
      await teacherPage.goto(`/messenger/${chatId}`)
      await secondMemberPage.goto(`/messenger/${chatId}`)
      await nonMemberPage.goto(`/messenger/${chatId}`)

      const deniedChatResponse = await nonMemberPage.request.get(`/api/v1/chats/${chatId}`)
      expect(deniedChatResponse.status()).toBe(403)

      const ownerLog = page.getByRole("log", { name: /Сообщения чата/i })
      const teacherLog = teacherPage.getByRole("log", { name: /Сообщения чата/i })
      const secondMemberLog = secondMemberPage.getByRole("log", { name: /Сообщения чата/i })
      await expect(ownerLog).toBeVisible()
      await expect(teacherLog).toBeVisible()
      await expect(secondMemberLog).toBeVisible()
      await expect
        .poll(() => teacherSocket.roomJoins.filter((room) => room === chatId).length)
        .toBeGreaterThan(0)
      await expect
        .poll(() => secondMemberSocket.roomJoins.filter((room) => room === chatId).length)
        .toBeGreaterThan(0)
      await expect
        .poll(() => nonMemberSocket.roomJoins.filter((room) => room === chatId).length)
        .toBeGreaterThan(0)

      const message = `live-group-ws-${crypto.randomUUID()}`
      const messageResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages`
        )
      })
      await page.locator("#chat-message-input").fill(message)
      await page.locator("#chat-send-btn").click()
      const messageResponse = await messageResponsePromise
      expect(messageResponse.ok()).toBe(true)
      const sentMessage = (await messageResponse.json()) as { id: string; content: string }
      expect(sentMessage.content).toBe(message)

      for (const socket of [teacherSocket, secondMemberSocket]) {
        await expect
          .poll(() =>
            eventsForMessage(socket, chatId, sentMessage.id).some(
              (event) => event.type === "new_message" && event.content === message
            )
          )
          .toBe(true)
      }
      await expect(teacherLog.getByText(message, { exact: true })).toBeVisible()
      await expect(secondMemberLog.getByText(message, { exact: true })).toBeVisible()

      const nonMemberAttempt = `live-group-outsider-${crypto.randomUUID()}`
      const nonMemberSendAttempt = await nonMemberPage.evaluate(
        async ({ chatId, content }) => {
          const readCsrfToken = (): string | null => {
            const cookie = document.cookie
              .split(";")
              .map((part) => part.trim())
              .find((part) => part.startsWith("csrf_token="))
            return cookie ? decodeURIComponent(cookie.slice("csrf_token=".length)) : null
          }

          let csrfToken = readCsrfToken()
          if (!csrfToken) {
            await fetch("/api/v1/auth/csrf-cookie", { credentials: "same-origin" })
            csrfToken = readCsrfToken()
          }
          if (!csrfToken) return { csrfAvailable: false, status: 0 }

          const body = new FormData()
          body.set("content", content)
          const response = await fetch(`/api/v1/chats/${chatId}/messages`, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRF-Token": csrfToken },
            body,
          })
          return { csrfAvailable: true, status: response.status }
        },
        { chatId, content: nonMemberAttempt }
      )
      expect(nonMemberSendAttempt.csrfAvailable).toBe(true)
      expect(nonMemberSendAttempt.status).toBe(403)

      for (const memberPage of [teacherPage, secondMemberPage]) {
        expect(await memberHistoryContains(memberPage, chatId, nonMemberAttempt)).toBe(false)
      }
      for (const socket of [teacherSocket, secondMemberSocket, nonMemberSocket]) {
        expect(
          socket.groupEvents.some(
            (event) => event.chatId === chatId && event.content === nonMemberAttempt
          )
        ).toBe(false)
      }
      for (const log of [teacherLog, secondMemberLog]) {
        await expect(log.getByText(nonMemberAttempt, { exact: true })).toHaveCount(0)
      }

      const editedContent = `${message}-edited`
      const messageRow = ownerLog
        .getByText(message, { exact: true })
        .locator(
          "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
        )
      await messageRow.getByRole("button", { name: "Изменить сообщение", exact: true }).click()
      await page
        .getByRole("textbox", { name: "Изменить сообщение", exact: true })
        .fill(editedContent)
      const editResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "PATCH" &&
          new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages/${sentMessage.id}`
        )
      })
      await page.getByRole("button", { name: "Сохранить", exact: true }).click()
      expect((await editResponsePromise).ok()).toBe(true)

      for (const socket of [teacherSocket, secondMemberSocket]) {
        await expect
          .poll(() =>
            eventsForMessage(socket, chatId, sentMessage.id).some(
              (event) =>
                event.type === "message_edited" &&
                event.content === editedContent &&
                typeof event.editedAt === "string" &&
                event.editedAt.length > 0
            )
          )
          .toBe(true)
      }
      for (const log of [teacherLog, secondMemberLog]) {
        await expect(log.getByText(editedContent, { exact: true })).toBeVisible()
        await expect(log.getByText(message, { exact: true })).toHaveCount(0)
      }

      const editedRow = ownerLog
        .getByText(editedContent, { exact: true })
        .locator(
          "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
        )
      await editedRow.getByRole("button", { name: "Удалить сообщение", exact: true }).click()
      const deleteDialog = page.getByRole("alertdialog", { name: "Удалить сообщение" })
      await expect(deleteDialog).toBeVisible()
      const deleteResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "DELETE" &&
          new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages/${sentMessage.id}`
        )
      })
      await deleteDialog.getByRole("button", { name: "Удалить", exact: true }).click()
      expect((await deleteResponsePromise).ok()).toBe(true)

      for (const socket of [teacherSocket, secondMemberSocket]) {
        await expect
          .poll(() =>
            eventsForMessage(socket, chatId, sentMessage.id).some(
              (event) =>
                event.type === "message_deleted" &&
                typeof event.deletedAt === "string" &&
                event.deletedAt.length > 0
            )
          )
          .toBe(true)
        const memberEvents = eventsForMessage(socket, chatId, sentMessage.id)
        const editIndex = memberEvents.findIndex((event) => event.type === "message_edited")
        const deleteIndex = memberEvents.findIndex((event) => event.type === "message_deleted")
        expect(editIndex).toBeGreaterThanOrEqual(0)
        expect(deleteIndex).toBeGreaterThan(editIndex)
      }
      for (const log of [teacherLog, secondMemberLog]) {
        await expect(log.getByText("Сообщение удалено", { exact: true })).toBeVisible()
        await expect(log.getByText(editedContent, { exact: true })).toHaveCount(0)
      }

      expect(eventsForMessage(nonMemberSocket, chatId, sentMessage.id)).toEqual([])
    } finally {
      await Promise.all(contexts.map((context) => context.close()))
    }
  })
})
