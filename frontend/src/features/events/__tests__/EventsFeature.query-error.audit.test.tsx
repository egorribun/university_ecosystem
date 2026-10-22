import { render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const auth = vi.hoisted(() => ({ user: { id: "student-1", role: "student" } }))
const listQuery = vi.hoisted(() => ({
  events: [] as unknown[],
  isLoading: false,
  isFetching: false,
  isFetchingNextPage: false,
  hasNextPage: false,
  isError: false,
  fetchNextPage: vi.fn(),
}))
const myQuery = vi.hoisted(() => ({
  data: undefined as unknown[] | undefined,
  isLoading: false,
  isFetching: false,
}))
const nav = vi.hoisted(() => ({ navigate: vi.fn() }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => (key === "common:statuses.error" ? "Something went wrong" : key),
  }),
}))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: auth.user }) }))
vi.mock("@/contexts/LanguageContext", () => ({ useLanguage: () => ({ language: "en" }) }))
vi.mock("@/contexts/CampusTimezoneContext", () => ({
  useCampusTimezone: () => "Europe/Istanbul",
}))
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => true }))
vi.mock("@/hooks/useDebounced", () => ({ useDebounced: <T,>(value: T) => value }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@tanstack/react-router", () => ({
  useSearch: () => ({}),
  useNavigate: () => nav.navigate,
}))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))
vi.mock("@/api/hooks/events", () => ({
  EVENTS_PAGE_SIZE: 12,
  useEventsListQuery: () => listQuery,
  useMyEventsQuery: () => myQuery,
}))
vi.mock("@/api/client", () => ({ resetEtagCache: vi.fn() }))
vi.mock("@/hooks/ui/useStableListHeight", () => ({ useStableListHeight: () => undefined }))
vi.mock("@/hooks/useEventsKeyboardNav", () => ({
  useEventsKeyboardNav: () => ({ activeIndex: -1, registerRef: vi.fn() }),
}))
vi.mock("@/components/events/EventsBackdrop", () => ({ EventsBackdrop: () => null }))
vi.mock("../components/EventsHeader", () => ({ EventsHeader: () => null }))
vi.mock("../components/EventFormDialog", () => ({ EventFormDialog: () => null }))
vi.mock("../components/EventsShortcutsOverlay", () => ({ EventsShortcutsOverlay: () => null }))
vi.mock("@/components/events/EventCard/EventCard", () => ({ default: () => null }))
vi.mock("@/components/events/EventCard/EventCardSkeleton", () => ({
  EventCardSkeleton: () => null,
}))
vi.mock("@/components/feedback/OfflineFallback", () => ({ OfflineFallback: () => null }))
vi.mock("@/components/ui/Button", () => ({
  Button: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <button {...props}>{children}</button>
  ),
}))
vi.mock("@/components/ui/EmptyState", () => ({
  EmptyState: ({ title, description }: { title: string; description?: string }) => (
    <div>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
    </div>
  ),
}))
vi.mock("@/components/error", () => ({
  FeatureErrorBoundary: ({ children }: { children?: ReactNode }) => <>{children}</>,
}))

import { EventsFeature } from "@/features/events/EventsFeature"

describe("AUD-214 events list query state", () => {
  beforeEach(() => {
    listQuery.events = []
    listQuery.isLoading = false
    listQuery.isFetching = false
    listQuery.isFetchingNextPage = false
    listQuery.hasNextPage = false
    listQuery.isError = false
    listQuery.fetchNextPage = vi.fn()
    myQuery.data = undefined
    myQuery.isLoading = false
    myQuery.isFetching = false
    nav.navigate = vi.fn()
  })

  it("shows the normal empty state for a successful empty response", () => {
    render(<EventsFeature />)

    expect(screen.getByText("events:states.empty")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("does not turn a failed event-list request into a successful empty result", () => {
    listQuery.isError = true

    render(<EventsFeature />)

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong")
    expect(screen.queryByText("events:states.empty")).not.toBeInTheDocument()
  })
})
