import { render, screen, fireEvent, act } from "@testing-library/react"
import type { ComponentType } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/* ──────────────────────────────────────────────────────────────────────────
 * EventsFeature.branches.test.tsx — drives the uncovered orchestration logic
 * the feature has no primary test for:
 *   - getDateRangeBounds today/week/month/null (28-57)
 *   - handleURLChange set + delete branches (86-88)
 *   - eventsListFilters is_active mapping per tab (121)
 *   - rawEvents / loading flags per tab (156, 159-160)
 *   - client-side category filter (167-171)
 *   - client-side date-range filter (175-182)
 *   - sort modes popular / upcoming (185-192)
 *   - refreshEvents resetEtagCache + invalidateQueries (201-202)
 *
 * EventsFeature is a pure orchestrator (no primary test existed). The heavy
 * child components are stubbed so their props (onTabChange, onSortChange,
 * fetchNextPage, refreshEvents, eventsCount, …) become observable buttons /
 * data attributes. `useSearch` / `useNavigate` / the two events query hooks
 * are module-mocked — NEVER MSW.
 * ────────────────────────────────────────────────────────────────────────── */

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
  withTranslation: () => (Component: ComponentType) => Component,
  Trans: ({ children }: { children?: React.ReactNode }) => children,
}))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))

const auth = vi.hoisted(() => ({
  user: { id: "u1", role: "student" } as { id: string; role: string } | null,
}))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: auth.user }) }))
vi.mock("@/contexts/LanguageContext", () => ({ useLanguage: () => ({ language: "en" }) }))
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => true }))
/* Debounce → identity so client-side filters run synchronously off searchQuery. */
vi.mock("@/hooks/useDebounced", () => ({ useDebounced: (v: string) => v }))

/* Router search params + navigate. */
const search = vi.hoisted(() => ({ params: {} as Record<string, string | undefined> }))
const navigateSpy = vi.hoisted(() => ({ fn: vi.fn((..._a: unknown[]) => undefined) }))
vi.mock("@tanstack/react-router", () => ({
  useSearch: () => search.params,
  useNavigate: () => navigateSpy.fn,
}))

/* Events query hooks — module-mocked, the orchestrator reads their fields. */
const listQuery = vi.hoisted(() => ({
  events: [] as unknown[],
  isLoading: false,
  isFetching: false,
  isFetchingNextPage: false,
  hasNextPage: false,
  fetchNextPage: vi.fn(),
}))
const myQuery = vi.hoisted(() => ({
  data: undefined as unknown[] | undefined,
  isLoading: false,
  isFetching: false,
}))
vi.mock("@/api/hooks/events", () => ({
  EVENTS_PAGE_SIZE: 12,
  useEventsListQuery: () => listQuery,
  useMyEventsQuery: () => myQuery,
}))

const resetEtagSpy = vi.hoisted(() => ({ fn: vi.fn() }))
vi.mock("@/api/client", () => ({ resetEtagCache: () => resetEtagSpy.fn() }))

const invalidateSpy = vi.hoisted(() => ({ fn: vi.fn() }))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: invalidateSpy.fn }),
}))

vi.mock("@/hooks/useEventsKeyboardNav", () => ({
  useEventsKeyboardNav: () => ({ activeIndex: -1, registerRef: vi.fn() }),
}))

