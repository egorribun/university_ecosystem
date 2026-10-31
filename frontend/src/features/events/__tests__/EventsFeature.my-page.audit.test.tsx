import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import "@/api/client"
import i18n from "@/i18n/config"
import enCommon from "@/i18n/locales/en/common.json"
import type { UserState } from "@/types/Auth"
import { useAuthStore } from "@/stores/useAuthStore"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { server } from "@/tests/mocks/server"

const state = vi.hoisted(() => ({
  search: { tab: "my" } as Record<string, string>,
  language: "en" as "en" | "ru",
  timezone: "UTC" as string | null,
  clock: Date.parse("2026-10-28T12:00:00Z"),
  user: { id: "account-a", role: "student" } as { id: string; role: string } | null,
}))

vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  useSearch: () => state.search,
  useNavigate:
    () => (options: { search: (previous: Record<string, string>) => typeof state.search }) => {
      state.search = options.search(state.search)
    },
}))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: state.user }) }))
vi.mock("@/contexts/LanguageContext", () => ({ useLanguage: () => ({ language: state.language }) }))
vi.mock("@/contexts/CampusTimezoneContext", () => ({ useCampusTimezone: () => state.timezone }))
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => true }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useDebounced", () => ({ useDebounced: (value: string) => value }))
vi.mock("@/hooks/useMinuteClock", () => ({ useMinuteClock: () => state.clock }))
vi.mock("@/hooks/ui/useStableListHeight", () => ({ useStableListHeight: () => undefined }))
vi.mock("@/hooks/useEventsKeyboardNav", () => ({
  useEventsKeyboardNav: () => ({ activeIndex: -1, registerRef: () => undefined }),
}))
vi.mock("@/components/events/EventsBackdrop", () => ({ EventsBackdrop: () => null }))
vi.mock("../components/EventFormDialog", () => ({ EventFormDialog: () => null }))
vi.mock("../components/EventsShortcutsOverlay", () => ({ EventsShortcutsOverlay: () => null }))
vi.mock("@/components/error", () => ({
  FeatureErrorBoundary: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock("@/components/events/EventCard/EventCard", () => ({
  default: ({
    id,
    participant_count,
    qrStorage,
  }: {
    id: string
    participant_count: number
    qrStorage: string
  }) => <div data-testid="card">{`${id}:${participant_count}:${qrStorage}`}</div>,
}))
vi.mock("../components/EventsHeader", () => ({
  EventsHeader: (props: {
    eventsCount?: number
    onCategoryChange: (category: "seminar") => void
    onSortChange: (sort: "popular") => void
  }) => (
    <div>
      <span data-testid="total">
        {props.eventsCount === undefined ? "unknown" : props.eventsCount}
      </span>
      <button type="button" onClick={() => props.onCategoryChange("seminar")}>
        category
      </button>
      <button type="button" onClick={() => props.onSortChange("popular")}>
        popular
      </button>
    </div>
  ),
}))

import { EventsFeature } from "../EventsFeature"

function event(id: number, participantCount = id) {
  return {
    id: `event-${id}`,
    title: `Event ${id}`,
    created_at: "2026-01-01T00:00:00Z",
    created_by: "owner",
    starts_at: "2026-12-10T10:00:00Z",
    ends_at: "2026-12-10T11:00:00Z",
    is_active: true,
    is_registered: true,
    participant_count: participantCount,
    my_qr_token: null,
  }
}

function installPages(requests: URL[]) {
  server.use(
    http.get("*/events/my/page", ({ request }) => {
      const url = new URL(request.url)
      requests.push(url)
      const cursor = url.searchParams.get("cursor")
      const popular = url.searchParams.get("sort") === "popular"
      const offset = cursor === "page-2" ? 12 : cursor === "page-3" ? 24 : 0
      const items = popular
        ? [event(2, 37), event(1, 8)]
        : Array.from({ length: Math.min(12, 25 - offset) }, (_, index) => event(offset + index + 1))
      const next = popular || offset === 24 ? null : offset === 0 ? "page-2" : "page-3"
      return HttpResponse.json({
        items,
        total: null,
        limit: 12,
        cursor,
        next_cursor: next,
        has_more: next !== null,
      })
    })
  )
}

function renderFeature() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <EventsFeature />
    </QueryClientProvider>
  )
  return {
    ...view,
    client,
    rerenderFeature: () =>
      view.rerender(
        <QueryClientProvider client={client}>
          <EventsFeature />
        </QueryClientProvider>
      ),
    dispose: () => {
      view.unmount()
      client.clear()
    },
  }
}

beforeEach(async () => {
  localStorage.clear()
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  state.search = { tab: "my" }
  state.language = "en"
  state.timezone = "UTC"
  state.clock = Date.parse("2026-10-28T12:00:00Z")
  state.user = { id: "account-a", role: "student" }
  useAuthStore.setState({ user: { id: "account-a" } as UserState, loading: false })
  await i18n.changeLanguage("en")
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: false })
  localStorage.clear()
})

