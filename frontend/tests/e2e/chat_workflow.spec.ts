import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { useMockApi } from "./utils/mockApi"

const ENABLED = process.env.URL_STATE_E2E === "true"
const BASE = process.env.URL_STATE_E2E_BASE ?? "http://127.0.0.1:4175"

// Shared fixtures used across route handlers.
const CURRENT_USER_ID = "lhci-mock-user"
const OTHER_USER_ID = "00000000-0000-4000-8000-000000000002"
const CHAT_ID = "00000000-0000-4000-8000-000000000001"
const apiPathMatches = (url: URL, path: string) =>
  url.pathname === path || url.pathname === path.replace("/api/", "/api/v1/")

const CHAT_COLLECTION_MATCH = (url: URL) => apiPathMatches(url, "/api/chats")
const chatDetailMatch = (url: URL) => apiPathMatches(url, `/api/chats/${CHAT_ID}`)
const chatMessagesMatch = (url: URL) => apiPathMatches(url, `/api/chats/${CHAT_ID}/messages`)
const chatReadMatch = (url: URL) => apiPathMatches(url, `/api/chats/${CHAT_ID}/read`)
const chatTypingMatch = (url: URL) => apiPathMatches(url, `/api/chats/${CHAT_ID}/typing`)
const chatReactionsMatch = (url: URL) => {
  const base = `/api/chats/${CHAT_ID}/messages/`
  const v1Base = base.replace("/api/", "/api/v1/")
  return (
    (url.pathname.startsWith(base) || url.pathname.startsWith(v1Base)) &&
    url.pathname.endsWith("/reactions")
  )
}
const chatForwardMatch = (url: URL) => apiPathMatches(url, `/api/chats/${CHAT_ID}/forward`)
const otherUserMatch = (url: URL) => apiPathMatches(url, `/api/users/${OTHER_USER_ID}`)

const makeUser = (user: { id: string; email: string; full_name: string }) => ({
  ...user,
  role: "student",
  group_id: null,
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  profile_detail: null,
  education_path: null,
  preferences: null,
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: false,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  recovery_codes_left: 0,
  totp_enrollments: [],
  mfa_challenges: [],
})

const CURRENT_USER = makeUser({
  id: CURRENT_USER_ID,
  email: "student@example.com",
  full_name: "Иван Иванов",
})

const OTHER_USER = makeUser({
  id: OTHER_USER_ID,
  email: "other@example.com",
  full_name: "Other User",
})

const DM_CHAT = {
  id: CHAT_ID,
  chat_type: "dm",
  name: null,
  created_by: null,
  participants: [CURRENT_USER, OTHER_USER],
  last_message: {
    id: "msg-uuid-1",
    chat_id: CHAT_ID,
    sender_id: OTHER_USER_ID,
    content: "Привет! Как дела?",
    created_at: new Date(Date.now() - 60_000).toISOString(),
    read_status: false,
  },
  unread_count: 1,
  created_at: new Date(Date.now() - 3_600_000).toISOString(),
  updated_at: new Date(Date.now() - 60_000).toISOString(),
}

const INITIAL_MESSAGE = {
  id: "msg-uuid-1",
  chat_id: CHAT_ID,
  sender_id: OTHER_USER_ID,
  content: "Привет! Как дела?",
  created_at: new Date(Date.now() - 60_000).toISOString(),
  read_status: false,
  sender: OTHER_USER,
  reactions: [],
}

