import type { ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { Message } from "@/components/messenger/types"

/**
 * This suite intentionally keeps the motion props observable.  The shared
 * framer-motion test double strips those props because most render tests only
 * care about the DOM.  ChatWindow's motion contract is part of its behaviour,
 * however: reduced-motion users must receive no entrance animation and newly
 * appended rows/FABs must retain their exact transition values.  Serialising
 * the props into data attributes gives mutation tests a deterministic oracle
 * without coupling production code to a test-only API.
 */
const motionState = vi.hoisted(() => ({ reduced: false }))
const virtualizerState = vi.hoisted(() => ({ scrollToIndex: vi.fn() }))

vi.mock("framer-motion", async () => {
  const React = await import("react")
  type MotionProps = Record<string, unknown> & { children?: ReactNode }
  const motionOnly = new Set([
    "initial",
    "animate",
    "exit",
    "transition",
    "whileHover",
    "whileTap",
    "variants",
    "layout",
  ])
  const serialise = (value: unknown) => (value === undefined ? "undefined" : JSON.stringify(value))
  const Motion = React.forwardRef<HTMLElement, MotionProps>(function Motion(
    { children, ...props },
    ref
  ) {
    const tag = (props["data-motion-tag"] as string | undefined) ?? "div"
    const cleaned: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(props)) {
      if (key === "data-motion-tag" || motionOnly.has(key)) continue
      cleaned[key] = value
    }
    const motionAttrs = {
      "data-motion-initial": serialise(props.initial),
      "data-motion-animate": serialise(props.animate),
      "data-motion-exit": serialise(props.exit),
      "data-motion-transition": serialise(props.transition),
      "data-motion-while-hover": serialise(props.whileHover),
      "data-motion-while-tap": serialise(props.whileTap),
    }
    return React.createElement(tag, { ...cleaned, ...motionAttrs, ref }, children as ReactNode)
  })
  const motion = new Proxy(
    {},
    {
      get: (_target, key) => {
        if (typeof key !== "string") return undefined
        return React.forwardRef<HTMLElement, MotionProps>(function MotionTag(props, ref) {
          return React.createElement(Motion, { ...props, ref, "data-motion-tag": key })
        })
      },
    }
  )
  return {
    m: motion,
    motion,
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  }
})

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => motionState.reduced,
}))

vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: <T,>(value: T) => value,
}))

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

vi.mock("@/components/messenger/ReactionPill", () => ({
  ReactionPill: ({ emoji, count }: { emoji: string; count: number }) => (
    <span data-testid={`reaction-${emoji}`}>
      {emoji}:{count}
    </span>
  ),
}))

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () =>
      Array.from({ length: count }, (_, index) => ({
        key: index,
        index,
        start: index * 80,
        end: (index + 1) * 80,
        size: 80,
        lane: 0,
      })),
    getTotalSize: () => count * 80,
    measureElement: () => undefined,
    scrollToIndex: virtualizerState.scrollToIndex,
  }),
}))

import { ChatWindow } from "@/components/messenger/ChatWindow"

const makeMessage = (overrides: Partial<Message> & Pick<Message, "id" | "text">): Message => {
  const { id, text, ...rest } = overrides
  return {
    id,
    text,
    senderId: "sender-1",
    senderName: "Alice",
    senderAvatar: "",
    timestamp: "12:00",
    isMe: false,
    ...rest,
  }
}

