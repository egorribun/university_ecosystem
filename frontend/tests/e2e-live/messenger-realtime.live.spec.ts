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

function hasNewMessage(value: unknown, content: string): boolean {
  if (Array.isArray(value)) return value.some((item) => hasNewMessage(item, content))
  if (!isRecord(value)) return false
  const message = value.message
  if (value.type === "new_message" && isRecord(message) && message.content === content) {
    return true
  }
  return Object.values(value).some((item) => hasNewMessage(item, content))
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

      const chatsResponse = await page.request.get("/api/v1/chats?limit=20")
      const chatsPayload = (await chatsResponse.json()) as {
        items?: Array<{
          id: string
          chat_type?: string
          participants?: Array<{ id?: string; full_name?: string | null }>
        }>
      }
      expect(chatsResponse.ok()).toBe(true)
      const existingDirectChat = (chatsPayload.items ?? []).find(
        (chat) =>
          chat.chat_type !== "group" &&
          chat.participants?.some((participant) => participant.id === student.id) &&
          chat.participants?.some((participant) => participant.id === teacher.id)
      )

      await page.goto("/messenger")
      await page.getByRole("button", { name: "Новый чат", exact: true }).click()
      await page.getByRole("textbox", { name: "Поиск пользователей" }).fill(teacher.full_name!)
      const searchOptions = page.getByRole("option")
      const noUsersFound = page.getByRole("status").filter({ hasText: "Пользователи не найдены" })
      await expect(searchOptions.first().or(noUsersFound)).toBeVisible()

      if ((await searchOptions.count()) === 1) {
        const teacherOption = searchOptions.filter({ hasText: teacher.full_name! })
        await expect(teacherOption).toHaveCount(1)
        await teacherOption.click()
      } else {
        // The backend omits users who already share a DM with the current
        // account. Resolve its ID through a read-only API call, then select
        // the rendered conversation row through the UI.
        await expect(searchOptions).toHaveCount(0)
        expect(existingDirectChat).toBeTruthy()
        if (!existingDirectChat)
          throw new Error("Expected the existing direct chat in the read-only list")
        const dialog = page.getByRole("dialog")
        await dialog.getByRole("button").first().click()
        const existingConversation = page.locator(`#messenger-contact-${existingDirectChat.id}`)
        await expect(existingConversation).toBeVisible()
        const peerInChat = existingDirectChat.participants?.find(
          (participant) => participant.id === teacher.id
        )
        if (peerInChat?.full_name) {
          await expect(existingConversation).toContainText(teacher.full_name!)
        }
        await existingConversation.click()
      }
      await expect(page).toHaveURL(/\/messenger\/[^/]+\/?$/)

      const chatId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1)
      expect(chatId).toBeTruthy()
      if (!chatId) throw new Error("New direct chat route did not contain a chat id")

      let receiverSocketCount = 0
      let receiverRoomJoinCount = 0
      let deliveredViaWebSocket = false
      receiverPage.on("websocket", (socket) => {
        receiverSocketCount += 1
        socket.on("framesent", (payload) => {
          if (hasRoomJoin(parseFrame(payload), chatId)) receiverRoomJoinCount += 1
        })
        socket.on("framereceived", (payload) => {
          if (hasNewMessage(parseFrame(payload), message)) deliveredViaWebSocket = true
        })
      })

      const senderLog = page.getByRole("log", { name: /Сообщения чата/i })
      await expect(senderLog).toBeVisible()
      await receiverPage.goto(`/messenger/${chatId}`)
      const messageLog = receiverPage.getByRole("log", { name: /Сообщения чата/i })
      await expect(messageLog).toBeVisible()
      await expect.poll(() => receiverSocketCount).toBeGreaterThan(0)
      await expect.poll(() => receiverRoomJoinCount).toBeGreaterThan(0)

      const messageResponse = page.waitForResponse((response) => {
        const request = response.request()
        return (
          request.method() === "POST" &&
          new URL(response.url()).pathname === `/api/v1/chats/${chatId}/messages`
        )
      })
      await page.locator("#chat-message-input").fill(message)
      await page.locator("#chat-send-btn").click()
      expect((await messageResponse).ok()).toBe(true)

      await expect.poll(() => deliveredViaWebSocket).toBe(true)
      await expect(messageLog.getByText(message, { exact: true })).toBeVisible()
    } finally {
      await receiverContext.close()
    }
  })
})
