import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, beforeEach, vi } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ContextType } from "react"
import { HttpResponse, http } from "msw"

import Events from "@/pages/Events"
import { AuthContext } from "@/contexts/AuthContext"
import type { Event } from "@/types/Event"
import { server } from "../mocks/server"
import { checkA11y } from "../axeTest"

vi.mock("../../components/EventCard", () => ({
  __esModule: true,
  default: ({ title }: { title: string }) => (
    <div data-testid="event-card">
      <span>{title}</span>
    </div>
  ),
}))

const buildEvent = (id: number, title: string, isActive: boolean): Event => {
  const start = new Date(Date.now() + id * 60 * 60 * 1000)
  const end = new Date(start.getTime() + 60 * 60 * 1000)
  return {
    id,
    title,
    description: `${title} description`,
    title_en: title,
    description_en: `${title} description`,
    location: `Auditorium ${id}`,
    location_en: `Auditorium ${id}`,
    event_type: null,
    event_type_en: null,
    starts_at: start.toISOString(),
    ends_at: end.toISOString(),
    created_by: 1,
    created_at: new Date().toISOString(),
    is_active: isActive,
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

const setScrollMetrics = (element: HTMLElement, height = 420, total = 1800) => {
  Object.defineProperty(element, "clientHeight", { value: height, configurable: true })
  Object.defineProperty(element, "scrollHeight", { value: total, configurable: true })
  element.getBoundingClientRect = () => ({
    width: 600,
    height,
    top: 0,
    left: 0,
    bottom: height,
    right: 600,
    x: 0,
    y: 0,
    toJSON: () => ({ width: 600, height }),
  })
  window.dispatchEvent(new Event("resize"))
}

describe("Events virtualization across tabs", () => {
  const activeEvents = Array.from({ length: 8 }, (_, index) =>
    buildEvent(index + 1, `Active Virtual Event ${index + 1}`, true)
  )
  const archiveEvents = Array.from({ length: 5 }, (_, index) =>
    buildEvent(100 + index + 1, `Archived Virtual Event ${index + 1}`, false)
  )
  const myEvents = Array.from({ length: 3 }, (_, index) =>
    buildEvent(200 + index + 1, `My Virtual Event ${index + 1}`, true)
  )

  beforeEach(() => {
    server.use(
      http.get("*/events", ({ request }) => {
        const url = new URL(request.url)
        const isActive = url.searchParams.get("is_active")
        const limitRaw = Number(url.searchParams.get("limit") ?? "")
        const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : 12

        if (isActive === "true") {
          return HttpResponse.json({
            items: activeEvents.slice(0, limit),
            total: activeEvents.length,
            limit,
            cursor: null,
            next_cursor: null,
            has_more: false,
          })
        }
        if (isActive === "false") {
          return HttpResponse.json({
            items: archiveEvents.slice(0, limit),
            total: archiveEvents.length,
            limit,
            cursor: null,
            next_cursor: null,
            has_more: false,
          })
        }
        return HttpResponse.json({
          items: [],
          total: 0,
          limit,
          cursor: null,
          next_cursor: null,
          has_more: false,
        })
      }),
      http.get("*/events/my", () => HttpResponse.json(myEvents))
    )
  })

  it("keeps virtualization stable across tabs and passes accessibility checks", async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })

    const { container } = render(
      <AuthContext.Provider value={authValue}>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <Events />
          </MemoryRouter>
        </QueryClientProvider>
      </AuthContext.Provider>
    )

    const activeScroller = await screen.findByTestId("events-virtual-scroll")
    setScrollMetrics(activeScroller)

    expect(await screen.findByText("Active Virtual Event 1")).toBeInTheDocument()
    await checkA11y(container)

    activeScroller.scrollTop = 260
    activeScroller.dispatchEvent(new Event("scroll"))

    const archiveTab = await screen.findByRole("tab", { name: /past events/i })
    await user.click(archiveTab)

    const archiveEvent = await screen.findByText("Archived Virtual Event 1")
    expect(archiveEvent).toBeInTheDocument()

    const archiveScroller = await screen.findByTestId("events-virtual-scroll")
    setScrollMetrics(archiveScroller)
    expect(archiveScroller.scrollTop).toBe(0)
    await checkA11y(container)

    const myTab = await screen.findByRole("tab", { name: /my events/i })
    await user.click(myTab)

    const myEvent = await screen.findByText("My Virtual Event 1")
    expect(myEvent).toBeInTheDocument()

    const myScroller = await screen.findByTestId("events-virtual-scroll")
    setScrollMetrics(myScroller)
    expect(myScroller.scrollTop).toBe(0)
    await checkA11y(container)

    expect(screen.getAllByTestId("event-card").length).toBeLessThanOrEqual(3)

    queryClient.clear()
  })
})
