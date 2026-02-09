import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { useNotifications } from "@/hooks/useNotifications"
import NotificationsBell from "../NotificationsBell"

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
    const Component = ({ children, className, onClick, ...props }: any) => {
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

      return (
        <Tag className={className} onClick={onClick} {...filteredProps}>
          {children}
        </Tag>
      )
    }
    Component.displayName = `Motion(${Tag})`
    return Component
  }

  return {
    AnimatePresence: ({ children }: any) => <>{children}</>,
    motion: {
      div: motionComponent("div"),
      button: motionComponent("button"),
      span: motionComponent("span"),
    },
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
    const { rerender } = render(<NotificationsBell />)

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
})




