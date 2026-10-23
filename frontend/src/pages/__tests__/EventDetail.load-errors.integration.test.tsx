import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { HttpResponse, http } from "msw"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { server } from "@/tests/mocks/server"
import EventDetail from "../EventDetail"

const mocks = vi.hoisted(() => ({
  id: "event-detail-http-404",
  user: null as { id: string; role: string } | null,
  navigate: vi.fn(),
  t: (key: string) => key,
}))

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ id: mocks.id }),
  useNavigate: () => mocks.navigate,
  useRouter: () => ({ history: { canGoBack: () => false, back: vi.fn() } }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t, i18n: { language: "en" } }),
}))

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: mocks.user }) }))

vi.mock("@/api/hooks/events", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/hooks/events")>()
  return {
    ...actual,
    useEventNavigation: () => ({ prevId: null, nextId: null, prevTitle: null, nextTitle: null }),
  }
})

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useSwipe", () => ({ useSwipe: () => ({}) }))
vi.mock("@/hooks/useRelatedEvents", () => ({ useRelatedEvents: () => [] }))
vi.mock("@/hooks/useEventRegistration", () => ({ useEventRegistration: () => ({}) }))
vi.mock("@/features/events/categories", () => ({ inferEventCategory: () => "lecture" }))
vi.mock("@/utils/eventsTransition", () => ({ setEventsHeroId: vi.fn() }))
vi.mock("@/app/logger", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/app/logger")>()
  return { ...actual, logError: vi.fn() }
})

vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))
vi.mock("@/components/ui/Button", () => ({
  Button: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}))
vi.mock("@/components/events/EventsBackdrop", () => ({ EventsBackdrop: () => null }))
vi.mock("@/components/events/EventDetailHeader", () => ({
  EventDetailHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}))
vi.mock("@/components/events/EventDetailHero", () => ({ EventDetailHero: () => null }))
vi.mock("@/components/events/EventDetailBody", () => ({ EventDetailBody: () => null }))
vi.mock("@/components/events/EventDetailNavigation", () => ({ EventDetailNavigation: () => null }))
vi.mock("@/components/events/RelatedEvents", () => ({ RelatedEvents: () => null }))
vi.mock("@/components/events/EventDetailSkeleton", () => ({ EventDetailSkeleton: () => null }))
vi.mock("@/components/events/EventDetailEditDialog", () => ({ EventDetailEditDialog: () => null }))

const eventUrl = "*/api/v1/events/:eventId"

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { gcTime: Infinity, retryDelay: 0 } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <EventDetail />
    </QueryClientProvider>
  )
  return queryClient
}

describe("EventDetail HTTP error states through the real event hook and SDK", () => {
  beforeEach(() => {
    mocks.id = "event-detail-http-404"
    mocks.user = null
    mocks.navigate.mockReset()
  })

  afterEach(() => {
    cleanup()
    server.resetHandlers()
  })

  it.each([
    [404, "events:detail.messages.notFound", "events:detail.messages.loadFailed"],
    [500, "events:detail.messages.loadFailed", "events:detail.messages.notFound"],
  ])(
    "maps a real HTTP %s response to the correct page message",
    async (status, message, otherMessage) => {
      const handled = vi.fn()
      server.use(
        http.get(eventUrl, () => {
          handled()
          return HttpResponse.json({ detail: `HTTP ${status}` }, { status })
        })
      )

      renderPage()

      expect(await screen.findByText(message)).toBeInTheDocument()
      expect(screen.queryByText(otherMessage)).not.toBeInTheDocument()
      expect(handled).toHaveBeenCalled()
    }
  )

  it("shows the load-failed message for a real network failure", async () => {
    const handled = vi.fn()
    server.use(
      http.get(eventUrl, () => {
        handled()
        return HttpResponse.error()
      })
    )

    renderPage()

    expect(await screen.findByText("events:detail.messages.loadFailed")).toBeInTheDocument()
    expect(screen.queryByText("events:detail.messages.notFound")).not.toBeInTheDocument()
    expect(handled).toHaveBeenCalled()
  })

  it("shows the load-failed message for an empty successful response", async () => {
    server.use(http.get(eventUrl, () => HttpResponse.text("")))

    renderPage()

    expect(await screen.findByText("events:detail.messages.loadFailed")).toBeInTheDocument()
    expect(screen.queryByText("events:detail.messages.notFound")).not.toBeInTheDocument()
  })

  it("renders a valid 2xx event payload", async () => {
    mocks.id = "event-detail-http-valid"
    server.use(
      http.get(eventUrl, () =>
        HttpResponse.json({
          id: mocks.id,
          title: "Validated lecture",
          created_at: "2026-10-23T10:00:00.000Z",
          created_by: "teacher-1",
          starts_at: "2026-10-24T10:00:00.000Z",
          ends_at: "2026-10-24T11:00:00.000Z",
          is_active: true,
        })
      )
    )

    renderPage()

    expect(await screen.findByRole("heading", { name: "Validated lecture" })).toBeInTheDocument()
  })
})
