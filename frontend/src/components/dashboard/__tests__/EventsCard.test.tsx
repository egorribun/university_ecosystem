import { createElement } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, vi, beforeEach } from "vitest"

const {
  eventsState,
  mockNavigate,
  mockPrefetchDashboardEvents,
  mockPrefetchEventsListQuery,
  reducedMotion,
} = vi.hoisted(() => ({
  eventsState: {
    current: { data: [] as unknown[] | undefined, isLoading: false, isFetching: false },
  },
  mockNavigate: vi.fn(),
  mockPrefetchDashboardEvents: vi.fn(),
  mockPrefetchEventsListQuery: vi.fn(),
  reducedMotion: { value: true },
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => reducedMotion.value }))
vi.mock("@tanstack/react-router", () => ({
  Link: ({
    children,
    to,
    ...rest
  }: { children?: unknown; to?: unknown } & Record<string, unknown>) =>
    createElement("a", { href: typeof to === "string" ? to : "#", ...rest }, children as never),
  useNavigate: () => mockNavigate,
}))
vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en", setLanguage: vi.fn() }),
}))
vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => eventsState.current,
  prefetchDashboardEvents: mockPrefetchDashboardEvents,
}))
vi.mock("@/api/hooks/events", () => ({
  prefetchEventsListQuery: mockPrefetchEventsListQuery,
  EVENTS_PAGE_SIZE: 20,
}))

import { EventsCard } from "@/components/dashboard/EventsCard"
import type { Event } from "@/types/Event"

const inTwoDays = new Date(Date.now() + 2 * 24 * 3600 * 1000).toISOString()
const EVENTS = [
  { id: 1, title: "Hackathon 2026", starts_at: inTwoDays, location: "ГУК-305" },
] as unknown as Event[]

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <EventsCard />
    </QueryClientProvider>
  )
}

describe("EventsCard", () => {
  beforeEach(() => {
    eventsState.current = { data: EVENTS, isLoading: false, isFetching: false }
    mockNavigate.mockReset()
    mockPrefetchDashboardEvents.mockReset()
    mockPrefetchEventsListQuery.mockReset()
    reducedMotion.value = true
  })

  it("does not mount perpetual decorative animations", () => {
    const { container } = renderCard()

    expect(container.querySelector('[style*="animation"]')).toBeNull()
    expect(container.querySelector(".dash-orb-reactive")).toBeNull()
  })

  it("renders the heading, view-all link, and scope toggles", () => {
    renderCard()
    expect(screen.getByText("dashboard:events.heading")).toBeInTheDocument()
    expect(screen.getByText("dashboard:viewAll")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "dashboard:scope.today" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "dashboard:scope.week" })).toBeInTheDocument()
  })

  it("shows an event after switching to the week scope", async () => {
    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole("button", { name: "dashboard:scope.week" }))
    expect(screen.getByText("Hackathon 2026")).toBeInTheDocument()
  })

  it("shows the empty state when no events match the scope", () => {
    eventsState.current = { data: [], isLoading: false, isFetching: false }
    renderCard()
    expect(screen.getByText("dashboard:events.empty")).toBeInTheDocument()
  })

  it("marks the card aria-busy while events load", () => {
    eventsState.current = { data: undefined, isLoading: true, isFetching: false }
    renderCard()
    expect(screen.getByText("dashboard:events.heading").closest("[aria-busy]")).toHaveAttribute(
      "aria-busy",
      "true"
    )
  })

  it("prefetches dashboard and list data from pointer and keyboard activation", () => {
    renderCard()
    const viewAll = screen.getByRole("link", { name: "dashboard:aria.viewAllEvents" })

    fireEvent.pointerDown(viewAll)
    fireEvent.keyDown(viewAll, { key: "Enter" })
    fireEvent.keyDown(viewAll, { key: " " })
    fireEvent.keyDown(viewAll, { key: "Spacebar" })
    fireEvent.keyDown(viewAll, { key: "Escape" })

    expect(mockPrefetchDashboardEvents).toHaveBeenCalledTimes(4)
    expect(mockPrefetchEventsListQuery).toHaveBeenCalledTimes(4)
    expect(mockPrefetchEventsListQuery).toHaveBeenCalledWith(expect.anything(), {
      language: "en",
      is_active: true,
      limit: 20,
    })
  })

  it("absorbs a rejected lazy page prefetch", async () => {
    vi.doMock("@/pages/Events", () => {
      throw new Error("chunk unavailable")
    })
    renderCard()

    fireEvent.pointerDown(screen.getByRole("link", { name: "dashboard:aria.viewAllEvents" }))
    await vi.waitFor(() => expect(mockPrefetchDashboardEvents).toHaveBeenCalledOnce())
    await Promise.resolve()
    vi.doUnmock("@/pages/Events")
  })

  it("filters invalid and missing dates, navigates today events, and renders no location badge", async () => {
    reducedMotion.value = false
    const today = new Date()
    today.setHours(12, 0, 0, 0)
    const todayIso = today.toISOString()
    eventsState.current = {
      data: [
        { id: 2, title: "Today event", starts_at: todayIso, location: "" },
        {
          id: 5,
          title: "Earlier today event",
          starts_at: new Date(today.getTime() - 60_000).toISOString(),
          location: "",
        },
        { id: 3, title: "Invalid event", starts_at: "not-a-date", location: "Room" },
        { id: 4, title: "No date", starts_at: null, location: "Room" },
      ],
      isLoading: false,
      isFetching: true,
    }

    const user = userEvent.setup()
    renderCard()
    expect(
      screen.getByText("dashboard:events.heading").closest("[data-refetching]")
    ).toHaveAttribute("data-refetching", "true")
    const event = screen.getAllByRole("button", { name: "dashboard:aria.eventItem" })[0]!
    expect(event).toBeInTheDocument()
    await user.click(event)
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/events/$id", params: { id: "5" } })
    expect(screen.queryByText("Room")).not.toBeInTheDocument()
  })
})
