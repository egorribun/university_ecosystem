import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { useNotifications } from "@/hooks/useNotifications"
import NotificationsBell, {
  canUpdateNotificationPosition,
  focusNotificationTrigger,
  shouldCloseNotificationDropdown,
} from "../feedback/NotificationsBell"

const useNotificationsMock = vi.fn()
const motionState = vi.hoisted(() => ({ reducedMotion: false }))
const translationState = vi.hoisted(() => ({ namespaces: [] as unknown[] }))
const mediaQueryState = vi.hoisted(() => ({ queries: [] as string[] }))

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => useNotificationsMock(),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    mediaQueryState.queries.push(query)
    return motionState.reducedMotion
  },
}))

const translations: Record<string, string> = {
  "system:notificationsBell.open": "Open notifications",
  "system:notificationsBell.title": "Notifications",
  "system:notificationsBell.new": "New",
  "system:notificationsBell.markAll": "Mark all as read",
  "system:notificationsBell.clear": "Clear",
  "system:notificationsBell.loading": "Loading…",
  "system:notificationsBell.empty": "Nothing yet",
  "system:notificationsBell.error": "Error loading notifications",
  "system:notificationsBell.markRead": "Mark as read",
  "system:notificationsBell.loadMore": "Load more",
  "system:notificationsBell.loadingMore": "Loading more…",
  "system:notificationsBell.loadMoreError": "Couldn't load more notifications",
  "system:errorBoundary.retry": "Try again",
}

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    translationState.namespaces.push(namespaces)
    return {
      t: (key: string) => translations[key] ?? key,
    }
  },
}))

// Mock framer-motion to avoid animation issues in tests
vi.mock("framer-motion", () => {
  const motionComponent = (Tag: string) => {
    const Component = ({
      children,
      className,
      onClick,
      ...props
    }: React.ComponentProps<"div"> & { [key: string]: unknown }) => {
      // Filter out framer-motion specific props
      const filteredProps = { ...props }
      const motionVariants = filteredProps.variants
      const motionInitial = filteredProps.initial
      const motionAnimate = filteredProps.animate
      const motionExit = filteredProps.exit
      const motionProps = [
        "initial",
        "animate",
        "exit",
        "variants",
        "transition",
        "whileHover",
        "whileTap",
        "whileFocus",
        "whileDrag",
        "whileInView",
        "viewport",
        "layout",
        "layoutId",
      ]
      motionProps.forEach((prop) => delete filteredProps[prop])
      if (motionVariants !== undefined) {
        filteredProps["data-motion-variants"] = JSON.stringify(motionVariants)
      }
      if (motionInitial !== undefined) filteredProps["data-motion-initial"] = String(motionInitial)
      if (motionAnimate !== undefined) filteredProps["data-motion-animate"] = String(motionAnimate)
      if (motionExit !== undefined) filteredProps["data-motion-exit"] = String(motionExit)

      const Element = Tag as React.ElementType
      return (
        <Element className={className} onClick={onClick} {...filteredProps}>
          {children}
        </Element>
      )
    }
    Component.displayName = `Motion(${Tag})`
    return Component as unknown as React.ComponentType<unknown>
  }

  // Wave 124 SW1 — also expose `m` (LazyMotion minimal component) since
  // production code now uses `<m.X>` JSX after the framer-motion → m bulk
  // swap. Same proxy shape as `motion` so any tag works.
  const motionProxy = {
    div: motionComponent("div"),
    button: motionComponent("button"),
    span: motionComponent("span"),
  }
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    LazyMotion: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    MotionConfig: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    domAnimation: {},
    domMax: {},
    motion: motionProxy,
    m: motionProxy,
    useReducedMotion: () => motionState.reducedMotion,
  }
})