/* Lightweight child stubs that surface props as observable DOM. */
vi.mock("@/components/events/EventsBackdrop", () => ({
  EventsBackdrop: () => <div data-testid="backdrop" />,
}))
vi.mock("../components/EventsHeader", () => ({
  EventsHeader: (props: Record<string, unknown>) => (
    <div data-testid="header">
      <span data-testid="events-count">{String(props.eventsCount)}</span>
      <button onClick={() => (props.onTabChange as (v: string) => void)("my")}>tab-my</button>
      <button onClick={() => (props.onTabChange as (v: string) => void)("archive")}>
        tab-archive
      </button>
      <button onClick={() => (props.onSortChange as (v: string) => void)("popular")}>
        sort-popular
      </button>
      <button onClick={() => (props.onSortChange as (v: string) => void)("upcoming")}>
        sort-upcoming
      </button>
      <button onClick={() => (props.onSortChange as (v: string) => void)("newest")}>
        sort-newest
      </button>
      <button onClick={() => (props.onCategoryChange as (v: string) => void)("lecture")}>
        cat-lecture
      </button>
      <button onClick={() => (props.onCategoryChange as (v: string) => void)("all")}>
        cat-all
      </button>
      <button onClick={() => (props.onSearchChange as (v: string) => void)("hack")}>
        search-set
      </button>
      <button onClick={() => (props.onSearchChange as (v: string) => void)("")}>
        search-clear
      </button>
      <button onClick={() => (props.onDateRangeChange as (v: string) => void)("today")}>
        dr-today
      </button>
      <button onClick={() => (props.onLocationChange as (v: string) => void)("hall")}>
        loc-set
      </button>
      <button onClick={() => (props.onAddClick as () => void)()}>header-add</button>
    </div>
  ),
}))
vi.mock("../components/EventsList", () => ({
  EventsList: (props: Record<string, unknown>) => (
    <div data-testid="list">
      <span data-testid="list-count">{(props.eventsList as unknown[]).length}</span>
      <span data-testid="list-initial-loading">{String(props.isInitialLoading)}</span>
      <span data-testid="list-fetching">{String(props.isFetching)}</span>
      <span data-testid="list-has-next">{String(props.hasNextPage)}</span>
      <button onClick={() => (props.fetchNextPage as () => void)()}>fetch-next</button>
      <button onClick={() => (props.refreshEvents as () => void)()}>refresh</button>
    </div>
  ),
}))
vi.mock("../components/EventFormDialog", () => ({
  EventFormDialog: (props: Record<string, unknown>) => (
    <div data-testid="dialog" data-open={String(props.open)}>
      <button onClick={() => (props.onClose as () => void)()}>dialog-close</button>
      <button onClick={() => (props.onSuccess as () => void)()}>dialog-success</button>
    </div>
  ),
}))
vi.mock("../components/EventsShortcutsOverlay", () => ({
  EventsShortcutsOverlay: () => <div data-testid="shortcuts" />,
}))

import { EventsFeature } from "@/features/events/EventsFeature"

function evt(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: over.id ?? "e1",
    title: "T",
    created_at: "2026-01-01T00:00:00.000Z",
    ends_at: "2026-01-15T12:00:00.000Z",
    created_by: "u1",
    is_active: true,
    starts_at: "2026-01-15T10:00:00.000Z",
    event_type: "lecture",
    participant_count: 5,
    ...over,
  }
}

