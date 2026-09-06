import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Message } from "@/components/messenger/types"
import type { Chat } from "@/api/chat"
import type { User } from "@/types/User"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"

/** Observe ChatArea's animation contract without changing production props. */
const state = vi.hoisted(() => ({
  reduced: false,
  navigate: vi.fn(),
  typing: vi.fn(),
  typingUsers: [] as unknown[],
  translationNamespaces: undefined as string[] | undefined,
}))

vi.mock("framer-motion", async () => {
  const React = await import("react")
  type Props = Record<string, unknown> & { children?: ReactNode }
  const motionOnly = new Set(["initial", "animate", "exit", "transition", "whileHover", "whileTap"])
  const serialise = (value: unknown) => (value === undefined ? "undefined" : JSON.stringify(value))
  const Motion = React.forwardRef<HTMLElement, Props>(function Motion({ children, ...props }, ref) {
    const tag = (props["data-motion-tag"] as string | undefined) ?? "div"
    const cleaned: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(props)) {
      if (key === "data-motion-tag" || motionOnly.has(key)) continue
      cleaned[key] = value
    }
    return React.createElement(
      tag,
      {
        ...cleaned,
        ref,
        "data-motion-initial": serialise(props.initial),
        "data-motion-animate": serialise(props.animate),
        "data-motion-exit": serialise(props.exit),
        "data-motion-transition": serialise(props.transition),
        "data-motion-while-hover": serialise(props.whileHover),
        "data-motion-while-tap": serialise(props.whileTap),
      },
      children as ReactNode
    )
  })
  const motion = new Proxy(
    {},
    {
      get: (_target, key) =>
        typeof key === "string"
          ? React.forwardRef<HTMLElement, Props>(function MotionElement(props, ref) {
              return React.createElement(Motion, { ...props, ref, "data-motion-tag": key })
            })
          : undefined,
    }
  )
  return {
    m: motion,
    motion,
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  }
})

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => state.reduced }))
vi.mock("@/contexts/MessengerContext", () => ({
  useMessenger: () => ({
    getTypingUsersForChat: () => state.typingUsers,
    sendTyping: state.typing,
  }),
}))
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => state.navigate }))
vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: string[]) => {
    state.translationNamespaces = namespaces
    return {
      t: (key: string, options?: Record<string, unknown>) =>
        options ? `${key}|${JSON.stringify(options)}` : key,
    }
  },
}))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))
vi.mock("@/components/messenger/GroupAvatar", () => ({
  GroupAvatar: ({ className }: { className?: string }) => (
    <div data-testid="group-avatar" className={className} />
  ),
}))
vi.mock("@/components/messenger", () => ({
  ChatWindow: (props: {
    onClearSearch?: () => void
    searchQuery?: string
    isLoading?: boolean
    isError?: boolean
    hasMore?: boolean
    isLoadingOlder?: boolean
    olderMessagesError?: boolean
  }) => (
    <div
      data-testid="chat-window-mock"
      data-is-loading={String(props.isLoading)}
      data-is-error={String(props.isError)}
      data-has-more={String(props.hasMore)}
      data-is-loading-older={String(props.isLoadingOlder)}
      data-older-messages-error={String(props.olderMessagesError)}
      data-search-query={props.searchQuery ?? ""}
    >
      {props.onClearSearch ? (
        <button type="button" onClick={props.onClearSearch}>
          clear
        </button>
      ) : null}
    </div>
  ),
  MessageInput: ({ onTyping }: { onTyping?: () => void }) => (
    <button type="button" data-testid="message-input-mock" onClick={onTyping}>
      type
    </button>
  ),
  TypingIndicator: ({ users }: { users?: unknown[] }) => (
    <div data-testid="typing-indicator-mock" data-user-count={users?.length ?? 0} />
  ),
}))

import { ChatArea } from "@/components/messenger/ChatArea"

const user = (id: string, name = "Alice", avatar_url = "") =>
  ({ id, full_name: name, avatar_url }) as unknown as User
