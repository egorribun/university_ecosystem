import { createElement } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { eventsState, mockNavigate } = vi.hoisted(() => ({
  eventsState: {
    current: { data: [] as unknown[] | undefined, isLoading: false, isFetching: false },
  },
  mockNavigate: vi.fn(),
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
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => true }))
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
  prefetchDashboardEvents: vi.fn(),
}))
vi.mock("@/api/hooks/events", () => ({
  prefetchEventsListQuery: vi.fn(),
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
})
