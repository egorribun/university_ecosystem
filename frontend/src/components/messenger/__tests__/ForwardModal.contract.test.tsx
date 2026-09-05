import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

import { ForwardModal } from "@/components/messenger/ForwardModal"

const mocks = vi.hoisted(() => ({
  motion: vi.fn(),
  translation: vi.fn(),
  mediaQuery: vi.fn(() => false),
  focusTrap: vi.fn(() => ({ current: null })),
}))

vi.mock("framer-motion", () => {
  const motionElement = (tag: "div" | "button") => {
    const MotionElement = ({
      children,
      ...props
    }: {
      children?: ReactNode
      [key: string]: unknown
    }) => {
      mocks.motion(tag, props)
      const domProps = Object.fromEntries(
        Object.entries(props).filter(
          ([key]) =>
            !["initial", "animate", "exit", "transition", "whileHover", "whileTap"].includes(key)
        )
      )
      return tag === "div" ? (
        <div {...domProps}>{children}</div>
      ) : (
        <button {...domProps}>{children}</button>
      )
    }
    MotionElement.displayName = `Motion${tag}`
    return MotionElement
  }
  return {
    AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
    m: { div: motionElement("div"), button: motionElement("button") },
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: (...args: unknown[]) => {
    mocks.translation(...args)
    return { t: (key: string) => key }
  },
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: mocks.mediaQuery }))
vi.mock("@/hooks/useFocusTrap", () => ({ default: mocks.focusTrap }))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt }: { alt?: string }) => <img alt={alt} />,
}))

const contacts = [
  {
    id: "chat-1",
    name: "Chat one",
    avatar: "",
    lastMessage: "hello",
    lastMessageTime: "10:00",
    unread: 0,
    online: false,
  },
] as never

describe("ForwardModal contracts", () => {
  it("passes the namespace and focus-trap contract", () => {
    const onClose = vi.fn()
    render(<ForwardModal open onClose={onClose} contacts={contacts} onSelect={() => {}} />)
    expect(mocks.translation).toHaveBeenCalledWith(["messenger", "common"])
    expect(mocks.focusTrap).toHaveBeenCalledWith({
      active: true,
      onDeactivate: onClose,
      initialFocus: false,
      returnFocus: true,
    })
  })

  it("keeps overlay, dialog and destination animation contracts", () => {
    render(<ForwardModal open onClose={() => {}} contacts={contacts} onSelect={() => {}} />)
    const overlay = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "div" && props.role === "presentation"
    )
    expect(overlay?.[1]).toMatchObject({
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    })
    const dialog = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "div" && props.role === "dialog"
    )
    expect(dialog?.[1]).toMatchObject({
      initial: { scale: 0.95, opacity: 0, y: 20 },
      animate: { scale: 1, opacity: 1, y: 0 },
      exit: { scale: 0.95, opacity: 0, y: 20 },
    })
    const option = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "button" && props.role === "option"
    )
    expect(option?.[1]).toMatchObject({
      whileHover: { x: 4, backgroundColor: "var(--bg-surface-hover)" },
      whileTap: { scale: 0.98 },
    })
  })

  it("disables destination motion under reduced-motion and forwarding states", () => {
    mocks.mediaQuery.mockReturnValue(true)
    const { rerender } = render(
      <ForwardModal open onClose={() => {}} contacts={contacts} onSelect={() => {}} />
    )
    let option = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "button" && props.role === "option"
    )
    expect(option?.[1]).toMatchObject({ whileHover: undefined, whileTap: undefined })
    mocks.motion.mockClear()
    rerender(
      <ForwardModal open onClose={() => {}} contacts={contacts} onSelect={() => {}} isForwarding />
    )
    option = mocks.motion.mock.calls.find(
      ([tag, props]) => tag === "button" && props.role === "option"
    )
    expect(option?.[1]).toMatchObject({
      whileHover: undefined,
      whileTap: undefined,
      disabled: true,
    })
    mocks.mediaQuery.mockReturnValue(false)
  })

  it("keeps the empty destination state accessible", () => {
    render(<ForwardModal open onClose={() => {}} contacts={[]} onSelect={() => {}} />)
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite")
    expect(screen.getByText("messenger:forwardNoChats")).toBeInTheDocument()
  })

  it("dispatches the selected destination and marks only the current chat", () => {
    const onSelect = vi.fn()
    const contacts = [
      {
        id: "chat-current",
        name: "Current chat",
        avatar: "",
        lastMessage: "",
        lastMessageTime: "10:00",
        unread: 0,
        online: false,
      },
      {
        id: "chat-other",
        name: "Other chat",
        avatar: "avatar.png",
        lastMessage: "A recent message",
        lastMessageTime: "10:01",
        unread: 2,
        online: true,
      },
    ] as never

    render(
      <ForwardModal
        open
        onClose={() => {}}
        contacts={contacts}
        currentChatId="chat-current"
        onSelect={onSelect}
      />
    )

    const options = screen.getAllByRole("option")
    expect(options).toHaveLength(2)
    expect(options[0]).toHaveTextContent("messenger:forwardCurrentChat")
    expect(options[0]).not.toHaveTextContent("A recent message")
    expect(options[1]).toHaveTextContent("A recent message")

    fireEvent.click(options[1]!)
    expect(onSelect).toHaveBeenCalledOnce()
    expect(onSelect).toHaveBeenCalledWith("chat-other")
  })

  it("blocks destination dispatch while forwarding and closes only from modal boundaries", () => {
    const onSelect = vi.fn()
    const onClose = vi.fn()
    const { container, rerender } = render(
      <ForwardModal open onClose={onClose} contacts={contacts} onSelect={onSelect} isForwarding />
    )

    const listbox = screen.getByRole("listbox", { name: "messenger:forwardTo" })
    expect(listbox).toHaveAttribute("aria-busy", "true")
    const option = screen.getByRole("option")
    expect(option).toBeDisabled()
    fireEvent.click(option)
    expect(onSelect).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("dialog"))
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(onClose).toHaveBeenCalledOnce()

    fireEvent.click(container.querySelector("[aria-hidden='true']")!)
    expect(onClose).toHaveBeenCalledTimes(2)
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(3)

    rerender(
      <ForwardModal open={false} onClose={onClose} contacts={contacts} onSelect={onSelect} />
    )
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(3)
  })
})
