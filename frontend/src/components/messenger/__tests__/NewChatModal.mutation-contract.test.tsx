import type { ReactNode } from "react"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  reduced: false,
  get: vi.fn(),
  focusTrap: vi.fn((options: unknown) => {
    void options
    return { current: null }
  }),
  translationCalls: vi.fn(),
  debounceCalls: vi.fn(),
  mediaQueries: vi.fn(),
}))

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
  useTranslation: (namespaces: unknown) => {
    state.translationCalls(namespaces)
    return {
      t: (key: string, options?: Record<string, unknown>) =>
        options ? `${key}|${JSON.stringify(options)}` : key,
    }
  },
}))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    state.mediaQueries(query)
    return state.reduced
  },
}))
vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: unknown) => {
    state.focusTrap(options)
    return { current: null }
  },
}))
vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: <T,>(value: T, strategy?: unknown) => {
    state.debounceCalls(value, strategy)
    return value
  },
}))
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
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"

let latestQueryClient: QueryClient
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={latestQueryClient}>{children}</QueryClientProvider>
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
  state.focusTrap.mockReset()
  state.translationCalls.mockReset()
  state.debounceCalls.mockReset()
  state.mediaQueries.mockReset()
  latestQueryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
})
afterEach(() => vi.restoreAllMocks())