const chat = ({ group = false }: { group?: boolean } = {}) =>
  ({
    id: "chat-1",
    participants: [user("me", "Me"), user("peer", group ? "Group peer" : "Alice")],
    unread_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }) as unknown as Chat
const message: Message = {
  id: "m1",
  senderId: "peer",
  senderName: "Alice",
  senderAvatar: "",
  text: "hello",
  timestamp: "12:00",
  isMe: false,
}
const base = {
  isMobile: false,
  selectedChatId: "chat-1",
  activeChat: chat(),
  messages: [message],
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
  getOtherParticipant: (value: Chat) => value.participants.find((item) => item.id !== "me"),
  presenceMap: {},
}

beforeEach(() => {
  state.reduced = false
  state.navigate.mockReset()
  state.typing.mockReset()
  state.typingUsers = []
  state.translationNamespaces = undefined
})
afterEach(() => vi.restoreAllMocks())

const attr = (element: Element, name: string) => element.getAttribute(name)

describe("ChatArea motion and delegation contract", () => {
  it("uses the mobile slide animation and stable root geometry", () => {
    const { container } = render(<ChatArea {...base} isMobile />)
    const root = container.firstElementChild!
    expect(attr(root, "data-motion-initial")).toBe(JSON.stringify({ x: 300, opacity: 0 }))
    expect(attr(root, "data-motion-animate")).toBe(JSON.stringify({ x: 0, opacity: 1 }))
    expect(attr(root, "data-motion-exit")).toBe(JSON.stringify({ x: 300, opacity: 0 }))
    expect(attr(root, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0.45, ease: [0.22, 1, 0.36, 1] })
    )
    expect(root).toHaveClass(
      "relative",
      "z-base",
      "flex",
      "h-full",
      "overflow-hidden",
      "bg-msg-chat"
    )
    expect(screen.getByTestId("chat-window-mock")).toBeInTheDocument()
  })

  it("disables all root/header motion when reduced motion is requested", () => {
    state.reduced = true
    const { container } = render(<ChatArea {...base} isMobile />)
    const root = container.firstElementChild!
    expect(attr(root, "data-motion-initial")).toBe("undefined")
    expect(attr(root, "data-motion-exit")).toBe("undefined")
    expect(attr(root, "data-motion-transition")).toBe(JSON.stringify({ duration: 0 }))
    const header = container.querySelector(".z-deep")!
    expect(attr(header, "data-motion-initial")).toBe("false")
    expect(attr(header, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0 }))
    expect(attr(header, "data-motion-transition")).toBe("undefined")
  })

  it("keeps normal/search header motion and close/reset behaviour deterministic", () => {
    const setShowSearchInChat = vi.fn()
    const setSearchQuery = vi.fn()
    const { container, rerender } = render(
      <ChatArea {...base} setShowSearchInChat={setShowSearchInChat} />
    )
    const searchButton = container.querySelector("#chat-search-toggle")!
    expect(searchButton).toHaveAttribute("aria-label", "messenger:searchMessages")
    expect(attr(searchButton, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.05 }))
    expect(attr(searchButton, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.95 }))
    fireEvent.click(searchButton)
    expect(setShowSearchInChat).toHaveBeenCalledWith(true)

    rerender(
      <ChatArea
        {...base}
        showSearchInChat
        searchQuery="needle"
        setShowSearchInChat={setShowSearchInChat}
        setSearchQuery={setSearchQuery}
      />
    )
    const searchHeader = container.querySelector(".sticky")!
    expect(attr(searchHeader, "data-motion-initial")).toBe(JSON.stringify({ y: -20, opacity: 0 }))
    expect(attr(searchHeader, "data-motion-animate")).toBe(JSON.stringify({ y: 0, opacity: 1 }))
    expect(attr(searchHeader, "data-motion-exit")).toBe(JSON.stringify({ y: -20, opacity: 0 }))
    expect(screen.getByTestId("chat-window-mock")).toHaveAttribute("data-search-query", "needle")
    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    expect(attr(closeButton, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.9 }))

    state.reduced = true
    rerender(
      <ChatArea
        {...base}
        showSearchInChat
        searchQuery="needle-reduced"
        setShowSearchInChat={setShowSearchInChat}
        setSearchQuery={setSearchQuery}
      />
    )
    expect(attr(container.querySelector(".sticky")!, "data-motion-initial")).toBe("false")
    expect(attr(container.querySelector(".sticky")!, "data-motion-exit")).toBe(
      JSON.stringify({ opacity: 0 })
    )
    state.reduced = false

    const input = screen.getByRole("textbox", { name: "messenger:searchMessages" })
    fireEvent.change(input, { target: { value: "needle next" } })
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(setSearchQuery).toHaveBeenNthCalledWith(1, "needle next")
    expect(setShowSearchInChat).toHaveBeenLastCalledWith(false)
    expect(setSearchQuery).toHaveBeenLastCalledWith("")
  })

  it("preserves empty-state card motion/style and child callback delegation", () => {
    const { container, rerender } = render(
      <ChatArea {...base} selectedChatId={null} activeChat={null} setSearchQuery={vi.fn()} />
    )
    const root = container.firstElementChild!
    expect(attr(root, "data-motion-initial")).toBe("undefined")
    const icon = container.querySelector(".messenger-card-matte")!
    expect(icon).toHaveStyle({ background: "var(--messenger-card-bg)" })
    expect(icon).toHaveClass("relative", "mb-7", "size-40", "items-center", "justify-center")
    expect(screen.getByRole("status", { name: "messenger:selectChat" })).toBeInTheDocument()
    expect(attr(icon, "data-motion-initial")).toBe(
      JSON.stringify({ scale: 0.85, opacity: 0, y: 8 })
    )
    expect(attr(icon, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0.6, ease: [0.22, 1, 0.36, 1] })
    )

    state.reduced = true
    rerender(<ChatArea {...base} selectedChatId={null} activeChat={null} />)
    expect(attr(container.querySelector(".messenger-card-matte")!, "data-motion-initial")).toBe(
      "false"
    )
    expect(attr(container.querySelector(".messenger-card-matte")!, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0 })
    )

    state.reduced = false
    const setSearchQuery = vi.fn()
    rerender(<ChatArea {...base} searchQuery="query" setSearchQuery={setSearchQuery} />)
    fireEvent.click(screen.getByRole("button", { name: "clear" }))
    expect(setSearchQuery).toHaveBeenCalledWith("")
  })

  it("keeps group header actions safe when the optional callback is absent", () => {
    const groupChat = chat({ group: true })

    render(
      <ChatArea
        {...base}
        activeChat={groupChat}
        activeChatDisplay={{
          isGroup: true,
          name: "Study group",
          avatar: "",
          memberCount: groupChat.participants.length,
        }}
        onOpenGroupInfo={undefined}
      />
    )

    const headerButton = screen.getByRole("button", { name: /Study group/ })
    expect(() => fireEvent.click(headerButton)).not.toThrow()
  })

  it("forwards all defensive defaults and the exact translation namespace contract", () => {
    state.typingUsers = [{ id: "peer" }]
    const { container, rerender } = render(<ChatArea {...base} showChatMenu />)

    expect(state.translationNamespaces).toEqual(["messenger", "common"])
    const chatWindow = screen.getByTestId("chat-window-mock")
    expect(chatWindow).toHaveAttribute("data-is-loading", "false")
    expect(chatWindow).toHaveAttribute("data-is-error", "false")
    expect(chatWindow).toHaveAttribute("data-has-more", "false")
    expect(chatWindow).toHaveAttribute("data-is-loading-older", "false")
    expect(chatWindow).toHaveAttribute("data-older-messages-error", "false")
    expect(screen.getByTestId("typing-indicator-mock")).toHaveAttribute("data-user-count", "1")
    expect(container.querySelector("#chat-action-clear-chat")).toBeNull()
    expect(container.querySelector("#chat-action-delete-chat")).toBeNull()

    rerender(<ChatArea {...base} selectedChatId={null} activeChat={null} />)
    expect(screen.queryByTestId("typing-indicator-mock")).toBeNull()
  })

  it("preserves online/offline status motion contracts and header fallback semantics", () => {
    const { container, rerender } = render(
      <ChatArea {...base} presenceMap={{ peer: { active: true, last_seen_at: null } }} />
    )
    const online = screen.getByText("messenger:online")
    expect(attr(online, "data-motion-initial")).toBe(JSON.stringify({ opacity: 0, y: 5 }))
    expect(attr(online, "data-motion-animate")).toBe(JSON.stringify({ opacity: 1, y: 0 }))
    expect(attr(online, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0, y: -5 }))

    const menuToggle = container.querySelector<HTMLButtonElement>("#chat-menu-toggle")!
    expect(menuToggle).toHaveAttribute("aria-label", "messenger:chatActions")
    expect(attr(menuToggle, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.05 }))
    expect(attr(menuToggle, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.95 }))

    rerender(<ChatArea {...base} presenceMap={{}} />)
    const offline = screen.getByText("messenger:offline")
    expect(attr(offline, "data-motion-initial")).toBe(JSON.stringify({ opacity: 0, y: 5 }))
    expect(attr(offline, "data-motion-animate")).toBe(JSON.stringify({ opacity: 1, y: 0 }))
    expect(attr(offline, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0, y: -5 }))
  })

  it("keeps normal header, mobile back and menu motion values exact", () => {
    const { container, rerender } = render(<ChatArea {...base} isMobile showChatMenu />)
    const header = container.querySelector(".z-deep")!
    expect(attr(header, "data-motion-initial")).toBe(JSON.stringify({ y: -20, opacity: 0 }))
    expect(attr(header, "data-motion-animate")).toBe(JSON.stringify({ y: 0, opacity: 1 }))
    expect(attr(header, "data-motion-exit")).toBe(JSON.stringify({ y: -20, opacity: 0 }))

    const titleButton = screen.getByRole("heading", { name: "Alice", level: 2 }).closest("button")!
    expect(attr(titleButton, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.02 }))
    expect(attr(titleButton, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.98 }))
    const backButton = screen.getByRole("button", { name: "messenger:backToChats" })
    expect(attr(backButton, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.9 }))

    const menu = container.querySelector(".card-glass")!
    expect(attr(menu, "data-motion-initial")).toBe(
      JSON.stringify({ opacity: 0, scale: 0.9, y: 10, x: 5 })
    )
    expect(attr(menu, "data-motion-animate")).toBe(
      JSON.stringify({ opacity: 1, scale: 1, y: 0, x: 0 })
    )
    expect(attr(menu, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0, scale: 0.9, y: 10 }))

    rerender(<ChatArea {...base} showChatMenu isMobile />)
    state.reduced = true
    rerender(<ChatArea {...base} showChatMenu isMobile searchQuery="force-rerender" />)
    expect(attr(container.querySelector(".card-glass")!, "data-motion-initial")).toBe("false")
    expect(attr(container.querySelector(".card-glass")!, "data-motion-exit")).toBe(
      JSON.stringify({ opacity: 0 })
    )
  })

  it("renders each menu label and semantic color without losing the actions", () => {
    const { container } = render(<ChatArea {...base} canManageChat showChatMenu />)
    const expected = [
      ["view-profile", "messenger:viewProfile", "text-primary-main"],
      ["clear-chat", "messenger:clearChat", "text-warning-text"],
      ["delete-chat", "messenger:deleteChat", "text-error-text"],
    ] as const

    for (const [id, label, color] of expected) {
      const action = container.querySelector<HTMLButtonElement>(`#chat-action-${id}`)!
      expect(action).toHaveTextContent(label)
      expect(action.querySelector("svg")).toHaveClass(color)
    }

    const menuToggle = container.querySelector<HTMLButtonElement>("#chat-menu-toggle")!
    expect(menuToggle).toHaveClass("bg-(--bg-surface-hover)")

    const { container: closedContainer } = render(<ChatArea {...base} />)
    const closedMenuToggle = closedContainer.querySelector<HTMLButtonElement>("#chat-menu-toggle")!
    expect(closedMenuToggle).toHaveClass("hover:bg-(--bg-surface-hover)/(--opacity-medium)")
  })

  it("preserves direct-message avatar and name fallbacks for all participant shapes", () => {
    const { container, rerender } = render(<ChatArea {...base} />)
    const fallbackAvatar = screen.getByRole("img", { name: "Alice" })
    expect(fallbackAvatar).toHaveAttribute("src", AVATAR_PLACEHOLDER_URL)
    expect(fallbackAvatar).toHaveClass("size-11", "rounded-full")

    const customPeer = user("peer", "Peer", "/peer.png")
    rerender(<ChatArea {...base} activeChat={chat()} getOtherParticipant={() => customPeer} />)
    expect(screen.getByRole("img", { name: "Peer" })).toHaveAttribute("src", "/peer.png")

    rerender(
      <ChatArea
        {...base}
        getOtherParticipant={() => undefined}
        presenceMap={{ "": { active: false, last_seen_at: null } }}
      />
    )
    expect(container.querySelector('img[alt=""]')).toHaveAttribute("src", AVATAR_PLACEHOLDER_URL)
    expect(container.querySelector("h2")).toHaveTextContent("")
  })

  it("cancels stale search focus frames and reruns the effect on a false-to-true transition", () => {
    const requested: FrameRequestCallback[] = []
    const cancelled: number[] = []
    vi.spyOn(globalThis, "requestAnimationFrame").mockImplementation((callback) => {
      requested.push(callback)
      return requested.length
    })
    vi.spyOn(globalThis, "cancelAnimationFrame").mockImplementation((id) => {
      cancelled.push(id)
    })

    const chatValue = chat()
    const { container, rerender } = render(<ChatArea {...base} activeChat={chatValue} />)
    expect(requested).toHaveLength(0)

    rerender(<ChatArea {...base} activeChat={chatValue} showSearchInChat />)
    expect(requested).toHaveLength(1)
    requested[0]!(0)
    expect(container.querySelector("#chat-search-input")).toHaveFocus()

    rerender(<ChatArea {...base} activeChat={chatValue} showSearchInChat={false} />)
    expect(cancelled).toEqual([1])
    expect(() => requested[0]!(0)).not.toThrow()
  })

  it("keeps empty-state orb, card, icon and typography styles observable", () => {
    const { container } = render(<ChatArea {...base} selectedChatId={null} activeChat={null} />)
    const orb = container.querySelector('[aria-hidden="true"].pointer-events-none')!
    expect(orb).toHaveStyle({
      background: "radial-gradient(circle, var(--messenger-orb-1) 0%, transparent 65%)",
      filter: "blur(50px)",
    })

    const card = container.querySelector(".messenger-card-matte")!
    expect(card).toHaveClass(
      "relative",
      "mb-7",
      "flex",
      "size-40",
      "items-center",
      "justify-center"
    )
    expect(attr(card, "data-motion-initial")).toBe(
      JSON.stringify({ scale: 0.85, opacity: 0, y: 8 })
    )
    expect(attr(card, "data-motion-animate")).toBe(JSON.stringify({ scale: 1, opacity: 1, y: 0 }))
    expect(attr(card, "data-motion-while-hover")).toBe(JSON.stringify({ rotate: 3, scale: 1.05 }))
    expect(attr(card, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0.6, ease: [0.22, 1, 0.36, 1] })
    )
    expect(card).toHaveStyle({ background: "var(--messenger-card-bg)" })
    expect(card.querySelector("svg")).toHaveClass("size-20", "text-(--color-violet-500)")
    expect(card.querySelector("svg")).toHaveStyle({ opacity: "var(--opacity-strong)" })

    const heading = screen.getByRole("heading", { name: "messenger:selectChat", level: 3 })
    const subtitle = screen.getByText("messenger:selectChatDesc")
    expect(heading).toHaveClass("mx-auto", "max-w-[42rem]", "self-stretch", "text-center")
    expect(heading).toHaveStyle({ fontSize: "var(--fs-messenger-hero)" })
    expect(subtitle).toHaveClass("mx-auto", "max-w-[32rem]", "self-stretch", "text-center")
    expect(subtitle).toHaveStyle({ fontSize: "var(--fs-messenger-subtitle)" })
  })
})
