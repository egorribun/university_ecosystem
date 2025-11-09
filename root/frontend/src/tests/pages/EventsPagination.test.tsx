import { act, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, beforeEach, vi } from "vitest"
import type { ContextType } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import Events from "@/pages/Events"
import { AuthContext } from "@/contexts/AuthContext"
import type { Event } from "@/types/Event"
import { setTestEvents } from "../mocks/handlers"

vi.mock("../../components/EventCard", () => ({
  __esModule: true,
  default: ({ title }: { title: string }) => (
    <div data-testid="event-card">
      <span>{title}</span>
    </div>
  ),
}))

const buildEvent = (id: number): Event => {
  const start = new Date(Date.now() + id * 60 * 60 * 1000)
  const end = new Date(start.getTime() + 60 * 60 * 1000)
  return {
    id,
    title: `Paginated event ${id}`,
    description: `Description ${id}`,
    title_en: `Paginated event ${id}`,
    description_en: `Description ${id}`,
    location: `Hall ${id}`,
    location_en: `Hall ${id}`,
    event_type: null,
    event_type_en: null,
    starts_at: start.toISOString(),
    ends_at: end.toISOString(),
    created_by: 1,
    created_at: new Date().toISOString(),
    is_active: true,
    speaker: null,
    image_url: null,
    about: null,
    about_en: null,
    files: [],
    participant_count: 0,
    is_registered: null,
    my_qr_token: null,
  }
}

type AuthContextValue = ContextType<typeof AuthContext>

const authValue: AuthContextValue = {
  isAuth: true,
  login: vi.fn(),
  logout: vi.fn(),
  user: {
    id: 1,
    email: "user@example.com",
    full_name: "Test User",
    role: "student",
    group_id: null,
    avatar_url: null,
    cover_url: null,
    about: null,
    record_book_number: null,
    status: null,
    institute: null,
    course: null,
    education_level: null,
    track: null,
    program: null,
    telegram: null,
    achievements: null,
    department: null,
    position: null,
    spotify_connected: false,
    spotify_display_name: null,
    spotify_is_connected: null,
    dnd_enabled: false,
    dnd_start: null,
    dnd_end: null,
    is_active: true,
    mfa_required: false,
    mfa_default_method: null,
    mfa_last_verified_at: null,
    mfa_recovery_codes_generated_at: null,
    totp_enrollments: [],
    webauthn_credentials: [],
    recovery_codes: [],
    mfa_challenges: [],
  },
  loading: false,
  setUser: vi.fn(),
  refresh: vi.fn(),
  pendingMfa: null,
  submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
  requireMfa: vi.fn().mockResolvedValue(null),
}

describe("Events pagination UI", () => {
  beforeEach(() => {
    const events = Array.from({ length: 15 }, (_, index) => buildEvent(index + 1))
    setTestEvents(events)
  })

  it("loads additional pages when clicking load more", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })

    render(
      <AuthContext.Provider value={authValue}>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <Events />
          </MemoryRouter>
        </QueryClientProvider>
      </AuthContext.Provider>
    )

    expect(await screen.findByText("Paginated event 1")).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId("event-card")).not.toHaveLength(0))

    const scroller = await screen.findByTestId("events-virtual-scroll")
    Object.defineProperty(scroller, "clientHeight", { value: 420, configurable: true })
    scroller.getBoundingClientRect = () => ({
      width: 600,
      height: 420,
      top: 200,
      left: 0,
      bottom: 620,
      right: 600,
      x: 0,
      y: 200,
      toJSON: () => ({ width: 600, height: 420 }),
    })

    await act(async () => {
      window.scrollTo({ top: 200 })
      window.dispatchEvent(new Event("resize"))
    })

    await act(async () => {
      window.scrollTo({ top: 10_000 })
      window.dispatchEvent(new Event("scroll"))
    })

    await waitFor(() => expect(screen.getByText("Paginated event 13")).toBeInTheDocument())
    expect(screen.getAllByTestId("event-card").length).toBeLessThan(15)

    queryClient.clear()
  })
})