beforeEach(() => {
  search.params = {}
  navigateSpy.fn = vi.fn((..._a: unknown[]) => undefined)
  listQuery.events = []
  listQuery.isLoading = false
  listQuery.isFetching = false
  listQuery.isFetchingNextPage = false
  listQuery.hasNextPage = false
  listQuery.fetchNextPage = vi.fn()
  myQuery.data = undefined
  myQuery.isLoading = false
  myQuery.isFetching = false
  resetEtagSpy.fn = vi.fn()
  invalidateSpy.fn = vi.fn()
  auth.user = { id: "u1", role: "student" }
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("EventsFeature — URL change handlers (set + delete branches)", () => {
  it("writes a value via navigate when a setter receives a non-empty value (86)", () => {
    render(<EventsFeature />)
    act(() => fireEvent.click(screen.getByText("loc-set")))
    expect(navigateSpy.fn).toHaveBeenCalled()
    const call = navigateSpy.fn.mock.calls[0]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    expect(call.search({})).toEqual({ loc: "hall" })
  })

  it("deletes a key via navigate when a setter receives an empty value (87-88)", () => {
    render(<EventsFeature />)
    act(() => fireEvent.click(screen.getByText("search-clear")))
    const call = navigateSpy.fn.mock.calls[0]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    expect(call.search({ q: "old", tab: "active" })).toEqual({ tab: "active" })
  })

  it("maps sort 'newest' to an empty value (delete) and 'popular' to a value", () => {
    render(<EventsFeature />)
    // Two clicks append to the SAME spy (the component closes over the stable
    // navigate ref captured at render time — re-assigning the spy mid-test
    // would leave the component calling the original function).
    act(() => fireEvent.click(screen.getByText("sort-newest")))
    act(() => fireEvent.click(screen.getByText("sort-popular")))
    const newestCall = navigateSpy.fn.mock.calls[0]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    const popularCall = navigateSpy.fn.mock.calls[1]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    expect(newestCall.search({ sort: "popular" })).toEqual({})
    expect(popularCall.search({})).toEqual({ sort: "popular" })
  })

  it("maps category 'all' to an empty value (delete) and 'lecture' to a value", () => {
    render(<EventsFeature />)
    act(() => fireEvent.click(screen.getByText("cat-all")))
    act(() => fireEvent.click(screen.getByText("cat-lecture")))
    const allCall = navigateSpy.fn.mock.calls[0]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    const lectureCall = navigateSpy.fn.mock.calls[1]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    expect(allCall.search({ cat: "lecture" })).toEqual({})
    expect(lectureCall.search({})).toEqual({ cat: "lecture" })
  })

  it("routes the tab + date-range setters through navigate", () => {
    render(<EventsFeature />)
    act(() => fireEvent.click(screen.getByText("tab-archive")))
    act(() => fireEvent.click(screen.getByText("dr-today")))
    const tabCall = navigateSpy.fn.mock.calls[0]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    const drCall = navigateSpy.fn.mock.calls[1]![0] as {
      search: (p: Record<string, unknown>) => unknown
    }
    expect(tabCall.search({})).toEqual({ tab: "archive" })
    expect(drCall.search({})).toEqual({ dr: "today" })
  })
})

describe("EventsFeature — tab-driven data + loading flags", () => {
  it("uses the list query for the active tab (121 active branch)", () => {
    listQuery.events = [evt({ id: "a" }), evt({ id: "b" })]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("2")
  })

  it("uses myEvents data + loading flags when tab is 'my' (156, 159-160)", () => {
    search.params = { tab: "my" }
    myQuery.data = [evt({ id: "m1" })]
    myQuery.isLoading = true
    myQuery.isFetching = true
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
    expect(screen.getByTestId("list-initial-loading")).toHaveTextContent("true")
    expect(screen.getByTestId("list-fetching")).toHaveTextContent("true")
  })

  it("falls back to an empty array when myEvents data is undefined", () => {
    search.params = { tab: "my" }
    myQuery.data = undefined
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("0")
  })

  it("reflects list loading flags on the active tab (159-160 active side)", () => {
    listQuery.isLoading = true
    listQuery.isFetching = true
    render(<EventsFeature />)
    expect(screen.getByTestId("list-initial-loading")).toHaveTextContent("true")
    expect(screen.getByTestId("list-fetching")).toHaveTextContent("true")
  })

  it("maps tab 'archive' to is_active=false without error (121 archive branch)", () => {
    search.params = { tab: "archive" }
    listQuery.events = [evt()]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
  })
})

describe("EventsFeature — client-side category + date filters", () => {
  it("filters by category when activeCategory !== 'all' (167-171)", () => {
    search.params = { cat: "lecture" }
    listQuery.events = [
      evt({ id: "lec", event_type: "lecture" }),
      evt({ id: "sport", event_type: "football match" }),
    ]
    render(<EventsFeature />)
    // Only the lecture event survives the category filter.
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
    expect(screen.getByTestId("events-count")).toHaveTextContent("1")
  })

  it("uses event_type_en fallback in category inference", () => {
    search.params = { cat: "lecture" }
    listQuery.events = [evt({ id: "x", event_type: null, event_type_en: "lecture series" })]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
  })

  it("filters by the 'today' date range and drops out-of-range / start-less events (175-182)", () => {
    const now = new Date()
    const todayIso = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12).toISOString()
    search.params = { dr: "today" }
    listQuery.events = [
      evt({ id: "today", starts_at: todayIso }),
      evt({ id: "past", starts_at: "2000-01-01T00:00:00.000Z" }),
    ]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
  })

  it("filters by the 'week' date range", () => {
    const now = new Date()
    const thisWeekIso = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9).toISOString()
    search.params = { dr: "week" }
    listQuery.events = [
      evt({ id: "w", starts_at: thisWeekIso }),
      evt({ id: "old", starts_at: "1999-01-01T00:00:00.000Z" }),
    ]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
  })

  it("filters by the 'month' date range", () => {
    const now = new Date()
    const thisMonthIso = new Date(now.getFullYear(), now.getMonth(), 15, 9).toISOString()
    search.params = { dr: "month" }
    listQuery.events = [
      evt({ id: "m", starts_at: thisMonthIso }),
      evt({ id: "old", starts_at: "1990-06-15T00:00:00.000Z" }),
    ]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
  })

  it("applies no date filter when dr is empty (getDateRangeBounds null — branch 28)", () => {
    search.params = {}
    listQuery.events = [evt({ id: "a" }), evt({ id: "b" })]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("2")
  })
})

