import { act, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

import { ReactionPill } from "@/components/messenger/ReactionPill"

const mocks = vi.hoisted(() => ({
  useFloating: vi.fn(),
  useHover: vi.fn(),
  useFocus: vi.fn(),
  useDismiss: vi.fn(),
  useRole: vi.fn(),
  useInteractions: vi.fn(),
  safePolygon: vi.fn(),
  offset: vi.fn(),
  flip: vi.fn(),
  shift: vi.fn(),
  autoUpdate: vi.fn(),
  useQuery: vi.fn(),
  translation: vi.fn(),
}))

vi.mock("@floating-ui/react", () => ({
  useFloating: mocks.useFloating,
  useHover: mocks.useHover,
  useFocus: mocks.useFocus,
  useDismiss: mocks.useDismiss,
  useRole: mocks.useRole,
  useInteractions: mocks.useInteractions,
  safePolygon: mocks.safePolygon,
  offset: mocks.offset,
  flip: mocks.flip,
  shift: mocks.shift,
  autoUpdate: mocks.autoUpdate,
  FloatingPortal: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock("@tanstack/react-query", async () => {
  const actual =
    await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query")
  return { ...actual, useQuery: mocks.useQuery }
})

vi.mock("react-i18next", () => ({
  useTranslation: (...args: unknown[]) => {
    mocks.translation(...args)
    return { t: (key: string) => key }
  },
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, srcRaw }: { alt?: string; srcRaw?: string }) => <img alt={alt} src={srcRaw} />,
}))

function renderContract(overrides: Partial<React.ComponentProps<typeof ReactionPill>> = {}) {
  const setReference = vi.fn()
  const setFloating = vi.fn()
  mocks.useFloating.mockReturnValue({
    refs: { setReference, setFloating },
    floatingStyles: {},
    context: { id: "floating-context" },
  })
  mocks.offset.mockImplementation((value: number) => ({ name: "offset", value }))
  mocks.flip.mockReturnValue({ name: "flip" })
  mocks.shift.mockImplementation((options: unknown) => ({ name: "shift", options }))
  mocks.safePolygon.mockReturnValue({ name: "safePolygon" })
  mocks.useHover.mockReturnValue({ name: "hover" })
  mocks.useFocus.mockReturnValue({ name: "focus" })
  mocks.useDismiss.mockReturnValue({ name: "dismiss" })
  mocks.useRole.mockReturnValue({ name: "role" })
  mocks.useInteractions.mockImplementation((interactions: unknown[]) => ({
    getReferenceProps: (props: Record<string, unknown>) => props,
    getFloatingProps: () => ({}),
    interactions,
  }))
  mocks.useQuery.mockReturnValue({ data: [], isLoading: false })

  const queryClient = new QueryClient()
  const onToggle = vi.fn()
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ReactionPill
        chatId="chat-1"
        messageId="message-1"
        emoji="👍"
        count={3}
        reactedByMe={false}
        onToggle={onToggle}
        {...overrides}
      />
    </QueryClientProvider>
  )
  return { ...view, onToggle, setReference }
}

describe("ReactionPill integration contracts", () => {
  it("configures Floating UI placement, middleware, hover, focus, role and query gating", () => {
    renderContract()

    expect(mocks.translation).toHaveBeenCalledWith(["messenger"])
    expect(mocks.offset).toHaveBeenCalledWith(6)
    expect(mocks.flip).toHaveBeenCalledWith()
    expect(mocks.shift).toHaveBeenCalledWith({ padding: 8 })
    expect(mocks.useFloating).toHaveBeenCalledWith(
      expect.objectContaining({
        placement: "top",
        middleware: [
          { name: "offset", value: 6 },
          { name: "flip" },
          { name: "shift", options: { padding: 8 } },
        ],
        whileElementsMounted: mocks.autoUpdate,
      })
    )
    expect(mocks.useHover).toHaveBeenCalledWith(
      { id: "floating-context" },
      expect.objectContaining({
        mouseOnly: true,
        handleClose: { name: "safePolygon" },
        delay: { open: 250 },
      })
    )
    expect(mocks.useRole).toHaveBeenCalledWith({ id: "floating-context" }, { role: "tooltip" })
    expect(mocks.useInteractions).toHaveBeenCalledWith([
      { name: "hover" },
      { name: "focus" },
      { name: "dismiss" },
      { name: "role" },
    ])
    expect(mocks.useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: false,
      })
    )
  })

  it("keeps the touch long-press lifecycle and all pointer cleanup handlers wired", () => {
    const { onToggle } = renderContract()
    const button = screen.getByRole("button")
    fireEvent.pointerDown(button, { pointerType: "mouse" })
    fireEvent.pointerMove(button, { pointerType: "mouse" })
    fireEvent.pointerUp(button, { pointerType: "mouse" })
    fireEvent.pointerLeave(button, { pointerType: "mouse" })
    fireEvent.pointerCancel(button, { pointerType: "mouse" })
    fireEvent.click(button)
    expect(onToggle).toHaveBeenCalledWith("👍")
  })

  it("renders the stable reaction and popover class contracts", () => {
    const { container } = renderContract()
    const button = screen.getByRole("button")
    expect(button).toHaveClass(
      "-m-2",
      "inline-flex",
      "min-h-[44px]",
      "min-w-[44px]",
      "items-center",
      "gap-1",
      "rounded-full",
      "border",
      "px-2",
      "py-0.5",
      "text-sm",
      "transition-colors"
    )
    expect(container.querySelector("[data-reaction-ui]")).toBe(button)
  })

  it("treats pen long-press as a popover gesture and suppresses its follow-up click", () => {
    vi.useFakeTimers()
    try {
      const { onToggle } = renderContract({ chatId: "chat-pen", emoji: "🖊️", count: 1 })
      const button = screen.getByRole("button")

      fireEvent.pointerDown(button, { pointerType: "pen" })
      act(() => {
        vi.advanceTimersByTime(500)
      })

      expect(screen.getByText("messenger:reactions.whoReacted")).toBeInTheDocument()
      expect(mocks.useQuery).toHaveBeenLastCalledWith(expect.objectContaining({ enabled: true }))

      fireEvent.click(button)
      expect(onToggle).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps pressed state, accessible tally and inactive styling distinct", () => {
    const { container } = renderContract({ reactedByMe: true, emoji: "✅", count: 0 })
    const button = screen.getByRole("button")

    expect(button).toHaveAttribute("aria-pressed", "true")
    expect(button).toHaveAttribute("aria-label", "messenger:reactions.tally")
    expect(button).toHaveClass(
      "border-(--color-violet-500)/(--opacity-medium)",
      "bg-(--color-violet-500)/(--opacity-soft)",
      "text-(--text-primary)"
    )
    expect(container.querySelector("[data-reaction-ui]")).toBe(button)
  })
})
