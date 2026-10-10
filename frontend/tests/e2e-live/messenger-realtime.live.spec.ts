import { devices, type Locator, type Page } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"
import { reportLiveHttpStatus } from "./http-status-diagnostic"

const LIVE_BASE_URL = process.env.LIVE_BASE_URL
if (!LIVE_BASE_URL) {
  throw new Error("LIVE_BASE_URL must be set to the endpoint printed by scripts/live_stand.py")
}

type JsonRecord = Record<string, unknown>

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

function hasRoomJoin(value: unknown, room: string): boolean {
  if (Array.isArray(value)) return value.some((item) => hasRoomJoin(item, room))
  if (!isRecord(value)) return false
  if (value.type === "join" && value.room === room) return true
  return Object.values(value).some((item) => hasRoomJoin(item, room))
}

type ReceivedMessageFrame = {
  chatId: unknown
  sequence: number | null
  replayed: boolean
  message: {
    id: unknown
    chatId: unknown
    senderId: unknown
    content: unknown
    replyToId?: unknown
    forwardedFromName?: unknown
  }
}

type MessageMutationFrame =
  | {
      type: "message_edited"
      chatId: unknown
      messageId: unknown
      content: unknown
      editedAt: unknown
    }
  | {
      type: "message_deleted"
      chatId: unknown
      messageId: unknown
      deletedAt: unknown
    }

type ReactionMutationFrame = {
  type: "reaction_changed"
  chatId: unknown
  messageId: unknown
  userId: unknown
  emoji: unknown
  action: unknown
}

function findNewMessageFrames(value: unknown): ReceivedMessageFrame[] {
  if (Array.isArray(value)) return value.flatMap(findNewMessageFrames)
  if (!isRecord(value)) return []

  const payload = isRecord(value.payload) ? value.payload : value
  if (payload.type === "new_message" && isRecord(payload.message)) {
    const replyToMetadata = isRecord(payload.message.reply_to)
      ? { replyToId: payload.message.reply_to.id }
      : {}
    const forwardedFromMetadata =
      typeof payload.message.forwarded_from_name === "string"
        ? { forwardedFromName: payload.message.forwarded_from_name }
        : {}
    return [
      {
        chatId: payload.chat_id,
        sequence: typeof value.seq === "number" ? value.seq : null,
        replayed: value.replayed === true,
        message: {
          id: payload.message.id,
          chatId: payload.message.chat_id,
          senderId: payload.message.sender_id,
          content: payload.message.content,
          ...replyToMetadata,
          ...forwardedFromMetadata,
        },
      },
    ]
  }
  return Object.values(value).flatMap(findNewMessageFrames)
}

function findMessageMutationFrames(value: unknown): MessageMutationFrame[] {
  if (Array.isArray(value)) return value.flatMap(findMessageMutationFrames)
  if (!isRecord(value)) return []

  const frames: MessageMutationFrame[] = []
  if (value.type === "message_edited") {
    frames.push({
      type: "message_edited",
      chatId: value.chat_id,
      messageId: value.message_id,
      content: value.content,
      editedAt: value.edited_at,
    })
  } else if (value.type === "message_deleted") {
    frames.push({
      type: "message_deleted",
      chatId: value.chat_id,
      messageId: value.message_id,
      deletedAt: value.deleted_at,
    })
  }
  return [...frames, ...Object.values(value).flatMap(findMessageMutationFrames)]
}

function findReactionMutationFrames(value: unknown): ReactionMutationFrame[] {
  if (Array.isArray(value)) return value.flatMap(findReactionMutationFrames)
  if (!isRecord(value)) return []
  if (value.type === "reaction_changed") {
    return [
      {
        type: "reaction_changed",
        chatId: value.chat_id,
        messageId: value.message_id,
        userId: value.user_id,
        emoji: value.emoji,
        action: value.action,
      },
    ]
  }
  return Object.values(value).flatMap(findReactionMutationFrames)
}

type CreatedLiveMessage = { id: string; content: string }
type ReceiverSocketSession = { joinedChat: boolean; closed: boolean }

async function sendLiveMessage(
  page: Page,
  chatId: string,
  content: string,
  project: string
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
  if (!response.ok()) {
    reportLiveHttpStatus(project, "messenger-message-send", response.status())
  }
  expect(response.ok()).toBe(true)
  const created = (await response.json()) as { id: string }
  expect(created.id).toBeTruthy()
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
  expect(response.ok()).toBe(true)
  await expect(renderedMessage).toHaveCount(0)
}

async function deleteOwnedForwardedLiveMessage(
  page: Page,
  log: Locator,
  chatId: string,
  message: CreatedLiveMessage & { forwardedFromName: string }
): Promise<void> {
  const attribution = log.getByText(`Переслано от ${message.forwardedFromName}`, { exact: true })
  let forwardedRow = attribution
    .locator(
      "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
    )
    .filter({ hasText: message.content })
  if ((await forwardedRow.count()) === 0) {
    const matchingContent = log.getByText(message.content, { exact: true })
    if ((await matchingContent.count()) < 2) return
    forwardedRow = matchingContent
      .last()
      .locator(
        "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
      )
  }

  const deleteButton = forwardedRow.getByRole("button", { name: "Удалить сообщение", exact: true })
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
  expect(response.ok()).toBe(true)
}

// Playwright traces can retain login request bodies. The seeded role fixtures
// are authenticated through the real UI, so this focused lane keeps them off.
test.use({ trace: "off", screenshot: "off" })