describe("NewChatModal motion/layout mutation contract", () => {
  it("keeps translation namespaces, debounce strategy, and motion media query explicit", () => {
    render(<NewChatModal open onClose={() => {}} onSelect={() => {}} />, { wrapper })

    expect(state.translationCalls).toHaveBeenCalledWith(["messenger", "common"])
    expect(state.debounceCalls).toHaveBeenCalledWith("", "search")
    expect(state.mediaQueries).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
  })

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
    fireEvent.click(dialog.querySelector("h3")!)
    fireEvent.click(dialog.firstElementChild!)
    expect(onClose).not.toHaveBeenCalled()
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
    expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
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
    expect(direct).toHaveClass("bg-(--color-violet-500)", "text-(--color-white)")
    expect(group).toHaveClass("text-(--text-secondary)")
    fireEvent.click(group)
    expect(screen.getByRole("heading", { name: "messenger:newGroup" })).toBeInTheDocument()
    const groupName = screen.getByRole("textbox", { name: "messenger:groupName" })
    expect(groupName).toHaveAttribute("maxlength", "128")
    expect(groupName).toHaveValue("")
    expect(groupName).toHaveAttribute("placeholder", "messenger:groupName")
    const searchInput = screen.getByRole("textbox", { name: "messenger:searchUsers" })
    expect(searchInput).toHaveAttribute("placeholder", "messenger:searchUsers")
    expect(group).toHaveClass("bg-(--color-violet-500)", "text-(--color-white)")
    expect(direct).toHaveClass("text-(--text-secondary)")
    expect(screen.queryByLabelText("messenger:selectMembers")).toBeNull()
    fireEvent.change(groupName, { target: { value: "  Project  " } })
    fireEvent.change(searchInput, {
      target: { value: "user" },
    })
    const first = await screen.findByRole("option", { name: /User one/ })
    expect(first.querySelector("img")).toHaveAttribute("src", "https://cdn.example/avatar.png")
    const secondBeforeSelection = await screen.findByRole("option", { name: /User two/ })
    expect(secondBeforeSelection.querySelector("img")).toHaveAttribute(
      "src",
      AVATAR_PLACEHOLDER_URL
    )
    expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
    expect(attr(first, "data-motion-while-hover")).toBe(
      JSON.stringify({ x: 4, backgroundColor: "var(--bg-surface-hover)" })
    )
    expect(attr(first, "data-motion-while-tap")).toBe(JSON.stringify({ scale: 0.98 }))
    expect(first).toHaveAttribute("aria-selected", "false")
    expect(first).not.toHaveClass("bg-(--messenger-active-bg)")
    expect(within(first).queryByText("User one")).toBeInTheDocument()
    fireEvent.click(first)
    expect(first).toHaveAttribute("aria-selected", "true")
    expect(first).toHaveClass("bg-(--messenger-active-bg)")
    const firstChip = screen.getByRole("button", {
      name: 'messenger:removeMember|{"name":"User one"}',
    })
    expect(screen.getByLabelText("messenger:selectMembers")).toBeInTheDocument()
    expect(firstChip).toHaveClass("matte-chip", "min-h-[44px]", "rounded-full")
    expect(firstChip.querySelector("img")).toHaveAttribute("src", "https://cdn.example/avatar.png")
    expect(first.querySelector("img")).toBeInTheDocument()
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
    const secondChip = screen.getByRole("button", {
      name: 'messenger:removeMember|{"name":"User two"}',
    })
    expect(secondChip.querySelector("img")).toHaveAttribute("src", AVATAR_PLACEHOLDER_URL)
    expect(within(second).getByText("User two")).toBeInTheDocument()
    expect(within(second).getByText("two@example.test")).toBeInTheDocument()
    expect(second.querySelector("img")).toBeInTheDocument()
    expect(second.querySelector('span[aria-hidden="true"]')).toBeInTheDocument()
    expect(second.querySelector('span[aria-hidden="true"]')).toHaveClass(
      "border-(--color-violet-500)",
      "bg-(--color-violet-500)",
      "text-(--color-white)"
    )
    expect(second.querySelector('span[aria-hidden="true"] svg')).toBeInTheDocument()
    expect(screen.getByLabelText("messenger:selectMembers")).toHaveTextContent("User one")
    expect(screen.getByLabelText("messenger:selectMembers")).toHaveTextContent("User two")
    fireEvent.click(create)
    expect(onCreateGroup).toHaveBeenCalledWith("Project", ["one", "two"])
    fireEvent.click(screen.getAllByRole("button", { name: /messenger:removeMember/ })[0]!)
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "false")
    expect(
      screen.getByRole("button", { name: 'messenger:removeMember|{"name":"User two"}' })
    ).toBeInTheDocument()
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true")
    expect(screen.getAllByRole("option")[0]).not.toHaveClass("bg-(--messenger-active-bg)")
    expect(screen.getAllByRole("option")[0]?.className).not.toContain("Stryker")
    expect(screen.getAllByRole("option")[0]?.querySelector('span[aria-hidden="true"]')).toHaveClass(
      "border-(--glass-border)"
    )
    expect(
      screen.getAllByRole("option")[0]?.querySelector('span[aria-hidden="true"] svg')
    ).toBeNull()
    expect(container.querySelector(".max-w-96")).toBeNull()
  })

  it("clears group drafts and selected members before the next open", async () => {
    state.get.mockResolvedValue({ data: [user("one")] })
    const { rerender } = render(
      <NewChatModal open onClose={() => {}} onSelect={() => {}} onCreateGroup={() => {}} />,
      { wrapper }
    )

    fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:groupName" }), {
      target: { value: "Temporary group" },
    })
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "one" },
    })
    fireEvent.click(await screen.findByRole("option", { name: /User one/ }))
    expect(screen.getByRole("button", { name: /messenger:removeMember/ })).toBeInTheDocument()

    rerender(
      <NewChatModal open={false} onClose={() => {}} onSelect={() => {}} onCreateGroup={() => {}} />
    )
    rerender(<NewChatModal open onClose={() => {}} onSelect={() => {}} onCreateGroup={() => {}} />)

    expect(screen.getByRole("heading", { name: "messenger:newChat" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))
    expect(screen.getByRole("textbox", { name: "messenger:groupName" })).toHaveValue("")
    expect(screen.queryByRole("button", { name: /messenger:removeMember/ })).toBeNull()
  })

  it("keeps DM rows single-select and group rows checkbox-selectable", async () => {
    state.get.mockResolvedValue({ data: [user("one"), user("two")] })
    const onSelect = vi.fn()
    render(<NewChatModal open onClose={() => {}} onSelect={onSelect} onCreateGroup={() => {}} />, {
      wrapper,
    })
    const searchInput = screen.getByRole("textbox", { name: "messenger:searchUsers" })
    fireEvent.change(searchInput, { target: { value: "users" } })
    const directRow = await screen.findByRole("option", { name: /User one/ })
    expect(directRow).toHaveAttribute("aria-selected", "false")
    expect(directRow.querySelector('span[aria-hidden="true"]')).toBeNull()
    fireEvent.click(directRow)
    expect(onSelect).toHaveBeenCalledWith("one")

    fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))
    const groupRow = screen.getByRole("option", { name: /User one/ })
    expect(groupRow).toHaveAttribute("aria-selected", "false")
    const checkbox = groupRow.querySelector('span[aria-hidden="true"]')!
    expect(checkbox).toHaveClass("border-(--glass-border)")
    expect(checkbox.querySelector("svg")).toBeNull()

    fireEvent.click(groupRow)
    expect(groupRow).toHaveAttribute("aria-selected", "true")
    expect(groupRow).toHaveClass("bg-(--messenger-active-bg)")
    expect(checkbox).toHaveClass(
      "border-(--color-violet-500)",
      "bg-(--color-violet-500)",
      "text-(--color-white)"
    )
    expect(checkbox.querySelector("svg")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /messenger:removeMember.*User one/ })
    ).toBeInTheDocument()

    fireEvent.click(groupRow)
    expect(groupRow).toHaveAttribute("aria-selected", "false")
    expect(groupRow).not.toHaveClass("bg-(--messenger-active-bg)")
    expect(checkbox).toHaveClass("border-(--glass-border)")
    expect(checkbox.querySelector("svg")).toBeNull()
    expect(screen.queryByRole("button", { name: /messenger:removeMember.*User one/ })).toBeNull()
  })

  it("renders user error retry motion and no-results branch without ambiguity", async () => {
    state.get.mockRejectedValueOnce(new Error("offline"))
    render(<NewChatModal open onClose={() => {}} onSelect={() => {}} />, { wrapper })
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "offline" },
    })
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveAttribute("aria-live", "assertive")
    expect(screen.queryByText("messenger:noUsersFound")).toBeNull()
    expect(alert.querySelector("h4")).toHaveTextContent("messenger:error.failedToLoadUsers")
    expect(alert).toHaveTextContent("messenger:error.failedToLoadUsersHint")
    expect(alert.querySelector(".messenger-card-matte")).toHaveStyle({
      background: "var(--messenger-card-bg)",
    })
    expect(alert.querySelector("svg")).toHaveStyle({ opacity: "var(--opacity-strong)" })
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

  it("keeps group submit guards exact for whitespace, member count and in-flight state", async () => {
    state.get.mockResolvedValue({ data: [user("one"), user("two"), user("three")] })
    const onCreateGroup = vi.fn()
    const { rerender } = render(
      <NewChatModal open onClose={() => {}} onSelect={() => {}} onCreateGroup={onCreateGroup} />,
      { wrapper }
    )
    fireEvent.click(screen.getByRole("tab", { name: "messenger:modeGroup" }))
    const name = screen.getByRole("textbox", { name: "messenger:groupName" })
    const create = screen.getByRole("button", { name: "messenger:createGroup" })
    expect(create).toBeDisabled()

    fireEvent.change(name, { target: { value: "   " } })
    fireEvent.change(screen.getByRole("textbox", { name: "messenger:searchUsers" }), {
      target: { value: "us" },
    })
    const options = await screen.findAllByRole("option")
    fireEvent.click(options[0]!)
    expect(create).toBeDisabled()

    // A valid member count must not bypass the whitespace-only name guard.
    fireEvent.click(options[1]!)
    expect(create).toBeDisabled()
    fireEvent.change(name, { target: { value: "A" } })
    await waitFor(() => expect(create).not.toBeDisabled())
    fireEvent.click(create)
    expect(onCreateGroup).toHaveBeenCalledWith("A", ["one", "two"])

    rerender(
      <NewChatModal
        open
        onClose={() => {}}
        onSelect={() => {}}
        onCreateGroup={onCreateGroup}
        isCreatingGroup
      />
    )
    const creating = screen.getByRole("button", { name: "messenger:creatingGroup" })
    expect(creating).toBeDisabled()
  })

  it("uses the two-character query boundary and keeps focus-trap options explicit", async () => {
    const { rerender } = render(
      <NewChatModal open={false} onClose={() => {}} onSelect={() => {}} />,
      { wrapper }
    )
    expect(state.focusTrap).toHaveBeenCalledWith(
      expect.objectContaining({ active: false, initialFocus: false, returnFocus: true })
    )

    rerender(<NewChatModal open onClose={() => {}} onSelect={() => {}} />)
    const input = screen.getByRole("textbox", { name: "messenger:searchUsers" })
    fireEvent.change(input, { target: { value: "a" } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(state.get).not.toHaveBeenCalled()
    expect(screen.queryByText("messenger:noUsersFound")).toBeNull()

    state.get.mockResolvedValue({ data: [] })
    fireEvent.change(input, { target: { value: "ab" } })
    await waitFor(() => expect(state.get).toHaveBeenCalledTimes(1))
    expect(state.get).toHaveBeenCalledWith("/users?limit=10&search=ab")
    await waitFor(() => expect(latestQueryClient?.getQueryData(["users", "ab"])).toEqual([]))
    expect(latestQueryClient?.getQueryData(["", "ab"])).toBeUndefined()
    expect(state.focusTrap).toHaveBeenLastCalledWith(
      expect.objectContaining({ active: true, initialFocus: false, returnFocus: true })
    )
  })

  it("schedules autofocus only while open and cancels the stale frame on close", () => {
    const requestAnimationFrame = vi.fn().mockReturnValue(17)
    const cancelAnimationFrame = vi.fn()
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame)
    vi.stubGlobal("cancelAnimationFrame", cancelAnimationFrame)
    try {
      const { rerender } = render(
        <NewChatModal open={false} onClose={() => {}} onSelect={() => {}} />,
        { wrapper }
      )
      expect(requestAnimationFrame).not.toHaveBeenCalled()
      rerender(<NewChatModal open onClose={() => {}} onSelect={() => {}} />)
      expect(requestAnimationFrame).toHaveBeenCalledTimes(1)
      rerender(<NewChatModal open={false} onClose={() => {}} onSelect={() => {}} />)
      expect(cancelAnimationFrame).toHaveBeenCalledWith(17)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("does not dereference the search input after a scheduled autofocus is cancelled", () => {
    let callback: FrameRequestCallback | undefined
    const requestAnimationFrame = vi.fn((next: FrameRequestCallback) => {
      callback = next
      return 17
    })
    const cancelAnimationFrame = vi.fn()
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame)
    vi.stubGlobal("cancelAnimationFrame", cancelAnimationFrame)
    try {
      const { rerender } = render(<NewChatModal open onClose={() => {}} onSelect={() => {}} />, {
        wrapper,
      })
      expect(requestAnimationFrame).toHaveBeenCalledTimes(1)
      rerender(<NewChatModal open={false} onClose={() => {}} onSelect={() => {}} />)

      expect(() => callback?.(performance.now())).not.toThrow()
      expect(cancelAnimationFrame).toHaveBeenCalledWith(17)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
