import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, describe, it, expect, vi } from "vitest"
import type { ComponentProps, ReactNode } from "react"

import { ChatArea } from "@/components/messenger/ChatArea"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { Message } from "@/components/messenger/types"
import type { Chat } from "@/api/chat"
import type { User } from "@/types/User"

type ChatAreaProps = ComponentProps<typeof ChatArea>
type ChatAreaCapabilityProps = ChatAreaProps & { canManageChat?: boolean }

/**
 * Wave 189 SW4 (B2) — ChatArea unit tests for the 19-prop render surface.
 *
 * Closes W185 SW3 partial defer (carried through W186 + W187 + W188).
 * ChatArea was the last messenger surface without dedicated test coverage —
 * W183 SW8-SW13 baseline + W184 SW3 ContactList tests + W185 SW2 ChatWindow
 * tests covered surrounding components but ChatArea's 19-prop API was only
 * exercised indirectly through MessengerFeature mounts.
 *
 * In-scope:
 *  - Empty-state render (2 tests): selectedChatId null OR activeChat null
 *  - Header rendering (3 tests): participant name + Search button + Menu button
 *  - Search header rendering (2 tests): showSearchInChat=true → input + close
 *  - Menu interactions (3 tests): 3 menu items (View Profile + Clear + Delete)
 *    fire correct callbacks
 *  - Mobile back button (1 test): renders only when isMobile=true
 *  - ChildComponent integration (1 test): ChatWindow + TypingIndicator +
 *    MessageInput rendered when chat selected
 *
 * Mocks applied:
 *  - react-i18next        → pass-through t() with JSON-serialized opts
 *  - SmartImage           → plain <img>
 *  - useMessenger         → { getTypingUsersForChat: () => [] }
 *  - useNavigate          → vi.fn() mock
 *  - ChatWindow           → stub <div data-testid="mock-chat-window" />
 *                           NB: ChatWindow uses @tanstack/react-virtual which
 *                           jsdom can't render meaningfully; stub avoids the
 *                           ChatArea test asserting ChatWindow's internals.
 *  - MessageInput         → stub <div data-testid="mock-message-input" />
 *  - TypingIndicator      → stub <div data-testid="mock-typing-indicator" />
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className }: { alt?: string; className?: string }) => (
    <img alt={alt} className={className} />
  ),
}))

const sendTypingMock = vi.hoisted(() => vi.fn())
const prefersReducedMotionMock = vi.hoisted(() => vi.fn(() => false))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    expect(query).toBe("(prefers-reduced-motion: reduce)")
    return prefersReducedMotionMock()
  },
}))

// W190 SW1 migrated ChatArea + sibling messenger components from framer-motion's
// jsdom-incompat `useReducedMotion()` hook to project's `useMediaQuery
// ("(prefers-reduced-motion: reduce)")` DEFAULT export (jsdom-polyfilled at
// setupTests.ts:13-30). The previous `vi.mock("framer-motion", { useReducedMotion:
// () => false })` block was W184 SW6 defensive code that's now dead — no SUT-tree
// code under this test calls framer-motion's useReducedMotion anymore. Removed at
// W190 polish-v1 «безупречно?» cleanup. framer-motion's `motion.div` +
// `AnimatePresence` exports used by ChatArea internals are still present from
// real framer-motion module (no mock needed; jsdom-compatible).

// useMessenger() context — only `getTypingUsersForChat` is consumed by ChatArea.
vi.mock("@/contexts/MessengerContext", () => ({
  useMessenger: () => ({
    getTypingUsersForChat: () => [],
    sendTyping: sendTypingMock,
  }),
}))

// useNavigate — only used by the mobile back button onClick.
const navigateMock = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}))

// Mock child components — ChatArea's tests focus on ChatArea's own rendering
// (header + menu + empty-state); ChatWindow's internal behavior is covered by
// ChatWindow.test.tsx. Stub the children so jsdom doesn't have to render
// @tanstack/react-virtual (W184 SW6 lesson) or framer-motion AnimatePresence
// child exits (jsdom doesn't render Framer Motion exit animations). Return only
// the three exports imported by ChatArea; importing the barrel's other exports
// would pull unrelated browser/WASM dependencies into this isolated suite.
vi.mock("@/components/messenger", () => ({
  ChatWindow: (props: { messages?: unknown[]; isError?: boolean; onClearSearch?: () => void }) => (
    <div data-testid="mock-chat-window" data-message-count={props.messages?.length ?? 0}>
      {props.onClearSearch && (
        <button
          type="button"
          data-testid="mock-chat-window-clear-search"
          onClick={props.onClearSearch}
        />
      )}
    </div>
  ),
  MessageInput: (props: { onTyping?: () => void; onCancelReply?: () => void }) => (
    <div data-testid="mock-message-input">
      <button type="button" data-testid="mock-message-input-typing" onClick={props.onTyping} />
      {props.onCancelReply && (
        <button
          type="button"
          data-testid="mock-message-input-cancel-reply"
          onClick={props.onCancelReply}
        />
      )}
    </div>
  ),
  TypingIndicator: () => <div data-testid="mock-typing-indicator" />,
}))

afterEach(() => {
  sendTypingMock.mockReset()
  prefersReducedMotionMock.mockReturnValue(false)
  navigateMock.mockReset()
})

const queryClient = new QueryClient()

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

// Test fixtures — minimal Chat + User shapes covering only fields ChatArea
// reads. Wave 189 SW4 — Phase 3 verified ChatArea consumes activeChat (header),
// getOtherParticipant(activeChat) (avatar + name + online dot), and
// presenceMap[userId]?.active (online status). User extends UserOut from
// generated OpenAPI types — fields beyond {id, full_name, avatar_url} are not
// referenced by ChatArea, so a partial fixture cast via `as unknown as User`
// avoids needing to satisfy the full openapi schema in unit tests.
const makeUser = (overrides: { id: string; full_name?: string; avatar_url?: string }): User =>
  ({
    id: overrides.id,
    full_name: overrides.full_name ?? "Alice Anderson",
    avatar_url: overrides.avatar_url ?? "",
  }) as unknown as User

const makeChat = (overrides: Partial<Chat> = {}): Chat =>
  ({
    id: "chat-1",
    participants: [makeUser({ id: "user-me" }), makeUser({ id: "user-alice" })],
    unread_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }) as Chat

const baseMessages: Message[] = [
  {
    id: "m1",
    text: "Hello",
    senderId: "user-alice",
    senderName: "Alice",
    senderAvatar: "",
    timestamp: "12:00",
    isMe: false,
  },
]

// Common default props for ChatArea — each test overrides what it needs.
// Typed via `ComponentProps<typeof ChatArea>` so TS enforces fixture shape
// against the production prop types directly (useMessengerController's
// ReturnType<...> derivation). `as ChatAreaProps` final cast covers the
// `messages: Message[]` field where the source's optimisticMessages type
// uses a structurally-identical UiMessage shape.
const baseProps: ChatAreaCapabilityProps = {
  isMobile: false,
  selectedChatId: null,
  activeChat: null,
  messages: [],
  messagesLoading: false,
  messagesError: false,
  onRetryMessages: vi.fn(),
  showSearchInChat: false,
  setShowSearchInChat: vi.fn(),
  searchQuery: "",
  setSearchQuery: vi.fn(),
  showChatMenu: false,
  setShowChatMenu: vi.fn(),
  handleSendMessage: vi.fn(),
  handleViewProfile: vi.fn(),
  handleClearChat: vi.fn(),
  handleDeleteChat: vi.fn(),
  // getOtherParticipant signature is `(chat: Chat) => User | undefined`
  // per useMessengerController.ts:367-372.
  getOtherParticipant: (chat) => chat.participants.find((p) => p.id !== "user-me"),
  presenceMap: {},
}

describe("ChatArea — empty state (no chat selected)", () => {
  it("renders 'select a chat' empty state when selectedChatId=null", () => {
    render(<ChatArea {...baseProps} />, { wrapper })

    // role="status" wrapper with aria-label from i18n
    const emptyState = screen.getByRole("status", { name: "messenger:selectChat" })
    expect(emptyState).toBeTruthy()

    // Heading + description i18n keys present
    expect(screen.getByText("messenger:selectChat")).toBeTruthy()
    expect(screen.getByText("messenger:selectChatDesc")).toBeTruthy()
  })

  it("renders empty state when activeChat=null even if selectedChatId is set", () => {
    render(<ChatArea {...baseProps} selectedChatId="chat-orphan" activeChat={null} />, {
      wrapper,
    })

    expect(screen.getByRole("status", { name: "messenger:selectChat" })).toBeTruthy()
    expect(screen.getByText("messenger:selectChat")).toBeTruthy()

    // Child components NOT rendered in empty state
    expect(screen.queryByTestId("mock-chat-window")).toBeFalsy()
    expect(screen.queryByTestId("mock-message-input")).toBeFalsy()
  })
})

describe("ChatArea — normal header rendering (chat selected)", () => {
  it("renders participant name in header when activeChat set", () => {
    const chat = makeChat()
    render(<ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} />, {
      wrapper,
    })

    // Participant full_name in h2
    const heading = screen.getByRole("heading", { name: "Alice Anderson", level: 2 })
    expect(heading).toBeTruthy()
  })

  it("opens the direct-chat profile from the header", () => {
    const handleViewProfile = vi.fn()
    const chat = makeChat()
    render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        handleViewProfile={handleViewProfile}
      />,
      { wrapper }
    )

    fireEvent.click(
      screen.getByRole("heading", { name: "Alice Anderson", level: 2 }).closest("button")!
    )
    expect(handleViewProfile).toHaveBeenCalledTimes(1)
  })

  it("renders offline status when participant NOT in presenceMap as active", () => {
    const chat = makeChat()
    render(
      <ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} presenceMap={{}} />,
      { wrapper }
    )

    // Offline i18n label present
    expect(screen.getByText("messenger:offline")).toBeTruthy()
    expect(screen.queryByText("messenger:online")).toBeFalsy()
  })

  it("gives header search and menu controls a 44x44 hit area", () => {
    const chat = makeChat()
    const { container } = render(
      <ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} />,
      { wrapper }
    )

    for (const id of ["chat-search-toggle", "chat-menu-toggle"]) {
      const control = container.querySelector(`#${id}`)
      expect(control).toBeTruthy()
      expect(control?.className).toContain("min-h-[44px]")
      expect(control?.className).toContain("min-w-[44px]")
    }
  })

  it("renders online status + presence indicator when presenceMap.active=true", () => {
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        presenceMap={{ "user-alice": { active: true, last_seen_at: null } }}
      />,
      { wrapper }
    )

    // Online i18n label visible (offline absent)
    expect(screen.getByText("messenger:online")).toBeTruthy()
    expect(screen.queryByText("messenger:offline")).toBeFalsy()

    // Wave 202 SW5 — the active-chat header avatar now renders the pulsing
    // presence ring (`.messenger-online-pulse`) instead of the static
    // `.messenger-online-indicator` dot (the static dot remains in ContactList
    // rows + ProfileModal). One infinite animation, only where the chat is open.
    const onlinePulse = container.querySelector(".messenger-online-pulse")
    expect(onlinePulse).toBeTruthy()
  })
})

describe("ChatArea — search interaction", () => {
  it("clicking Search button fires setShowSearchInChat(true)", () => {
    const setShowSearchInChat = vi.fn()
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        setShowSearchInChat={setShowSearchInChat}
      />,
      { wrapper }
    )

    const searchToggle = container.querySelector("#chat-search-toggle")
    expect(searchToggle).toBeTruthy()
    fireEvent.click(searchToggle!)
    expect(setShowSearchInChat).toHaveBeenCalledWith(true)
  })

  it("renders search input when showSearchInChat=true", () => {
    let focusFrame: FrameRequestCallback | undefined
    vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation((callback) => {
      focusFrame = callback
      return 1
    })
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        showSearchInChat
        searchQuery="hello"
      />,
      { wrapper }
    )

    const searchInput = container.querySelector<HTMLInputElement>("#chat-search-input")
    expect(searchInput).toBeTruthy()
    expect(searchInput!.value).toBe("hello")
    expect(searchInput!.placeholder).toBe("messenger:searchMessages")
    focusFrame?.(0)
    expect(searchInput).toHaveFocus()
  })

  it("uses reduced-motion transitions for the search header", () => {
    prefersReducedMotionMock.mockReturnValue(true)
    const chat = makeChat()
    render(
      <ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} showSearchInChat />,
      { wrapper }
    )

    expect(screen.getByRole("textbox", { name: "messenger:searchMessages" })).toBeTruthy()
  })

  it("updates the query and closes search with a full reset", () => {
    const setShowSearchInChat = vi.fn()
    const setSearchQuery = vi.fn()
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        showSearchInChat
        searchQuery="hello"
        setShowSearchInChat={setShowSearchInChat}
        setSearchQuery={setSearchQuery}
      />,
      { wrapper }
    )

    const searchInput = screen.getByRole("textbox", { name: "messenger:searchMessages" })
    fireEvent.change(searchInput, { target: { value: "hello world" } })
    expect(setSearchQuery).toHaveBeenCalledWith("hello world")

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(setShowSearchInChat).toHaveBeenCalledWith(false)
    expect(setSearchQuery).toHaveBeenCalledWith("")
    expect(container.querySelector("#chat-search-input")).toBeTruthy()
  })
})

describe("ChatArea — chat menu interactions", () => {
  it("clicking Menu button fires setShowChatMenu toggle", () => {
    const setShowChatMenu = vi.fn()
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        showChatMenu={false}
        setShowChatMenu={setShowChatMenu}
      />,
      { wrapper }
    )

    const menuToggle = container.querySelector("#chat-menu-toggle")
    expect(menuToggle).toBeTruthy()
    fireEvent.click(menuToggle!)
    // setShowChatMenu(!false) → setShowChatMenu(true)
    expect(setShowChatMenu).toHaveBeenCalledWith(true)
  })

  it("hides destructive chat actions for a non-admin participant", () => {
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        canManageChat={false}
        selectedChatId={chat.id}
        activeChat={chat}
        showChatMenu
      />,
      { wrapper }
    )

    expect(container.querySelector("#chat-action-view-profile")).toBeTruthy()
    expect(container.querySelector("#chat-action-clear-chat")).toBeFalsy()
    expect(container.querySelector("#chat-action-delete-chat")).toBeFalsy()
  })

  it("renders destructive chat actions for an admin", () => {
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        canManageChat
        selectedChatId={chat.id}
        activeChat={chat}
        showChatMenu
      />,
      { wrapper }
    )

    expect(container.querySelector("#chat-action-view-profile")).toBeTruthy()
    expect(container.querySelector("#chat-action-clear-chat")).toBeTruthy()
    expect(container.querySelector("#chat-action-delete-chat")).toBeTruthy()
  })

  it("gives every chat menu action a 44x44 hit area", () => {
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        canManageChat
        selectedChatId={chat.id}
        activeChat={chat}
        showChatMenu
      />,
      { wrapper }
    )

    for (const id of [
      "chat-action-view-profile",
      "chat-action-clear-chat",
      "chat-action-delete-chat",
    ]) {
      const action = container.querySelector(`#${id}`)
      expect(action).toBeTruthy()
      expect(action?.className).toContain("min-h-[44px]")
      expect(action?.className).toContain("min-w-[44px]")
    }
  })

  it("clicking menu items fires the correct callback (Clear Chat case)", () => {
    const handleClearChat = vi.fn()
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        canManageChat
        selectedChatId={chat.id}
        activeChat={chat}
        showChatMenu
        handleClearChat={handleClearChat}
      />,
      { wrapper }
    )

    const clearBtn = container.querySelector("#chat-action-clear-chat")
    expect(clearBtn).toBeTruthy()
    fireEvent.click(clearBtn!)
    expect(handleClearChat).toHaveBeenCalledTimes(1)
  })

  it("routes view-profile and delete actions to their callbacks", () => {
    const handleViewProfile = vi.fn()
    const handleDeleteChat = vi.fn()
    const chat = makeChat()
    const { container } = render(
      <ChatArea
        {...baseProps}
        canManageChat
        selectedChatId={chat.id}
        activeChat={chat}
        showChatMenu
        handleViewProfile={handleViewProfile}
        handleDeleteChat={handleDeleteChat}
      />,
      { wrapper }
    )

    fireEvent.click(container.querySelector("#chat-action-view-profile")!)
    fireEvent.click(container.querySelector("#chat-action-delete-chat")!)
    expect(handleViewProfile).toHaveBeenCalledTimes(1)
    expect(handleDeleteChat).toHaveBeenCalledTimes(1)
  })
})

describe("ChatArea — group header and typing delegation", () => {
  it("opens group info and renders the resolved member count", () => {
    const onOpenGroupInfo = vi.fn()
    const chat = makeChat()
    render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        activeChatDisplay={{ isGroup: true, name: "Study group", avatar: "", memberCount: 4 }}
        onOpenGroupInfo={onOpenGroupInfo}
      />,
      { wrapper }
    )

    expect(screen.getByRole("heading", { name: "Study group", level: 2 })).toBeTruthy()
    expect(screen.getByText('messenger:group.members|{"count":4}')).toBeTruthy()
    fireEvent.click(screen.getByRole("heading", { name: "Study group", level: 2 }))
    expect(onOpenGroupInfo).toHaveBeenCalledTimes(1)
    expect(screen.queryByText("messenger:online")).toBeFalsy()
    expect(screen.queryByText("messenger:offline")).toBeFalsy()
  })

  it("does not call a profile handler when group info has no callback", () => {
    const handleViewProfile = vi.fn()
    const chat = makeChat()
    render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        activeChatDisplay={{ isGroup: true, name: "Study group", avatar: "", memberCount: 4 }}
        onOpenGroupInfo={undefined}
        handleViewProfile={handleViewProfile}
      />,
      { wrapper }
    )

    fireEvent.click(screen.getByRole("button", { name: /Study group/ }))
    expect(handleViewProfile).not.toHaveBeenCalled()
  })

  it("falls back safely when a direct chat has no other participant", () => {
    const chat = makeChat({ participants: [makeUser({ id: "user-me" })] })
    render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        getOtherParticipant={() => undefined}
        presenceMap={{ "": { active: true, last_seen_at: null } }}
      />,
      { wrapper }
    )

    expect(document.querySelector("h2")?.textContent).toBe("")
    expect(screen.getByText("messenger:online")).toBeTruthy()
    expect(document.querySelector(".messenger-online-pulse")).toBeTruthy()
  })

  it("delegates typing to the selected chat and renders reduced-motion transitions", () => {
    prefersReducedMotionMock.mockReturnValue(true)
    const chat = makeChat()
    const { rerender } = render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        showChatMenu
        replyingTo={{ senderName: "Alice", isMe: false, text: "Hello" }}
        onCancelReply={vi.fn()}
      />,
      { wrapper }
    )

    fireEvent.click(screen.getByTestId("mock-message-input-typing"))
    expect(sendTypingMock).toHaveBeenCalledWith(chat.id)
    expect(screen.getByTestId("mock-message-input-cancel-reply")).toBeTruthy()

    rerender(<ChatArea {...baseProps} />)
    expect(screen.getByRole("status", { name: "messenger:selectChat" })).toBeTruthy()
  })
})

describe("ChatArea — mobile vs desktop", () => {
  it("renders ChevronLeft back button only when isMobile=true", () => {
    const chat = makeChat()
    const { container, rerender } = render(
      <ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} isMobile={false} />,
      { wrapper }
    )

    // Desktop: no back-button click handler — only the header avatar button +
    // search + menu (3 m.buttons total). lucide-react ChevronLeft icon should
    // not be rendered. Check for absence of the lucide chevron SVG class.
    const lucideChevronDesktop = container.querySelector(".lucide-chevron-left")
    expect(lucideChevronDesktop).toBeFalsy()

    rerender(<ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} isMobile />)
    const lucideChevronMobile = container.querySelector(".lucide-chevron-left")
    expect(lucideChevronMobile).toBeTruthy()

    const backButton = screen.getByRole("button", { name: "messenger:backToChats" })
    expect(backButton.className).toContain("min-h-[44px]")
    expect(backButton.className).toContain("min-w-[44px]")

    fireEvent.click(backButton)
    expect(navigateMock).toHaveBeenCalledWith({ to: "/messenger", replace: true })

    prefersReducedMotionMock.mockReturnValue(true)
    rerender(
      <ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} isMobile={false} />
    )
    rerender(<ChatArea {...baseProps} selectedChatId={chat.id} activeChat={chat} isMobile />)
    expect(container.querySelector(".lucide-chevron-left")).toBeTruthy()
  })
})

describe("ChatArea — child component integration", () => {
  it("renders ChatWindow + TypingIndicator + MessageInput when chat selected", () => {
    const chat = makeChat()
    render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        messages={baseMessages}
      />,
      { wrapper }
    )

    // All 3 child stubs present
    const chatWindow = screen.getByTestId("mock-chat-window")
    expect(chatWindow).toBeTruthy()
    // Message count threaded through as data attribute (test that messages prop
    // forwards through to ChatWindow)
    expect(chatWindow.getAttribute("data-message-count")).toBe(String(baseMessages.length))

    expect(screen.getByTestId("mock-typing-indicator")).toBeTruthy()
    expect(screen.getByTestId("mock-message-input")).toBeTruthy()
  })

  it("forwards ChatWindow's clear-search action", () => {
    const setSearchQuery = vi.fn()
    const chat = makeChat()
    render(
      <ChatArea
        {...baseProps}
        selectedChatId={chat.id}
        activeChat={chat}
        searchQuery="needle"
        setSearchQuery={setSearchQuery}
      />,
      { wrapper }
    )

    fireEvent.click(screen.getByTestId("mock-chat-window-clear-search"))
    expect(setSearchQuery).toHaveBeenCalledWith("")
  })
})