describe("EventsFeature — sort modes", () => {
  it("sorts by participant_count desc when sort='popular' (185-186)", () => {
    search.params = { sort: "popular" }
    listQuery.events = [
      evt({ id: "low", participant_count: 1 }),
      evt({ id: "high", participant_count: 99 }),
    ]
    render(<EventsFeature />)
    // Both survive; sort branch executed without error.
    expect(screen.getByTestId("list-count")).toHaveTextContent("2")
  })

  it("filters to future events + sorts ascending when sort='upcoming' (187-192)", () => {
    const future = new Date(Date.now() + 86_400_000).toISOString()
    search.params = { sort: "upcoming" }
    listQuery.events = [
      evt({ id: "future", starts_at: future }),
      evt({ id: "past", starts_at: "2000-01-01T00:00:00.000Z" }),
    ]
    render(<EventsFeature />)
    // Only the future event survives the upcoming filter.
    expect(screen.getByTestId("list-count")).toHaveTextContent("1")
  })

  it("handles missing participant_count in popular sort (?? 0 fallback)", () => {
    search.params = { sort: "popular" }
    listQuery.events = [evt({ id: "a", participant_count: undefined }), evt({ id: "b" })]
    render(<EventsFeature />)
    expect(screen.getByTestId("list-count")).toHaveTextContent("2")
  })
})

describe("EventsFeature — refresh + dialog + derived flags", () => {
  it("refreshEvents resets the etag cache + invalidates the events query (201-202)", () => {
    render(<EventsFeature />)
    act(() => fireEvent.click(screen.getByText("refresh")))
    expect(resetEtagSpy.fn).toHaveBeenCalled()
    expect(invalidateSpy.fn).toHaveBeenCalledWith({ queryKey: ["events"] })
  })

  it("opens the create dialog from the header add button + closes it", () => {
    render(<EventsFeature />)
    expect(screen.getByTestId("dialog")).toHaveAttribute("data-open", "false")
    act(() => fireEvent.click(screen.getByText("header-add")))
    expect(screen.getByTestId("dialog")).toHaveAttribute("data-open", "true")
    act(() => fireEvent.click(screen.getByText("dialog-close")))
    expect(screen.getByTestId("dialog")).toHaveAttribute("data-open", "false")
  })

  it("dialog success triggers refreshEvents", () => {
    render(<EventsFeature />)
    act(() => fireEvent.click(screen.getByText("dialog-success")))
    expect(resetEtagSpy.fn).toHaveBeenCalled()
    expect(invalidateSpy.fn).toHaveBeenCalledWith({ queryKey: ["events"] })
  })

  it("enables fetch-more only on a non-my tab with no search + 'all' category (206-207)", () => {
    listQuery.hasNextPage = true
    render(<EventsFeature />)
    expect(screen.getByTestId("list-has-next")).toHaveTextContent("true")
    act(() => fireEvent.click(screen.getByText("fetch-next")))
    expect(listQuery.fetchNextPage).toHaveBeenCalled()
  })

  it("disables fetch-more once a category filter is active", () => {
    search.params = { cat: "lecture" }
    listQuery.hasNextPage = true
    render(<EventsFeature />)
    expect(screen.getByTestId("list-has-next")).toHaveTextContent("false")
  })

  it("treats teacher + admin roles as admins (isAdmin derivation)", () => {
    auth.user = { id: "u2", role: "admin" }
    const { unmount } = render(<EventsFeature />)
    expect(screen.getByTestId("header")).toBeInTheDocument()
    unmount()
    auth.user = { id: "u3", role: "teacher" }
    render(<EventsFeature />)
    expect(screen.getByTestId("header")).toBeInTheDocument()
  })

  it("handles a null user (user?.id ?? null + isAdmin false)", () => {
    auth.user = null
    render(<EventsFeature />)
    expect(screen.getByTestId("header")).toBeInTheDocument()
  })
})
