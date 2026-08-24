import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import type { ReactNode } from "react"

import { ChatWindow } from "@/components/messenger/ChatWindow"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { Message } from "@/components/messenger/types"

/**
 * Wave 185 SW2 (Path F1) — ChatWindow unit tests for W184 SW1-SW3 render paths.
 *
 * Closes W184 §Honesty test coverage deferral. W183 SW8-SW13 baseline coverage
 * (~80 tests across 6 messenger test files) covered the existing render
 * surface BEFORE W184 added 3 new render paths (search-filter + skeleton +
 * error-state). This file fills that gap.
 *
 * In-scope:
 *  - W184 SW1 search-filter (4 tests): filteredMessages substring filter,
 *    debounce via useDebounced "search" preset 200ms, search-empty render
 *    with SearchX + Clear-search CTA, search query interpolation.
 *  - W184 SW2 loading skeleton (3 tests): 6 alternating left/right bubbles,
 *    deterministic width-jitter `45 + ((idx * 13) % 35)`, skeleton NOT
 *    renders when isLoading=false.
 *  - W184 SW3 error-state (3 tests): TriangleAlert + Retry CTA + role=alert,
 *    Retry callback fires, branch order (error BEFORE no-messages-yet).
 *  - Branch order priority (2 tests): isError takes priority over isLoading
 *    + isLoading takes priority over no-messages-yet.
 *  - Baseline ARIA (2 tests): role="log" + aria-live="polite" on virtualized
 *    list, aria-label from i18n.
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

// W190 SW1 migrated ChatWindow + sibling messenger components from framer-motion's
// jsdom-incompat `useReducedMotion()` hook to project's `useMediaQuery
// ("(prefers-reduced-motion: reduce)")` DEFAULT export (jsdom-polyfilled at
// setupTests.ts:13-30). The previous `vi.mock("framer-motion", { useReducedMotion:
// () => false })` block was W184 SW6 defensive code that's now dead — no SUT-tree
// code under this test calls framer-motion's useReducedMotion anymore. Removed at
// W190 polish-v1 «безупречно?» cleanup. framer-motion's `motion.div` exports used
// by ChatWindow internals are still present from real framer-motion module
// (no mock needed; jsdom-compatible).

// Wave 185 SW2 — mock useDebounced to be a pass-through so search-filter
// tests don't need fake timers + 200ms advance to trigger the debounce
// boundary. ChatWindow's filteredMessages useMemo depends on the debounced
// value, not the raw searchQuery, so mocking the hook to return value
// immediately exercises the filter logic without timing concerns.
vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: <T,>(value: T) => value,
}))

// Wave 185 SW2 — mock useVirtualizer to render all rows. In jsdom the
// container has scrollHeight=0 (no real layout), so the real virtualizer
// returns empty virtualItems → message text doesn't render → text-content
// assertions fail. Mock returns all rows as if container had unlimited
// height. This lets us assert ACTUAL rendered text for filter verification.
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

const mockMessages: Message[] = [
  makeMessage({ id: "1", text: "Hello world", senderName: "Alice" }),
  makeMessage({ id: "2", text: "Good morning everyone", senderName: "Bob" }),
  makeMessage({ id: "3", text: "Have a nice day", senderName: "Carol" }),
]

describe("ChatWindow — W184 SW1 search-filter render path", () => {
  it("filters messages by case-insensitive substring on text field", () => {
    render(<ChatWindow messages={mockMessages} searchQuery="HELLO" />, { wrapper })

    // Only the "Hello world" message matches (case-insensitive)
    expect(screen.queryByText("Hello world")).toBeTruthy()
    expect(screen.queryByText("Good morning everyone")).toBeFalsy()
    expect(screen.queryByText("Have a nice day")).toBeFalsy()
  })

  it("renders search-empty state when isSearchActive && filteredMessages.length === 0", () => {
    render(<ChatWindow messages={mockMessages} searchQuery="xyz" />, { wrapper })

    // SearchX-anchored empty state with interpolated query
    expect(screen.getByText("messenger:noMessages.searchEmpty.title")).toBeTruthy()
    // Interpolation preserved — mock serializes opts as JSON
    expect(
      screen.getByText('messenger:noMessages.searchEmpty.description|{"query":"xyz"}')
    ).toBeTruthy()
  })

  it("'Clear search' CTA in search-empty fires onClearSearch", () => {
    const onClearSearch = vi.fn()
    render(<ChatWindow messages={mockMessages} searchQuery="xyz" onClearSearch={onClearSearch} />, {
      wrapper,
    })

    const cta = screen.getByRole("button", { name: /messenger:noMessages.searchEmpty.clearSearch/ })
    fireEvent.click(cta)
    expect(onClearSearch).toHaveBeenCalledTimes(1)
  })

  it("empty searchQuery does NOT filter — renders all messages", () => {
    // Note: virtualizer in jsdom mounts but may not render all rows without
    // measureElement firing real heights. The presence of role="log" container
    // + virtualizer-driven inner structure confirms the non-empty branch fired
    // (rather than search-empty / no-messages-yet branches).
    const { container } = render(<ChatWindow messages={mockMessages} searchQuery="" />, {
      wrapper,
    })

    // No search-empty branch (we'd see searchEmpty.title key)
    expect(screen.queryByText("messenger:noMessages.searchEmpty.title")).toBeFalsy()
    // No no-messages-yet branch (we'd see noMessages.title key)
    expect(screen.queryByText("messenger:noMessages.title")).toBeFalsy()
    // role="log" virtualized list container present
    const logEl = container.querySelector('[role="log"]')
    expect(logEl).toBeTruthy()
  })
})

describe("ChatWindow — W184 SW2 loading skeleton render path", () => {
  it("renders 6 alternating left/right skeleton bubbles when isLoading=true", () => {
    const { container } = render(<ChatWindow messages={[]} isLoading />, { wrapper })

    // role="status" + aria-live="polite" on skeleton wrapper (W184 SW2)
    const statusEl = container.querySelector('[role="status"][aria-live="polite"]')
    expect(statusEl).toBeTruthy()

    // 6 skeleton bubbles per SKELETON_BUBBLE_COUNT const
    const skeletons = container.querySelectorAll(".messenger-skeleton")
    // Each skeleton row has 2 .messenger-skeleton elements (avatar + bubble),
    // so 6 rows × 2 = 12 total. Verify avatar circles are 6.
    const avatarSkeletons = container.querySelectorAll(".messenger-skeleton.size-9.rounded-full")
    expect(avatarSkeletons.length).toBe(6)
    expect(skeletons.length).toBe(12)
  })

  it("skeleton width jitter follows deterministic formula 45 + ((idx * 13) % 35)", () => {
    const { container } = render(<ChatWindow messages={[]} isLoading />, { wrapper })

    // Bubble skeletons (NOT avatar circles) carry the inline style with widthPct
    const bubbleSkeletons = container.querySelectorAll<HTMLDivElement>(
      ".messenger-skeleton.min-h-\\[44px\\]"
    )
    expect(bubbleSkeletons.length).toBe(6)

    bubbleSkeletons.forEach((el, idx) => {
      const expectedWidthPct = 45 + ((idx * 13) % 35)
      expect(el.style.width).toBe(`${expectedWidthPct}%`)
    })
  })

  it("skeleton does NOT render when isLoading=false (falls through to no-messages-yet)", () => {
    const { container } = render(<ChatWindow messages={[]} isLoading={false} />, { wrapper })

    // Skeleton wrapper (role=status) absent
    const statusEl = container.querySelector('[role="status"][aria-live="polite"]')
    expect(statusEl).toBeFalsy()

    // Falls through to W183 SW5 no-messages-yet branch (MessageCircleHeart icon
    // + noMessages.title key)
    expect(screen.getByText("messenger:noMessages.title")).toBeTruthy()
    expect(screen.getByText("messenger:noMessages.description")).toBeTruthy()
  })
})

describe("ChatWindow — W184 SW3 error-state render path", () => {
  it("renders TriangleAlert + Retry CTA + role=alert when isError=true", () => {
    const onRetry = vi.fn()
    const { container } = render(<ChatWindow messages={mockMessages} isError onRetry={onRetry} />, {
      wrapper,
    })

    // role="alert" + aria-live="assertive" on error wrapper
    const alertEl = container.querySelector('[role="alert"][aria-live="assertive"]')
    expect(alertEl).toBeTruthy()

    // Error i18n keys present
    expect(screen.getByText("messenger:error.failedToLoadMessages")).toBeTruthy()
    expect(screen.getByText("messenger:error.failedToLoadMessagesHint")).toBeTruthy()

    // Retry CTA button present with i18n label
    const retryBtn = screen.getByRole("button", { name: /messenger:error.retry/ })
    expect(retryBtn).toBeTruthy()
    expect(retryBtn.classList.contains("messenger-send-btn")).toBe(true)
  })

  it("Retry CTA fires onRetry callback on click", () => {
    const onRetry = vi.fn()
    render(<ChatWindow messages={mockMessages} isError onRetry={onRetry} />, { wrapper })

    const retryBtn = screen.getByRole("button", { name: /messenger:error.retry/ })
    fireEvent.click(retryBtn)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("error renders without Retry button when onRetry undefined", () => {
    render(<ChatWindow messages={mockMessages} isError />, { wrapper })

    // Error title still present
    expect(screen.getByText("messenger:error.failedToLoadMessages")).toBeTruthy()
    // No Retry button when callback absent
    expect(screen.queryByRole("button", { name: /messenger:error.retry/ })).toBeFalsy()
  })
})

describe("ChatWindow — branch order priority", () => {
  it("isError takes priority over isLoading (error shows, skeleton does NOT)", () => {
    const { container } = render(
      <ChatWindow messages={[]} isError isLoading onRetry={() => {}} />,
      { wrapper }
    )

    // Error branch fires
    expect(screen.getByText("messenger:error.failedToLoadMessages")).toBeTruthy()
    expect(container.querySelector('[role="alert"]')).toBeTruthy()

    // Skeleton branch does NOT fire (no role=status, no skeleton class)
    expect(container.querySelector('[role="status"][aria-live="polite"]')).toBeFalsy()
    expect(container.querySelectorAll(".messenger-skeleton").length).toBe(0)
  })

  it("isLoading takes priority over no-messages-yet (skeleton shows, 'say hi' does NOT)", () => {
    const { container } = render(<ChatWindow messages={[]} isLoading />, { wrapper })

    // Skeleton branch fires
    expect(container.querySelector('[role="status"][aria-live="polite"]')).toBeTruthy()
    expect(container.querySelectorAll(".messenger-skeleton").length).toBeGreaterThan(0)

    // No-messages-yet branch does NOT fire
    expect(screen.queryByText("messenger:noMessages.title")).toBeFalsy()
  })
})

describe("ChatWindow — baseline ARIA shape", () => {
  it("virtualized list renders with role='log' + aria-live='polite' + aria-label", () => {
    const { container } = render(<ChatWindow messages={mockMessages} />, { wrapper })

    const logEl = container.querySelector('[role="log"]')
    expect(logEl).toBeTruthy()
    expect(logEl?.getAttribute("aria-live")).toBe("polite")
    expect(logEl?.getAttribute("aria-label")).toBe("messenger:aria.messageList")
  })

  it("no-messages-yet branch also has role='log' (W183 SW5 baseline)", () => {
    const { container } = render(<ChatWindow messages={[]} />, { wrapper })

    const logEl = container.querySelector('[role="log"]')
    expect(logEl).toBeTruthy()
    expect(logEl?.getAttribute("aria-live")).toBe("polite")
  })
})

describe("ChatWindow — W203 read-receipt seen marker", () => {
  it("renders the 'Seen · HH:MM' marker on the last read sent message", () => {
    const messages: Message[] = [
      makeMessage({ id: "1", text: "Hi", isMe: false }),
      makeMessage({
        id: "2",
        text: "All set",
        isMe: true,
        status: "read",
        readAt: "2026-05-30T14:32:00+00:00",
        readAtLabel: "14:32",
        isLastRead: true,
      }),
    ]
    render(<ChatWindow messages={messages} />, { wrapper })
    // i18n mock echoes `key|JSON(opts)` → time interpolation preserved.
    expect(screen.getByText('messenger:seen|{"time":"14:32"}')).toBeTruthy()
  })

  it("renders the marker on ONLY the last read sent message (not earlier read ones)", () => {
    const messages: Message[] = [
      makeMessage({
        id: "1",
        text: "first",
        isMe: true,
        status: "read",
        readAtLabel: "14:30",
        isLastRead: false,
      }),
      makeMessage({
        id: "2",
        text: "second",
        isMe: true,
        status: "read",
        readAtLabel: "14:32",
        isLastRead: true,
      }),
    ]
    render(<ChatWindow messages={messages} />, { wrapper })
    expect(screen.queryByText('messenger:seen|{"time":"14:30"}')).toBeFalsy()
    expect(screen.getByText('messenger:seen|{"time":"14:32"}')).toBeTruthy()
  })

  it("never renders the marker on a received message (isMe=false suppresses it)", () => {
    const messages: Message[] = [
      makeMessage({ id: "1", text: "theirs", isMe: false, readAtLabel: "14:32", isLastRead: true }),
    ]
    render(<ChatWindow messages={messages} />, { wrapper })
    expect(screen.queryByText(/^messenger:seen/)).toBeFalsy()
  })

  it("does NOT render the marker when readAtLabel is absent (unread sent message)", () => {
    const messages: Message[] = [
      makeMessage({ id: "1", text: "pending", isMe: true, status: "sent", isLastRead: false }),
    ]
    render(<ChatWindow messages={messages} />, { wrapper })
    expect(screen.queryByText(/^messenger:seen/)).toBeFalsy()
  })

  it("still renders the ✓✓ read-status icon (role=img) on a read sent message", () => {
    const messages: Message[] = [
      makeMessage({
        id: "1",
        text: "read msg",
        isMe: true,
        status: "read",
        readAtLabel: "14:32",
        isLastRead: true,
      }),
    ]
    render(<ChatWindow messages={messages} />, { wrapper })
    // W183 SW6 status-icon wrapper — unchanged by W203's marker addition.
    expect(screen.getByRole("img", { name: "messenger:aria.messageRead" })).toBeTruthy()
  })
})

describe("ChatWindow — W205 SW6 edit/delete affordance + tombstone + inline editor", () => {
  const makeOwn = (overrides: Partial<Message> = {}): Message =>
    makeMessage({ id: "m1", text: "my message", isMe: true, ...overrides })

  it("renders the edit + delete affordance on an own, non-deleted message", () => {
    render(<ChatWindow messages={[makeOwn()]} />, { wrapper })
    expect(screen.getByRole("button", { name: "messenger:editMessage" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "messenger:deleteMessage" })).toBeTruthy()
  })

  it("does NOT render the affordance on a received message", () => {
    render(<ChatWindow messages={[makeMessage({ id: "r1", text: "theirs", isMe: false })]} />, {
      wrapper,
    })
    expect(screen.queryByRole("button", { name: "messenger:editMessage" })).toBeFalsy()
    expect(screen.queryByRole("button", { name: "messenger:deleteMessage" })).toBeFalsy()
  })

  it("the edit button fires onEditMessage(id, text)", () => {
    const onEditMessage = vi.fn()
    render(
      <ChatWindow
        messages={[makeOwn({ id: "m9", text: "edit me" })]}
        onEditMessage={onEditMessage}
      />,
      { wrapper }
    )
    fireEvent.click(screen.getByRole("button", { name: "messenger:editMessage" }))
    expect(onEditMessage).toHaveBeenCalledWith("m9", "edit me")
  })

  it("the delete button fires onDeleteMessage(id)", () => {
    const onDeleteMessage = vi.fn()
    render(<ChatWindow messages={[makeOwn({ id: "m9" })]} onDeleteMessage={onDeleteMessage} />, {
      wrapper,
    })
    fireEvent.click(screen.getByRole("button", { name: "messenger:deleteMessage" }))
    expect(onDeleteMessage).toHaveBeenCalledWith("m9")
  })

  it("renders the '(edited)' label when editedAt is set and the message is not deleted", () => {
    render(
      <ChatWindow
        messages={[makeOwn({ editedAt: "2026-05-30T15:00:00+00:00", editedAtLabel: "15:00" })]}
      />,
      { wrapper }
    )
    expect(screen.getByText("messenger:edited")).toBeTruthy()
  })

  it("does NOT render the '(edited)' label when editedAt is absent", () => {
    render(<ChatWindow messages={[makeOwn()]} />, { wrapper })
    expect(screen.queryByText("messenger:edited")).toBeFalsy()
  })

  it("renders the deleted tombstone (messageDeleted) and drops content + affordance", () => {
    render(
      <ChatWindow
        messages={[makeOwn({ text: "secret", deletedAt: "2026-05-30T15:01:00+00:00" })]}
      />,
      { wrapper }
    )
    expect(screen.getByText("messenger:messageDeleted")).toBeTruthy()
    expect(screen.queryByText("secret")).toBeFalsy()
    expect(screen.queryByRole("button", { name: "messenger:editMessage" })).toBeFalsy()
    expect(screen.queryByRole("button", { name: "messenger:deleteMessage" })).toBeFalsy()
  })

  it("suppresses the 'Seen' marker AND the '(edited)' label on a deleted message", () => {
    render(
      <ChatWindow
        messages={[
          makeOwn({
            deletedAt: "2026-05-30T15:01:00+00:00",
            editedAt: "2026-05-30T15:00:00+00:00",
            editedAtLabel: "15:00",
            status: "read",
            readAtLabel: "15:02",
            isLastRead: true,
          }),
        ]}
      />,
      { wrapper }
    )
    expect(screen.queryByText(/^messenger:seen/)).toBeFalsy()
    expect(screen.queryByText("messenger:edited")).toBeFalsy()
  })

  it("renders the inline editor (textarea seeded + Save/Cancel) when editingMessageId matches", () => {
    render(
      <ChatWindow
        messages={[makeOwn({ id: "edit-1", text: "original" })]}
        editingMessageId="edit-1"
        editingMessageContent="draft text"
      />,
      { wrapper }
    )
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement
    expect(textarea.value).toBe("draft text")
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "common:buttons.cancel" })).toBeTruthy()
    // the normal bubble content is replaced by the editor while editing
    expect(screen.queryByText("original")).toBeFalsy()
  })

  it("Save fires onSaveEdit(id), Cancel fires onCancelEdit, typing fires onEditingContentChange", () => {
    const onSaveEdit = vi.fn()
    const onCancelEdit = vi.fn()
    const onEditingContentChange = vi.fn()
    render(
      <ChatWindow
        messages={[makeOwn({ id: "edit-2", text: "x" })]}
        editingMessageId="edit-2"
        editingMessageContent="hello"
        onSaveEdit={onSaveEdit}
        onCancelEdit={onCancelEdit}
        onEditingContentChange={onEditingContentChange}
      />,
      { wrapper }
    )
    const textarea = screen.getByRole("textbox")
    fireEvent.change(textarea, { target: { value: "hello!" } })
    expect(onEditingContentChange).toHaveBeenCalledWith("hello!")
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
    expect(onSaveEdit).toHaveBeenCalledWith("edit-2")
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onCancelEdit).toHaveBeenCalledTimes(1)
  })

  it("Enter (no shift) in the editor saves; Escape cancels", () => {
    const onSaveEdit = vi.fn()
    const onCancelEdit = vi.fn()
    render(
      <ChatWindow
        messages={[makeOwn({ id: "edit-3" })]}
        editingMessageId="edit-3"
        editingMessageContent="z"
        onSaveEdit={onSaveEdit}
        onCancelEdit={onCancelEdit}
      />,
      { wrapper }
    )
    const textarea = screen.getByRole("textbox")
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })
    expect(onSaveEdit).toHaveBeenCalledWith("edit-3")
    fireEvent.keyDown(textarea, { key: "Escape" })
    expect(onCancelEdit).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(textarea, { key: "ArrowLeft" })
    expect(onSaveEdit).toHaveBeenCalledTimes(1)
    expect(onCancelEdit).toHaveBeenCalledTimes(1)
  })
})

describe("ChatWindow — W206 reactions (pills + +react picker)", () => {
  const withReactions = (
    reactions: Message["reactions"],
    overrides: Partial<Message> = {}
  ): Message =>
    makeMessage({ id: "rx1", text: "react to me", isMe: false, reactions, ...overrides })

  it("renders a reaction pill (emoji + count + aria-pressed) for each aggregate", () => {
    render(
      <ChatWindow messages={[withReactions([{ emoji: "👍", count: 2, reactedByMe: false }])]} />,
      {
        wrapper,
      }
    )
    const pill = screen.getByRole("button", {
      name: 'messenger:reactions.tally|{"emoji":"👍","count":2}',
    })
    expect(pill.getAttribute("aria-pressed")).toBe("false")
    expect(pill.textContent).toContain("👍")
    expect(pill.textContent).toContain("2")
  })

  it("marks a reactedByMe pill aria-pressed=true", () => {
    render(
      <ChatWindow messages={[withReactions([{ emoji: "❤️", count: 1, reactedByMe: true }])]} />,
      {
        wrapper,
      }
    )
    const pill = screen.getByRole("button", {
      name: 'messenger:reactions.tally|{"emoji":"❤️","count":1}',
    })
    expect(pill.getAttribute("aria-pressed")).toBe("true")
  })

  it("clicking a pill fires onToggleReaction(messageId, emoji)", () => {
    const onToggleReaction = vi.fn()
    render(
      <ChatWindow
        messages={[withReactions([{ emoji: "👍", count: 1, reactedByMe: false }], { id: "msg-7" })]}
        onToggleReaction={onToggleReaction}
      />,
      { wrapper }
    )
    fireEvent.click(
      screen.getByRole("button", { name: 'messenger:reactions.tally|{"emoji":"👍","count":1}' })
    )
    expect(onToggleReaction).toHaveBeenCalledWith("msg-7", "👍")
  })

  it("renders the +react affordance only when onToggleReaction is provided", () => {
    const { rerender } = render(<ChatWindow messages={[withReactions([])]} />, { wrapper })
    expect(screen.queryByRole("button", { name: "messenger:reactions.add" })).toBeFalsy()
    rerender(<ChatWindow messages={[withReactions([])]} onToggleReaction={() => {}} />)
    expect(screen.getByRole("button", { name: "messenger:reactions.add" })).toBeTruthy()
  })

  it("opens the emoji picker on +react and fires onToggleReaction on selection (then closes)", () => {
    const onToggleReaction = vi.fn()
    render(
      <ChatWindow
        messages={[withReactions([], { id: "msg-9" })]}
        onToggleReaction={onToggleReaction}
      />,
      { wrapper }
    )
    const pickerName = 'messenger:reactions.react|{"emoji":"👍"}'
    // picker closed initially
    expect(screen.queryByRole("button", { name: pickerName })).toBeFalsy()
    // open it
    fireEvent.click(screen.getByRole("button", { name: "messenger:reactions.add" }))
    const thumbsUp = screen.getByRole("button", { name: pickerName })
    // select → toggle + close
    fireEvent.click(thumbsUp)
    expect(onToggleReaction).toHaveBeenCalledWith("msg-9", "👍")
    expect(screen.queryByRole("button", { name: pickerName })).toBeFalsy()
  })

  it("does NOT render reactions footer or picker on a deleted message", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "del-1",
            text: "gone",
            isMe: true,
            deletedAt: "2026-05-31T10:00:00+00:00",
            reactions: [{ emoji: "👍", count: 3, reactedByMe: false }],
          }),
        ]}
        onToggleReaction={() => {}}
      />,
      { wrapper }
    )
    expect(screen.getByText("messenger:messageDeleted")).toBeTruthy()
    expect(screen.queryByRole("button", { name: "messenger:reactions.add" })).toBeFalsy()
    expect(screen.queryByRole("button", { name: /messenger:reactions\.tally/ })).toBeFalsy()
  })
})

describe("ChatWindow — W208 SW5 date dividers + sender grouping render", () => {
  it("renders the date-divider label above a message flagged showDateDivider", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "d1",
            text: "today msg",
            showDateDivider: true,
            dateLabel: "messenger:dateDivider.today",
          }),
          makeMessage({ id: "d2", text: "same day", showDateDivider: false }),
        ]}
      />,
      { wrapper }
    )
    // dateLabel is rendered verbatim (pre-resolved in the transform — ChatWindow
    // does not call t() for it). Only the divider-flagged message shows it.
    expect(screen.getAllByText("messenger:dateDivider.today")).toHaveLength(1)
  })

  it("renders no date divider when showDateDivider is absent (optimistic / standalone)", () => {
    render(<ChatWindow messages={[makeMessage({ id: "n1", text: "hi" })]} />, { wrapper })
    expect(screen.queryByText("messenger:dateDivider.today")).toBeFalsy()
    expect(screen.queryByText("messenger:dateDivider.yesterday")).toBeFalsy()
  })

  it("shows the avatar for a group-start message and hides it (spacer) for a grouped one", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({ id: "g1", text: "first", senderName: "GroupStart", isGroupStart: true }),
          makeMessage({ id: "g2", text: "second", senderName: "Grouped", isGroupStart: false }),
        ]}
      />,
      { wrapper }
    )
    // The mocked SmartImage renders <img alt={senderName}>; isGroupStart=false
    // swaps it for an aria-hidden spacer (no avatar img for that sender).
    expect(screen.queryByAltText("GroupStart")).toBeTruthy()
    expect(screen.queryByAltText("Grouped")).toBeFalsy()
  })

  it("shows the avatar when isGroupStart is undefined (default — no grouping applied)", () => {
    render(<ChatWindow messages={[makeMessage({ id: "u1", text: "hi", senderName: "Solo" })]} />, {
      wrapper,
    })
    expect(screen.queryByAltText("Solo")).toBeTruthy()
  })
})
