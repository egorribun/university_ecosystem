import type { ReactNode } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ reduced: false, get: vi.fn() }))

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
  const cache = new Map<string, unknown>()
  const motion = new Proxy(
    {},
    {
      get: (_target, key) => {
        if (typeof key !== "string") return undefined
        const cached = cache.get(key)
        if (cached) return cached
        const component = React.forwardRef<HTMLElement, Props>(function MotionElement(props, ref) {
          return React.createElement(Motion, { ...props, ref, "data-motion-tag": key })
        })
        cache.set(key, component)
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

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}|${JSON.stringify(options)}` : key,
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => state.reduced }))
vi.mock("@/hooks/useFocusTrap", () => ({ default: () => ({ current: null }) }))
vi.mock("@/hooks/useDebounced", () => ({ useDebounced: <T,>(value: T) => value }))
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>()
  return {
    ...actual,
    default: { ...actual.default, get: state.get },
  }
})
vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))

import { NewChatModal } from "@/components/messenger/NewChatModal"

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider
    client={
      new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
    }
  >
    {children}
  </QueryClientProvider>
)

const user = (id: string, name = `User ${id}`) => ({
  id,
  full_name: name,
  email: `${id}@example.test`,
  avatar_url: id === "one" ? "https://cdn.example/avatar.png" : null,
})

const attr = (element: Element, name: string) => element.getAttribute(name)

beforeEach(() => {
  state.reduced = false
  state.get.mockReset().mockResolvedValue({ data: [] })
})
afterEach(() => vi.restoreAllMocks())

describe("NewChatModal motion/layout mutation contract", () => {
  it("keeps overlay and dialog entrance/exit values and accessible shell stable", () => {
    const { container } = render(<NewChatModal open onClose={() => {}} onSelect={() => {}} />, {
      wrapper,
    })
    const overlay = container.querySelector("[role='presentation']")!
    expect(attr(overlay, "data-motion-initial")).toBe(JSON.stringify({ opacity: 0 }))
    expect(attr(overlay, "data-motion-animate")).toBe(JSON.stringify({ opacity: 1 }))
    expect(attr(overlay, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0 }))
    expect(overlay).toHaveClass("fixed", "inset-0", "z-modal", "p-4")
    expect(container.querySelector(".absolute.inset-0")).toHaveClass(
      "bg-black/(--opacity-strong)",
      "backdrop-blur-md",
      "cursor-default"
    )

    const dialog = screen.getByRole("dialog")
    expect(attr(dialog, "data-motion-initial")).toBe(
      JSON.stringify({ scale: 0.95, opacity: 0, y: 20 })
    )
    expect(attr(dialog, "data-motion-animate")).toBe(JSON.stringify({ scale: 1, opacity: 1, y: 0 }))
    expect(attr(dialog, "data-motion-exit")).toBe(
      JSON.stringify({ scale: 0.95, opacity: 0, y: 20 })
    )
    expect(attr(dialog, "data-motion-transition")).toBe("undefined")
    expect(dialog).toHaveClass(
      "messenger-card-matte",
      "w-full",
      "max-w-[28rem]",
      "backdrop-blur-2xl"
    )
    expect(dialog).toHaveAttribute("aria-modal", "true")
    expect(screen.getByRole("heading", { name: "messenger:newChat" })).toHaveClass(
      "text-xl",
      "font-black",
      "tracking-tight",
      "sf-pro"
    )
  })

  it("uses reduced-motion dialog values and keeps close/backdrop handlers", () => {
    state.reduced = true
    const onClose = vi.fn()
    const { container } = render(<NewChatModal open onClose={onClose} onSelect={() => {}} />, {
      wrapper,
    })
    const dialog = screen.getByRole("dialog")
    expect(attr(dialog, "data-motion-initial")).toBe("false")
    expect(attr(dialog, "data-motion-exit")).toBe(JSON.stringify({ opacity: 0 }))
    expect(attr(dialog, "data-motion-transition")).toBe(JSON.stringify({ duration: 0 }))
    const close = screen.getByRole("button", { name: "common:buttons.close" })
    expect(close).toHaveClass("min-h-[44px]", "min-w-[44px]", "rounded-xl")
    fireEvent.click(close)
    fireEvent.click(container.querySelector(".absolute.inset-0")!)
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it("observes deterministic loading skeleton geometry and listbox semantics", async () => {
    let resolve: ((value: { data: never[] }) => void) | undefined
    state.get.mockReturnValue(new Promise<{ data: never[] }>((done) => (resolve = done)))
    const { container } = render(<NewChatModal open onClose={() => {}} onSelect={() => {}} />, {
      wrapper,
    })
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "pending" },
    })
    const status = await screen.findByRole("status", { name: "messenger:loading.users" })
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(status.querySelectorAll(".messenger-skeleton")).toHaveLength(15)
    expect(
      [...status.querySelectorAll<HTMLElement>("[style]")].map((node) => node.style.width)
    ).toEqual(["55%", "35%", "68%", "42%", "81%", "49%", "64%", "56%", "77%", "63%"])
    const listbox = screen.getByRole("listbox", { name: "messenger:searchUsers" })
    expect(listbox).toHaveAttribute("aria-busy", "true")
    expect(container.querySelector(".max-h-96")).toHaveClass("overflow-y-auto", "custom-scrollbar")
    resolve?.({ data: [] })
  })

  it("covers group mode selection, row motion, chips and create validation", async () => {
    state.get.mockResolvedValue({ data: [user("one"), user("two")] })
    const onCreateGroup = vi.fn()
    const { container } = render(
      <NewChatModal open onClose={() => {}} onSelect={() => {}} onCreateGroup={onCreateGroup} />,
      { wrapper }
    )
    expect(screen.getByRole("tablist")).toHaveClass("grid", "grid-cols-2", "rounded-2xl")
    const direct = screen.getByRole("tab", { name: "messenger:modeDirect" })
    const group = screen.getByRole("tab", { name: "messenger:modeGroup" })
    expect(direct).toHaveAttribute("aria-selected", "true")
    expect(group).toHaveAttribute("aria-selected", "false")
    fireEvent.click(group)
    expect(screen.getByRole("heading", { name: "messenger:newGroup" })).toBeInTheDocument()
    const groupName = screen.getByRole("textbox", { name: "messenger:groupName" })
    expect(groupName).toHaveAttribute("maxlength", "128")
    fireEvent.change(groupName, { target: { value: "  Project  " } })
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "user" },
    })
    const first = await screen.findByRole("option", { name: /User one/ })
    expect(attr(first, "data-motion-while-hover")).toBe(
      JSON.stringify({ x: 4, backgroundColor: "var(--bg-surface-hover)" })
    )
    expect(attr(first, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.98 }))
    expect(first).toHaveAttribute("aria-selected", "false")
    fireEvent.click(first)
    expect(first).toHaveAttribute("aria-selected", "true")
    expect(first).toHaveClass("bg-(--messenger-active-bg)")
    expect(screen.getByRole("button", { name: /messenger:removeMember/ })).toHaveClass(
      "matte-chip",
      "min-h-[44px]",
      "rounded-full"
    )
    const create = screen.getByRole("button", { name: "messenger:createGroup" })
    expect(create).toBeDisabled()
    expect(screen.getByText("messenger:error.minMembers")).toHaveClass(
      "mt-2",
      "text-center",
      "text-xs"
    )
    const second = await screen.findByRole("option", { name: /User two/ })
    fireEvent.click(second)
    await waitFor(() => expect(create).not.toBeDisabled())
    expect(screen.queryByText("messenger:error.minMembers")).toBeNull()
    fireEvent.click(create)
    expect(onCreateGroup).toHaveBeenCalledWith("Project", ["one", "two"])
    fireEvent.click(screen.getAllByRole("button", { name: /messenger:removeMember/ })[0]!)
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "false")
    expect(container.querySelector(".max-w-96")).toBeNull()
  })

  it("renders user error retry motion and no-results branch without ambiguity", async () => {
    state.get.mockRejectedValueOnce(new Error("offline"))
    render(<NewChatModal open onClose={() => {}} onSelect={() => {}} />, { wrapper })
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "offline" },
    })
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveAttribute("aria-live", "assertive")
    expect(alert.querySelector(".messenger-card-matte")).toHaveStyle({
      background: "var(--messenger-card-bg)",
    })
    const retry = screen.getByRole("button", { name: "messenger:error.retry" })
    expect(attr(retry, "data-motion-while-hover")).toBe(JSON.stringify({ scale: 1.04 }))
    expect(attr(retry, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.96 }))
    state.get.mockResolvedValueOnce({ data: [] })
    fireEvent.click(retry)
    expect(await screen.findByText("messenger:noUsersFound")).toHaveClass(
      "text-sm",
      "font-bold",
      "text-(--text-secondary)"
    )
  })
})
