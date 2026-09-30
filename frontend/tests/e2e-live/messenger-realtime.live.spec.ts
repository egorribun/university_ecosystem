import { devices } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"

const LIVE_BASE_URL = process.env.LIVE_BASE_URL ?? "http://localhost"

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
  message: {
    id: unknown
    chatId: unknown
    senderId: unknown
    content: unknown
  }
}

function findNewMessageFrames(value: unknown): ReceivedMessageFrame[] {
  if (Array.isArray(value)) return value.flatMap(findNewMessageFrames)
  if (!isRecord(value)) return []

  const frames: ReceivedMessageFrame[] = []
  if (value.type === "new_message" && isRecord(value.message)) {
    frames.push({
      chatId: value.chat_id,
      message: {
        id: value.message.id,
        chatId: value.message.chat_id,
        senderId: value.message.sender_id,
        content: value.message.content,
      },
    })
  }
  return [...frames, ...Object.values(value).flatMap(findNewMessageFrames)]
}

// Playwright traces can retain login request bodies. The seeded role fixtures
// are authenticated through the real UI, so this focused lane keeps them off.
test.use({ trace: "off", screenshot: "off" })

test.describe("live messenger delivery", () => {
  test("a message appears in the other authenticated session", async ({
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
      receiverPage.on("websocket", (socket) => {
        receiverSocketCount += 1
        socket.on("framesent", (payload) => {
          if (hasRoomJoin(parseFrame(payload), chatId)) receiverRoomJoinCount += 1
        })
        socket.on("framereceived", (payload) => {
          receiverMessages.push(...findNewMessageFrames(parseFrame(payload)))
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

      const expectedFrame: ReceivedMessageFrame = {
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
      expect(receiverMessages).toContainEqual(expectedFrame)
      const renderedMessage = messageLog.getByText(message, { exact: true })
      await expect(renderedMessage).toHaveCount(1)
      await expect(renderedMessage).toBeVisible()
    } finally {
      await receiverContext.close()
    }
  })
})
