import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
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
  "system:errorBoundary.retry": "Try again",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => translations[key] ?? key,
  }),
}))

describe("NotificationsBell", () => {
  const baseState = () => ({
    data: [],
    unreadCount: 0,
    hasMore: false,
    nextCursor: null,
    isLoading: false,
    isError: false,
    error: null as unknown,
    isRefetching: false,
    refetch: vi.fn(),
    markRead: vi.fn(),
    markAll: vi.fn(),
    clearAll: vi.fn(),
    isMarkingAll: false,
    isClearing: false,
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

    const openButton = await screen.findByRole("button", { name: "Open notifications" })
    await user.click(openButton)

    expect(await screen.findByText("Error loading notifications")).toBeInTheDocument()

    const markAllButton = screen.getByRole("button", { name: "Mark all as read" })
    const clearButton = screen.getByRole("button", { name: "Clear" })

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

    const openButton = await screen.findByRole("button", { name: "Open notifications" })
    await user.click(openButton)

    const retryButton = await screen.findByRole("button", { name: "Try again" })
    await user.click(retryButton)

    expect(refetch).toHaveBeenCalledTimes(1)

    state.isRefetching = true
    rerender(<NotificationsBell />)

    expect(await screen.findByText("Loading…")).toBeInTheDocument()
  })
})
