import { render, screen, fireEvent, act } from "@testing-library/react"
import { describe, it, expect, vi, afterEach } from "vitest"
import type { ReactNode } from "react"

import { ChatWindow } from "@/components/messenger/ChatWindow"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { Message } from "@/components/messenger/types"

const { motionState } = vi.hoisted(() => ({
  motionState: { reduced: false },
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => motionState.reduced,
}))

/**
 * Sibling branch-coverage test for ChatWindow (do NOT touch ChatWindow.test.tsx).
 *
 * The existing test covers loading/error/search-empty/no-messages-yet, the
 * edit/delete/tombstone/inline-editor, reactions pills + picker, seen marker,
 * and date dividers + sender grouping. This file fills the remaining uncovered
 * branches of the normal-bubble render path:
 *  - reply affordance (onStartReply) on ALL bubbles
 *  - forward affordance (onForward) on ALL bubbles
 *  - "Forwarded from X" chip (W211)
 *  - reply/quote chip — "You" vs sender name + deleted-original placeholder (W207)
 *  - attachments — image (with/without sanitizable url) + file types (W205)
 *  - jump-to-bottom FAB + scroll handler (W208 SW4)
 *  - reactions picker outside-click / Escape close (W206)
 *
 * Mocks mirror ChatWindow.test.tsx exactly so the i18n key echoes line up.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    alt,
    className,
    onClick,
  }: {
    alt?: string
    className?: string
    onClick?: () => void
  }) =>
    onClick ? (
      <button type="button" onClick={onClick} aria-label={alt}>
        <img alt={alt} className={className} />
      </button>
    ) : (
      <img alt={alt} className={className} />
    ),
}))

// Pass-through debounce so search filtering applies immediately (no fake timers).
vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: <T,>(value: T) => value,
}))

// Render all rows: jsdom has scrollHeight=0 so the real virtualizer yields no
// rows → message bubbles never mount. The mock renders one row per message.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () =>
      Array.from({ length: count }, (_, idx) => ({
        key: idx,
        index: idx,
        start: idx * 80,
        end: (idx + 1) * 80,
        size: 80,
        lane: 0,
      })),
    getTotalSize: () => count * 80,
    measureElement: () => {},
    scrollToIndex: () => {},
  }),
}))

const queryClient = new QueryClient()

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const makeMessage = (overrides: Partial<Message> & Pick<Message, "id" | "text">): Message => ({
  senderId: "user-1",
  senderName: "Alice",
  senderAvatar: "",
  timestamp: "12:00",
  isMe: false,
  ...overrides,
})

afterEach(() => {
  vi.useRealTimers()
  motionState.reduced = false
})

describe("ChatWindow — reply / forward affordances (all bubbles)", () => {
  it("renders the reply affordance and fires onStartReply(id) for a received message", () => {
    const onStartReply = vi.fn()
    render(
      <ChatWindow
        messages={[makeMessage({ id: "r1", text: "theirs", isMe: false })]}
        onStartReply={onStartReply}
      />,
      { wrapper }
    )
    const btn = screen.getByRole("button", { name: "messenger:reply" })
    fireEvent.click(btn)
    expect(onStartReply).toHaveBeenCalledWith("r1")
  })

  it("renders the forward affordance and fires onForward(id) for a received message", () => {
    const onForward = vi.fn()
    render(
      <ChatWindow
        messages={[makeMessage({ id: "f1", text: "theirs", isMe: false })]}
        onForward={onForward}
      />,
      { wrapper }
    )
    const btn = screen.getByRole("button", { name: "messenger:forward" })
    fireEvent.click(btn)
    expect(onForward).toHaveBeenCalledWith("f1")
  })

  it("renders reply + forward + edit + delete together on an own message", () => {
    render(
      <ChatWindow
        messages={[makeMessage({ id: "o1", text: "mine", isMe: true })]}
        onStartReply={() => {}}
        onForward={() => {}}
      />,
      { wrapper }
    )
    expect(screen.getByRole("button", { name: "messenger:reply" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "messenger:forward" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "messenger:editMessage" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "messenger:deleteMessage" })).toBeTruthy()
  })

  it("renders the empty placeholder span when no affordance applies (received, no handlers)", () => {
    render(<ChatWindow messages={[makeMessage({ id: "p1", text: "theirs", isMe: false })]} />, {
      wrapper,
    })
    // No reply/forward/edit/delete buttons → falls into the <span aria-hidden> branch.
    expect(screen.queryByRole("button", { name: "messenger:reply" })).toBeFalsy()
    expect(screen.queryByRole("button", { name: "messenger:forward" })).toBeFalsy()
    expect(screen.queryByRole("button", { name: "messenger:editMessage" })).toBeFalsy()
  })
})

describe("ChatWindow — forwarded-from chip (W211)", () => {
  it("renders the 'Forwarded from {name}' chip when forwardedFromName is set", () => {
    render(
      <ChatWindow
        messages={[makeMessage({ id: "fw1", text: "passed along", forwardedFromName: "Анна" })]}
      />,
      { wrapper }
    )
    expect(screen.getByText('messenger:forwardedFrom|{"name":"Анна"}')).toBeTruthy()
  })

  it("does NOT render the forwarded chip when forwardedFromName is absent", () => {
    render(<ChatWindow messages={[makeMessage({ id: "fw2", text: "normal" })]} />, { wrapper })
    expect(screen.queryByText(/^messenger:forwardedFrom/)).toBeFalsy()
  })
})

describe("ChatWindow — reply/quote chip (W207)", () => {
  it("renders the quoted preview with sender name + snippet for a non-mine quote", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "q1",
            text: "answer",
            replyTo: {
              id: "src",
              senderName: "Bob",
              isMe: false,
              text: "original question",
              deletedAt: null,
            },
          }),
        ]}
      />,
      { wrapper }
    )
    expect(screen.getByText("Bob")).toBeTruthy()
    expect(screen.getByText("original question")).toBeTruthy()
  })

  it("renders 'You' as the author when the quoted message isMe", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "q2",
            text: "reply to my own",
            replyTo: { id: "src", senderName: "Me", isMe: true, text: "self", deletedAt: null },
          }),
        ]}
      />,
      { wrapper }
    )
    expect(screen.getByText("messenger:replyTo.you")).toBeTruthy()
  })

  it("renders the unknown-sender label when the quote senderName is null", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "q3",
            text: "reply",
            replyTo: { id: "src", senderName: null, isMe: false, text: "anon", deletedAt: null },
          }),
        ]}
      />,
      { wrapper }
    )
    expect(screen.getByText("messenger:replyTo.unknownSender")).toBeTruthy()
  })

  it("renders the 'original deleted' placeholder when the quoted message was soft-deleted", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "q4",
            text: "reply",
            replyTo: {
              id: "src",
              senderName: "Bob",
              isMe: false,
              text: "gone text",
              deletedAt: "2026-05-31T10:00:00+00:00",
            },
          }),
        ]}
      />,
      { wrapper }
    )
    expect(screen.getByText("messenger:replyTo.deletedOriginal")).toBeTruthy()
    expect(screen.queryByText("gone text")).toBeFalsy()
  })
})

describe("ChatWindow — attachments (W205)", () => {
  it("renders an image attachment (sanitizable url) as an <img>", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "a1",
            text: "photo",
            attachments: [
              {
                id: "att-1",
                url: "https://example.com/pic.png",
                type: "image",
                name: "pic.png",
                size: 2048,
              },
            ],
          }),
        ]}
      />,
      { wrapper }
    )
    expect(screen.getByAltText("pic.png")).toBeTruthy()
  })

  it("renders a file attachment as a link with name + size", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "a2",
            text: "doc",
            attachments: [
              {
                id: "att-2",
                url: "https://example.com/report.pdf",
                type: "file",
                name: "report.pdf",
                size: 4096,
              },
            ],
          }),
        ]}
      />,
      { wrapper }
    )
    const link = screen.getByRole("link", { name: /report\.pdf/ })
    expect(link.getAttribute("href")).toBe("https://example.com/report.pdf")
    // size rendered as KB → 4096 / 1024 = 4.0
    expect(screen.getByText("4.0 KB")).toBeTruthy()
  })

  it("renders an image attachment with a non-sanitizable url as null (no img)", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "a3",
            text: "bad",
            attachments: [
              {
                id: "att-3",
                url: "javascript:alert(1)",
                type: "image",
                name: "evil.png",
                size: 1024,
              },
            ],
          }),
        ]}
      />,
      { wrapper }
    )
    expect(screen.queryByAltText("evil.png")).toBeFalsy()
  })
})

describe("ChatWindow — jump-to-bottom FAB (W208 SW4)", () => {
  it("shows the FAB after scrolling up past the threshold, hides it after scrolling back", () => {
    const { container } = render(
      <ChatWindow messages={[makeMessage({ id: "j1", text: "msg" })]} />,
      { wrapper }
    )
    const log = container.querySelector('[role="log"]') as HTMLDivElement
    expect(log).toBeTruthy()

    // Stub scroll metrics so distanceFromBottom > SCROLL_FAB_THRESHOLD (240).
    Object.defineProperty(log, "scrollHeight", { value: 1000, configurable: true })
    Object.defineProperty(log, "clientHeight", { value: 300, configurable: true })
    Object.defineProperty(log, "scrollTop", { value: 100, configurable: true })
    // distanceFromBottom = 1000 - 100 - 300 = 600 > 240 → FAB visible.
    act(() => {
      fireEvent.scroll(log)
    })
    expect(screen.getByRole("button", { name: "messenger:aria.jumpToLatest" })).toBeTruthy()

    // Scroll back to bottom → distanceFromBottom = 1000 - 700 - 300 = 0 → hide.
    Object.defineProperty(log, "scrollTop", { value: 700, configurable: true })
    act(() => {
      fireEvent.scroll(log)
    })
    expect(screen.queryByRole("button", { name: "messenger:aria.jumpToLatest" })).toBeFalsy()
  })

  it("clicking the FAB does not throw (scrollToIndex mocked)", () => {
    const { container } = render(
      <ChatWindow messages={[makeMessage({ id: "j2", text: "msg" })]} />,
      { wrapper }
    )
    const log = container.querySelector('[role="log"]') as HTMLDivElement
    Object.defineProperty(log, "scrollHeight", { value: 1000, configurable: true })
    Object.defineProperty(log, "clientHeight", { value: 300, configurable: true })
    Object.defineProperty(log, "scrollTop", { value: 100, configurable: true })
    act(() => {
      fireEvent.scroll(log)
    })
    const fab = screen.getByRole("button", { name: "messenger:aria.jumpToLatest" })
    expect(() => fireEvent.click(fab)).not.toThrow()
  })
})

describe("ChatWindow — reactions picker outside-click / Escape close (W206)", () => {
  it("closes the open picker on an outside mousedown", () => {
    render(
      <ChatWindow
        messages={[makeMessage({ id: "rx1", text: "react", reactions: [] })]}
        onToggleReaction={() => {}}
      />,
      { wrapper }
    )
    const pickerEmoji = 'messenger:reactions.react|{"emoji":"👍"}'
    expect(screen.queryByRole("button", { name: pickerEmoji })).toBeFalsy()
    fireEvent.click(screen.getByRole("button", { name: "messenger:reactions.add" }))
    expect(screen.getByRole("button", { name: pickerEmoji })).toBeTruthy()
    // outside mousedown closes
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole("button", { name: pickerEmoji })).toBeFalsy()
  })

  it("closes the open picker on Escape", () => {
    render(
      <ChatWindow
        messages={[makeMessage({ id: "rx2", text: "react", reactions: [] })]}
        onToggleReaction={() => {}}
      />,
      { wrapper }
    )
    const pickerEmoji = 'messenger:reactions.react|{"emoji":"👍"}'
    fireEvent.click(screen.getByRole("button", { name: "messenger:reactions.add" }))
    expect(screen.getByRole("button", { name: pickerEmoji })).toBeTruthy()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("button", { name: pickerEmoji })).toBeFalsy()
  })

  it("keeps the picker open on an inside (data-reaction-ui) mousedown", () => {
    render(
      <ChatWindow
        messages={[makeMessage({ id: "rx3", text: "react", reactions: [] })]}
        onToggleReaction={() => {}}
      />,
      { wrapper }
    )
    const pickerEmoji = 'messenger:reactions.react|{"emoji":"👍"}'
    fireEvent.click(screen.getByRole("button", { name: "messenger:reactions.add" }))
    const insideBtn = screen.getByRole("button", { name: pickerEmoji })
    // mousedown on a [data-reaction-ui] element is exempt → picker stays open
    fireEvent.mouseDown(insideBtn)
    expect(screen.getByRole("button", { name: pickerEmoji })).toBeTruthy()
  })

  it("toggles the picker closed when +react is clicked twice", () => {
    render(
      <ChatWindow
        messages={[makeMessage({ id: "rx4", text: "react", reactions: [] })]}
        onToggleReaction={() => {}}
      />,
      { wrapper }
    )
    const pickerEmoji = 'messenger:reactions.react|{"emoji":"👍"}'
    const addBtn = screen.getByRole("button", { name: "messenger:reactions.add" })
    fireEvent.click(addBtn)
    expect(screen.getByRole("button", { name: pickerEmoji })).toBeTruthy()
    fireEvent.click(addBtn)
    expect(screen.queryByRole("button", { name: pickerEmoji })).toBeFalsy()
  })
})

describe("ChatWindow — defensive motion and message-state branches", () => {
  it("renders reduced-motion error states with and without retry", () => {
    motionState.reduced = true
    const onRetry = vi.fn()
    const { rerender } = render(<ChatWindow messages={[]} isError onRetry={onRetry} />, { wrapper })

    fireEvent.click(screen.getByRole("button", { name: "messenger:error.retry" }))
    expect(onRetry).toHaveBeenCalledOnce()

    rerender(<ChatWindow messages={[]} isError />)
    expect(screen.queryByRole("button", { name: "messenger:error.retry" })).toBeFalsy()
  })

  it("renders reduced-motion empty and search-empty states with clear callback", () => {
    motionState.reduced = true
    const onClearSearch = vi.fn()
    const { rerender } = render(<ChatWindow messages={[]} />, { wrapper })
    expect(screen.getByText("messenger:noMessages.title")).toBeTruthy()

    rerender(
      <ChatWindow
        messages={[makeMessage({ id: "search-edge", text: "visible" })]}
        searchQuery="missing"
        onClearSearch={onClearSearch}
      />
    )
    const clear = screen.getByRole("button", {
      name: "messenger:noMessages.searchEmpty.clearSearch",
    })
    fireEvent.click(clear)
    expect(onClearSearch).toHaveBeenCalledOnce()
  })

  it("opens safe image attachments and covers sent reply, forward, reaction, and seen states", () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null)
    const onToggleReaction = vi.fn()
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "edge-message",
            text: "reply body",
            isMe: true,
            forwardedFromName: "Alice",
            editedAt: "2026-07-31T10:00:00Z",
            replyTo: {
              id: "quoted",
              senderName: "Alice",
              isMe: true,
              text: "deleted body",
              deletedAt: "2026-07-31T09:00:00Z",
            },
            attachments: [
              {
                id: "image-edge",
                url: "https://example.com/photo.png",
                type: "image",
                name: "photo.png",
                size: 1024,
              },
            ],
            reactions: [],
            seenByCount: 2,
            seenByTotal: 3,
          }),
        ]}
        onToggleReaction={onToggleReaction}
      />,
      { wrapper }
    )

    fireEvent.click(screen.getByAltText("photo.png"))
    expect(openSpy).toHaveBeenCalledWith(
      "https://example.com/photo.png",
      "_blank",
      "noopener,noreferrer"
    )
    expect(screen.getByText('messenger:seenByGroup|{"count":2,"total":3}')).toBeTruthy()
    expect(screen.getByText('messenger:forwardedFrom|{"name":"Alice"}')).toBeTruthy()
    expect(screen.getByText("messenger:replyTo.deletedOriginal")).toBeTruthy()

    fireEvent.click(screen.getByRole("button", { name: "messenger:reactions.add" }))
    fireEvent.click(
      screen.getByRole("button", { name: 'messenger:reactions.react|{"emoji":"👍"}' })
    )
    expect(onToggleReaction).toHaveBeenCalledWith("edge-message", "👍")
    openSpy.mockRestore()
  })

  it("covers received tombstones, inline editors, edited labels, and attachment fallbacks", () => {
    const { rerender } = render(
      <ChatWindow
        messages={[makeMessage({ id: "received-deleted", text: "gone", deletedAt: "2026-07-31" })]}
      />,
      { wrapper }
    )
    expect(screen.getByText("messenger:messageDeleted")).toBeTruthy()

    rerender(
      <ChatWindow
        messages={[makeMessage({ id: "received-edit", text: "draft target" })]}
        editingMessageId="received-edit"
        editingMessageContent="draft"
      />
    )
    expect(screen.getByRole("textbox")).toHaveValue("draft")

    rerender(
      <ChatWindow
        messages={[makeMessage({ id: "received-edited", text: "updated", editedAt: "2026-07-31" })]}
      />
    )
    expect(screen.getByText("messenger:edited")).toBeTruthy()

    rerender(
      <ChatWindow
        messages={[
          makeMessage({
            id: "sent-file",
            text: "file",
            isMe: true,
            attachments: [
              {
                id: "file-1",
                url: "https://example.com/file.pdf",
                type: "file",
                name: "file.pdf",
                size: 2048,
              },
            ],
          }),
        ]}
      />
    )
    expect(screen.getByRole("link", { name: /file\.pdf/ })).toBeTruthy()

    rerender(
      <ChatWindow
        messages={[
          makeMessage({
            id: "bad-file",
            text: "bad file",
            attachments: [
              {
                id: "file-2",
                url: "javascript:alert(1)",
                type: "file",
                name: "bad.pdf",
                size: 2048,
              },
            ],
          }),
        ]}
      />
    )
    expect(screen.queryByRole("link", { name: /bad\.pdf/ })).toBeFalsy()
  })

  it("animates appended rows and renders the zero-count group-read branch", () => {
    const first = makeMessage({ id: "append-1", text: "first", senderAvatar: "avatar-1" })
    const second = makeMessage({
      id: "append-2",
      text: "second",
      senderName: "",
      senderAvatar: "avatar-2",
      isMe: true,
      seenByCount: 0,
      seenByTotal: 3,
    })
    const { rerender } = render(<ChatWindow messages={[first]} />, { wrapper })

    act(() => rerender(<ChatWindow messages={[first, second]} />))

    expect(screen.getAllByAltText("Alice")).toHaveLength(1)
    expect(screen.queryByText(/^messenger:seenByGroup/)).toBeFalsy()
  })

  it("uses reduced-motion transitions on the jump-to-latest FAB", () => {
    motionState.reduced = true
    const { container } = render(
      <ChatWindow messages={[makeMessage({ id: "reduced-jump", text: "msg" })]} />,
      { wrapper }
    )
    const log = container.querySelector('[role="log"]') as HTMLDivElement
    Object.defineProperty(log, "scrollHeight", { value: 1000, configurable: true })
    Object.defineProperty(log, "clientHeight", { value: 300, configurable: true })
    Object.defineProperty(log, "scrollTop", { value: 100, configurable: true })
    fireEvent.scroll(log)

    fireEvent.click(screen.getByRole("button", { name: "messenger:aria.jumpToLatest" }))
    expect(screen.getByRole("button", { name: "messenger:aria.jumpToLatest" })).toBeTruthy()
  })
})
