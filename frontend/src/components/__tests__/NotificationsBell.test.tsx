import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { useNotifications } from "@/hooks/useNotifications"
import NotificationsBell from "../feedback/NotificationsBell"

const useNotificationsMock = vi.fn()

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: () => useNotificationsMock(),
}))

const translations: Record<string, string> = {
  "system:notificationsBell.open": "Open notifications",
  "system:notificationsBell.title": "Notifications",
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
  useTranslation: () => ({
    t: (key: string) => translations[key] ?? key,
  }),
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
    useReducedMotion: () => false,
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
  })

  it("exposes dialog state and closes with Escape while restoring trigger focus", async () => {
    useNotificationsMock.mockReturnValue(baseState())
    const user = userEvent.setup()
    render(<NotificationsBell />)
    const trigger = screen.getByRole("button", { name: "Open notifications" })

    await user.click(trigger)
    expect(trigger).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument()

    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
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

    await user.click(screen.getByText("Unread chat"))
    expect(markRead).toHaveBeenCalledWith("chat-1")

    fireEvent.click(screen.getByText("Unread reminder"))
    expect(markRead).toHaveBeenCalledWith("schedule-1")

    fireEvent.click(screen.getByText("Read update"))
    expect(markRead).toHaveBeenCalledTimes(2)

    const markButtons = screen.getAllByTitle("Mark as read")
    expect(markButtons).toHaveLength(2)
    await user.click(markButtons[0]!)
    expect(markRead).toHaveBeenCalledWith("chat-1")
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
