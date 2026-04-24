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
    
    const { result } = renderHook(() => useEventCardLogic({ 
      ...eventProps, 
      starts_at: startsAt,
      ends_at: endsAt
    }))
    
    expect(result.current.timeStatus.status).toBe("soon")
  })

  it("navigates to details when card is clicked", () => {
    const { result } = renderHook(() => useEventCardLogic(eventProps))
    const mockEvent = { 
      target: { closest: () => null } as any 
    } as any
    
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
})
