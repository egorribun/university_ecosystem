import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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
    id: String(id),
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
    created_by: "uuid-1",
    created_at: new Date().toISOString(),
    is_active: true,
    speaker: null,
    image_url: null,
    image_url_optimized: null,
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
  loginWithPasskey: vi.fn(),
  logout: vi.fn(),
  user: {
    id: "uuid-1",
    email: "user@example.com",
    full_name: "Test User",
    role: "student",
    group_id: null,
    avatar_url: null,
    avatar_url_optimized: null,
    cover_url: null,
    cover_url_optimized: null,
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
    recovery_codes_left: 0,
    totp_enrollments: [],
    mfa_challenges: [],
  },
  loading: false,
  setUser: vi.fn(),
  refresh: vi.fn(),
  pendingMfa: null,
  submitMfaChallenge: vi.fn().mockResolvedValue(undefined),
  requireMfa: vi.fn().mockResolvedValue(null),
  resetEtagCache: vi.fn(),
}

describe("Events pagination UI", () => {
  beforeEach(() => {
    const events = Array.from({ length: 15 }, (_, index) => buildEvent(index + 1))
    setTestEvents(events)
  })

  it("loads additional pages when clicking load more", async () => {
    const user = userEvent.setup()
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
    await waitFor(() => expect(screen.getAllByTestId("event-card")).toHaveLength(12))

    const loadMoreButton = await screen.findByRole("button", { name: /load more/i })
    await user.click(loadMoreButton)

    await waitFor(() => expect(screen.getAllByTestId("event-card")).toHaveLength(15))
    expect(await screen.findByText("Paginated event 13")).toBeInTheDocument()

    queryClient.clear()
  })
})
