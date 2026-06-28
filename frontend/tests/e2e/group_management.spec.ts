import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { useMockApi } from "./utils/mockApi"

const ENABLED = process.env.URL_STATE_E2E === "true"
const BASE = process.env.URL_STATE_E2E_BASE ?? "http://127.0.0.1:4175"

// ── Shared fixtures ────────────────────────────────────────────────────────────
const CURRENT_USER_ID = "lhci-mock-user"
const GROUP_CHAT_ID = "chat-uuid-group"
const MEMBER_TWO_ID = "member-user-2"
const apiPathMatches = (url: URL, path: string) =>
  url.pathname === path || url.pathname === path.replace("/api/", "/api/v1/")

const CHAT_COLLECTION_MATCH = (url: URL) => apiPathMatches(url, "/api/chats")
const GROUP_CREATE_MATCH = (url: URL) => apiPathMatches(url, "/api/chats/groups")
const USERS_MATCH = (url: URL) => apiPathMatches(url, "/api/users")
const groupDetailMatch = (url: URL) => apiPathMatches(url, `/api/chats/${GROUP_CHAT_ID}`)
const groupMessagesMatch = (url: URL) => apiPathMatches(url, `/api/chats/${GROUP_CHAT_ID}/messages`)
const groupParticipantsMatch = (url: URL) =>
  apiPathMatches(url, `/api/chats/${GROUP_CHAT_ID}/participants`)
const memberTwoParticipantMatch = (url: URL) =>
  apiPathMatches(url, `/api/chats/${GROUP_CHAT_ID}/participants/${MEMBER_TWO_ID}`)

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

const MEMBER_ONE = makeUser({
  id: "member-user-1",
  email: "member1@example.com",
  full_name: "Member One",
})

const MEMBER_TWO = makeUser({
  id: MEMBER_TWO_ID,
  email: "member2@example.com",
  full_name: "Member Two",
})

const MEMBER_THREE = makeUser({
  id: "member-user-3",
  email: "member3@example.com",
  full_name: "Member Three",
})

const SEARCH_RESULTS = [MEMBER_ONE, MEMBER_TWO, MEMBER_THREE]

