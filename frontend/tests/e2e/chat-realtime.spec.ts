import { expect, test, type Page } from "./test"
import { gotoWithTransientRetry } from "./utils/navigation"

/**
 * Chat real-time behaviour specs — W24.
 *
 * All tests require a running backend with WebSocket support and are
 * therefore skipped in CI environments that only spin up the static
 * frontend preview. The `test.skip` guard at the describe level
 * short-circuits the whole suite unless `REALTIME_E2E=true` is set.
 *
 * Patterns:
 *   - WebSocket reconnect: verifies the client re-subscribes after the
 *     connection is closed and delivers subsequent messages.
 *   - Typing indicator: verifies the indicator UI appears when a typing
 *     event arrives over the WebSocket channel.
 *   - Message sent confirmation: verifies the server accepted the exact
 *     message and the matching bubble shows its accessible sent/read status.
 */

const REALTIME_ENABLED = process.env.REALTIME_E2E === "true"

/** Chat sockets are the only connections opened with the `?ticket=` query (useChatWebSocket). */
const CHAT_SOCKET_MARKER = "ticket="
/** WebSocket.OPEN, written out because the constant is read inside the page context. */
const SOCKET_OPEN = 1

type RecordingWindow = Window & { __e2eSockets?: WebSocket[] }

/**
 * Test-owned recorder: keeps a handle on every WebSocket the page opens, so the
 * lifecycle is driven through the browser's own socket objects, not app internals.
 */
async function recordWebSockets(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const NativeWebSocket = window.WebSocket
    const sockets: WebSocket[] = []
    Object.defineProperty(window, "__e2eSockets", { value: sockets })
    window.WebSocket = class RecordingWebSocket extends NativeWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols)
        sockets.push(this)
      }
    }
  })
}

/** Ready states of the chat sockets in open order; the length is the number of chat connections. */
const chatSocketStates = (page: Page) =>
  page.evaluate(
    (marker) =>
      ((window as RecordingWindow).__e2eSockets ?? [])
        .filter((socket) => socket.url.includes(marker))
        .map((socket) => socket.readyState),
    CHAT_SOCKET_MARKER
  )