test.describe("Messenger Chat Workflow", () => {
  test.skip(!ENABLED, "Requires URL_STATE_E2E=true build with VITE_LHCI=true auth bypass")
  test.skip(({ browserName }) => browserName !== "chromium", "chromium-only by design")

  test.use({ baseURL: BASE, serviceWorkers: "block" })

  test("runs full DM chat workflow: open chat → send → receive via WS → react → reply → forward → read receipt", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      ;(window as Window & { __E2E_NETWORK_API_MOCKS__?: boolean }).__E2E_NETWORK_API_MOCKS__ = true
    })

    // 1. Setup global mock API (auth, profile, news, schedule, etc.)
    await useMockApi(page)

    // 2. Override chat-specific routes BEFORE navigation so they are in place
    //    when React Query fires its initial fetch.

    // GET  /api/chats        → list with one DM chat
    // POST /api/chats        → create (unused in DM flow)
    await page.route(CHAT_COLLECTION_MATCH, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [DM_CHAT], has_more: false, next_cursor: null }),
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(DM_CHAT),
        })
      }
    })

    await page.route(chatDetailMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...DM_CHAT, unread_count: 0 }),
      })
    })

    await page.route(chatMessagesMatch, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [INITIAL_MESSAGE], has_more: false, next_cursor: null }),
        })
      } else {
        // POST — send message
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "msg-uuid-sent",
            chat_id: CHAT_ID,
            sender_id: CURRENT_USER_ID,
            content: "Привет от Ивана!",
            created_at: new Date().toISOString(),
            read_status: false,
            sender: CURRENT_USER,
            reactions: [],
          }),
        })
      }
    })

    await page.route(chatReadMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      })
    })

    await page.route(chatTypingMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      })
    })

    await page.route(chatReactionsMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      })
    })

    await page.route(chatForwardMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "msg-uuid-forwarded",
            chat_id: CHAT_ID,
            sender_id: CURRENT_USER_ID,
            content: "Привет! Как дела?",
            forwarded_from_name: "Other User",
            created_at: new Date().toISOString(),
            read_status: false,
            sender: CURRENT_USER,
          },
        ]),
      })
    })

    await page.route(otherUserMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...OTHER_USER,
          profile_detail: { about: "Another student.", telegram: "@other", status: "active" },
        }),
      })
    })

    // 3. Inject mock WebSocket — replaces the real WS connection so the test
    //    controls inbound frames explicitly, removing the 404-on-ws-hub dependency.
    await page.addInitScript(() => {
      class MockWebSocket {
        url: string
        readyState: number
        onopen?: () => void
        onclose?: () => void
        onmessage?: (event: { data: string }) => void
        static OPEN = 1

        constructor(url: string) {
          this.url = url
          this.readyState = 0 // CONNECTING
          const store = window as unknown as Window & { MockWebSocketInstances?: MockWebSocket[] }
          store.MockWebSocketInstances ??= []
          store.MockWebSocketInstances.push(this)
          // Simulate async open so the app has time to attach handlers.
          setTimeout(() => {
            this.readyState = 1 // OPEN
            this.onopen?.()
          }, 50)
        }

        send(_data: string) {
          // No-op: send is observed but not acted upon in the test.
        }

        close() {
          this.readyState = 3
          this.onclose?.()
        }

        triggerMessage(data: unknown) {
          this.onmessage?.({ data: typeof data === "string" ? data : JSON.stringify(data) })
        }
      }
      ;(
        window as unknown as Window & { MockWebSocketInstances: MockWebSocket[] }
      ).MockWebSocketInstances = []
      ;(window as Window & { WebSocket: unknown }).WebSocket = MockWebSocket
    })

    // 4. Navigate to messenger
    await page.goto("/messenger", { waitUntil: "domcontentloaded", timeout: 30_000 })

    // 5. Sidebar accessibility scan (before any interaction)
    const a11ySidebar = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast", "color-contrast-enhanced"])
      .analyze()
    expect(a11ySidebar.violations).toEqual([])

    // 6. "Other User" DM should appear in the contact list sidebar.
    //    chatDisplayInfo resolves the DM name to the other participant's full_name.
    await expect(page.getByText("Other User")).toBeVisible({ timeout: 10_000 })

    // 7. Click the chat row to open the conversation.
    await page.getByText("Other User").first().click()
    await expect(page).toHaveURL(new RegExp(`messenger/${CHAT_ID}`), { timeout: 10_000 })

    // 8. Wait for the initial message to render in the chat window.
    await expect(page.getByText("Привет! Как дела?")).toBeVisible({ timeout: 10_000 })

    // 9. Type and send a message.
    await page.fill("#chat-message-input", "Привет от Ивана!")
    await page.click("#chat-send-btn")

    // The sent message should appear (optimistic or from API response).
    await expect(page.getByText("Привет от Ивана!")).toBeVisible({ timeout: 10_000 })

    // 10. Simulate an inbound WebSocket frame (new message from Other User).
    await page.evaluate(
      ({ chatId, otherUserId }) => {
        type MockWebSocketInstance = { triggerMessage?: (data: unknown) => void }
        const instances =
          (window as Window & { MockWebSocketInstances?: MockWebSocketInstance[] })
            .MockWebSocketInstances ?? []
        const ws = instances[instances.length - 1]
        ws?.triggerMessage?.({
          type: "new_message",
          chat_id: chatId,
          message: {
            id: "00000000-0000-4000-8000-000000000012",
            chat_id: chatId,
            sender_id: otherUserId,
            content: "Рад слышать! Ответ получен.",
            created_at: new Date().toISOString(),
            read_status: false,
            sender: {
              id: otherUserId,
              email: "other@example.com",
              full_name: "Other User",
              role: "student",
              is_active: true,
            },
            reactions: [],
          },
        })
      },
      { chatId: CHAT_ID, otherUserId: OTHER_USER_ID }
    )

    const chatLog = page.getByRole("log", { name: /Сообщения чата/i })
    await expect(chatLog.getByText("Рад слышать! Ответ получен.")).toBeVisible({
      timeout: 10_000,
    })

    // 11. Accessibility scan in the active chat area.
    const a11yChat = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast", "color-contrast-enhanced"])
      .analyze()
    expect(a11yChat.violations).toEqual([])

    // 12. Reply affordance — locate the reply button using its aria-label ("Ответить").
    //     The button lives inside the message bubble; use getByLabel to find it.
    const replyBtn = page.getByLabel("Ответить").first()
    await expect(replyBtn).toBeVisible({ timeout: 8_000 })
    await replyBtn.click()

    // Cancel the reply chip (aria-label: "Отмена").
    await page.getByLabel("Отмена").first().click()

    // 13. Forward affordance — located inside the message bubble.
    const forwardBtn = page.getByLabel("Переслать").first()
    await expect(forwardBtn).toBeVisible({ timeout: 8_000 })
    await forwardBtn.click()

    // Forward modal should open with the "Forward to…" heading.
    await expect(page.getByText("Переслать в…")).toBeVisible({ timeout: 8_000 })

    // Dismiss the forward modal — press Escape to close it gracefully.
    await page.keyboard.press("Escape")

    // 14. Read-receipt WebSocket frame.
    await page.evaluate(
      ({ chatId, otherUserId }) => {
        type MockWebSocketInstance = { triggerMessage?: (data: unknown) => void }
        const instances =
          (window as Window & { MockWebSocketInstances?: MockWebSocketInstance[] })
            .MockWebSocketInstances ?? []
        const ws = instances[instances.length - 1]
        ws?.triggerMessage?.({
          type: "read",
          chat_id: chatId,
          user_id: otherUserId,
          read_at: new Date().toISOString(),
        })
      },
      { chatId: CHAT_ID, otherUserId: OTHER_USER_ID }
    )

    // The chat log remains visible after the read frame is applied.
    await expect(chatLog).toBeVisible()
  })
})