describe("NotificationsBell", () => {
  type NotificationsState = ReturnType<typeof useNotifications>

  const baseState = (): NotificationsState => ({
    data: [],
    unreadCount: 0,
    hasMore: false,
    nextCursor: null,
    isLoading: false,
    isError: false,
    error: null,
    isRefetching: false,
    refetch: vi.fn(),
    markRead: vi.fn(),
    markAll: vi.fn(),
    clearAll: vi.fn(),
    isMarkingAll: false,
    isClearing: false,
    fetchMore: vi.fn(),
    isFetchingMore: false,
    isFetchMoreError: false,
    fetchMoreError: null,
  })

  beforeEach(() => {
    useNotificationsMock.mockReset()
    motionState.reducedMotion = false
    translationState.namespaces.length = 0
    mediaQueryState.queries.length = 0
  })

  it("starts closed and loads notification strings from the system namespace", () => {
    useNotificationsMock.mockReturnValue(baseState())
    const addEventListener = vi.spyOn(window, "addEventListener")
    render(<NotificationsBell />)

    const trigger = screen.getByRole("button", { name: "Open notifications" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(trigger).not.toHaveAttribute("data-unread")
    expect(document.querySelector(".animate-ping")).not.toBeInTheDocument()
    expect(translationState.namespaces).toContainEqual(["system"])
    expect(mediaQueryState.queries).toContain("(prefers-reduced-motion: reduce)")
    expect(addEventListener.mock.calls.some(([type]) => String(type) === "resize")).toBe(false)
    addEventListener.mockRestore()
  })

  it("keeps positioning, focus, and outside-click guards total for missing nodes", () => {
    const trigger = document.createElement("button")
    const dropdown = document.createElement("div")
    const outside = document.createElement("span")
    document.body.append(trigger, dropdown, outside)
    const focus = vi.spyOn(trigger, "focus")

    expect(canUpdateNotificationPosition(false, null)).toBe(false)
    expect(canUpdateNotificationPosition(false, trigger)).toBe(false)
    expect(canUpdateNotificationPosition(true, null)).toBe(false)
    expect(canUpdateNotificationPosition(true, trigger)).toBe(true)

    focusNotificationTrigger(null)
    expect(focus).not.toHaveBeenCalled()
    focusNotificationTrigger(trigger)
    expect(focus).toHaveBeenCalledTimes(1)

    expect(shouldCloseNotificationDropdown(false, trigger, dropdown, outside)).toBe(false)
    expect(shouldCloseNotificationDropdown(true, null, dropdown, outside)).toBe(false)
    expect(shouldCloseNotificationDropdown(true, trigger, null, outside)).toBe(false)
    expect(shouldCloseNotificationDropdown(true, trigger, dropdown, trigger)).toBe(false)
    expect(shouldCloseNotificationDropdown(true, trigger, dropdown, dropdown)).toBe(false)
    expect(shouldCloseNotificationDropdown(true, trigger, dropdown, outside)).toBe(true)

    trigger.remove()
    dropdown.remove()
    outside.remove()
  })

  it("does not render an unread badge when the count is zero", async () => {
    const state = baseState()
    state.data = [
      {
        id: "read-only",
        title: "Read update",
        body: "No badge expected",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    useNotificationsMock.mockReturnValue(state)
    const user = userEvent.setup()
    render(<NotificationsBell />)

    await user.click(screen.getByRole("button", { name: "Open notifications" }))
    expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument()
    expect(screen.queryByText(/New$/)).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open notifications" })).not.toHaveAttribute(
      "data-unread"
    )
  })

  it("does not access the DOM while rendering on the server", () => {
    useNotificationsMock.mockReturnValue(baseState())
    const serverDocument = globalThis.document
    vi.stubGlobal("document", undefined)
    try {
      expect(() => renderToString(<NotificationsBell />)).not.toThrow()
    } finally {
      vi.stubGlobal("document", serverDocument)
    }
  })

  it("exposes dialog state and closes with Escape while restoring trigger focus", async () => {
    useNotificationsMock.mockReturnValue(baseState())
    const user = userEvent.setup()
    render(<NotificationsBell />)
    const trigger = screen.getByRole("button", { name: "Open notifications" })

    await user.click(trigger)
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Mark all as read" })).toHaveAttribute(
      "aria-label",
      "Mark all as read"
    )
    expect(screen.getByRole("button", { name: "Mark all as read" })).toHaveAttribute(
      "title",
      "Mark all as read"
    )
    expect(screen.getByRole("button", { name: "Clear" })).toHaveAttribute("aria-label", "Clear")
    expect(screen.getByRole("button", { name: "Clear" })).toHaveAttribute("title", "Clear")

    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("keeps the dialog open for non-Escape keys under reduced motion", async () => {
    motionState.reducedMotion = true
    useNotificationsMock.mockReturnValue(baseState())
    const user = userEvent.setup()
    render(<NotificationsBell />)

    await user.click(screen.getByRole("button", { name: "Open notifications" }))
    fireEvent.keyDown(document, { key: "Enter" })

    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument()
  })

  it("renders an error message and disables bulk actions when loading fails", async () => {
    const state = baseState()
    state.isError = true
    state.error = new Error("failed")
    const refetch = vi.fn()
    state.refetch = refetch
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)

    const openButton = screen.getByRole("button", { name: "Open notifications" })
    await user.click(openButton)

    expect(screen.getByText("Error loading notifications")).toBeInTheDocument()

    const markAllButton = screen.getByTitle("Mark all as read")
    const clearButton = screen.getByTitle("Clear")

    expect(markAllButton).toBeDisabled()
    expect(clearButton).toBeDisabled()
  })

  it("retries fetching notifications when requested", async () => {
    const state = baseState()
    state.isError = true
    const refetch = vi.fn()
    state.refetch = refetch
    useNotificationsMock.mockImplementation(() => state)

    const user = userEvent.setup()
    render(<NotificationsBell />)

    const openButton = screen.getByRole("button", { name: "Open notifications" })
    await user.click(openButton)

    const retryButton = screen.getByRole("button", { name: "Try again" })
    await user.click(retryButton)

    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it("renders pagination controls and requests more notifications", async () => {
    const state = baseState()
    state.data = [
      {
        id: "uuid-1",
        title: "Welcome",
        body: "",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    state.hasMore = true
    state.nextCursor = "cursor-123"
    const fetchMore = vi.fn()
    state.fetchMore = fetchMore
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)

    const openButton = screen.getByRole("button", { name: "Open notifications" })
    await user.click(openButton)

    const loadMoreButton = screen.getByRole("button", { name: "Load more" })
    await user.click(loadMoreButton)

    expect(fetchMore).toHaveBeenCalledWith("cursor-123")
  })

  it("disables the pagination button while loading more", async () => {
    const state = baseState()
    state.data = [
      {
        id: "uuid-1",
        title: "Welcome",
        body: "",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    state.hasMore = true
    state.nextCursor = "cursor-123"
    state.isFetchingMore = true
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)

    const openButton = screen.getByRole("button", { name: "Open notifications" })
    await user.click(openButton)

    const loadMoreButton = screen.getByRole("button", { name: "Loading more…" })
    expect(loadMoreButton).toBeDisabled()
  })

  it("disables pagination when the server advertises more data without a cursor", async () => {
    const state = baseState()
    state.data = [
      {
        id: "uuid-no-cursor",
        title: "Welcome",
        body: "",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    state.hasMore = true
    state.nextCursor = null
    const fetchMore = vi.fn()
    state.fetchMore = fetchMore
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    const loadMoreButton = screen.getByRole("button", { name: "Load more" })
    expect(loadMoreButton).toBeDisabled()
    await user.click(loadMoreButton)
    expect(fetchMore).not.toHaveBeenCalled()
  })

  it("surfaces pagination errors to the user", async () => {
    const state = baseState()
    state.data = [
      {
        id: "uuid-1",
        title: "Welcome",
        body: "",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    state.hasMore = true
    state.isFetchMoreError = true
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)

    const openButton = screen.getByRole("button", { name: "Open notifications" })
    await user.click(openButton)

    expect(screen.getByText("Couldn't load more notifications")).toBeInTheDocument()
  })

  it("renders the initial loading state while a refetching error is in flight", async () => {
    const state = baseState()
    state.isLoading = true
    state.isError = true
    state.isRefetching = true
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    expect(document.querySelector(".animate-spin")).toBeInTheDocument()
  })

  it("handles unread links, read markers, and notification icon variants", async () => {
    const state = baseState()
    const markRead = vi.fn()
    state.markRead = markRead
    state.data = [
      {
        id: "chat-1",
        title: "Unread chat",
        body: "New message",
        created_at: "2024-01-01T00:00:00Z",
        read: false,
        type: "chat.message",
      },
      {
        id: "schedule-1",
        title: "Unread reminder",
        body: "Lesson starts soon",
        created_at: "2024-01-01T00:00:00Z",
        read: false,
        type: "schedule.reminder",
        link: "/schedule",
      },
      {
        id: "other-1",
        title: "Read update",
        body: "A general update",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    const chatLink = screen.getByText("Unread chat").closest("a")!
    const scheduleLink = screen.getByText("Unread reminder").closest("a")!
    const readLink = screen.getByText("Read update").closest("a")!
    expect(chatLink).toHaveAttribute("href", "#")
    expect(chatLink).toHaveClass("flex", "gap-3", "cursor-default")
    expect(scheduleLink).toHaveAttribute("href", "/schedule")
    expect(scheduleLink).toHaveClass("cursor-pointer")
    expect(readLink).toHaveAttribute("href", "#")
    expect(readLink).toHaveClass("cursor-default")

    const chatRow = chatLink.parentElement!
    const scheduleRow = scheduleLink.parentElement!
    const readRow = readLink.parentElement!
    expect(chatRow).toHaveClass("relative", "group", "bg-brand/(--opacity-faint)")
    expect(readRow).not.toHaveClass("bg-brand/(--opacity-faint)")
    expect(readRow.className).toBe(
      "relative group border-b border-glass-border last:border-0 p-4 transition-all hover:bg-(--text-secondary)/(--opacity-faint)"
    )
    expect(chatLink.children[0]).toHaveClass(
      "w-8",
      "h-8",
      "rounded-full",
      "bg-brand/(--opacity-subtle)",
      "text-brand",
      "dark:text-brand"
    )
    expect(readLink.children[0]).toHaveClass(
      "w-8",
      "h-8",
      "rounded-full",
      "bg-(--border-subtle)",
      "text-(--text-secondary)"
    )
    expect(chatLink.querySelector("svg")).toHaveClass("lucide-message-circle")
    expect(scheduleLink.querySelector("svg")).toHaveClass("lucide-calendar")
    expect(readLink.querySelector("svg")).toHaveClass("lucide-bell")
    expect(screen.getByText("Unread chat")).toHaveClass("text-text-primary")
    expect(screen.getByText("Read update")).toHaveClass("text-(--text-secondary)")
    expect(screen.getByText("Unread chat")).toHaveClass("text-sm", "font-medium", "leading-tight")
    expect(chatRow.querySelector("svg")?.outerHTML).not.toBe(
      scheduleRow.querySelector("svg")?.outerHTML
    )
    expect(scheduleRow.querySelector("svg")?.outerHTML).not.toBe(
      readRow.querySelector("svg")?.outerHTML
    )
    const itemVariants = JSON.parse(chatRow.getAttribute("data-motion-variants") ?? "null") as {
      hidden: { opacity: number; x: number }
      visible: { opacity: number; x: number }
    }
    expect(itemVariants.hidden).toMatchObject({ opacity: 0, x: -10 })
    expect(itemVariants.visible).toMatchObject({ opacity: 1, x: 0 })

    await user.click(screen.getByText("Unread chat"))
    expect(markRead).toHaveBeenCalledWith("chat-1")

    const noLinkClick = new MouseEvent("click", { bubbles: true, cancelable: true })
    fireEvent(chatLink, noLinkClick)
    expect(noLinkClick.defaultPrevented).toBe(true)
    expect(markRead).toHaveBeenCalledTimes(2)

    fireEvent.click(screen.getByText("Unread reminder"))
    expect(markRead).toHaveBeenCalledWith("schedule-1")

    fireEvent.click(screen.getByText("Read update"))
    expect(markRead).toHaveBeenCalledTimes(3)

    const markButtons = screen.getAllByTitle("Mark as read")
    expect(markButtons).toHaveLength(2)
    expect(markButtons[0]).toHaveClass(
      "absolute",
      "top-2",
      "right-2",
      "min-h-11",
      "min-w-11",
      "opacity-0",
      "group-hover:opacity-100",
      "focus:opacity-100"
    )
    markRead.mockClear()
    const markReadClick = new MouseEvent("click", { bubbles: true, cancelable: true })
    fireEvent(markButtons[0]!, markReadClick)
    expect(markReadClick.defaultPrevented).toBe(true)
    expect(markRead).toHaveBeenCalledTimes(1)
    expect(markRead).toHaveBeenCalledWith("chat-1")
  })

  it("keeps linked notification clicks cancellable only when no destination exists", async () => {
    const state = baseState()
    state.data = [
      {
        id: "linked-click",
        title: "Linked update",
        body: "Open the destination",
        created_at: "2024-01-01T00:00:00Z",
        read: false,
        link: "/news/linked-click",
      },
    ]
    const markRead = vi.fn()
    state.markRead = markRead
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    const link = screen.getByRole("link", { name: /Linked update Open the destination/ })
    const click = new MouseEvent("click", { bubbles: true, cancelable: true })
    fireEvent(link, click)

    expect(click.defaultPrevented).toBe(false)
    expect(markRead).toHaveBeenCalledWith("linked-click")
  })

  it("uses the localized new-notifications label for the unread badge", async () => {
    const state = baseState()
    state.unreadCount = 2
    state.data = [
      {
        id: "unread-1",
        title: "Unread update",
        body: "A new update",
        created_at: "2024-01-01T00:00:00Z",
        read: false,
      },
    ]
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    expect(screen.getByText("2 New")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open notifications" })).toHaveAttribute(
      "data-unread",
      ""
    )
    expect(document.querySelector(".animate-ping")).toBeInTheDocument()
  })

  it("reflects open state in the trigger styling and bell rotation", async () => {
    useNotificationsMock.mockReturnValue(baseState())
    const user = userEvent.setup()
    render(<NotificationsBell />)
    const trigger = screen.getByRole("button", { name: "Open notifications" })
    const bell = trigger.querySelector("svg")

    expect(trigger).toHaveClass("relative", "nav-action-btn", "group", "text-text-primary")
    expect(trigger).toHaveClass("hover:text-(--primary-main)")
    expect(bell).toHaveClass("nav-action-icon", "bell-wiggle")
    expect(bell).not.toHaveClass("rotate-[-10deg]")

    await user.click(trigger)
    expect(trigger).toHaveClass(
      "bg-(--primary-main)/(--opacity-subtle)",
      "!border-(--primary-main)/(--opacity-soft)",
      "shadow-sm",
      "text-(--primary-main)"
    )
    expect(bell).toHaveClass("rotate-[-10deg]")

    await user.click(trigger)
    expect(trigger).toHaveClass("text-text-primary", "hover:text-(--primary-main)")
    expect(bell).not.toHaveClass("rotate-[-10deg]")
  })

  it("uses the trigger geometry and desktop breakpoint at exactly 640px", async () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 640,
    })
    const state = baseState()
    useNotificationsMock.mockReturnValue(state)

    const user = userEvent.setup()
    render(<NotificationsBell />)
    const trigger = screen.getByRole("button", { name: "Open notifications" })
    vi.spyOn(trigger, "getBoundingClientRect").mockReturnValue({
      top: 10,
      left: 20,
      right: 100,
      bottom: 42,
      width: 80,
      height: 32,
      x: 20,
      y: 10,
      toJSON: () => ({}),
    })

    await user.click(trigger)
    const dropdown = screen.getByRole("dialog", { name: "Notifications" })
    expect(dropdown).toHaveStyle({ top: "54px", right: "540px" })
    expect(dropdown).not.toHaveStyle({ width: "calc(100vw - 2rem)" })

    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 1024,
    })
  })

  it("installs and removes the Escape listener only while open", async () => {
    useNotificationsMock.mockReturnValue(baseState())
    const addEventListener = vi.spyOn(document, "addEventListener")
    const removeEventListener = vi.spyOn(document, "removeEventListener")
    const user = userEvent.setup()
    render(<NotificationsBell />)

    expect(addEventListener.mock.calls.filter(([type]) => type === "keydown")).toHaveLength(0)

    await user.click(screen.getByRole("button", { name: "Open notifications" }))
    const keydownRegistration = addEventListener.mock.calls.find(([type]) => type === "keydown")
    expect(keydownRegistration).toBeDefined()

    await user.keyboard("{Escape}")
    expect(removeEventListener).toHaveBeenCalledWith("keydown", keydownRegistration?.[1])
  })

  it("removes the exact resize handler when the dropdown closes", async () => {
    useNotificationsMock.mockReturnValue(baseState())
    const addEventListener = vi.spyOn(window, "addEventListener")
    const removeEventListener = vi.spyOn(window, "removeEventListener")
    const user = userEvent.setup()
    render(<NotificationsBell />)
    const trigger = screen.getByRole("button", { name: "Open notifications" })

    await user.click(trigger)
    const resizeRegistration = addEventListener.mock.calls.find(
      ([type]) => String(type) === "resize"
    )
    expect(resizeRegistration).toBeDefined()

    await user.click(trigger)
    expect(removeEventListener).toHaveBeenCalledWith("resize", resizeRegistration?.[1])
  })

  it("keeps bulk actions disabled for each in-flight mutation with notifications present", async () => {
    const state = baseState()
    state.data = [
      {
        id: "uuid-1",
        title: "Welcome",
        body: "Hello",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    useNotificationsMock.mockReturnValue(state)
    const user = userEvent.setup()
    const rendered = render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    for (const field of [
      "isLoading",
      "isError",
      "isRefetching",
      "isMarkingAll",
      "isClearing",
    ] as const) {
      state[field] = true
      rendered.rerender(<NotificationsBell />)
      expect(screen.getByTitle("Mark all as read")).toBeDisabled()
      expect(screen.getByTitle("Clear")).toBeDisabled()
      state[field] = false
      rendered.rerender(<NotificationsBell />)
    }
  })

  it("renders existing notifications instead of a spinner during background loading", async () => {
    const state = baseState()
    state.isLoading = true
    state.data = [
      {
        id: "uuid-1",
        title: "Welcome",
        body: "Hello",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    useNotificationsMock.mockReturnValue(state)
    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    expect(screen.getByText("Welcome")).toBeInTheDocument()
    expect(document.querySelector(".animate-spin")).not.toBeInTheDocument()
  })

  it("renders the compact empty state when there are no notifications", async () => {
    useNotificationsMock.mockReturnValue(baseState())
    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    expect(screen.getByText("Nothing yet")).toBeInTheDocument()
    const emptyMessage = screen.getByText("Nothing yet")
    expect(emptyMessage).toHaveClass("text-sm", "opacity-medium", "font-medium")
    expect(emptyMessage.parentElement).toHaveClass(
      "p-12",
      "text-center",
      "text-(--text-secondary)",
      "flex",
      "flex-col",
      "items-center",
      "gap-3"
    )
    expect(screen.queryByTitle("Mark as read")).not.toBeInTheDocument()
  })

  it("keeps the panel and bulk-action touch targets on the shared surface contract", async () => {
    const state = baseState()
    state.data = [
      {
        id: "surface-contract",
        title: "Surface contract",
        body: "Verify controls",
        created_at: "2024-01-01T00:00:00Z",
        read: true,
      },
    ]
    useNotificationsMock.mockReturnValue(state)
    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    expect(screen.getByRole("dialog", { name: "Notifications" })).toHaveClass(
      "fixed",
      "z-popover",
      "origin-top-right",
      "max-sm:left-1/2",
      "sm:w-96",
      "bg-glass",
      "backdrop-blur-xl",
      "border",
      "border-glass-border",
      "rounded-2xl",
      "shadow-glass",
      "overflow-hidden",
      "ring-1",
      "ring-black/(--opacity-faint)"
    )
    expect(screen.getByTitle("Mark all as read")).toHaveClass(
      "min-h-11",
      "min-w-11",
      "p-2",
      "text-(--text-secondary)",
      "hover:text-text-primary",
      "hover:bg-(--text-secondary)/(--opacity-faint)",
      "rounded-lg",
      "transition-colors",
      "focus-ring-premium",
      "disabled:opacity-soft",
      "disabled:hover:bg-transparent"
    )
    expect(screen.getByTitle("Clear")).toHaveClass(
      "min-h-11",
      "min-w-11",
      "p-2",
      "text-(--text-secondary)",
      "hover:text-error-text",
      "hover:bg-error-bg/(--opacity-subtle)",
      "rounded-lg",
      "transition-colors",
      "focus-ring-premium",
      "disabled:opacity-soft",
      "disabled:hover:bg-transparent"
    )
  })

  it("exposes exact motion state and reduced-motion variants for the dropdown", async () => {
    motionState.reducedMotion = true
    useNotificationsMock.mockReturnValue(baseState())
    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    const dropdown = screen.getByRole("dialog", { name: "Notifications" })
    expect(dropdown).toHaveAttribute("data-motion-initial", "hidden")
    expect(dropdown).toHaveAttribute("data-motion-animate", "visible")
    expect(dropdown).toHaveAttribute("data-motion-exit", "exit")
    const variants = JSON.parse(dropdown.getAttribute("data-motion-variants") ?? "null") as {
      hidden: { opacity: number; y: number; scale: number; x: number | string }
      visible: {
        opacity: number
        y: number
        scale: number
        x: number | string
        transition: { duration: number; ease: string; staggerChildren: number }
      }
      exit: {
        opacity: number
        y: number
        scale: number
        x: number | string
        transition: { duration: number; ease: string }
      }
    }
    expect(variants.hidden).toMatchObject({ opacity: 0, y: -10, scale: 0.95 })
    expect(variants.visible).toMatchObject({ opacity: 1, y: 0, scale: 1 })
    expect(variants.hidden.x).toBe(0)
    expect(variants.visible.x).toBe(0)
    expect(variants.visible.transition.duration).toBe(0)
    expect(variants.visible.transition).toMatchObject({ ease: "easeOut", staggerChildren: 0.05 })
    expect(variants.exit).toMatchObject({ opacity: 0, y: -10, scale: 0.95 })
    expect(variants.exit.x).toBe(0)
    expect(variants.exit.transition.duration).toBe(0)
    expect(variants.exit.transition.ease).toBe("easeIn")
  })

  it("uses the documented motion durations when reduced motion is not requested", async () => {
    motionState.reducedMotion = false
    useNotificationsMock.mockReturnValue(baseState())
    const user = userEvent.setup()
    render(<NotificationsBell />)
    await user.click(screen.getByRole("button", { name: "Open notifications" }))

    const dropdown = screen.getByRole("dialog", { name: "Notifications" })
    const variants = JSON.parse(dropdown.getAttribute("data-motion-variants") ?? "null") as {
      visible: { transition: { duration: number } }
      exit: { transition: { duration: number } }
    }
    expect(variants.visible.transition.duration).toBe(0.2)
    expect(variants.exit.transition.duration).toBe(0.15)
  })

  describe("dropdown positioning", () => {
    const originalInnerWidth = window.innerWidth

    const setInnerWidth = (width: number) => {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        writable: true,
        value: width,
      })
    }

    afterEach(() => {
      setInnerWidth(originalInnerWidth)
    })

    it("computes desktop coordinates (right offset, no mobile width)", async () => {
      setInnerWidth(1024)
      const state = baseState()
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      await user.click(screen.getByRole("button", { name: "Open notifications" }))

      const dropdown = screen.getByRole("heading", { name: "Notifications" }).closest("div")!
        .parentElement!.parentElement as HTMLElement
      // jsdom getBoundingClientRect is all-zero → top = 0 + 12, right = 1024 - 0
      expect(dropdown.style.top).toBe("12px")
      expect(dropdown.style.right).toBe("1024px")
      // Desktop branch leaves width unset (undefined → empty string)
      expect(dropdown.style.width).toBe("")
    })

    it("computes mobile coordinates (no right offset, viewport-relative width)", async () => {
      setInnerWidth(500)
      const state = baseState()
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      await user.click(screen.getByRole("button", { name: "Open notifications" }))

      const dropdown = screen.getByRole("heading", { name: "Notifications" }).closest("div")!
        .parentElement!.parentElement as HTMLElement
      expect(dropdown.style.top).toBe("12px")
      // Mobile branch sets right to null → undefined → empty string
      expect(dropdown.style.right).toBe("")
      expect(dropdown.style.width).toBe("calc(100vw - 2rem)")
      const variants = JSON.parse(dropdown.getAttribute("data-motion-variants") ?? "null") as {
        hidden: { x: number | string }
        visible: { x: number | string }
        exit: { x: number | string }
      }
      expect(variants.hidden.x).toBe("-50%")
      expect(variants.visible.x).toBe("-50%")
      expect(variants.exit.x).toBe("-50%")
    })

    it("recomputes position when the window resizes", async () => {
      setInnerWidth(1024)
      const state = baseState()
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      await user.click(screen.getByRole("button", { name: "Open notifications" }))

      const findDropdown = () =>
        screen.getByRole("heading", { name: "Notifications" }).closest("div")!.parentElement!
          .parentElement as HTMLElement

      expect(findDropdown().style.right).toBe("1024px")

      // Shrink below the mobile breakpoint and fire the resize listener
      setInnerWidth(500)
      act(() => {
        window.dispatchEvent(new Event("resize"))
      })

      const dropdown = findDropdown()
      expect(dropdown.style.right).toBe("")
      expect(dropdown.style.width).toBe("calc(100vw - 2rem)")
    })
  })

  describe("click-outside handling", () => {
    it("closes the dropdown when clicking outside the button and dropdown", async () => {
      const state = baseState()
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      await user.click(screen.getByRole("button", { name: "Open notifications" }))
      expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument()

      // mousedown on document.body — outside both refs → closes
      fireEvent.mouseDown(document.body)

      expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument()
    })

    it("keeps the dropdown open when clicking inside it", async () => {
      const state = baseState()
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      await user.click(screen.getByRole("button", { name: "Open notifications" }))

      const heading = screen.getByRole("heading", { name: "Notifications" })
      // mousedown inside the dropdown → guard short-circuits, stays open
      fireEvent.mouseDown(heading)

      expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument()
    })

    it("keeps the dropdown open when clicking the trigger button itself", async () => {
      const state = baseState()
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      const openButton = screen.getByRole("button", { name: "Open notifications" })
      await user.click(openButton)

      // mousedown on the button is inside buttonRef → contains() guard keeps it open
      fireEvent.mouseDown(openButton)

      expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument()
    })

    it("removes the document listener on unmount", () => {
      useNotificationsMock.mockReturnValue(baseState())
      const addEventListener = vi.spyOn(document, "addEventListener")
      const removeEventListener = vi.spyOn(document, "removeEventListener")
      const rendered = render(<NotificationsBell />)
      const registration = addEventListener.mock.calls.find(
        ([type]) => String(type) === "mousedown"
      )

      expect(registration).toBeDefined()
      rendered.unmount()
      expect(removeEventListener).toHaveBeenCalledWith("mousedown", registration?.[1])
    })
  })

  describe("bulk actions", () => {
    it("marks all notifications as read", async () => {
      const state = baseState()
      state.data = [
        {
          id: "uuid-1",
          title: "Welcome",
          body: "",
          created_at: "2024-01-01T00:00:00Z",
          read: false,
        },
      ]
      state.unreadCount = 1
      const markAll = vi.fn()
      state.markAll = markAll
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      await user.click(screen.getByRole("button", { name: "Open notifications" }))
      await user.click(screen.getByTitle("Mark all as read"))

      expect(markAll).toHaveBeenCalledTimes(1)
    })

    it("clears all notifications and closes the dropdown on success", async () => {
      const state = baseState()
      state.data = [
        {
          id: "uuid-1",
          title: "Welcome",
          body: "",
          created_at: "2024-01-01T00:00:00Z",
          read: true,
        },
      ]
      const clearAll = vi.fn((_arg?: unknown, opts?: { onSuccess?: () => void }) => {
        opts?.onSuccess?.()
      })
      state.clearAll = clearAll as NotificationsState["clearAll"]
      useNotificationsMock.mockReturnValue(state)

      const user = userEvent.setup()
      render(<NotificationsBell />)

      await user.click(screen.getByRole("button", { name: "Open notifications" }))
      expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument()

      await user.click(screen.getByTitle("Clear"))

      expect(clearAll).toHaveBeenCalledTimes(1)
      // onSuccess callback flips isOpen → false, unmounting the dropdown
      expect(screen.queryByRole("heading", { name: "Notifications" })).not.toBeInTheDocument()
    })
  })
})
