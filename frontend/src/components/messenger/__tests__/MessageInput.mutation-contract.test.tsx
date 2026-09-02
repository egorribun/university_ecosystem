import type { ReactNode } from "react"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ reduced: false }))

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
  const componentCache = new Map<string, unknown>()
  const motion = new Proxy(
    {},
    {
      get: (_target, key) => {
        if (typeof key !== "string") return undefined
        const cached = componentCache.get(key)
        if (cached) return cached
        const component = React.forwardRef<HTMLElement, Props>(function MotionElement(props, ref) {
          return React.createElement(Motion, { ...props, ref, "data-motion-tag": key })
        })
        componentCache.set(key, component)
        return component
      },
    }
  )
  return {
    m: motion,
    motion,
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  }
})

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => state.reduced }))
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

import { MessageInput } from "@/components/messenger/MessageInput"

const attr = (element: Element, name: string) => element.getAttribute(name)

beforeEach(() => {
  state.reduced = false
  vi.spyOn(URL, "createObjectURL").mockImplementation((file) => `blob:${(file as File).name}`)
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
  vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000000")
})
afterEach(() => vi.restoreAllMocks())

describe("MessageInput motion and DOM contract", () => {
  it("exposes exact attach/send animations, touch targets and Unicode maxLength", async () => {
    const onSend = vi.fn()
    const { container } = render(<MessageInput onSend={onSend} />)
    const attach = screen.getByRole("button", { name: "messenger:aria.attachments" })
    const send = screen.getByRole("button", { name: "messenger:aria.sendMessage" })
    expect(attr(attach, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.1 }))
    expect(attr(attach, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.9 }))
    expect(attr(send, "data-motion-while-hover")).toBe("undefined")
    expect(attr(send, "data-motion-while-tap")).toBe("undefined")
    expect(attach).toHaveClass("min-h-[44px]", "min-w-[44px]", "rounded-xl")
    expect(send).toBeDisabled()
    expect(send).toHaveClass("min-h-[44px]", "min-w-[44px]", "rounded-xl")
    const textarea = screen.getByRole("textbox", {
      name: "messenger:typeMessage",
    }) as HTMLTextAreaElement
    expect(textarea.maxLength).toBe(65536)
    expect(textarea).toHaveClass("flex-1", "resize-none", "max-h-48", "text-base")

    const user = userEvent.setup()
    await user.type(textarea, "hello")
    await waitFor(() => expect(textarea).toHaveValue("hello"))
    expect(send).not.toBeDisabled()
    expect(attr(send, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.08 }))
    expect(attr(send, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.92 }))
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()
    fireEvent.keyDown(textarea, { key: "Enter" })
    expect(onSend).toHaveBeenCalledWith("hello", [])
    expect(send).toBeDisabled()
    expect(
      container.querySelector('[class*="bg-(--bg-surface-hover)/(--opacity-subtle)"]')
    ).toBeTruthy()
  })

  it("uses no animation values in reduced-motion mode", () => {
    state.reduced = true
    render(
      <MessageInput
        onSend={() => {}}
        replyingTo={{ senderName: "Alice", isMe: false, text: "quote" }}
      />
    )
    const attach = screen.getByRole("button", { name: "messenger:aria.attachments" })
    const send = screen.getByRole("button", { name: "messenger:aria.sendMessage" })
    expect(attr(attach, "data-motion-while-hover")).toBe("undefined")
    expect(attr(attach, "data-motion-while-tap")).toBe("undefined")
    expect(attr(send, "data-motion-while-hover")).toBe("undefined")
    expect(attr(send, "data-motion-while-tap")).toBe("undefined")
    expect(screen.getByText('messenger:replyingTo|{"name":"Alice"}')).toBeInTheDocument()
  })

  it("keeps attachment menu animation, item colors and accept contracts stable", () => {
    const { container } = render(<MessageInput onSend={() => {}} />)
    fireEvent.click(screen.getByRole("button", { name: "messenger:aria.attachments" }))
    const menu = container.querySelector(".absolute.bottom-full")!
    expect(attr(menu, "data-motion-initial")).toBe(
      JSON.stringify({ opacity: 0, scale: 0.95, y: 10 })
    )
    expect(attr(menu, "data-motion-animate")).toBe(JSON.stringify({ opacity: 1, scale: 1, y: 0 }))
    expect(attr(menu, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0, scale: 0.95, y: 10 }))
    expect(menu).toHaveClass("min-w-(--min-w-column)", "rounded-2xl", "shadow-premium")
    expect(container.querySelector("#chat-attach-type-photo > div")).toHaveClass(
      "text-(--primary-main)",
      "bg-(--primary-main)/(--opacity-subtle)"
    )
    expect(container.querySelector("#chat-attach-type-document > div")).toHaveClass(
      "text-(--success-text)",
      "bg-(--success-text)/(--opacity-subtle)"
    )
    expect(container.querySelector("#chat-attach-type-file > div")).toHaveClass(
      "text-(--warning-text)",
      "bg-(--warning-text)/(--opacity-subtle)"
    )
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    vi.spyOn(input, "click").mockImplementation(() => undefined)
    fireEvent.click(screen.getByRole("button", { name: "messenger:attachPhoto" }))
    expect(input.accept).toBe("image/png,image/jpeg,image/gif,image/webp")
    fireEvent.click(screen.getByRole("button", { name: "messenger:aria.attachments" }))
    fireEvent.click(screen.getByRole("button", { name: "messenger:attachDocument" }))
    expect(input.accept).toBe(".pdf,.doc,.docx,.txt")
    fireEvent.click(screen.getByRole("button", { name: "messenger:aria.attachments" }))
    fireEvent.click(screen.getByRole("button", { name: "messenger:attachFile" }))
    expect(input.accept).toBe("*")
  })

  it("serialises rejected SVG alert animation and reply-chip accessibility", async () => {
    const { container } = render(
      <MessageInput
        onSend={() => {}}
        replyingTo={{ senderName: null, isMe: false, text: "quoted" }}
        onCancelReply={vi.fn()}
      />
    )
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const svg = new File(["<svg/>"], "vector.svg", { type: "image/svg+xml" })
    Object.defineProperty(fileInput, "files", { value: [svg], configurable: true })
    await act(async () => {
      fireEvent.change(fileInput)
    })
    const alert = screen.getByRole("alert")
    expect(attr(alert, "data-motion-initial")).toBe(JSON.stringify({ opacity: 0, y: 8 }))
    expect(attr(alert, "data-motion-animate")).toBe(JSON.stringify({ opacity: 1, y: 0 }))
    expect(attr(alert, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0, y: 8 }))
    expect(alert).toHaveClass("absolute", "-top-10", "bg-error-bg", "text-error-text")
    expect(
      screen.getByText('messenger:replyingTo|{"name":"messenger:replyTo.unknownSender"}')
    ).toBeInTheDocument()
    expect(screen.getByText("quoted")).toHaveClass("truncate", "text-sm")
  })
})
