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
  ReactionPill: ({
    emoji,
    count,
    onToggle,
  }: {
    emoji: string
    count: number
    onToggle?: (value: string) => void
  }) => (
    <button type="button" data-testid={`reaction-${emoji}`} onClick={() => onToggle?.(emoji)}>
      {emoji}:{count}
    </button>
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

import {
  ChatWindow,
  getMessageEntranceMotion,
  getMessageSkeletonKey,
  shouldAnimateMessageEntrance,
} from "@/components/messenger/ChatWindow"

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

  it("keeps error icon semantics and retry motion affordance exact", () => {
    const { container } = render(<ChatWindow messages={[]} isError onRetry={() => {}} />)
    const alert = screen.getByRole("alert", { name: "messenger:aria.messageList" })
    const icon = alert.querySelector(".messenger-card-matte svg")!
    expect(icon).toHaveClass("size-8", "text-(--color-violet-500)")
    expect(icon).toHaveStyle({ opacity: "var(--opacity-strong)" })
    expect(icon).toHaveAttribute("aria-hidden", "true")

    const retry = screen.getByRole("button", { name: "messenger:error.retry" })
    expect(retry).toHaveClass(
      "messenger-send-btn",
      "inline-flex",
      "min-h-[44px]",
      "items-center",
      "gap-2",
      "rounded-full",
      "px-5"
    )
    expect(motionAttr(retry, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.04 }))
    expect(motionAttr(retry, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.96 }))
    expect(retry.querySelector("svg")).toHaveClass("size-4")
    expect(retry.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(container.querySelector('[role="alert"]')).toHaveAttribute("aria-live", "assertive")
  })

  it("renders six deterministic alternating loading skeletons with width geometry", () => {
    const { container } = render(<ChatWindow messages={[]} isLoading />)
    const status = screen.getByRole("status", { name: "messenger:loading.messages" })
    const rows = [...status.querySelectorAll(":scope > div > div")]
    expect(rows).toHaveLength(6)
    rows.forEach((row, index) => {
      const isMine = index % 2 === 1
      expect(row.classList.contains("flex-row-reverse")).toBe(isMine)
      expect(row.classList.contains("flex-row")).toBe(!isMine)
      expect(row.classList.contains("items-end")).toBe(true)
      expect(row.classList.contains("gap-2")).toBe(true)
      expect(row.classList.contains("md:gap-3")).toBe(true)
      expect(row.classList.contains("flex-row") && row.classList.contains("flex-row-reverse")).toBe(
        false
      )
    })
    const widths = [...status.querySelectorAll<HTMLElement>("[style]")]
      .map((element) => element.style.width)
      .filter(Boolean)
    expect(widths).toEqual(["45%", "58%", "71%", "49%", "62%", "75%"])
    expect(container.querySelectorAll(".messenger-skeleton")).toHaveLength(12)
  })

  it("keeps skeleton bubble corner geometry aligned with each side", () => {
    const { container } = render(<ChatWindow messages={[]} isLoading />)
    const status = screen.getByRole("status", { name: "messenger:loading.messages" })
    const rows = [...status.querySelectorAll<HTMLElement>(":scope > div > div")]
    rows.forEach((row, index) => {
      const bubble = row.querySelector<HTMLElement>(".messenger-skeleton.min-h-\\[44px\\]")!
      expect(row).toHaveAttribute("aria-hidden", "true")
      if (index % 2 === 1) {
        expect(bubble).toHaveClass("rounded-br-sm", "md:rounded-br-2xl", "md:rounded-bl-sm")
        expect(bubble).not.toHaveClass("rounded-bl-sm")
      } else {
        expect(bubble).toHaveClass("rounded-bl-sm")
        expect(bubble).not.toHaveClass("rounded-br-sm", "md:rounded-bl-sm")
      }
    })
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(6)
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

  it("keeps empty and search-empty card icons, typography and motion affordances exact", () => {
    const empty = render(<ChatWindow messages={[]} />)
    const emptyCard = empty.container.querySelector(".messenger-card-matte")!
    const emptyAnimated = emptyCard.parentElement!
    expect(emptyAnimated).toHaveClass("flex", "w-full", "max-w-[24rem]", "flex-col", "items-center")
    expect(emptyAnimated.querySelector("svg")).toHaveClass("size-8", "text-(--color-violet-500)")
    expect(emptyAnimated.querySelector("svg")).toHaveStyle({ opacity: "var(--opacity-strong)" })
    expect(emptyAnimated.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
    expect(emptyCard).toHaveClass("mb-5", "flex", "size-16", "items-center", "justify-center")
    expect(emptyCard).toHaveStyle({ background: "var(--messenger-card-bg)" })
    expect(motionAttr(emptyAnimated, "data-motion-animate")).toBe(
      JSON.stringify({ scale: 1, opacity: 1, y: 0 })
    )
    expect(empty.container.querySelector("h3")).toHaveClass(
      "sf-pro",
      "mb-2",
      "text-base",
      "font-bold",
      "leading-tight",
      "text-(--text-primary)"
    )
    expect(empty.container.querySelector("p")).toHaveClass(
      "text-sm",
      "leading-relaxed",
      "text-(--text-secondary)"
    )
    empty.unmount()

    const onClearSearch = vi.fn()
    const search = render(
      <ChatWindow
        messages={[makeMessage({ id: "search-style", text: "ordinary" })]}
        searchQuery="absent"
        onClearSearch={onClearSearch}
      />
    )
    const searchCard = search.container.querySelector(".messenger-card-matte")!
    const searchAnimated = searchCard.parentElement!
    expect(searchAnimated.querySelector("svg")).toHaveClass("size-8", "text-(--color-violet-500)")
    expect(searchAnimated.querySelector("svg")).toHaveStyle({ opacity: "var(--opacity-strong)" })
    expect(searchCard).toHaveClass("mb-5", "flex", "size-16", "items-center", "justify-center")
    const clear = screen.getByRole("button", {
      name: "messenger:noMessages.searchEmpty.clearSearch",
    })
    expect(motionAttr(clear, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.04 }))
    expect(motionAttr(clear, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.96 }))
    expect(clear).toHaveClass(
      "inline-flex",
      "min-h-[44px]",
      "items-center",
      "gap-2",
      "rounded-full",
      "border",
      "px-5"
    )
    expect(clear.querySelector("svg")).toHaveClass("size-4")
    expect(clear.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
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

  it("keeps the virtualizer canvas geometry and row transforms deterministic", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({ id: "virtual-0", text: "first" }),
          makeMessage({ id: "virtual-1", text: "second" }),
          makeMessage({ id: "virtual-2", text: "third" }),
        ]}
      />
    )

    const log = container.querySelector('[role="log"]')!
    const canvas = log.firstElementChild as HTMLElement
    expect(canvas).toHaveStyle({ height: "240px", width: "100%", position: "relative" })
    const rows = [...canvas.querySelectorAll<HTMLElement>(":scope > [data-index]")]
    expect(rows).toHaveLength(3)
    rows.forEach((row, index) => {
      expect(row).toHaveClass("absolute", "top-0", "left-0", "w-full")
      expect(row).toHaveAttribute("data-index", String(index))
      expect(row.style.transform).toBe(`translateY(${index * 80}px)`)
    })
  })

  it("suppresses row entrance motion for reduced motion and active search", () => {
    const first = makeMessage({ id: "append-0", text: "first" })
    const second = makeMessage({ id: "append-1", text: "second" })
    const { container, rerender } = render(<ChatWindow messages={[first]} />)

    motionState.reduced = true
    rerender(<ChatWindow messages={[first, second]} />)
    expect(
      [...container.querySelectorAll<HTMLElement>("[data-index]")].map((row) =>
        row.querySelector<HTMLElement>(".group")?.getAttribute("data-motion-initial")
      )
    ).toEqual(["false", "false"])

    motionState.reduced = false
    rerender(<ChatWindow messages={[first, second]} searchQuery="second" />)
    expect(container.querySelector('[data-index="0"] .group')).toHaveAttribute(
      "data-motion-initial",
      "false"
    )
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

  it("does not reserve an attachment or reaction footer for empty arrays", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "empty-arrays",
            text: "plain",
            attachments: [],
            reactions: [],
          }),
        ]}
      />
    )

    const row = container.querySelector('[data-index="0"]')!
    expect(row.querySelector(".mb-2.space-y-2")).toBeNull()
    expect(row.querySelector(".flex.flex-wrap.items-center.gap-1")).toBeNull()
  })

  it("keeps sent and received attachment surfaces and reply previews theme-aware", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "sent-attachment",
            text: "sent attachment",
            isMe: true,
            attachments: [
              {
                id: "sent-file",
                url: "https://example.test/sent.pdf",
                type: "file",
                name: "sent.pdf",
                size: 1024,
              },
            ],
            replyTo: {
              id: "sent-reply",
              senderName: "Bob",
              isMe: false,
              text: "quoted sent",
              deletedAt: null,
            },
          }),
          makeMessage({
            id: "received-attachment",
            text: "received attachment",
            attachments: [
              {
                id: "received-file",
                url: "https://example.test/received.pdf",
                type: "file",
                name: "received.pdf",
                size: 2048,
              },
            ],
            replyTo: {
              id: "deleted-reply",
              senderName: "Carol",
              isMe: false,
              text: "quoted deleted",
              deletedAt: "2026-01-01",
            },
          }),
        ]}
      />
    )

    const sentLink = container.querySelector<HTMLAnchorElement>(
      'a[href="https://example.test/sent.pdf"]'
    )!
    expect(sentLink).toHaveClass(
      "flex",
      "items-center",
      "gap-3",
      "p-3",
      "rounded-xl",
      "border",
      "border-white/(--opacity-faint)",
      "bg-(--messenger-attachment-bg)"
    )
    expect(sentLink.querySelector("div")).toHaveClass(
      "p-2",
      "rounded-lg",
      "bg-(--messenger-attachment-bg)",
      "text-[var(--text-inverse)]"
    )

    const receivedLink = container.querySelector<HTMLAnchorElement>(
      'a[href="https://example.test/received.pdf"]'
    )!
    expect(receivedLink).toHaveClass("bg-(--bg-surface-raised)/(--opacity-medium)")
    expect(receivedLink.querySelector("div")).toHaveClass(
      "p-2",
      "rounded-lg",
      "bg-(--bg-surface-raised)",
      "text-(--brand-main)"
    )

    const sentReply = screen.getByText("quoted sent").parentElement!
    expect(sentReply).toHaveClass(
      "mb-2",
      "rounded-lg",
      "border-l-2",
      "px-2.5",
      "py-1.5",
      "border-(--text-inverse)/(--opacity-medium)",
      "bg-(--text-inverse)/(--opacity-faint)"
    )
    expect(sentReply.querySelector("p")).toHaveClass("font-semibold", "text-[var(--text-inverse)]")

    const deletedReply = screen.getByText("messenger:replyTo.deletedOriginal").parentElement!
    expect(deletedReply).toHaveClass(
      "mb-2",
      "rounded-lg",
      "border-l-2",
      "px-2.5",
      "py-1.5",
      "border-(--color-violet-500)/(--opacity-medium)",
      "bg-(--color-violet-500)/(--opacity-faint)"
    )
    expect(deletedReply.querySelectorAll("p")[1]).toHaveClass("italic")
  })

  it("keeps reaction pills read-only and safe when no toggle handler is supplied", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "reaction-read-only",
            text: "reacted",
            reactions: [{ emoji: "👍", count: 1, reactedByMe: false }],
          }),
        ]}
      />
    )

    expect(() => fireEvent.click(screen.getByTestId("reaction-👍"))).not.toThrow()
  })

  it("keeps reaction footer alignment and enforces one active picker at a time", () => {
    const onToggleReaction = vi.fn()
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({ id: "reaction-received", text: "received", reactions: [] }),
          makeMessage({ id: "reaction-sent", text: "sent", isMe: true, reactions: [] }),
        ]}
        onToggleReaction={onToggleReaction}
      />
    )

    const receivedRow = container.querySelector('[data-index="0"]')!
    const sentRow = container.querySelector('[data-index="1"]')!
    const addButtons = screen.getAllByRole("button", { name: "messenger:reactions.add" })
    expect(addButtons).toHaveLength(2)
    expect(receivedRow.querySelector(".flex.flex-wrap.items-center.gap-1")).toHaveClass(
      "justify-start"
    )
    expect(sentRow.querySelector(".flex.flex-wrap.items-center.gap-1")).toHaveClass("justify-end")

    fireEvent.click(addButtons[0]!)
    let currentAddButtons = screen.getAllByRole("button", { name: "messenger:reactions.add" })
    expect(currentAddButtons[0]).toHaveAttribute("aria-expanded", "true")
    expect(currentAddButtons[1]).toHaveAttribute("aria-expanded", "false")
    const receivedPicker = container.querySelector('[role="group"]')!
    expect(receivedPicker).toHaveClass(
      "messenger-card-matte",
      "flex",
      "items-center",
      "gap-1",
      "rounded-full",
      "px-2",
      "py-1",
      "self-start"
    )
    expect(receivedPicker).toHaveAttribute("aria-label", "messenger:reactions.add")
    expect(receivedPicker.querySelectorAll("button")).toHaveLength(5)
    for (const button of receivedPicker.querySelectorAll("button")) {
      expect(button).toHaveClass(
        "-m-2",
        "inline-flex",
        "min-h-[44px]",
        "min-w-[44px]",
        "items-center",
        "justify-center",
        "rounded-full",
        "text-xl"
      )
      expect(button.getAttribute("aria-label")).toMatch(/^messenger:reactions.react\|/)
      expect(button.querySelector("span")).toHaveAttribute("aria-hidden", "true")
    }

    fireEvent.click(currentAddButtons[1]!)
    currentAddButtons = screen.getAllByRole("button", { name: "messenger:reactions.add" })
    expect(currentAddButtons[0]).toHaveAttribute("aria-expanded", "false")
    expect(currentAddButtons[1]).toHaveAttribute("aria-expanded", "true")
    expect(container.querySelector('[role="group"]')).toHaveClass("self-end")

    fireEvent.click(currentAddButtons[1]!)
    expect(screen.getAllByRole("button", { name: "messenger:reactions.add" })[1]).toHaveAttribute(
      "aria-expanded",
      "false"
    )
    expect(container.querySelector('[role="group"]')).toBeNull()
  })

  it("renders date dividers only when both the flag and a non-empty label exist", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "date-valid",
            text: "valid",
            showDateDivider: true,
            dateLabel: "Today",
          }),
          makeMessage({ id: "date-no-label", text: "no label", showDateDivider: true }),
          makeMessage({
            id: "date-flag-off",
            text: "flag off",
            showDateDivider: false,
            dateLabel: "Should not render",
          }),
        ]}
      />
    )

    expect(screen.getByText("Today")).toBeInTheDocument()
    expect(screen.queryByText("Should not render")).toBeNull()
    expect(container.querySelectorAll('[data-index="0"] .justify-center')).toHaveLength(1)
    expect(container.querySelector('[data-index="1"] .justify-center')).toBeNull()
    expect(container.querySelector('[data-index="2"] .justify-center')).toBeNull()
  })

  it("keeps grouped-row spacing and avatar spacer semantics exact", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "group-start",
            text: "first",
            senderName: "First",
            isGroupStart: true,
          }),
          makeMessage({ id: "grouped", text: "second", senderName: "Second", isGroupStart: false }),
          makeMessage({ id: "group-default", text: "third", senderName: "Third" }),
        ]}
      />
    )

    const firstRow = container.querySelector('[data-index="0"]')!
    const groupedRow = container.querySelector('[data-index="1"]')!
    const defaultRow = container.querySelector('[data-index="2"]')!
    expect(firstRow.querySelector(".group")?.classList.contains("py-1")).toBe(true)
    expect(groupedRow.querySelector(".group")?.classList.contains("py-0.5")).toBe(true)
    expect(groupedRow.querySelector('[aria-hidden="true"]')).toBeInTheDocument()
    expect(groupedRow.querySelector('img[alt="Second"]')).toBeNull()
    expect(defaultRow.querySelector('img[alt="Third"]')).toBeInTheDocument()
  })

  it("keeps sent/received row alignment and forwarded-header styling distinct", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "row-sent",
            text: "sent",
            isMe: true,
            forwardedFromName: "Alice",
          }),
          makeMessage({
            id: "row-received",
            text: "received",
            isMe: false,
            forwardedFromName: "Bob",
          }),
        ]}
      />
    )

    const sentRow = container.querySelector('[data-index="0"] .group')!
    const receivedRow = container.querySelector('[data-index="1"] .group')!
    expect(sentRow).toHaveClass("flex-row-reverse", "justify-start")
    expect(sentRow).not.toHaveClass("flex-row")
    expect(receivedRow).toHaveClass("flex-row", "justify-start")
    expect(receivedRow).not.toHaveClass("flex-row-reverse")

    const forwardedHeaders = [...container.querySelectorAll<HTMLElement>(".italic")].filter(
      (element) => element.textContent?.includes("messenger:forwardedFrom")
    )
    expect(forwardedHeaders).toHaveLength(2)
    expect(forwardedHeaders[0]).toHaveClass(
      "mb-1.5",
      "flex",
      "items-center",
      "gap-1",
      "font-semibold",
      "text-[var(--text-inverse)]",
      "opacity-medium"
    )
    expect(forwardedHeaders[1]).toHaveClass(
      "mb-1.5",
      "flex",
      "items-center",
      "gap-1",
      "font-semibold",
      "text-(--brand-main)"
    )
    expect(forwardedHeaders[0]!.querySelector("svg")).toHaveClass("size-3", "shrink-0")
    expect(forwardedHeaders[0]!.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
  })

  it("keeps tombstones and inline editors accessible without cross-branch styles", () => {
    const { container, rerender } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "tombstone",
            text: "secret",
            isMe: true,
            deletedAt: "2026-01-01",
          }),
        ]}
      />
    )
    const tombstone = container.querySelector(".messenger-bubble-received")!
    expect(tombstone).toHaveClass(
      "relative",
      "max-w-full",
      "px-4",
      "py-2.5",
      "text-base",
      "messenger-bubble-received",
      "rounded-2xl",
      "rounded-br-sm",
      "md:rounded-br-2xl",
      "md:rounded-bl-sm"
    )
    expect(tombstone.querySelector("p")).toHaveClass(
      "italic",
      "leading-relaxed",
      "text-text-secondary"
    )
    expect(tombstone.querySelector("p")).toHaveTextContent("messenger:messageDeleted")
    expect(screen.queryByText("secret")).toBeNull()

    const own = makeMessage({ id: "editor-contract", text: "draft me", isMe: true })
    rerender(
      <ChatWindow messages={[own]} editingMessageId={own.id} editingMessageContent="draft" />
    )
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement
    const label = container.querySelector(`label[for="edit-message-${own.id}"]`)
    expect(label).toBeInTheDocument()
    expect(textarea).toHaveAttribute("id", `edit-message-${own.id}`)
    expect(textarea).toHaveAttribute("rows", "2")
    expect(textarea).toHaveClass(
      "w-full",
      "resize-none",
      "rounded-lg",
      "bg-(--bg-surface)/(--opacity-medium)",
      "px-3",
      "py-2",
      "text-base",
      "leading-relaxed"
    )
    expect(label).toHaveTextContent("messenger:editMessage")
  })

  it("distinguishes read and sent status icons for own messages", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({ id: "status-read", text: "read", isMe: true, status: "read" }),
          makeMessage({ id: "status-sent", text: "sent", isMe: true, status: "sent" }),
        ]}
      />
    )

    const readStatus = screen.getByRole("img", { name: "messenger:aria.messageRead" })
    const sentStatus = screen.getByRole("img", { name: "messenger:aria.messageSent" })
    expect(readStatus.querySelector(".lucide-check-check")).toBeInTheDocument()
    expect(readStatus.querySelector(".lucide-check")).toBeNull()
    expect(sentStatus.querySelector(".lucide-check")).toBeInTheDocument()
    expect(sentStatus.querySelector(".lucide-check-check")).toBeNull()
    expect(
      container.querySelectorAll('[role="img"][aria-label^="messenger:aria.message"]').length
    ).toBe(2)
  })

  it("keeps edited labels, timestamp colors and tooltip interpolation side-aware", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "edited-own",
            text: "own edit",
            isMe: true,
            editedAt: "2026-01-01",
            editedAtLabel: "15:00",
            timestamp: "15:01",
          }),
          makeMessage({
            id: "edited-received",
            text: "received edit",
            isMe: false,
            editedAt: "2026-01-01",
            editedAtLabel: "15:02",
            timestamp: "15:03",
          }),
        ]}
      />
    )

    const ownRow = container.querySelector('[data-index="0"]')!
    const receivedRow = container.querySelector('[data-index="1"]')!
    const ownEdited = ownRow.querySelector("span.text-micro")!
    const receivedEdited = receivedRow.querySelector("span.text-micro")!
    expect(ownEdited).toHaveTextContent("messenger:edited")
    expect(ownEdited).toHaveAttribute("title", 'messenger:messageEditedAt|{"time":"15:00"}')
    expect(ownEdited).toHaveStyle({ color: "var(--primary-subtle)" })
    expect(receivedEdited).toHaveTextContent("messenger:edited")
    expect(receivedEdited).toHaveAttribute("title", 'messenger:messageEditedAt|{"time":"15:02"}')
    expect(receivedEdited).toHaveStyle({ color: "var(--text-secondary)" })

    const ownTimestamps = ownRow.querySelectorAll("span.text-micro")
    const receivedTimestamps = receivedRow.querySelectorAll("span.text-micro")
    expect([...ownTimestamps].some((element) => element.textContent === "15:01")).toBe(true)
    expect([...receivedTimestamps].some((element) => element.textContent === "15:03")).toBe(true)
    expect([...ownTimestamps].find((element) => element.textContent === "15:01")).toHaveStyle({
      color: "var(--primary-subtle)",
    })
    expect([...receivedTimestamps].find((element) => element.textContent === "15:03")).toHaveStyle({
      color: "var(--text-secondary)",
    })
  })

  it("applies seen-marker precedence for group counts, partial data and tombstones", () => {
    render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "seen-group",
            text: "group seen",
            isMe: true,
            seenByCount: 2,
            seenByTotal: 3,
            isLastRead: true,
            readAtLabel: "10:00",
          }),
          makeMessage({
            id: "seen-zero",
            text: "group zero",
            isMe: true,
            seenByCount: 0,
            seenByTotal: 3,
            isLastRead: true,
            readAtLabel: "10:01",
          }),
          makeMessage({
            id: "seen-partial-count",
            text: "partial count",
            isMe: true,
            seenByCount: 1,
            isLastRead: true,
            readAtLabel: "10:02",
          }),
          makeMessage({
            id: "seen-partial-total",
            text: "partial total",
            isMe: true,
            seenByTotal: 3,
            isLastRead: true,
            readAtLabel: "10:03",
          }),
          makeMessage({
            id: "seen-deleted",
            text: "deleted",
            isMe: true,
            deletedAt: "2026-01-01",
            seenByCount: 2,
            seenByTotal: 3,
            isLastRead: true,
            readAtLabel: "10:04",
          }),
          makeMessage({
            id: "seen-received",
            text: "received",
            isMe: false,
            seenByCount: 2,
            seenByTotal: 3,
            isLastRead: true,
            readAtLabel: "10:05",
          }),
        ]}
      />
    )

    const rows = [...document.querySelectorAll<HTMLElement>("[data-index]")]
    expect(rows[0]).toHaveTextContent('messenger:seenByGroup|{"count":2,"total":3}')
    expect(rows[0]).not.toHaveTextContent('messenger:seen|{"time":"10:00"}')
    expect(rows[1]).not.toHaveTextContent('messenger:seenByGroup|{"count":0,"total":3}')
    expect(rows[1]).not.toHaveTextContent('messenger:seen|{"time":"10:01"}')
    expect(rows[2]).toHaveTextContent('messenger:seen|{"time":"10:02"}')
    expect(rows[3]).toHaveTextContent('messenger:seen|{"time":"10:03"}')
    expect(rows[4]).not.toHaveTextContent('messenger:seenByGroup|{"count":2,"total":3}')
    expect(rows[4]).not.toHaveTextContent('messenger:seen|{"time":"10:04"}')
    expect(rows[5]).not.toHaveTextContent('messenger:seen|{"time":"10:05"}')
  })

  it("does not throw when optional edit/delete callbacks are omitted", () => {
    const own = makeMessage({ id: "optional-actions", text: "edit me", isMe: true })
    const { container, rerender } = render(<ChatWindow messages={[own]} />)

    expect(() =>
      fireEvent.click(screen.getByRole("button", { name: "messenger:editMessage" }))
    ).not.toThrow()
    expect(() =>
      fireEvent.click(screen.getByRole("button", { name: "messenger:deleteMessage" }))
    ).not.toThrow()

    rerender(
      <ChatWindow messages={[own]} editingMessageId={own.id} editingMessageContent="draft" />
    )
    const textarea = screen.getByRole("textbox")
    expect(() => fireEvent.change(textarea, { target: { value: "draft next" } })).not.toThrow()
    expect(() => fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })).not.toThrow()
    expect(() => fireEvent.keyDown(textarea, { key: "Escape" })).not.toThrow()
    expect(() =>
      fireEvent.click(screen.getByRole("button", { name: "common:buttons.save" }))
    ).not.toThrow()
    expect(() =>
      fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    ).not.toThrow()
    expect(container.querySelector("textarea")).toBeInTheDocument()
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
    expect(fab.querySelector("svg")).toHaveClass("size-5")
    expect(fab.querySelector("svg")).toHaveAttribute("stroke-width", "2.5")
    expect(fab.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
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

  it("keeps the loading-row identity stable and explicit", () => {
    expect(getMessageSkeletonKey(0)).toBe("message-skeleton-0")
    expect(getMessageSkeletonKey(5)).toBe("message-skeleton-5")
  })

  it("keeps reduced-motion transitions observable for both empty branches", () => {
    motionState.reduced = true
    const empty = render(<ChatWindow messages={[]} />)
    const emptyAnimated = empty.container.querySelector("[data-motion-initial]")!
    expect(motionAttr(emptyAnimated, "data-motion-initial")).toBe("false")
    expect(motionAttr(emptyAnimated, "data-motion-animate")).toBe(
      JSON.stringify({ scale: 1, opacity: 1, y: 0 })
    )
    expect(motionAttr(emptyAnimated, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0 })
    )
    expect(emptyAnimated.parentElement?.querySelector(".messenger-card-matte")).toHaveStyle({
      background: "var(--messenger-card-bg)",
    })
    empty.unmount()

    const search = render(
      <ChatWindow
        messages={[makeMessage({ id: "search-motion", text: "visible" })]}
        searchQuery="absent"
      />
    )
    const searchAnimated = search.container.querySelector("[data-motion-initial]")!
    expect(motionAttr(searchAnimated, "data-motion-initial")).toBe("false")
    expect(motionAttr(searchAnimated, "data-motion-animate")).toBe(
      JSON.stringify({ scale: 1, opacity: 1, y: 0 })
    )
    expect(motionAttr(searchAnimated, "data-motion-transition")).toBe(
      JSON.stringify({ duration: 0 })
    )
    expect(searchAnimated.parentElement?.querySelector(".messenger-card-matte")).toHaveStyle({
      background: "var(--messenger-card-bg)",
    })
    search.unmount()
  })

  it("animates only the newly appended row with the canonical transition", () => {
    const first = makeMessage({ id: "append-first", text: "first" })
    const second = makeMessage({ id: "append-second", text: "second" })
    const { container, rerender } = render(<ChatWindow messages={[first]} />)

    rerender(<ChatWindow messages={[first, second]} />)
    expect(container.querySelectorAll("[data-index]")).toHaveLength(2)
    expect(
      shouldAnimateMessageEntrance({
        prefersReducedMotion: false,
        isSearchActive: false,
        index: 1,
        animateFromIndex: 1,
      })
    ).toBe(true)
    expect(
      shouldAnimateMessageEntrance({
        prefersReducedMotion: false,
        isSearchActive: false,
        index: 0,
        animateFromIndex: 1,
      })
    ).toBe(false)
    expect(getMessageEntranceMotion(true)).toEqual({
      initial: { opacity: 0, y: 10, scale: 0.95 },
      animate: { opacity: 1, y: 0, scale: 1 },
      transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] },
    })
    expect(
      shouldAnimateMessageEntrance({
        prefersReducedMotion: true,
        isSearchActive: false,
        index: 1,
        animateFromIndex: 1,
      })
    ).toBe(false)
    expect(
      shouldAnimateMessageEntrance({
        prefersReducedMotion: false,
        isSearchActive: true,
        index: 1,
        animateFromIndex: 1,
      })
    ).toBe(false)
    expect(getMessageEntranceMotion(false)).toEqual({
      initial: false,
      animate: { opacity: 1, y: 0, scale: 1 },
      transition: { duration: 0 },
    })

    rerender(<ChatWindow messages={[first, second]} searchQuery="second" />)
    const searchRow = container.querySelector('[data-index="0"] .group')!
    expect(searchRow).toHaveAttribute("data-motion-initial", "false")
  })

  it("preserves exact sender, column, bubble and reply styling for both sides", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({
            id: "styled-sent",
            text: "sent body",
            senderName: "",
            isMe: true,
            replyTo: {
              id: "sent-reply",
              senderName: "Bob",
              isMe: false,
              text: "quoted sent",
              deletedAt: null,
            },
          }),
          makeMessage({
            id: "styled-received",
            text: "received body",
            senderName: "Carol",
            replyTo: {
              id: "received-reply",
              senderName: "Dana",
              isMe: false,
              text: "quoted received",
              deletedAt: null,
            },
          }),
        ]}
      />
    )

    const sentRow = container.querySelector('[data-index="0"]')!
    const receivedRow = container.querySelector('[data-index="1"]')!
    expect(sentRow.querySelector('img[alt=""]')).toBeInTheDocument()
    expect(sentRow.querySelector(".group")).toHaveClass("flex-row-reverse", "justify-start")
    expect(receivedRow.querySelector(".group")).toHaveClass("flex-row", "justify-start")
    const sentColumn = sentRow.querySelector<HTMLElement>(".group > div:nth-child(2)")!
    const receivedColumn = receivedRow.querySelector<HTMLElement>(".group > div:nth-child(2)")!
    for (const column of [sentColumn, receivedColumn]) {
      expect(column).toHaveClass(
        "flex",
        "min-w-0",
        "max-w-4/5",
        "flex-col",
        "gap-1",
        "sm:max-w-3/4",
        "md:max-w-[68%]",
        "lg:max-w-[60%]",
        "xl:max-w-[52%]"
      )
    }
    expect(sentColumn).toHaveClass("items-end")
    expect(receivedColumn).toHaveClass("items-start")

    const sentBubble = sentRow.querySelector(".messenger-bubble-sent")!
    const receivedBubble = receivedRow.querySelector(".messenger-bubble-received")!
    expect(sentBubble).toHaveClass("relative", "max-w-full", "px-4", "py-2.5", "text-base")
    expect(receivedBubble).toHaveClass("relative", "max-w-full", "px-4", "py-2.5", "text-base")

    const sentReply = screen.getByText("quoted sent")
    const receivedReply = screen.getByText("quoted received")
    expect(sentReply).toHaveClass(
      "line-clamp-2",
      "text-sm",
      "leading-snug",
      "text-[var(--text-inverse)]",
      "opacity-medium"
    )
    expect(receivedReply).toHaveClass(
      "line-clamp-2",
      "text-sm",
      "leading-snug",
      "text-(--text-secondary)"
    )
    expect(screen.getByText("Bob")).toHaveClass("text-[var(--text-inverse)]")
    expect(screen.getByText("Dana")).toHaveClass("text-(--brand-main)")
  })

  it("keeps tombstone and inline-edit corner styles side-aware", () => {
    const own = makeMessage({ id: "edit-own", text: "own", isMe: true })
    const received = makeMessage({ id: "edit-received", text: "received", isMe: false })
    const deletedOwn = makeMessage({
      id: "deleted-own",
      text: "secret",
      isMe: true,
      deletedAt: "2026-01-01",
    })
    const deletedReceived = makeMessage({
      id: "deleted-received",
      text: "secret2",
      isMe: false,
      deletedAt: "2026-01-01",
    })
    const { container, rerender } = render(<ChatWindow messages={[deletedOwn, deletedReceived]} />)
    const tombstones = [...container.querySelectorAll<HTMLElement>(".messenger-bubble-received")]
    expect(tombstones[0]).toHaveClass("rounded-br-sm", "md:rounded-br-2xl", "md:rounded-bl-sm")
    expect(tombstones[1]).toHaveClass("rounded-bl-sm")
    expect(tombstones[1]).not.toHaveClass("rounded-br-sm")

    rerender(
      <ChatWindow messages={[own]} editingMessageId={own.id} editingMessageContent="draft" />
    )
    const ownEditor = container.querySelector(".messenger-bubble-received")!
    expect(ownEditor).toHaveClass(
      "relative",
      "w-full",
      "max-w-full",
      "rounded-2xl",
      "px-3",
      "py-2.5"
    )
    expect(ownEditor).toHaveClass("rounded-br-sm", "md:rounded-br-2xl", "md:rounded-bl-sm")
    expect(ownEditor).not.toHaveClass("rounded-bl-sm")

    rerender(
      <ChatWindow
        messages={[received]}
        editingMessageId={received.id}
        editingMessageContent="draft"
      />
    )
    const receivedEditor = container.querySelector(".messenger-bubble-received")!
    expect(receivedEditor).toHaveClass("rounded-bl-sm")
    expect(receivedEditor).not.toHaveClass("rounded-br-sm", "md:rounded-bl-sm")
  })

  it("keeps reply and forward hit targets side-aware", () => {
    const { container } = render(
      <ChatWindow
        messages={[
          makeMessage({ id: "actions-sent", text: "sent", isMe: true }),
          makeMessage({ id: "actions-received", text: "received", isMe: false }),
        ]}
        onStartReply={() => {}}
        onForward={() => {}}
      />
    )
    const sentRow = container.querySelector('[data-index="0"]')!
    const receivedRow = container.querySelector('[data-index="1"]')!
    for (const label of ["messenger:reply", "messenger:forward"]) {
      expect(sentRow.querySelector(`button[aria-label="${label}"]`)).toHaveClass(
        "-m-2",
        "flex",
        "min-h-[44px]",
        "min-w-[44px]",
        "text-[var(--text-inverse)]",
        "focus-visible:ring-[var(--text-inverse)]"
      )
      expect(receivedRow.querySelector(`button[aria-label="${label}"]`)).toHaveClass(
        "-m-2",
        "flex",
        "min-h-[44px]",
        "min-w-[44px]",
        "text-(--text-secondary)",
        "focus-visible:ring-(--color-violet-500)"
      )
    }
  })

  it("hides reaction controls while editing and keeps read-only pills safe", () => {
    const message = makeMessage({
      id: "reaction-editing",
      text: "react",
      reactions: [{ emoji: "👍", count: 1, reactedByMe: false }],
    })
    const { rerender } = render(
      <ChatWindow
        messages={[message]}
        editingMessageId={message.id}
        editingMessageContent="draft"
        onToggleReaction={() => {}}
      />
    )
    expect(screen.queryByTestId("reaction-👍")).toBeNull()
    expect(screen.queryByRole("button", { name: "messenger:reactions.add" })).toBeNull()

    rerender(<ChatWindow messages={[message]} />)
    const pill = screen.getByTestId("reaction-👍")
    expect(() => fireEvent.click(pill)).not.toThrow()
  })
})
