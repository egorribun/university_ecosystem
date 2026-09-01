import { createElement } from "react"
import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, vi, beforeEach } from "vitest"

const {
  eventsState,
  mockNavigate,
  mockPrefetchDashboardEvents,
  mockPrefetchEventsListQuery,
  mockUseMediaQuery,
  mockUseTranslation,
  reducedMotion,
} = vi.hoisted(() => ({
  eventsState: {
    current: { data: [] as unknown[] | undefined, isLoading: false, isFetching: false },
  },
  mockNavigate: vi.fn(),
  mockPrefetchDashboardEvents: vi.fn(),
  mockPrefetchEventsListQuery: vi.fn(),
  mockUseMediaQuery: vi.fn(() => true),
  mockUseTranslation: vi.fn(() => ({
    t: (key: string, options?: { title?: string }) =>
      key === "dashboard:aria.eventItem" && options?.title ? `${key}:${options.title}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
  reducedMotion: { value: true },
}))

vi.mock("framer-motion", () => {
  const motion = new Proxy(
    {},
    {
      get:
        () =>
        ({
          children,
          initial,
          animate,
          exit,
          transition,
          ...props
        }: {
          children?: unknown
          initial?: unknown
          animate?: unknown
          exit?: unknown
          transition?: unknown
          [key: string]: unknown
        }) =>
          createElement(
            "li",
            {
              ...props,
              "data-motion-initial": JSON.stringify(initial),
              "data-motion-animate": JSON.stringify(animate),
              "data-motion-exit": JSON.stringify(exit),
              "data-motion-transition": JSON.stringify(transition),
            },
            children as never
          ),
    }
  )
  const AnimatePresence = ({ children, initial }: { children?: unknown; initial?: unknown }) =>
    createElement("div", { "data-presence-initial": String(initial) }, children as never)
  return { m: motion, motion, AnimatePresence }
})
vi.mock("react-i18next", () => ({ useTranslation: mockUseTranslation }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: mockUseMediaQuery }))
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

import { EventsCard, prepareOnKey } from "@/components/dashboard/EventsCard"
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
    mockUseMediaQuery.mockReset()
    mockUseMediaQuery.mockImplementation(() => reducedMotion.value)
    mockUseTranslation.mockClear()
    reducedMotion.value = true
  })

  it("does not mount perpetual decorative animations", () => {
    const { container } = renderCard()

    expect(container.querySelector('[style*="animation"]')).toBeNull()
    expect(container.querySelector(".dash-orb-reactive")).toBeNull()
  })

  it("renders the heading, view-all link, and scope toggles", () => {
    renderCard()
    expect(mockUseTranslation).toHaveBeenCalledWith(["dashboard", "common"])
    expect(mockUseMediaQuery).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    expect(screen.getByText("dashboard:events.heading")).toBeInTheDocument()
    expect(screen.getByText("dashboard:viewAll")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "dashboard:scope.today" })).toHaveAttribute(
      "aria-pressed",
      "true"
    )
    expect(screen.getByRole("button", { name: "dashboard:scope.week" })).toHaveAttribute(
      "aria-pressed",
      "false"
    )
  })

  it("shows an event after switching to the week scope", async () => {
    const user = userEvent.setup()
    renderCard()
    await user.click(screen.getByRole("button", { name: "dashboard:scope.week" }))
    expect(screen.getByText("Hackathon 2026")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "dashboard:scope.today" })).toHaveAttribute(
      "aria-pressed",
      "false"
    )
    expect(screen.getByRole("button", { name: "dashboard:scope.week" })).toHaveAttribute(
      "aria-pressed",
      "true"
    )
    expect(screen.getByRole("list", { name: "dashboard:aria.eventsWeek" })).toBeInTheDocument()
  })

  it("shows the empty state when no events match the scope", () => {
    eventsState.current = { data: [], isLoading: false, isFetching: false }
    renderCard()
    expect(screen.getByText("dashboard:events.empty")).toBeInTheDocument()
    expect(screen.queryByRole("list")).not.toBeInTheDocument()
  })

  it("marks the card aria-busy while events load", () => {
    eventsState.current = { data: undefined, isLoading: true, isFetching: false }
    renderCard()
    expect(screen.getByText("dashboard:events.heading").closest("[aria-busy]")).toHaveAttribute(
      "aria-busy",
      "true"
    )
    expect(screen.getByRole("presentation").querySelectorAll('[aria-busy="true"]')).toHaveLength(9)
    expect(screen.queryByText("dashboard:events.empty")).not.toBeInTheDocument()
  })

  it("does not mark loaded data as loading while a refetch is idle", () => {
    renderCard()
    fireEvent.click(screen.getByRole("button", { name: "dashboard:scope.week" }))
    const card = screen.getByText("dashboard:events.heading").closest("[aria-busy]")
    expect(card).toHaveAttribute("aria-busy", "false")
    expect(card).toHaveAttribute("data-refetching", "false")
    expect(screen.queryByRole("presentation")).not.toBeInTheDocument()
    expect(screen.queryByText("dashboard:events.empty")).not.toBeInTheDocument()
  })

  it("keeps stale events visible while the query is still loading", () => {
    eventsState.current = { data: EVENTS, isLoading: true, isFetching: true }
    renderCard()
    fireEvent.click(screen.getByRole("button", { name: "dashboard:scope.week" }))
    const card = screen.getByText("dashboard:events.heading").closest("[aria-busy]")
    expect(card).toHaveAttribute("aria-busy", "false")
    expect(card).toHaveAttribute("data-refetching", "false")
    expect(screen.getByText("Hackathon 2026")).toBeInTheDocument()
    expect(screen.queryByRole("presentation")).not.toBeInTheDocument()
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

  it("accepts each supported keyboard activation and ignores other keys", () => {
    renderCard()
    const viewAll = screen.getByRole("link", { name: "dashboard:aria.viewAllEvents" })

    fireEvent.keyDown(viewAll, { key: "Enter" })
    expect(mockPrefetchDashboardEvents).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(viewAll, { key: " " })
    expect(mockPrefetchDashboardEvents).toHaveBeenCalledTimes(2)
    fireEvent.keyDown(viewAll, { key: "Spacebar" })
    expect(mockPrefetchDashboardEvents).toHaveBeenCalledTimes(3)
    fireEvent.keyDown(viewAll, { key: "Escape" })
    expect(mockPrefetchDashboardEvents).toHaveBeenCalledTimes(3)
  })

  it("preserves the shell, event identity, and reduced-motion animation contracts", () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date(2026, 8, 1, 9, 0, 0, 0))
      reducedMotion.value = false
      eventsState.current = {
        data: [
          {
            id: 40,
            title: "Morning event",
            starts_at: new Date(2026, 8, 1, 10, 0, 0, 0).toISOString(),
            location: "Room 101",
          },
          {
            id: 41,
            title: "No-location event",
            starts_at: new Date(2026, 8, 1, 11, 0, 0, 0).toISOString(),
            location: "",
          },
        ],
        isLoading: false,
        isFetching: false,
      }

      renderCard()
      const card = screen.getByText("dashboard:events.heading").closest("[aria-busy]")!
      expect(card).toHaveClass("glass-noise", "refetch-shimmer", "dash-panel-events")
      expect(card).toHaveClass("motion-reduce:hover:transform-none")
      expect(screen.getByText("dashboard:events.heading").style.fontSize).toBe(
        "clamp(1.35rem, 2.5vw, 1.75rem)"
      )

      const todayToggle = screen.getByRole("button", { name: "dashboard:scope.today" })
      const scopeGroup = todayToggle.parentElement!
      expect(scopeGroup).toHaveStyle({ background: "var(--dash-btn-bg)" })
      expect(todayToggle).toHaveClass("rounded-md", "bg-brand", "shadow-sm")
      expect(screen.getByRole("button", { name: "dashboard:scope.week" })).toHaveClass(
        "rounded-md",
        "text-text-secondary"
      )

      const todayList = screen.getByRole("list", { name: "dashboard:aria.eventsToday" })
      expect(todayList.querySelector("[data-presence-initial]")).toHaveAttribute(
        "data-presence-initial",
        "false"
      )
      const eventButtons = within(todayList).getAllByRole("button")
      expect(eventButtons).toHaveLength(2)
      expect(eventButtons[0]).toHaveAttribute(
        "aria-label",
        "dashboard:aria.eventItem:Morning event"
      )
      expect(eventButtons[1]).toHaveAttribute(
        "aria-label",
        "dashboard:aria.eventItem:No-location event"
      )
      expect(eventButtons[0]).toHaveClass(
        "group",
        "list-item-blue",
        "list-item-blue-hover",
        "flex",
        "items-center",
        "active:scale-(--scale-active)"
      )
      expect(eventButtons[0]).toHaveTextContent("10:00")
      expect(eventButtons[0]).toHaveTextContent("Room 101")
      expect(eventButtons[1]).not.toHaveTextContent("Room 101")

      const firstItem = eventButtons[0]!.closest("li")!
      const secondItem = eventButtons[1]!.closest("li")!
      expect(firstItem).toHaveAttribute("data-event-key", "today-40")
      expect(secondItem).toHaveAttribute("data-event-key", "today-41")
      expect(firstItem).toHaveAttribute("data-motion-initial", '{"opacity":0,"y":8}')
      expect(firstItem).toHaveAttribute("data-motion-animate", '{"opacity":1,"y":0}')
      expect(firstItem).toHaveAttribute("data-motion-exit", '{"opacity":0,"y":-4}')
      expect(firstItem).toHaveAttribute("data-motion-transition", '{"duration":0.2,"delay":0}')
      expect(secondItem).toHaveAttribute("data-motion-transition", '{"duration":0.2,"delay":0.04}')
    } finally {
      vi.useRealTimers()
    }
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
    const event = screen.getAllByRole("button", { name: /dashboard:aria\.eventItem:/ })[0]!
    expect(event).toBeInTheDocument()
    await user.click(event)
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/events/$id", params: { id: "5" } })
    expect(screen.queryByText("Room")).not.toBeInTheDocument()
  })

  it("sorts today events, keeps the six-item limit, and exposes the formatted details", () => {
    vi.useFakeTimers()
    try {
      const noon = new Date(2026, 8, 1, 12, 0, 0, 0)
      vi.setSystemTime(noon)
      const events = Array.from({ length: 8 }, (_, index) => ({
        id: index + 1,
        title: `Today ${index + 1}`,
        starts_at: new Date(2026, 8, 1, 12 - index, 0, 0, 0).toISOString(),
        location: index === 7 ? "Room 101" : "",
      }))
      events.push(
        { id: 20, title: "Invalid", starts_at: "not-a-date", location: "" },
        {
          id: 21,
          title: "Tomorrow",
          starts_at: new Date(2026, 8, 2, 0, 0, 0, 0).toISOString(),
          location: "",
        }
      )
      eventsState.current = { data: events, isLoading: false, isFetching: false }

      renderCard()
      const todayList = screen.getByRole("list", { name: "dashboard:aria.eventsToday" })
      const items = within(todayList).getAllByRole("button")
      expect(items).toHaveLength(6)
      expect(items.map((item) => item.getAttribute("aria-label"))).toEqual([
        "dashboard:aria.eventItem:Today 8",
        "dashboard:aria.eventItem:Today 7",
        "dashboard:aria.eventItem:Today 6",
        "dashboard:aria.eventItem:Today 5",
        "dashboard:aria.eventItem:Today 4",
        "dashboard:aria.eventItem:Today 3",
      ])
      expect(within(todayList).getByText("Today 8")).toBeInTheDocument()
      expect(within(todayList).getByText("Today 3")).toBeInTheDocument()
      expect(within(todayList).queryByText("Today 2")).not.toBeInTheDocument()
      expect(screen.queryByText("Invalid")).not.toBeInTheDocument()
      expect(screen.queryByText("Tomorrow")).not.toBeInTheDocument()
      expect(within(todayList).getByText("Room 101")).toBeInTheDocument()
      const earliestEvent = within(todayList).getByText("Today 8").closest("button")
      expect(earliestEvent).not.toBeNull()
      expect(within(earliestEvent!).getByText("05:00")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("applies the inclusive seven-day week boundary and refreshes query data", () => {
    vi.useFakeTimers()
    try {
      const noon = new Date(2026, 8, 1, 12, 0, 0, 0)
      vi.setSystemTime(noon)
      const weekEnd = new Date(2026, 8, 8, 23, 59, 59, 999).toISOString()
      const outsideWeek = new Date(2026, 8, 9, 0, 0, 0, 0).toISOString()
      eventsState.current = {
        data: [
          { id: 30, title: "Week end", starts_at: weekEnd, location: "" },
          { id: 31, title: "Outside week", starts_at: outsideWeek, location: "" },
        ],
        isLoading: false,
        isFetching: false,
      }

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const view = render(
        <QueryClientProvider client={queryClient}>
          <EventsCard />
        </QueryClientProvider>
      )
      fireEvent.click(screen.getByRole("button", { name: "dashboard:scope.week" }))
      const weekList = screen.getByRole("list", { name: "dashboard:aria.eventsWeek" })
      expect(within(weekList).getByText("Week end")).toBeInTheDocument()
      expect(within(weekList).queryByText("Outside week")).not.toBeInTheDocument()

      eventsState.current = {
        data: [{ id: 32, title: "Updated week event", starts_at: weekEnd, location: "" }],
        isLoading: false,
        isFetching: false,
      }
      view.rerender(
        <QueryClientProvider client={queryClient}>
          <EventsCard data-fade="updated" />
        </QueryClientProvider>
      )
      expect(screen.getByText("Updated week event")).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("includes events exactly at the local day boundaries", () => {
    vi.useFakeTimers()
    try {
      const noon = new Date(2026, 8, 1, 12, 0, 0, 0)
      vi.setSystemTime(noon)
      const startOfDay = new Date(noon)
      startOfDay.setHours(0, 0, 0, 0)
      const endOfDay = new Date(noon)
      endOfDay.setHours(23, 59, 59, 999)

      eventsState.current = {
        data: [
          { id: 6, title: "At day start", starts_at: startOfDay.toISOString(), location: "" },
          { id: 7, title: "At day end", starts_at: endOfDay.toISOString(), location: "" },
          {
            id: 8,
            title: "Tomorrow event",
            starts_at: new Date(endOfDay.getTime() + 1).toISOString(),
            location: "",
          },
        ],
        isLoading: false,
        isFetching: false,
      }

      renderCard()
      const todayList = screen.getByRole("list", { name: "dashboard:aria.eventsToday" })
      expect(within(todayList).getByText("At day start")).toBeInTheDocument()
      expect(within(todayList).getByText("At day end")).toBeInTheDocument()
      expect(screen.queryByText("Tomorrow event")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("recomputes the today scope when query data changes", () => {
    vi.useFakeTimers()
    try {
      const noon = new Date(2026, 8, 1, 12, 0, 0, 0)
      vi.setSystemTime(noon)
      eventsState.current = {
        data: [
          {
            id: 90,
            title: "Initial today event",
            starts_at: new Date(2026, 8, 1, 10, 0, 0, 0).toISOString(),
            location: "",
          },
        ],
        isLoading: false,
        isFetching: false,
      }

      const view = renderCard()
      expect(screen.getByText("Initial today event")).toBeInTheDocument()

      eventsState.current = {
        data: [
          {
            id: 91,
            title: "Updated today event",
            starts_at: new Date(2026, 8, 1, 11, 0, 0, 0).toISOString(),
            location: "",
          },
        ],
        isLoading: false,
        isFetching: false,
      }
      view.rerender(
        <QueryClientProvider client={new QueryClient()}>
          <EventsCard data-fade="updated-today" />
        </QueryClientProvider>
      )

      expect(screen.getByText("Updated today event")).toBeInTheDocument()
      expect(screen.queryByText("Initial today event")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("excludes falsey timestamps and invalid dates from the today scope", () => {
    vi.useFakeTimers()
    try {
      // Epoch zero is a valid Date but a falsey API value.  This distinguishes
      // the explicit starts_at presence guard from the later date predicate.
      vi.setSystemTime(new Date(1970, 0, 1, 12, 0, 0, 0))
      const invalidComparableDate = new Date(1970, 0, 1, 8, 0, 0, 0)
      invalidComparableDate.getTime = () => Number.NaN
      invalidComparableDate.valueOf = () => new Date(1970, 0, 1, 8, 0, 0, 0).getTime()
      eventsState.current = {
        data: [
          { id: 92, title: "Falsey timestamp", starts_at: 0, location: "" },
          {
            id: 93,
            title: "Invalid date object",
            starts_at: invalidComparableDate,
            location: "",
          },
          {
            id: 94,
            title: "Previous day event",
            starts_at: new Date(1969, 11, 31, 23, 0, 0, 0).toISOString(),
            location: "",
          },
        ],
        isLoading: false,
        isFetching: false,
      }

      renderCard()
      expect(screen.queryByText("Falsey timestamp")).not.toBeInTheDocument()
      expect(screen.queryByText("Invalid date object")).not.toBeInTheDocument()
      expect(screen.queryByText("Previous day event")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("uses start-of-day bounds and chronological ordering for the week scope", () => {
    vi.useFakeTimers()
    try {
      const noon = new Date(1970, 0, 1, 12, 0, 0, 0)
      vi.setSystemTime(noon)
      const startOfDay = new Date(1970, 0, 1, 0, 0, 0, 0)
      const invalidComparableDate = new Date(1970, 0, 1, 8, 30, 0, 0)
      invalidComparableDate.getTime = () => Number.NaN
      invalidComparableDate.valueOf = () => new Date(1970, 0, 1, 8, 30, 0, 0).getTime()
      eventsState.current = {
        data: [
          {
            id: 95,
            title: "Later this morning",
            starts_at: new Date(1970, 0, 1, 8, 0, 0, 0).toISOString(),
            location: "",
          },
          {
            id: 96,
            title: "At week start",
            starts_at: startOfDay.toISOString(),
            location: "",
          },
          {
            id: 97,
            title: "Earlier this morning",
            starts_at: new Date(1970, 0, 1, 7, 0, 0, 0).toISOString(),
            location: "",
          },
          {
            id: 98,
            title: "Previous day",
            starts_at: new Date(1969, 11, 31, 23, 59, 59, 999).toISOString(),
            location: "",
          },
          {
            id: 99,
            title: "Week end",
            starts_at: new Date(1970, 0, 8, 23, 59, 59, 999).toISOString(),
            location: "",
          },
          {
            id: 100,
            title: "Falsey week timestamp",
            starts_at: 0,
            location: "",
          },
          {
            id: 101,
            title: "Invalid week date object",
            starts_at: invalidComparableDate,
            location: "",
          },
          {
            id: 102,
            title: "Second week day",
            starts_at: new Date(1970, 0, 2, 9, 0, 0, 0).toISOString(),
            location: "",
          },
          {
            id: 103,
            title: "Third week day",
            starts_at: new Date(1970, 0, 3, 9, 0, 0, 0).toISOString(),
            location: "",
          },
          {
            id: 104,
            title: "Fourth week day",
            starts_at: new Date(1970, 0, 4, 9, 0, 0, 0).toISOString(),
            location: "",
          },
        ],
        isLoading: false,
        isFetching: false,
      }

      renderCard()
      fireEvent.click(screen.getByRole("button", { name: "dashboard:scope.week" }))
      const weekList = screen.getByRole("list", { name: "dashboard:aria.eventsWeek" })
      expect(
        within(weekList)
          .getAllByRole("button")
          .map((button) => button.textContent)
      ).toEqual([
        expect.stringContaining("At week start"),
        expect.stringContaining("Earlier this morning"),
        expect.stringContaining("Later this morning"),
        expect.stringContaining("Second week day"),
        expect.stringContaining("Third week day"),
        expect.stringContaining("Fourth week day"),
      ])
      expect(within(weekList).queryByText("Previous day")).not.toBeInTheDocument()
      expect(within(weekList).queryByText("Week end")).not.toBeInTheDocument()
      expect(within(weekList).queryByText("Falsey week timestamp")).not.toBeInTheDocument()
      expect(within(weekList).queryByText("Invalid week date object")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it("keeps reduced-motion presence values inert", () => {
    reducedMotion.value = true
    eventsState.current = {
      data: [
        {
          id: 99,
          title: "Reduced motion event",
          starts_at: new Date(Date.now() + 60_000).toISOString(),
          location: "",
        },
      ],
      isLoading: false,
      isFetching: false,
    }

    renderCard()
    const item = screen.getByText("Reduced motion event").closest("li")!
    expect(item).toHaveAttribute("data-motion-initial", "false")
    expect(item).toHaveAttribute("data-motion-exit", '{"opacity":0}')
    expect(item).toHaveAttribute("data-motion-transition", '{"duration":0}')
  })

  it("activates the view-all link for the legacy Spacebar key", () => {
    renderCard()
    const viewAll = screen.getByRole("link", { name: "dashboard:aria.viewAllEvents" })
    const event = new KeyboardEvent("keydown", { key: "Spacebar", bubbles: true })
    viewAll.dispatchEvent(event)

    expect(mockPrefetchDashboardEvents).toHaveBeenCalledOnce()
    expect(mockPrefetchEventsListQuery).toHaveBeenCalledOnce()
  })

  it("recognizes Spacebar directly in the keyboard activation helper", () => {
    const callback = vi.fn()
    prepareOnKey({ key: "Spacebar" }, callback)
    expect(callback).toHaveBeenCalledOnce()
  })
})