const CREATED_GROUP = {
  id: GROUP_CHAT_ID,
  chat_type: "group",
  name: "Супер Группа",
  created_by: CURRENT_USER_ID,
  participants: [CURRENT_USER, MEMBER_ONE, MEMBER_TWO],
  unread_count: 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

// ── Tests ──────────────────────────────────────────────────────────────────────
test.describe("Group Chat Management", () => {
  test.skip(!ENABLED, "Requires URL_STATE_E2E=true build with VITE_LHCI=true auth bypass")
  test.skip(({ browserName }) => browserName !== "chromium", "chromium-only by design")

  test.use({ baseURL: BASE, serviceWorkers: "block" })

  test("creates a group and manages members/title in group info panel", async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as Window & { __E2E_NETWORK_API_MOCKS__?: boolean }).__E2E_NETWORK_API_MOCKS__ = true
    })

    // 1. Global mocks (auth, profile, news, schedule…)
    await useMockApi(page)

    // 2. Inject mock WebSocket so the WS hub 404 does not stall page load.
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
          this.readyState = 0
          const store = window as unknown as Window & { MockWebSocketInstances?: MockWebSocket[] }
          store.MockWebSocketInstances ??= []
          store.MockWebSocketInstances.push(this)
          setTimeout(() => {
            this.readyState = 1
            this.onopen?.()
          }, 50)
        }
        send(_data: string) {}
        close() {
          this.readyState = 3
          this.onclose?.()
        }
      }
      ;(
        window as unknown as Window & { MockWebSocketInstances: MockWebSocket[] }
      ).MockWebSocketInstances = []
      ;(window as Window & { WebSocket: unknown }).WebSocket = MockWebSocket
    })

    // 3. Chat API mocks — registered before navigation so they're active
    //    when the initial React Query fetch fires.

    // GET  /api/chats  → empty list (no existing chats)
    // POST /api/chats  → group creation returns the new group
    await page.route(CHAT_COLLECTION_MATCH, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(CREATED_GROUP),
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [], has_more: false, next_cursor: null }),
        })
      }
    })

    await page.route(GROUP_CREATE_MATCH, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CREATED_GROUP),
      })
    })

    // User search — any query string on /api/users with a "search" param.
    // Playwright glob "**/api/users*" matches any URL starting with /api/users.
    await page.route(USERS_MATCH, async (route) => {
      const url = route.request().url()
      if (url.includes("search=")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(SEARCH_RESULTS),
        })
      } else {
        await route.fallback()
      }
    })

    // GET  /api/chats/{id}   → group details
    // PATCH /api/chats/{id}  → rename response
    // DELETE /api/chats/{id} → group deletion
    await page.route(groupDetailMatch, async (route) => {
      if (route.request().method() === "PATCH") {
        const payload = ((await route.request().postDataJSON()) ?? {}) as { name?: string }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ...CREATED_GROUP,
            name: payload.name ?? CREATED_GROUP.name,
          }),
        })
      } else if (route.request().method() === "DELETE") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ chat_id: GROUP_CHAT_ID, status: "deleted" }),
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(CREATED_GROUP),
        })
      }
    })

    await page.route(groupMessagesMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], has_more: false, next_cursor: null }),
      })
    })

    // Add participant
    await page.route(groupParticipantsMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      })
    })

    // Kick participant (Member Two)
    await page.route(memberTwoParticipantMatch, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true }),
      })
    })

    // 4. Navigate to messenger (empty state — no existing chats).
    await page.goto("/messenger", { waitUntil: "domcontentloaded", timeout: 30_000 })

    // 5. Open the "New Chat" modal via the icon button in the sidebar header.
    //    The button has no visible text — it uses aria-label="Новый чат".
    await page.getByLabel("Новый чат").click()

    // 6. Switch to the "Group" tab (role="tab", text = "Группа" in RU locale).
    await page.getByRole("tab", { name: "Группа" }).click()

    // 7. Fill in the group name.
    //    Input uses aria-label={t("messenger:groupName")} = "Название группы".
    await page.getByLabel("Название группы").fill("Супер Группа")

    // 8. Search users. The search input uses aria-label="Поиск пользователей".
    await page.getByRole("textbox", { name: "Поиск пользователей" }).fill("Member")

    // 9. Wait for the search results listbox to populate, then select members.
    //    Each option has role="option"; select by visible text.
    await page.getByRole("option", { name: "Member One" }).click()
    await page.getByRole("option", { name: "Member Two" }).click()

    // 10. Create the group. Button text = t("messenger:createGroup") = "Создать группу".
    await page.getByRole("button", { name: "Создать группу" }).click()

    // 11. The app should navigate to the new group chat URL.
    await expect(page).toHaveURL(new RegExp(`messenger/${GROUP_CHAT_ID}`), { timeout: 10_000 })

    // 12. The chat header shows the group name. It is rendered as a button
    //     (clicking it opens the GroupInfoPanel).
    const groupHeaderBtn = page.getByRole("button", { name: /Супер Группа/ })
    await expect(groupHeaderBtn).toBeVisible({ timeout: 10_000 })

    // 13. Open the GroupInfoPanel.
    await groupHeaderBtn.click()

    // The panel dialog should appear (role="dialog").
    const infoPanel = page.getByRole("dialog")
    await expect(infoPanel).toBeVisible({ timeout: 8_000 })

    // The member list subtitle renders "N участник(ов)" — check the dialog is open
    // by verifying the close button (aria-label from common:buttons.close = "Закрыть").
    await expect(page.getByLabel("Закрыть")).toBeVisible({ timeout: 5_000 })

    // 14. Accessibility scan of the GroupInfoPanel.
    const a11yPanel = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .disableRules(["color-contrast", "color-contrast-enhanced"])
      .analyze()
    expect(a11yPanel.violations).toEqual([])

    // 15. Rename the group.
    //     Button text = t("messenger:renameGroup") = "Переименовать группу".
    await page.getByRole("button", { name: "Переименовать группу" }).click()

    // The inline rename input appears (aria-label = "Название группы").
    const renameInput = page.getByLabel("Название группы")
    await expect(renameInput).toBeVisible({ timeout: 5_000 })
    await renameInput.fill("Супер Группа v2")

    // Save (aria-label = common:buttons.save = "Сохранить").
    await page.getByLabel("Сохранить").click()

    // 16. Add a member.
    //     Button text = t("messenger:addMember") = "Добавить участников".
    await page.getByRole("button", { name: "Добавить участников" }).click()

    // Search input (aria-label = "Поиск пользователей") appears inside the panel.
    const addSearchInput = infoPanel.getByLabel("Поиск пользователей")
    await expect(addSearchInput).toBeVisible({ timeout: 5_000 })
    await addSearchInput.fill("Three")

    // Wait for search result and click.
    await page.getByRole("button", { name: "Member Three" }).click()

    // 17. Kick Member Two.
    //     Button has aria-label = t("messenger:removeMember", { name: "Member Two" }) = "Удалить Member Two".
    const kickBtn = page.getByLabel("Удалить Member Two")
    await expect(kickBtn).toBeVisible({ timeout: 5_000 })
    await kickBtn.click()
    const removeDialog = page.getByRole("alertdialog", { name: "Удалить участника?" })
    await expect(removeDialog).toBeVisible({ timeout: 5_000 })
    await removeDialog.getByRole("button", { name: "Удалить" }).click()
    await expect(removeDialog).not.toBeVisible()

    // 18. Close the panel.
    await page.getByLabel("Закрыть").click()
    await expect(infoPanel).not.toBeVisible()
  })
})