beforeEach(() => {
  motionState.reduced = false
  virtualizerState.scrollToIndex.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

const motionAttr = (element: Element, name: string) => element.getAttribute(name)

describe("ChatWindow motion and layout mutation contract", () => {
  it("keeps the error state animation, transition and retry affordance stable", () => {
    const onRetry = vi.fn()
    const { container } = render(<ChatWindow messages={[]} isError onRetry={onRetry} />)
    const alert = screen.getByRole("alert", { name: "messenger:aria.messageList" })
    const animated = alert.querySelector("[data-motion-initial]")!

    expect(motionAttr(animated, "data-motion-initial")).toBe(
      JSON.stringify({ scale: 0.92, opacity: 0, y: 8 })
    )
    expect(motionAttr(animated, "data-motion-animate")).toBe(
      JSON.stringify({ scale: 1, opacity: 1, y: 0 })
    )
    expect(motionAttr(animated, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0.45, ease: [0.22, 1, 0.36, 1] })
    )
    expect(animated).toHaveClass("flex", "w-full", "max-w-[24rem]", "flex-col", "items-center")

    const iconWrap = container.querySelector(".messenger-card-matte")!
    expect(iconWrap).toHaveStyle({ background: "var(--messenger-card-bg)" })
    expect(screen.getByText("messenger:error.failedToLoadMessages")).toBeInTheDocument()
    expect(screen.getByText("messenger:error.failedToLoadMessagesHint")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "messenger:error.retry" }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it("uses an explicit zero-duration transition for reduced-motion error state", () => {
    motionState.reduced = true
    render(<ChatWindow messages={[]} isError />)
    const alert = screen.getByRole("alert", { name: "messenger:aria.messageList" })
    const animated = alert.querySelector("[data-motion-initial]")!
    expect(motionAttr(animated, "data-motion-initial")).toBe("false")
    expect(motionAttr(animated, "data-motion-transition")).toBe(JSON.stringify({ duration: 0 }))
    expect(screen.queryByRole("button", { name: "messenger:error.retry" })).toBeNull()
  })

  it("renders six deterministic alternating loading skeletons with width geometry", () => {
    const { container } = render(<ChatWindow messages={[]} isLoading />)
    const status = screen.getByRole("status", { name: "messenger:loading.messages" })
    const rows = [...status.querySelectorAll(":scope > div > div")]
    expect(rows).toHaveLength(6)
    expect(rows.map((row) => row.className)).toEqual([
      expect.stringContaining("flex-row"),
      expect.stringContaining("flex-row-reverse"),
      expect.stringContaining("flex-row"),
      expect.stringContaining("flex-row-reverse"),
      expect.stringContaining("flex-row"),
      expect.stringContaining("flex-row-reverse"),
    ])
    const widths = [...status.querySelectorAll<HTMLElement>("[style]")]
      .map((element) => element.style.width)
      .filter(Boolean)
    expect(widths).toEqual(["45%", "58%", "71%", "49%", "62%", "75%"])
    expect(container.querySelectorAll(".messenger-skeleton")).toHaveLength(12)
  })

  it("keeps empty/search-empty cards and clear-search contract observable", () => {
    const empty = render(<ChatWindow messages={[]} />)
    const emptyAnimated = empty.container.querySelector("[data-motion-initial]")!
    expect(motionAttr(emptyAnimated, "data-motion-initial")).toBe(
      JSON.stringify({ scale: 0.92, opacity: 0, y: 8 })
    )
    expect(motionAttr(emptyAnimated, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0.45, ease: [0.22, 1, 0.36, 1] })
    )
    expect(empty.container.querySelector(".messenger-card-matte")).toHaveStyle({
      background: "var(--messenger-card-bg)",
    })
    expect(screen.getByText("messenger:noMessages.title")).toBeInTheDocument()
    empty.unmount()

    const onClearSearch = vi.fn()
    const search = render(
      <ChatWindow
        messages={[makeMessage({ id: "search-1", text: "ordinary message" })]}
        searchQuery="missing"
        onClearSearch={onClearSearch}
      />
    )
    const searchEmptyAnimated = search.container.querySelector("[data-motion-initial]")!
    expect(motionAttr(searchEmptyAnimated, "data-motion-initial")).toBe(
      JSON.stringify({ scale: 0.92, opacity: 0, y: 8 })
    )
    expect(
      screen.getByText('messenger:noMessages.searchEmpty.description|{"query":"missing"}')
    ).toBeInTheDocument()
    const clear = screen.getByRole("button", {
      name: "messenger:noMessages.searchEmpty.clearSearch",
    })
    expect(clear).toHaveClass("inline-flex", "min-h-[44px]", "rounded-full", "border")
    fireEvent.click(clear)
    expect(onClearSearch).toHaveBeenCalledTimes(1)
  })

  it("renders row animation only for appended rows and preserves all bubble geometry", () => {
    const messages = [
      makeMessage({
        id: "mine",
        text: "mine body",
        isMe: true,
        status: "read",
        timestamp: "12:01",
        showDateDivider: true,
        dateLabel: "Today",
        isGroupStart: true,
        attachments: [
          {
            id: "file",
            url: "https://example.test/file.pdf",
            type: "file",
            name: "file.pdf",
            size: 2048,
          },
        ],
      }),
      makeMessage({ id: "theirs", text: "received body", senderName: "Bob", isGroupStart: false }),
    ]
    const { container } = render(<ChatWindow messages={messages} />)
    const rowMotions = [...container.querySelectorAll("[data-motion-initial]")].filter((element) =>
      element.className.includes("items-end")
    )
    expect(rowMotions).toHaveLength(2)
    expect(rowMotions.every((row) => motionAttr(row, "data-motion-initial") === "false")).toBe(true)
    expect(container.querySelector(".absolute.top-0.left-0")?.getAttribute("style")).toContain(
      "translateY(0px)"
    )
    expect(container.querySelector(".messenger-bubble-sent")).toHaveClass(
      "rounded-2xl",
      "rounded-br-sm"
    )
    expect(container.querySelector(".messenger-bubble-received")).toHaveClass(
      "rounded-2xl",
      "rounded-bl-sm"
    )
    expect(screen.getByText("Today")).toBeInTheDocument()
    expect(screen.getByText("mine body")).toBeInTheDocument()
    expect(screen.getByText("received body")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "messenger:aria.messageRead" })).toBeInTheDocument()
    expect(screen.getByText("2.0 KB")).toBeInTheDocument()
  })

  it("observes sent and received attachment/reply/status class branches", () => {
    const messages = [
      makeMessage({
        id: "sent-rich",
        text: "sent",
        isMe: true,
        forwardedFromName: "Carol",
        replyTo: { id: "q", senderName: "Bob", isMe: false, text: "quoted", deletedAt: null },
        reactions: [{ emoji: "👍", count: 2, reactedByMe: true }],
        seenByCount: 2,
        seenByTotal: 3,
        attachments: [
          {
            id: "img",
            url: "https://example.test/image.png",
            type: "image",
            name: "image.png",
            size: 1,
          },
        ],
      }),
      makeMessage({
        id: "received-rich",
        text: "received",
        isMe: false,
        replyTo: {
          id: "deleted",
          senderName: null,
          isMe: false,
          text: "gone",
          deletedAt: "2026-01-01",
        },
        attachments: [
          { id: "unsafe", url: "javascript:alert(1)", type: "image", name: "unsafe.png", size: 1 },
        ],
      }),
    ]
    const { container } = render(
      <ChatWindow
        messages={messages}
        onToggleReaction={() => {}}
        onStartReply={() => {}}
        onForward={() => {}}
      />
    )
    expect(screen.getByText('messenger:forwardedFrom|{"name":"Carol"}')).toBeInTheDocument()
    expect(screen.getByText("quoted")).toBeInTheDocument()
    expect(screen.getByText("messenger:replyTo.unknownSender")).toBeInTheDocument()
    expect(screen.getByText('messenger:seenByGroup|{"count":2,"total":3}')).toBeInTheDocument()
    expect(screen.getByTestId("reaction-👍")).toBeInTheDocument()
    expect(screen.getByAltText("image.png")).toBeInTheDocument()
    expect(screen.queryByAltText("unsafe.png")).toBeNull()
    expect(container.querySelector(".justify-end")).toBeTruthy()
    expect(container.querySelector(".justify-start")).toBeTruthy()
    expect(screen.getAllByRole("button", { name: "messenger:reply" })).toHaveLength(2)
    expect(screen.getAllByRole("button", { name: "messenger:forward" })).toHaveLength(2)
  })

  it("preserves jump-to-latest scroll alignment and reduced-motion FAB props", () => {
    const { container, unmount } = render(
      <ChatWindow messages={[makeMessage({ id: "jump", text: "x" })]} />
    )
    const log = container.querySelector('[role="log"]') as HTMLDivElement
    Object.defineProperty(log, "scrollHeight", { value: 1000, configurable: true })
    Object.defineProperty(log, "clientHeight", { value: 300, configurable: true })
    Object.defineProperty(log, "scrollTop", { value: 0, configurable: true })
    fireEvent.scroll(log)
    const fab = screen.getByRole("button", { name: "messenger:aria.jumpToLatest" })
    expect(motionAttr(fab, "data-motion-initial")).toBe(
      JSON.stringify({ opacity: 0, scale: 0.85, y: 8 })
    )
    expect(motionAttr(fab, "data-motion-animate")).toBe(
      JSON.stringify({ opacity: 1, scale: 1, y: 0 })
    )
    expect(motionAttr(fab, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0.2, ease: [0.22, 1, 0.36, 1] })
    )
    expect(fab).toHaveClass("absolute", "bottom-4", "right-4", "size-11", "rounded-full")
    fireEvent.click(fab)
    expect(virtualizerState.scrollToIndex).toHaveBeenCalledWith(0, {
      align: "end",
      behavior: "smooth",
    })

    unmount()
    motionState.reduced = true
    const reduced = render(
      <ChatWindow messages={[makeMessage({ id: "jump-reduced", text: "x" })]} />
    )
    const reducedLog = reduced.container.querySelector('[role="log"]') as HTMLDivElement
    Object.defineProperty(reducedLog, "scrollHeight", { value: 1000, configurable: true })
    Object.defineProperty(reducedLog, "clientHeight", { value: 300, configurable: true })
    Object.defineProperty(reducedLog, "scrollTop", { value: 0, configurable: true })
    fireEvent.scroll(reducedLog)
    const reducedFab = screen.getByRole("button", { name: "messenger:aria.jumpToLatest" })
    expect(motionAttr(reducedFab, "data-motion-initial")).toBe("false")
    expect(motionAttr(reducedFab, "data-motion-while-hover")).toBe("undefined")
    expect(motionAttr(reducedFab, "data-motion-while-tap")).toBe("undefined")
  })
})