describe("AUD-260 My Events integration", () => {
  it("loads one page at a time and supports first, next and previous without a false total", async () => {
    const requests: URL[] = []
    installPages(requests)
    const view = renderFeature()
    await waitFor(() => expect(screen.getByText("event-1:1:memory")).toBeInTheDocument(), {
      timeout: 1_500,
    })
    expect(screen.getAllByTestId("card")).toHaveLength(12)
    expect(screen.getByTestId("total")).toHaveTextContent("unknown")
    expect(requests).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: enCommon.pagination.nextPage }))
    await waitFor(() => expect(screen.getByText("event-13:13:memory")).toBeInTheDocument())
    expect(screen.queryByText("event-1:1:memory")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: enCommon.pagination.nextPage }))
    await waitFor(() => expect(screen.getByText("event-25:25:memory")).toBeInTheDocument())
    expect(screen.getAllByTestId("card")).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: enCommon.pagination.prevPage }))
    await waitFor(() => expect(screen.getByText("event-13:13:memory")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: enCommon.pagination.firstPage }))
    await waitFor(() => expect(screen.getByText("event-1:1:memory")).toBeInTheDocument())
    expect(requests.map((url) => url.searchParams.get("cursor"))).toEqual([
      null,
      "page-2",
      "page-3",
      "page-2",
      null,
    ])
    view.dispose()
  })

  it("resets the cursor before changing category and uses server popularity and counts", async () => {
    const requests: URL[] = []
    installPages(requests)
    const view = renderFeature()
    await waitFor(() => expect(screen.getByText("event-1:1:memory")).toBeInTheDocument(), {
      timeout: 1_500,
    })
    fireEvent.click(screen.getByRole("button", { name: enCommon.pagination.nextPage }))
    await waitFor(() => expect(screen.getByText("event-13:13:memory")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "category" }))
    view.rerenderFeature()
    await waitFor(() =>
      expect(requests.some((url) => url.searchParams.get("category") === "seminar")).toBe(true)
    )
    expect(
      requests
        .filter((url) => url.searchParams.get("category") === "seminar")
        .every((url) => url.searchParams.get("cursor") === null)
    ).toBe(true)
    fireEvent.click(screen.getByRole("button", { name: "popular" }))
    view.rerenderFeature()
    await waitFor(() => expect(screen.getByText("event-2:37:memory")).toBeInTheDocument())
    expect(screen.getAllByTestId("card").map((card) => card.textContent)).toEqual([
      "event-2:37:memory",
      "event-1:8:memory",
    ])
    expect(requests.at(-1)?.searchParams.get("sort")).toBe("popular")
    view.dispose()
  })

  it("keeps the upcoming cutoff fixed while navigating a chain", async () => {
    state.search.sort = "upcoming"
    const requests: URL[] = []
    installPages(requests)
    const view = renderFeature()
    await waitFor(() => expect(screen.getByText("event-1:1:memory")).toBeInTheDocument(), {
      timeout: 1_500,
    })
    state.clock += 60_000
    view.rerenderFeature()
    fireEvent.click(screen.getByRole("button", { name: enCommon.pagination.nextPage }))
    await waitFor(() => expect(screen.getByText("event-13:13:memory")).toBeInTheDocument())
    expect(requests[0]?.searchParams.get("upcoming_after")).toBe("2026-10-28T12:00:00.000Z")
    expect(requests[1]?.searchParams.get("upcoming_after")).toBe(
      requests[0]?.searchParams.get("upcoming_after")
    )
    view.dispose()
  })

  it("does not fetch an unfiltered My page when the campus timezone is unavailable", async () => {
    state.search.dr = "today"
    state.timezone = null
    const requests: URL[] = []
    installPages(requests)
    const view = renderFeature()
    await act(async () => undefined)
    expect(requests).toHaveLength(0)
    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText("event-1:1:memory")).not.toBeInTheDocument()
    view.dispose()
  })
})