test.describe("live messenger delivery", () => {
  test("a message is delivered, edited, and tombstoned in the other authenticated session", async ({
    browser,
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === "mobile"
    const receiverContext = await browser.newContext({
      ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
      baseURL: LIVE_BASE_URL,
      locale: "ru-RU",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    })

    try {
      const receiverPage = await receiverContext.newPage()
      const message = `live-ws-${crypto.randomUUID()}`

      await loginAs(page, "student")
      await loginAs(receiverPage, "teacher")
      const studentResponse = await page.request.get("/api/v1/users/me")
      expect(studentResponse.ok()).toBe(true)
      const student = (await studentResponse.json()) as { id: string; role: string }
      expect(student.role).toBe("student")

      const teacherResponse = await receiverPage.request.get("/api/v1/users/me")
      expect(teacherResponse.ok()).toBe(true)
      const teacher = (await teacherResponse.json()) as {
        id: string
        full_name: string | null
        role: string
      }
      expect(teacher.role).toBe("teacher")
      expect(teacher.full_name).toBeTruthy()
      expect(teacher.id).not.toBe(student.id)

      await page.goto("/messenger")
      await page.getByRole("button", { name: "Новый чат", exact: true }).click()
      await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(teacher.full_name!)
      const teacherOption = page.getByRole("option").filter({ hasText: teacher.full_name! })
      await expect(teacherOption).toHaveCount(1)
      await teacherOption.click()
      await expect(page).toHaveURL(/\/messenger\/[^/]+\/?$/)

      const chatId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1)
      expect(chatId).toBeTruthy()
      if (!chatId) throw new Error("New direct chat route did not contain a chat id")

      let receiverSocketCount = 0
      let receiverRoomJoinCount = 0
      const receiverMessages: ReceivedMessageFrame[] = []
      const receiverMutations: MessageMutationFrame[] = []
      receiverPage.on("websocket", (socket) => {
        receiverSocketCount += 1
        socket.on("framesent", (payload) => {
          if (hasRoomJoin(parseFrame(payload), chatId)) receiverRoomJoinCount += 1
        })
        socket.on("framereceived", (payload) => {
          const frame = parseFrame(payload)
          receiverMessages.push(...findNewMessageFrames(frame))
          receiverMutations.push(...findMessageMutationFrames(frame))
        })
      })

      const senderLog = page.getByRole("log", { name: /Сообщения чата/i })
      await expect(senderLog).toBeVisible()
      await receiverPage.goto(`/messenger/${chatId}`)
      const messageLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
      await expect(messageLog).toBeVisible()
      await expect.poll(() => receiverSocketCount).toBeGreaterThan(0)
      await expect.poll(() => receiverRoomJoinCount).toBeGreaterThan(0)

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
      if (!messageResponse.ok()) {
        reportLiveHttpStatus(
          testInfo.project.name,
          "messenger-message-send",
          messageResponse.status()
        )
      }
      expect(messageResponse.ok()).toBe(true)
      const sentMessage = (await messageResponse.json()) as {
        id: string
        chat_id: string
        sender_id: string
        content: string
      }
      expect(sentMessage).toMatchObject({
        chat_id: chatId,
        sender_id: student.id,
        content: message,
      })
      expect(sentMessage.id).toBeTruthy()

      const expectedFrame = {
        chatId,
        message: {
          id: sentMessage.id,
          chatId,
          senderId: student.id,
          content: message,
        },
      }
      await expect
        .poll(() =>
          receiverMessages.some(
            (frame) =>
              frame.chatId === expectedFrame.chatId &&
              frame.message.id === expectedFrame.message.id &&
              frame.message.chatId === expectedFrame.message.chatId &&
              frame.message.senderId === expectedFrame.message.senderId &&
              frame.message.content === expectedFrame.message.content
          )
        )
        .toBe(true)
      expect(receiverMessages).toContainEqual(expect.objectContaining(expectedFrame))
      const renderedMessage = messageLog.getByText(message, { exact: true })
      await expect(renderedMessage).toHaveCount(1)
      await expect(renderedMessage).toBeVisible()

      const editedContent = `${message}-edited`
      const sentMessageRow = senderLog
        .getByText(message, { exact: true })
        .locator(
          "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
        )
      await sentMessageRow.getByRole("button", { name: "Изменить сообщение", exact: true }).click()
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
      const editResponse = await editResponsePromise
      expect(editResponse.ok()).toBe(true)

      await expect
        .poll(() =>
          receiverMutations.some(
            (frame) =>
              frame.type === "message_edited" &&
              frame.chatId === chatId &&
              frame.messageId === sentMessage.id &&
              frame.content === editedContent &&
              typeof frame.editedAt === "string" &&
              frame.editedAt.length > 0
          )
        )
        .toBe(true)
      await expect(messageLog.getByText(editedContent, { exact: true })).toBeVisible()
      await expect(messageLog.getByText(message, { exact: true })).toHaveCount(0)

      const receivedEditedMessageRow = messageLog
        .getByText(editedContent, { exact: true })
        .locator(
          "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
        )
      await receivedEditedMessageRow
        .getByRole("button", { name: "Добавить реакцию", exact: true })
        .click()
      const reactionPicker = receiverPage.getByRole("group", {
        name: "Добавить реакцию",
        exact: true,
      })
      await expect(reactionPicker).toBeVisible()
      const reactionResponsePromise = receiverPage.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname ===
            `/api/v1/chats/${chatId}/messages/${sentMessage.id}/reactions`
        )
      })
      await reactionPicker.getByRole("button", { name: "Отреагировать 👍", exact: true }).click()
      const reactionResponse = await reactionResponsePromise
      expect(reactionResponse.ok()).toBe(true)
      await expect(
        receivedEditedMessageRow.getByRole("button", {
          name: /Переключить реакцию 👍, 1/,
          exact: true,
        })
      ).toBeVisible()

      const editedMessageRow = senderLog
        .getByText(editedContent, { exact: true })
        .locator(
          "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
        )
      await editedMessageRow.getByRole("button", { name: "Удалить сообщение", exact: true }).click()
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
      const deleteResponse = await deleteResponsePromise
      expect(deleteResponse.ok()).toBe(true)

      await expect
        .poll(() =>
          receiverMutations.some(
            (frame) =>
              frame.type === "message_deleted" &&
              frame.chatId === chatId &&
              frame.messageId === sentMessage.id &&
              typeof frame.deletedAt === "string" &&
              frame.deletedAt.length > 0
          )
        )
        .toBe(true)
      const editFrameIndex = receiverMutations.findIndex(
        (frame) => frame.type === "message_edited" && frame.messageId === sentMessage.id
      )
      const deleteFrameIndex = receiverMutations.findIndex(
        (frame) => frame.type === "message_deleted" && frame.messageId === sentMessage.id
      )
      expect(editFrameIndex).toBeGreaterThanOrEqual(0)
      expect(deleteFrameIndex).toBeGreaterThan(editFrameIndex)
      const tombstone = messageLog.getByText("Сообщение удалено", { exact: true })
      await expect(tombstone).toBeVisible()
      await expect(messageLog.getByText(editedContent, { exact: true })).toHaveCount(0)
      const tombstoneRow = tombstone.locator(
        "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
      )
      await expect(tombstoneRow).toBeVisible()
      await expect(tombstoneRow.getByRole("button", { name: /реакци/i })).toHaveCount(0)

      const [senderHistoryResponse, receiverHistoryResponse] = await Promise.all([
        page.request.get(`/api/v1/chats/${chatId}/messages?limit=50`),
        receiverPage.request.get(`/api/v1/chats/${chatId}/messages?limit=50`),
      ])
      expect(senderHistoryResponse.ok()).toBe(true)
      expect(receiverHistoryResponse.ok()).toBe(true)
      const senderHistory = (await senderHistoryResponse.json()) as {
        items: Array<{
          id: string
          content: string
          deleted_at: string | null
          reactions: Array<{ emoji: string; count: number; reacted_by_me: boolean }>
        }>
      }
      const receiverHistory = (await receiverHistoryResponse.json()) as {
        items: Array<{
          id: string
          content: string
          deleted_at: string | null
          reactions: Array<{ emoji: string; count: number; reacted_by_me: boolean }>
        }>
      }
      const senderTombstone = senderHistory.items.find((item) => item.id === sentMessage.id)
      const receiverTombstone = receiverHistory.items.find((item) => item.id === sentMessage.id)
      expect(senderTombstone).toMatchObject({ id: sentMessage.id, content: "" })
      expect(senderTombstone?.deleted_at).toBeTruthy()
      expect(receiverTombstone).toMatchObject({ id: sentMessage.id, content: "" })
      expect(receiverTombstone?.deleted_at).toBeTruthy()
      expect(senderTombstone?.reactions).toEqual([{ emoji: "👍", count: 1, reacted_by_me: false }])
      expect(receiverTombstone?.reactions).toEqual([{ emoji: "👍", count: 1, reacted_by_me: true }])
    } finally {
      await receiverContext.close()
    }
  })

  test("direct-message replay stays ordered and exactly once across receiver reconnect", async ({
    browser,
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === "mobile"
    const receiverContext = await browser.newContext({
      ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
      baseURL: LIVE_BASE_URL,
      locale: "ru-RU",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    })
    const createdMessages: CreatedLiveMessage[] = []
    let chatId: string | null = null
    let senderLog: Locator | null = null

    try {
      const receiverPage = await receiverContext.newPage()
      await loginAs(page, "student")
      await loginAs(receiverPage, "teacher")

      const studentResponse = await page.request.get("/api/v1/users/me")
      const teacherResponse = await receiverPage.request.get("/api/v1/users/me")
      expect(studentResponse.ok()).toBe(true)
      expect(teacherResponse.ok()).toBe(true)
      const student = (await studentResponse.json()) as { id: string; role: string }
      const teacher = (await teacherResponse.json()) as {
        id: string
        full_name: string | null
        role: string
      }
      expect(student.role).toBe("student")
      expect(teacher.role).toBe("teacher")
      expect(teacher.full_name).toBeTruthy()
      expect(teacher.id).not.toBe(student.id)

      await page.goto("/messenger")
      await page.getByRole("button", { name: "Новый чат", exact: true }).click()
      await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(teacher.full_name!)
      const teacherOption = page.getByRole("option").filter({ hasText: teacher.full_name! })
      await expect(teacherOption).toHaveCount(1)
      await teacherOption.click()
      await expect(page).toHaveURL(/\/messenger\/[^/]+\/?$/)
      const chatIdFromRoute = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1)
      expect(chatIdFromRoute).toBeTruthy()
      if (!chatIdFromRoute) throw new Error("Direct chat route did not contain a chat id")
      chatId = chatIdFromRoute

      const receiverMessages: ReceivedMessageFrame[] = []
      const receiverSessions: ReceiverSocketSession[] = []
      receiverPage.on("websocket", (socket) => {
        const session: ReceiverSocketSession = { joinedChat: false, closed: false }
        receiverSessions.push(session)
        socket.on("framesent", (frame) => {
          if (hasRoomJoin(parseFrame(frame), chatIdFromRoute)) session.joinedChat = true
        })
        socket.on("framereceived", (frame) => {
          receiverMessages.push(...findNewMessageFrames(parseFrame(frame)))
        })
        socket.on("close", () => {
          session.closed = true
        })
      })

      senderLog = page.getByRole("log", { name: /Сообщения чата/i })
      const receiverLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
      await expect(senderLog).toBeVisible()
      await receiverPage.goto(`/messenger/${chatIdFromRoute}`)
      await expect(receiverLog).toBeVisible()
      await expect.poll(() => receiverSessions.some((session) => session.joinedChat)).toBe(true)

      const first = await sendLiveMessage(
        page,
        chatIdFromRoute,
        `live-dm-order-first-${crypto.randomUUID()}`,
        testInfo.project.name
      )
      createdMessages.push(first)
      const second = await sendLiveMessage(
        page,
        chatIdFromRoute,
        `live-dm-order-second-${crypto.randomUUID()}`,
        testInfo.project.name
      )
      createdMessages.push(second)
      const messageIds = [first.id, second.id]
      const deliveriesForMessages = () =>
        receiverMessages.filter(
          (frame) =>
            frame.chatId === chatIdFromRoute && messageIds.includes(String(frame.message.id))
        )

      for (const message of createdMessages) {
        await expect
          .poll(
            () => deliveriesForMessages().filter((frame) => frame.message.id === message.id).length
          )
          .toBe(1)
        await expect(receiverLog.getByText(message.content, { exact: true })).toHaveCount(1)
      }

      const orderedDeliveries = deliveriesForMessages()
      expect(orderedDeliveries.map((frame) => frame.message.id)).toEqual(messageIds)
      const firstSequence = orderedDeliveries[0]?.sequence
      const secondSequence = orderedDeliveries[1]?.sequence
      if (typeof firstSequence !== "number" || typeof secondSequence !== "number") {
        throw new Error("Direct message delivery sequence was missing")
      }
      expect(firstSequence).toBeLessThan(secondSequence)

      const activeSession = [...receiverSessions].reverse().find((session) => session.joinedChat)
      expect(activeSession).toBeDefined()
      const previousSessionCount = receiverSessions.length
      await receiverContext.setOffline(true)
      await expect.poll(() => activeSession?.closed ?? false).toBe(true)
      await expect.poll(() => receiverPage.evaluate(() => navigator.onLine)).toBe(false)

      const missedWhileOffline = await sendLiveMessage(
        page,
        chatIdFromRoute,
        `live-dm-reconnect-missed-${crypto.randomUUID()}`,
        testInfo.project.name
      )
      createdMessages.push(missedWhileOffline)
      const missedDeliveries = () =>
        receiverMessages.filter(
          (frame) => frame.chatId === chatIdFromRoute && frame.message.id === missedWhileOffline.id
        )
      expect(missedDeliveries()).toEqual([])
      await expect(receiverLog.getByText(missedWhileOffline.content, { exact: true })).toHaveCount(
        0
      )

      const historyRefetchPromise = receiverPage.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "GET" &&
          new URL(response.url()).pathname === `/api/v1/chats/${chatIdFromRoute}/messages`
        )
      })
      await receiverContext.setOffline(false)
      await expect
        .poll(() =>
          receiverSessions.slice(previousSessionCount).some((session) => session.joinedChat)
        )
        .toBe(true)
      const historyRefetch = await historyRefetchPromise
      expect(historyRefetch.ok()).toBe(true)

      await expect.poll(() => missedDeliveries().length).toBe(1)
      const missedDelivery = missedDeliveries()[0]!
      expect(missedDelivery.replayed).toBe(true)
      const missedSequence = missedDelivery.sequence
      if (typeof missedSequence !== "number") {
        throw new Error("Replayed direct message delivery sequence was missing")
      }
      expect(secondSequence).toBeLessThan(missedSequence)
      await expect(receiverLog.getByText(missedWhileOffline.content, { exact: true })).toHaveCount(
        1
      )

      const afterReconnect = await sendLiveMessage(
        page,
        chatIdFromRoute,
        `live-dm-reconnect-after-${crypto.randomUUID()}`,
        testInfo.project.name
      )
      createdMessages.push(afterReconnect)
      const afterReconnectDeliveries = () =>
        receiverMessages.filter(
          (frame) => frame.chatId === chatIdFromRoute && frame.message.id === afterReconnect.id
        )
      await expect.poll(() => afterReconnectDeliveries().length).toBe(1)
      const afterReconnectDelivery = afterReconnectDeliveries()[0]!
      expect(afterReconnectDelivery.replayed).toBe(false)
      const afterReconnectSequence = afterReconnectDelivery.sequence
      if (typeof afterReconnectSequence !== "number") {
        throw new Error("Post-reconnect direct message delivery sequence was missing")
      }
      expect(missedSequence).toBeLessThan(afterReconnectSequence)

      const expectedMessageIds = [first.id, second.id, missedWhileOffline.id, afterReconnect.id]
      const allTestDeliveries = receiverMessages.filter(
        (frame) =>
          frame.chatId === chatIdFromRoute && expectedMessageIds.includes(String(frame.message.id))
      )
      expect(allTestDeliveries.map((frame) => frame.message.id)).toEqual(expectedMessageIds)
      expect(allTestDeliveries).toHaveLength(expectedMessageIds.length)

      for (const message of createdMessages) {
        await expect(receiverLog.getByText(message.content, { exact: true })).toHaveCount(1)
      }
    } finally {
      if (chatId && senderLog) {
        for (const message of createdMessages) {
          try {
            await deleteOwnedLiveMessage(page, senderLog, chatId, message)
          } catch {
            // Cleanup uses the authenticated sender UI and only deletes its own messages.
          }
        }
      }
      await receiverContext.close()
    }
  })

  test("a receiver reaction is delivered to the sender over the live WebSocket", async ({
    browser,
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === "mobile"
    const receiverContext = await browser.newContext({
      ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
      baseURL: LIVE_BASE_URL,
      locale: "ru-RU",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    })
    let chatId: string | null = null
    let createdMessage: CreatedLiveMessage | null = null
    let senderLog: Locator | null = null

    try {
      const receiverPage = await receiverContext.newPage()
      const messageContent = `live-reaction-${crypto.randomUUID()}`

      await loginAs(page, "student")
      await loginAs(receiverPage, "teacher")
      const senderResponse = await page.request.get("/api/v1/users/me")
      const receiverResponse = await receiverPage.request.get("/api/v1/users/me")
      expect(senderResponse.ok()).toBe(true)
      expect(receiverResponse.ok()).toBe(true)
      const sender = (await senderResponse.json()) as { id: string; role: string }
      const receiver = (await receiverResponse.json()) as {
        id: string
        full_name: string | null
        role: string
      }
      expect(sender.role).toBe("student")
      expect(receiver.role).toBe("teacher")
      expect(receiver.full_name).toBeTruthy()
      expect(receiver.id).not.toBe(sender.id)

      const senderRoomJoinFrames: unknown[] = []
      const senderReactions: ReactionMutationFrame[] = []
      page.on("websocket", (socket) => {
        socket.on("framesent", (payload) => senderRoomJoinFrames.push(parseFrame(payload)))
        socket.on("framereceived", (payload) => {
          senderReactions.push(...findReactionMutationFrames(parseFrame(payload)))
        })
      })

      await page.goto("/messenger")
      await page.getByRole("button", { name: "Новый чат", exact: true }).click()
      await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(receiver.full_name!)
      const receiverOption = page.getByRole("option").filter({ hasText: receiver.full_name! })
      await expect(receiverOption).toHaveCount(1)
      await receiverOption.click()
      await expect(page).toHaveURL(/\/messenger\/[^/]+\/?$/)
      const activeChatId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1)
      expect(activeChatId).toBeTruthy()
      if (!activeChatId) throw new Error("New direct chat route did not contain a chat id")
      chatId = activeChatId

      senderLog = page.getByRole("log", { name: /Сообщения чата/i })
      await expect(senderLog).toBeVisible()

      const receiverRoomJoinFrames: unknown[] = []
      receiverPage.on("websocket", (socket) => {
        socket.on("framesent", (payload) => receiverRoomJoinFrames.push(parseFrame(payload)))
      })
      await receiverPage.goto(`/messenger/${activeChatId}`)
      const receiverLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
      await expect(receiverLog).toBeVisible()
      await expect
        .poll(() => senderRoomJoinFrames.some((frame) => hasRoomJoin(frame, activeChatId)))
        .toBe(true)
      await expect
        .poll(() => receiverRoomJoinFrames.some((frame) => hasRoomJoin(frame, activeChatId)))
        .toBe(true)

      createdMessage = await sendLiveMessage(
        page,
        activeChatId,
        messageContent,
        testInfo.project.name
      )
      await expect(senderLog.getByText(messageContent, { exact: true })).toBeVisible()
      const receiverMessage = receiverLog.getByText(messageContent, { exact: true })
      await expect(receiverMessage).toBeVisible()

      const receiverMessageRow = receiverMessage.locator(
        "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
      )
      await receiverMessageRow
        .getByRole("button", { name: "Добавить реакцию", exact: true })
        .click()
      const reactionPicker = receiverPage.getByRole("group", {
        name: "Добавить реакцию",
        exact: true,
      })
      await expect(reactionPicker).toBeVisible()

      const reactionResponsePromise = receiverPage.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname ===
            `/api/v1/chats/${activeChatId}/messages/${createdMessage?.id}/reactions`
        )
      })
      await reactionPicker.getByRole("button", { name: "Отреагировать 👍", exact: true }).click()
      const reactionResponse = await reactionResponsePromise
      expect(reactionResponse.ok()).toBe(true)

      await expect
        .poll(() =>
          senderReactions.filter(
            (frame) =>
              frame.chatId === activeChatId &&
              frame.messageId === createdMessage?.id &&
              frame.userId === receiver.id &&
              frame.emoji === "👍" &&
              frame.action === "added"
          )
        )
        .toHaveLength(1)

      const reactionMessageId = createdMessage.id
      const senderHistoryResponse = await page.request.get(
        `/api/v1/chats/${activeChatId}/messages?limit=50`
      )
      expect(senderHistoryResponse.ok()).toBe(true)
      const senderHistory = (await senderHistoryResponse.json()) as {
        items: Array<{
          id: string
          reactions: Array<{ emoji: string; count: number; reacted_by_me: boolean }>
        }>
      }
      const senderMessageHistory = senderHistory.items.find(
        (message) => message.id === reactionMessageId
      )
      expect(senderMessageHistory?.reactions).toEqual([
        { emoji: "👍", count: 1, reacted_by_me: false },
      ])

      const receiverHistoryResponse = await receiverPage.request.get(
        `/api/v1/chats/${activeChatId}/messages?limit=50`
      )
      expect(receiverHistoryResponse.ok()).toBe(true)
      const receiverHistory = (await receiverHistoryResponse.json()) as {
        items: Array<{
          id: string
          reactions: Array<{ emoji: string; count: number; reacted_by_me: boolean }>
        }>
      }
      const receiverMessageHistory = receiverHistory.items.find(
        (message) => message.id === reactionMessageId
      )
      expect(receiverMessageHistory?.reactions).toEqual([
        { emoji: "👍", count: 1, reacted_by_me: true },
      ])

      const senderMessage = senderLog.getByText(messageContent, { exact: true })
      const senderMessageRow = senderMessage.locator(
        "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
      )
      await expect(
        senderMessageRow.getByRole("button", {
          name: /Переключить реакцию 👍, 1/,
          exact: true,
        })
      ).toBeVisible()

      const receiverReactionButton = receiverMessageRow.getByRole("button", {
        name: /Переключить реакцию 👍, 1/,
        exact: true,
      })
      await expect(receiverReactionButton).toBeVisible()
      const removeReactionResponsePromise = receiverPage.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname ===
            `/api/v1/chats/${activeChatId}/messages/${createdMessage?.id}/reactions`
        )
      })
      await receiverReactionButton.click()
      const removeReactionResponse = await removeReactionResponsePromise
      expect(removeReactionResponse.ok()).toBe(true)

      await expect
        .poll(() =>
          senderReactions.filter(
            (frame) =>
              frame.chatId === activeChatId &&
              frame.messageId === createdMessage?.id &&
              frame.userId === receiver.id &&
              frame.emoji === "👍" &&
              frame.action === "removed"
          )
        )
        .toHaveLength(1)

      const senderAfterRemoval = await page.request.get(
        `/api/v1/chats/${activeChatId}/messages?limit=50`
      )
      expect(senderAfterRemoval.ok()).toBe(true)
      const senderAfterRemovalHistory = (await senderAfterRemoval.json()) as {
        items: Array<{
          id: string
          reactions: Array<{ emoji: string; count: number; reacted_by_me: boolean }>
        }>
      }
      expect(
        senderAfterRemovalHistory.items.find((message) => message.id === reactionMessageId)
          ?.reactions
      ).toEqual([])

      const receiverAfterRemoval = await receiverPage.request.get(
        `/api/v1/chats/${activeChatId}/messages?limit=50`
      )
      expect(receiverAfterRemoval.ok()).toBe(true)
      const receiverAfterRemovalHistory = (await receiverAfterRemoval.json()) as {
        items: Array<{
          id: string
          reactions: Array<{ emoji: string; count: number; reacted_by_me: boolean }>
        }>
      }
      expect(
        receiverAfterRemovalHistory.items.find((message) => message.id === reactionMessageId)
          ?.reactions
      ).toEqual([])
    } finally {
      try {
        if (chatId && createdMessage && senderLog) {
          await deleteOwnedLiveMessage(page, senderLog, chatId, createdMessage)
        }
      } finally {
        await receiverContext.close()
      }
    }
  })

  test("a sender reply preserves its parent identity and reaches the receiver", async ({
    browser,
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === "mobile"
    const receiverContext = await browser.newContext({
      ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
      baseURL: LIVE_BASE_URL,
      locale: "ru-RU",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    })
    let chatId: string | null = null
    let parentMessage: CreatedLiveMessage | null = null
    let replyMessage: CreatedLiveMessage | null = null
    let senderLog: Locator | null = null

    try {
      const receiverPage = await receiverContext.newPage()
      const parentContent = `live-reply-parent-${crypto.randomUUID()}`
      const replyContent = `live-reply-child-${crypto.randomUUID()}`

      await loginAs(page, "student")
      await loginAs(receiverPage, "teacher")
      const senderResponse = await page.request.get("/api/v1/users/me")
      const receiverResponse = await receiverPage.request.get("/api/v1/users/me")
      expect(senderResponse.ok()).toBe(true)
      expect(receiverResponse.ok()).toBe(true)
      const sender = (await senderResponse.json()) as { id: string; role: string }
      const receiver = (await receiverResponse.json()) as {
        id: string
        full_name: string | null
        role: string
      }
      expect(sender.role).toBe("student")
      expect(receiver.role).toBe("teacher")
      expect(receiver.full_name).toBeTruthy()
      expect(receiver.id).not.toBe(sender.id)

      const senderRoomJoinFrames: unknown[] = []
      page.on("websocket", (socket) => {
        socket.on("framesent", (payload) => senderRoomJoinFrames.push(parseFrame(payload)))
      })

      await page.goto("/messenger")
      await page.getByRole("button", { name: "Новый чат", exact: true }).click()
      await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(receiver.full_name!)
      const receiverOption = page.getByRole("option").filter({ hasText: receiver.full_name! })
      await expect(receiverOption).toHaveCount(1)
      await receiverOption.click()
      await expect(page).toHaveURL(/\/messenger\/[^/]+\/?$/)
      const activeChatId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1)
      expect(activeChatId).toBeTruthy()
      if (!activeChatId) throw new Error("New direct chat route did not contain a chat id")
      chatId = activeChatId

      senderLog = page.getByRole("log", { name: /Сообщения чата/i })
      await expect(senderLog).toBeVisible()
      const receiverRoomJoinFrames: unknown[] = []
      const receiverMessages: ReceivedMessageFrame[] = []
      receiverPage.on("websocket", (socket) => {
        socket.on("framesent", (payload) => receiverRoomJoinFrames.push(parseFrame(payload)))
        socket.on("framereceived", (payload) => {
          receiverMessages.push(...findNewMessageFrames(parseFrame(payload)))
        })
      })
      await receiverPage.goto(`/messenger/${activeChatId}`)
      const receiverLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
      await expect(receiverLog).toBeVisible()
      await expect
        .poll(() => senderRoomJoinFrames.some((frame) => hasRoomJoin(frame, activeChatId)))
        .toBe(true)
      await expect
        .poll(() => receiverRoomJoinFrames.some((frame) => hasRoomJoin(frame, activeChatId)))
        .toBe(true)

      const createdParent = await sendLiveMessage(
        page,
        activeChatId,
        parentContent,
        testInfo.project.name
      )
      parentMessage = createdParent
      await expect(senderLog.getByText(parentContent, { exact: true })).toBeVisible()
      const receiverParent = receiverLog.getByText(parentContent, { exact: true })
      await expect(receiverParent).toBeVisible()
      const senderParent = senderLog.getByText(parentContent, { exact: true })
      const senderParentRow = senderParent.locator(
        "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
      )
      await senderParentRow.getByRole("button", { name: "Ответить", exact: true }).click()
      await expect(page.getByText(/^Ответ:/)).toBeVisible()

      const replyResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname === `/api/v1/chats/${activeChatId}/messages`
        )
      })
      await page.locator("#chat-message-input").fill(replyContent)
      await page.locator("#chat-send-btn").click()
      const replyResponse = await replyResponsePromise
      if (!replyResponse.ok()) {
        reportLiveHttpStatus(
          testInfo.project.name,
          "messenger-message-send",
          replyResponse.status()
        )
      }
      expect(replyResponse.ok()).toBe(true)
      const createdReply = (await replyResponse.json()) as {
        id: string
        chat_id: string
        sender_id: string
        content: string
        reply_to: {
          id: string
          sender_id: string
          content: string
        } | null
      }
      replyMessage = { id: createdReply.id, content: replyContent }
      expect(createdReply).toMatchObject({
        chat_id: activeChatId,
        sender_id: sender.id,
        content: replyContent,
        reply_to: {
          id: createdParent.id,
          sender_id: sender.id,
          content: parentContent,
        },
      })

      await expect
        .poll(() =>
          receiverMessages.filter(
            (frame) =>
              frame.chatId === activeChatId &&
              frame.message.id === createdReply.id &&
              frame.message.replyToId === createdParent.id
          )
        )
        .toHaveLength(1)
      const receiverReply = receiverLog.getByText(replyContent, { exact: true })
      await expect(receiverReply).toBeVisible()
      const receiverReplyRow = receiverReply.locator(
        "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
      )
      await expect(receiverReplyRow.getByText(parentContent, { exact: true })).toBeVisible()
    } finally {
      try {
        if (senderLog && chatId && replyMessage) {
          await deleteOwnedLiveMessage(page, senderLog, chatId, replyMessage)
        }
      } finally {
        try {
          if (senderLog && chatId && parentMessage) {
            await deleteOwnedLiveMessage(page, senderLog, chatId, parentMessage)
          }
        } finally {
          await receiverContext.close()
        }
      }
    }
  })

  test("forwarding through the current-chat modal preserves attribution and reaches the receiver", async ({
    browser,
    page,
  }, testInfo) => {
    const mobile = testInfo.project.name === "mobile"
    const receiverContext = await browser.newContext({
      ...(mobile ? devices["Pixel 7"] : devices["Desktop Chrome"]),
      baseURL: LIVE_BASE_URL,
      locale: "ru-RU",
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    })
    let chatId: string | null = null
    let sourceMessage: CreatedLiveMessage | null = null
    let forwardedMessage: (CreatedLiveMessage & { forwardedFromName: string }) | null = null
    let senderLog: Locator | null = null

    try {
      const receiverPage = await receiverContext.newPage()
      const sourceContent = `live-forward-${crypto.randomUUID()}`

      await loginAs(page, "student")
      await loginAs(receiverPage, "teacher")
      const senderResponse = await page.request.get("/api/v1/users/me")
      const receiverResponse = await receiverPage.request.get("/api/v1/users/me")
      expect(senderResponse.ok()).toBe(true)
      expect(receiverResponse.ok()).toBe(true)
      const sender = (await senderResponse.json()) as {
        id: string
        full_name: string | null
        role: string
      }
      const receiver = (await receiverResponse.json()) as {
        id: string
        full_name: string | null
        role: string
      }
      expect(sender.role).toBe("student")
      expect(receiver.role).toBe("teacher")
      expect(sender.full_name).toBeTruthy()
      expect(receiver.full_name).toBeTruthy()
      expect(receiver.id).not.toBe(sender.id)
      const senderName = sender.full_name
      if (!senderName) throw new Error("Forward source sender does not have a display name")

      const senderRoomJoinFrames: unknown[] = []
      page.on("websocket", (socket) => {
        socket.on("framesent", (payload) => senderRoomJoinFrames.push(parseFrame(payload)))
      })
      await page.goto("/messenger")
      await page.getByRole("button", { name: "Новый чат", exact: true }).click()
      await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(receiver.full_name!)
      const receiverOption = page.getByRole("option").filter({ hasText: receiver.full_name! })
      await expect(receiverOption).toHaveCount(1)
      await receiverOption.click()
      await expect(page).toHaveURL(/\/messenger\/[^/]+\/?$/)
      const activeChatId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1)
      expect(activeChatId).toBeTruthy()
      if (!activeChatId) throw new Error("New direct chat route did not contain a chat id")
      chatId = activeChatId

      senderLog = page.getByRole("log", { name: /Сообщения чата/i })
      await expect(senderLog).toBeVisible()
      const receiverRoomJoinFrames: unknown[] = []
      const receiverMessages: ReceivedMessageFrame[] = []
      receiverPage.on("websocket", (socket) => {
        socket.on("framesent", (payload) => receiverRoomJoinFrames.push(parseFrame(payload)))
        socket.on("framereceived", (payload) => {
          receiverMessages.push(...findNewMessageFrames(parseFrame(payload)))
        })
      })
      await receiverPage.goto(`/messenger/${activeChatId}`)
      const receiverLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
      await expect(receiverLog).toBeVisible()
      await expect
        .poll(() => senderRoomJoinFrames.some((frame) => hasRoomJoin(frame, activeChatId)))
        .toBe(true)
      await expect
        .poll(() => receiverRoomJoinFrames.some((frame) => hasRoomJoin(frame, activeChatId)))
        .toBe(true)

      const createdSource = await sendLiveMessage(
        page,
        activeChatId,
        sourceContent,
        testInfo.project.name
      )
      sourceMessage = createdSource
      await expect(senderLog.getByText(sourceContent, { exact: true })).toBeVisible()
      await expect(receiverLog.getByText(sourceContent, { exact: true })).toBeVisible()
      const sourceRow = senderLog
        .getByText(sourceContent, { exact: true })
        .locator(
          "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
        )
      await sourceRow.getByRole("button", { name: "Переслать", exact: true }).click()

      const forwardDialog = page.getByRole("dialog")
      await expect(forwardDialog).toBeVisible()
      const currentChatOption = forwardDialog.getByRole("option").filter({ hasText: "Текущий" })
      await expect(currentChatOption).toHaveCount(1)
      const forwardResponsePromise = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname === `/api/v1/chats/${activeChatId}/forward`
        )
      })
      await currentChatOption.click()
      const forwardResponse = await forwardResponsePromise
      expect(forwardResponse.ok()).toBe(true)
      expect(forwardResponse.request().postDataJSON()).toEqual({
        source_chat_id: activeChatId,
        message_ids: [createdSource.id],
      })

      const forwardResults = (await forwardResponse.json()) as Array<{
        id: string
        chat_id: string
        sender_id: string
        content: string
        forwarded_from_name: string | null
      }>
      expect(forwardResults).toHaveLength(1)
      const createdForward = forwardResults[0]
      if (!createdForward) throw new Error("Forward API returned no created message")
      forwardedMessage = {
        id: createdForward.id,
        content: createdForward.content,
        forwardedFromName: senderName,
      }
      expect(createdForward).toMatchObject({
        chat_id: activeChatId,
        sender_id: sender.id,
        content: sourceContent,
        forwarded_from_name: senderName,
      })

      const historyResponse = await page.request.get(
        `/api/v1/chats/${activeChatId}/messages?limit=50`
      )
      expect(historyResponse.ok()).toBe(true)
      const history = (await historyResponse.json()) as {
        items: Array<{
          id: string
          sender_id: string
          content: string
          forwarded_from_name: string | null
        }>
      }
      expect(history.items.find((message) => message.id === createdForward.id)).toMatchObject({
        sender_id: sender.id,
        content: sourceContent,
        forwarded_from_name: senderName,
      })
      expect(history.items.find((message) => message.id === createdSource.id)).toMatchObject({
        sender_id: sender.id,
        content: sourceContent,
        forwarded_from_name: null,
      })

      await expect
        .poll(() =>
          receiverMessages.filter(
            (frame) =>
              frame.chatId === activeChatId &&
              frame.message.id === createdForward.id &&
              frame.message.content === sourceContent &&
              frame.message.forwardedFromName === senderName
          )
        )
        .toHaveLength(1)
      const receiverForwardAttribution = receiverLog.getByText(`Переслано от ${senderName}`, {
        exact: true,
      })
      await expect(receiverForwardAttribution).toBeVisible()
      const receiverForwardRow = receiverForwardAttribution
        .locator(
          "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
        )
        .filter({ hasText: sourceContent })
      await expect(receiverForwardRow).toHaveCount(1)
      await expect(receiverForwardRow.getByText(sourceContent, { exact: true })).toBeVisible()
    } finally {
      try {
        if (senderLog && chatId && forwardedMessage) {
          await deleteOwnedForwardedLiveMessage(page, senderLog, chatId, forwardedMessage)
        }
      } finally {
        try {
          if (senderLog && chatId && sourceMessage) {
            await deleteOwnedLiveMessage(page, senderLog, chatId, sourceMessage)
          }
        } finally {
          await receiverContext.close()
        }
      }
    }
  })
})
