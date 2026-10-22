import { renderHook, act } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { useEventCardLogic } from "../useEventCardLogic"

// Mock dependencies
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(() => ({ user: { id: 1, role: "admin" } })),
}))

const mockNavigate = vi.fn()
vi.mock("@tanstack/react-router", () => ({
  useNavigate: vi.fn(() => mockNavigate),
}))

vi.mock("react-i18next", () => ({
  useTranslation: vi.fn(() => ({ t: (s: string) => s })),
}))

vi.mock("@/components/ui/Spotlight", () => ({
  useSpotlight: vi.fn(() => ({})),
}))

const mockRegistration = {
  isRegistered: false,
  participantCount: 0,
  register: vi.fn(),
  unregister: vi.fn(),
}
vi.mock("@/hooks/useEventRegistration", () => ({
  useEventRegistration: vi.fn(() => mockRegistration),
}))

vi.mock("@/api/client", () => ({
  default: {
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

describe("useEventCardLogic", () => {
  const eventProps = {
    id: "event-1",
    title: "Initial Title",
    starts_at: "2026-12-01T10:00:00Z",
    ends_at: "2026-12-01T12:00:00Z",
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  it("initializes with correct edit data", () => {
    const { result } = renderHook(() => useEventCardLogic(eventProps))
    expect(result.current.editData.title).toBe("Initial Title")
    expect(result.current.menuId).toBe("event-card-menu-event-1")
  })

  it("calculates time status correctly (future)", () => {
    // Set 'now' to 1 hour before the event
    // Using a simpler string format that normalizeDate might handle better across environments
    const startsAt = "2026-12-01 10:00:00"
    const endsAt = "2026-12-01 12:00:00"
    vi.setSystemTime(new Date("2026-12-01T09:00:00"))

    const { result } = renderHook(() =>
      useEventCardLogic({
        ...eventProps,
        starts_at: startsAt,
        ends_at: endsAt,
      })
    )

    expect(result.current.timeStatus.status).toBe("soon")
  })

  it("navigates to details when card is clicked", () => {
    const { result } = renderHook(() => useEventCardLogic(eventProps))
    const mockEvent = {
      target: { closest: () => null },
    } as unknown as React.MouseEvent

    act(() => {
      result.current.onCardClick(mockEvent)
    })

    expect(mockNavigate).toHaveBeenCalledWith({
      to: "/events/$id",
      params: { id: "event-1" },
    })
  })

  it("opens edit dialog and updates state", () => {
    const { result } = renderHook(() => useEventCardLogic(eventProps))

    act(() => {
      result.current.setEditOpen(true)
      result.current.setEditData({ ...result.current.editData, title: "New Title" })
    })

    expect(result.current.editOpen).toBe(true)
    expect(result.current.editData.title).toBe("New Title")
  })

  it("reopens the edit form from the card's current props, not the mount-time snapshot", () => {
    const { result, rerender } = renderHook(
      (props: typeof eventProps) => useEventCardLogic(props),
      { initialProps: eventProps }
    )
    act(() => {
      result.current.setEditOpen(true)
      result.current.setEditData({ ...result.current.editData, title: "Unsaved draft" })
    })
    act(() => result.current.setEditOpen(false))

    rerender({ ...eventProps, title: "Title saved elsewhere" })
    act(() => result.current.setEditOpen(true))

    expect(result.current.editData.title).toBe("Title saved elsewhere")
  })

  it("keeps an in-progress draft while the card's props change under an open form", () => {
    const { result, rerender } = renderHook(
      (props: typeof eventProps) => useEventCardLogic(props),
      { initialProps: eventProps }
    )
    act(() => {
      result.current.setEditOpen(true)
      result.current.setEditData({ ...result.current.editData, title: "Typed draft" })
    })

    rerender({ ...eventProps, title: "Title saved elsewhere" })

    expect(result.current.editData.title).toBe("Typed draft")
  })

  it("re-evaluates live and ended status when the clock passes the event boundaries", () => {
    vi.setSystemTime(new Date("2026-12-01T11:59:30Z"))
    const { result } = renderHook(() =>
      useEventCardLogic({
        ...eventProps,
        starts_at: "2026-12-01T11:00:00Z",
        ends_at: "2026-12-01T12:00:00Z",
      })
    )
    expect(result.current.timeStatus.status).toBe("live")
    expect(result.current.eventEnded).toBe(false)

    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    expect(result.current.timeStatus.status).toBe("none")
    expect(result.current.eventEnded).toBe(true)
  })
})