test.describe("Chat real-time behaviour", () => {
  test.skip(!REALTIME_ENABLED, "needs running backend with WebSocket support (REALTIME_E2E=true)")

  // ── 1. WebSocket reconnect after disconnect ────────────────────────────
  //
  // Opens the messenger, closes the chat socket with a retryable client-owned
  // code (4000), then requires a second chat socket that reaches OPEN. There is
  // no fallback path: a page that never reconnects fails this test.
  test("reconnects the chat WebSocket after a forced disconnect", async ({ page }) => {
    await recordWebSockets(page)
    await gotoWithTransientRetry(page, "/messenger", { waitUntil: "networkidle" })
    await page.getByRole("listitem").first().click()

    await expect.poll(() => chatSocketStates(page), { timeout: 15_000 }).toEqual([SOCKET_OPEN])
    await page.evaluate((marker) => {
      const socket = (window as RecordingWindow).__e2eSockets?.find((candidate) =>
        candidate.url.includes(marker)
      )
      socket?.close(4000, "playwright-forced-close")
    }, CHAT_SOCKET_MARKER)

    await expect
      .poll(() => chatSocketStates(page), { timeout: 20_000 })
      .toEqual([expect.any(Number), SOCKET_OPEN])
    const errorBanner = page.locator('[role="alert"]').filter({ hasText: /connection|соединение/i })
    await expect(errorBanner).not.toBeVisible({ timeout: 5000 })
  })

  // ── 2. Typing indicator ────────────────────────────────────────────────
  //
  // Simulates a typing event arriving from another user by injecting a
  // synthetic WebSocket message, then verifies the UI renders the indicator.
  test("shows typing indicator when remote user sends typing event", async ({ page }) => {
    await gotoWithTransientRetry(page, "/messenger", { waitUntil: "networkidle" })
    await page.getByRole("listitem").first().click()
    await page.waitForTimeout(500)

    // Dispatch a synthetic WebSocket message that mimics a server typing event.
    await page.evaluate(() => {
      const event = new MessageEvent("message", {
        data: JSON.stringify({
          type: "typing",
          chat_id: "00000000-0000-4000-8000-000000000001",
          user_id: "00000000-0000-4000-8000-000000000002",
          user_name: "Other User",
          is_typing: true,
        }),
      })
      // Dispatch on the window so the app's WS listener can pick it up if
      // it uses window-level event forwarding.
      window.dispatchEvent(event)
    })

    await page.waitForTimeout(500)

    // The typing indicator element — common patterns are a role="status" with
    // text like "is typing" or "печатает".
    const typingIndicator = page
      .locator('[role="status"], [data-testid="typing-indicator"]')
      .filter({ hasText: /typing|печатает/i })
    await expect(typingIndicator).toBeVisible({ timeout: 5000 })
  })

  // ── 3. Message sent confirmation ──────────────────────────────────────
  //
  // Sends a message, checks the server response, and scopes the status to that
  // message rather than looking for a nonexistent global delivery marker.
  test("shows sent confirmation after the server accepts the message", async ({ page }) => {
    await gotoWithTransientRetry(page, "/messenger", { waitUntil: "networkidle" })
    await page.getByRole("listitem").first().click()
    await page.waitForTimeout(500)

    const messageText = `e2e-delivery-${Date.now()}`
    const input = page.getByRole("textbox", { name: /message|сообщение/i })
    const sendResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        /\/chats\/[^/]+\/messages\/?$/u.test(new URL(response.url()).pathname)
    )
    await input.fill(messageText)
    await input.press("Enter")

    const response = await sendResponse
    expect(response.ok()).toBe(true)
    const acceptedMessage = (await response.json()) as { id?: string; content?: string }
    expect(acceptedMessage.id).toBeTruthy()
    expect(acceptedMessage.content).toBe(messageText)

    const sentMessage = page.getByText(messageText, { exact: true })
    await expect(sentMessage).toBeVisible({ timeout: 5000 })
    const sentRow = sentMessage.locator(
      "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' group ')][1]"
    )
    await expect(
      sentRow.getByRole("img", {
        name: /^(Отправлено|Прочитано получателем|Sent|Read by recipient)$/i,
      })
    ).toBeVisible({ timeout: 10_000 })
  })

  // ── 4. Message read confirmation & Seen-by-N ──────────────────────────
  //
  // Simulates a read confirmation event arriving from another user by
  // injecting a synthetic WS read frame, then verifies the UI reflects the
  // read status (either specific "Seen" / "Прочитано" label or group "seen by" status).
  test("shows read confirmation after remote user reads the message", async ({ page }) => {
    await gotoWithTransientRetry(page, "/messenger", { waitUntil: "networkidle" })
    await page.getByRole("listitem").first().click()
    await page.waitForTimeout(500)

    const messageText = `e2e-read-${Date.now()}`
    const input = page.getByRole("textbox", { name: /message|сообщение/i })
    await input.fill(messageText)
    await input.press("Enter")

    const sentMessage = page.getByText(messageText)
    await expect(sentMessage).toBeVisible({ timeout: 5000 })

    // Dispatch a synthetic WebSocket read event from another user.
    await page.evaluate(() => {
      const event = new MessageEvent("message", {
        data: JSON.stringify({
          type: "read",
          chat_id: "00000000-0000-4000-8000-000000000001",
          user_id: "00000000-0000-4000-8000-000000000002",
          read_at: new Date().toISOString(),
        }),
      })
      window.dispatchEvent(event)
    })

    // Expect the read status text or label to appear in the message container.
    const seenLabel = page.locator("span").filter({ hasText: /seen|прочитано|прочли/i })
    await expect(seenLabel.last()).toBeVisible({ timeout: 10_000 })
  })
})
