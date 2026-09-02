import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Message } from "@/components/messenger/types"
import type { Chat } from "@/api/chat"
import type { User } from "@/types/User"

/** Observe ChatArea's animation contract without changing production props. */
const state = vi.hoisted(() => ({ reduced: false, navigate: vi.fn(), typing: vi.fn() }))

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
    getTypingUsersForChat: () => [],
    sendTyping: state.typing,
  }),
}))
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => state.navigate }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}|${JSON.stringify(options)}` : key,
  }),
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
  ChatWindow: ({ onClearSearch }: { onClearSearch?: () => void }) => (
    <div data-testid="chat-window-mock">
      {onClearSearch ? (
        <button type="button" onClick={onClearSearch}>
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
  TypingIndicator: () => <div data-testid="typing-indicator-mock" />,
}))

import { ChatArea } from "@/components/messenger/ChatArea"

const user = (id: string, name = "Alice") =>
  ({ id, full_name: name, avatar_url: "" }) as unknown as User
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

    const setSearchQuery = vi.fn()
    rerender(<ChatArea {...base} searchQuery="query" setSearchQuery={setSearchQuery} />)
    fireEvent.click(screen.getByRole("button", { name: "clear" }))
    expect(setSearchQuery).toHaveBeenCalledWith("")
  })
})
