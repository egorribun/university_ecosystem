import { createEvent, fireEvent, render, screen } from "@testing-library/react"
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useDebounced", () => ({ useDebounced: <T,>(value: T) => value }))
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
    measureElement: () => {},
    scrollToIndex: () => {},
    scrollToEnd: () => {},
    isAtEnd: () => false,
    getDistanceFromEnd: () => 500,
  }),
}))
type MotionFields = {
  initial?: unknown
  animate?: unknown
  transition?: unknown
  whileHover?: unknown
  whileTap?: unknown
}

vi.mock("framer-motion", () => ({
  m: {
    div: ({
      children,
      initial,
      animate,
      transition,
      ...props
    }: HTMLAttributes<HTMLDivElement> & MotionFields & { children?: ReactNode }) => {
      void initial
      void animate
      void transition
      return <div {...props}>{children}</div>
    },
    button: ({
      children,
      initial,
      animate,
      transition,
      whileHover,
      whileTap,
      ...props
    }: ButtonHTMLAttributes<HTMLButtonElement> & MotionFields & { children?: ReactNode }) => {
      void initial
      void animate
      void transition
      void whileHover
      void whileTap
      return <button {...props}>{children}</button>
    },
  },
}))

import { ChatWindow } from "@/components/messenger/ChatWindow"
import type { Message } from "@/components/messenger/types"

const message: Message = {
  id: "ime-message",
  senderId: "sender-1",
  senderName: "Sender",
  senderAvatar: "",
  text: "Original text",
  timestamp: "12:00",
  isMe: true,
}

afterEach(() => {
  vi.restoreAllMocks()
})

function renderInlineEdit(onSaveEdit: (messageId: string) => void) {
  return render(
    <ChatWindow
      messages={[message]}
      editingMessageId={message.id}
      editingMessageContent="Edit draft"
      onSaveEdit={onSaveEdit}
    />
  )
}

describe("AUD-217 IME-safe inline message editing", () => {
  it("does not submit or prevent the active IME composition Enter event", () => {
    const onSaveEdit = vi.fn()
    renderInlineEdit(onSaveEdit)
    const textarea = screen.getByRole("textbox", { name: "messenger:editMessage" })
    const composingEnter = createEvent.keyDown(textarea, {
      key: "Enter",
      shiftKey: false,
      isComposing: true,
      keyCode: 229,
    })

    expect(composingEnter).toBeInstanceOf(KeyboardEvent)
    expect((composingEnter as KeyboardEvent).isComposing).toBe(true)
    expect((composingEnter as KeyboardEvent).keyCode).toBe(229)
    fireEvent(textarea, composingEnter)

    expect(onSaveEdit).not.toHaveBeenCalled()
    expect(composingEnter.defaultPrevented).toBe(false)
  })

  it("does not submit the legacy 229 composition key when isComposing is false", () => {
    const onSaveEdit = vi.fn()
    renderInlineEdit(onSaveEdit)
    const textarea = screen.getByRole("textbox", { name: "messenger:editMessage" })
    const legacyCompositionEnter = createEvent.keyDown(textarea, {
      key: "Enter",
      shiftKey: false,
      isComposing: false,
      keyCode: 229,
    })

    expect(legacyCompositionEnter).toBeInstanceOf(KeyboardEvent)
    expect((legacyCompositionEnter as KeyboardEvent).isComposing).toBe(false)
    expect((legacyCompositionEnter as KeyboardEvent).keyCode).toBe(229)
    fireEvent(textarea, legacyCompositionEnter)

    expect(onSaveEdit).not.toHaveBeenCalled()
    expect(legacyCompositionEnter.defaultPrevented).toBe(false)
  })

  it("still submits one normal Enter and leaves Shift+Enter for a newline", () => {
    const onSaveEdit = vi.fn()
    renderInlineEdit(onSaveEdit)
    const textarea = screen.getByRole("textbox", { name: "messenger:editMessage" })

    const normalEnter = createEvent.keyDown(textarea, {
      key: "Enter",
      shiftKey: false,
      isComposing: false,
      keyCode: 13,
    })
    fireEvent(textarea, normalEnter)
    expect(onSaveEdit).toHaveBeenCalledTimes(1)
    expect(onSaveEdit).toHaveBeenCalledWith(message.id)
    expect(normalEnter.defaultPrevented).toBe(true)

    onSaveEdit.mockClear()
    const newline = createEvent.keyDown(textarea, {
      key: "Enter",
      shiftKey: true,
      isComposing: false,
      keyCode: 13,
    })
    fireEvent(textarea, newline)
    expect(onSaveEdit).not.toHaveBeenCalled()
    expect(newline.defaultPrevented).toBe(false)
  })
})
