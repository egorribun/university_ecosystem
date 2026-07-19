import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import EventDetail from "../EventDetail"

const event = {
  id: "event-1",
  title: "Open lecture",
  description: "A practical event description.",
  image_url: "https://example.test/event.jpg",
  event_type: "lecture",
  participant_count: 8,
  is_registered: false,
  is_active: true,
  starts_at: "2026-08-01T10:00:00.000Z",
}

const mocks = vi.hoisted(() => ({
  detail: {} as Record<string, unknown>,
  navigate: vi.fn(),
  invalidateQueries: vi.fn(),
  delete: vi.fn(),
  setEventsHeroId: vi.fn(),
  t: (key: string) => key,
}))

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ id: "event-1" }),
  useNavigate: () => mocks.navigate,
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t, i18n: { language: "en" } }),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "admin-1", role: "admin" } }),
}))

vi.mock("@/api/hooks/events", () => ({
  useEventDetailQuery: () => mocks.detail,
  useEventNavigation: () => ({ prevId: null, nextId: null, prevTitle: null, nextTitle: null }),
}))

vi.mock("@/api/client", () => ({ default: { delete: mocks.delete } }))
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useSwipe", () => ({ useSwipe: () => ({}) }))
vi.mock("@/hooks/useRelatedEvents", () => ({ useRelatedEvents: () => [] }))
vi.mock("@/hooks/useEventRegistration", () => ({
  useEventRegistration: () => ({
    participantCount: 8,
    isRegistered: false,
    isLoading: false,
    register: vi.fn(),
    unregister: vi.fn(),
  }),
}))
vi.mock("@/features/events/categories", () => ({ inferEventCategory: () => "lecture" }))
vi.mock("@/utils/eventsTransition", () => ({ setEventsHeroId: mocks.setEventsHeroId }))

vi.mock("@/components/ui", () => ({
  Button: ({
    children,
    onClick,
    disabled,
  }: {
    children: ReactNode
    onClick?: () => void
    disabled?: boolean
  }) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  ConfirmDialog: ({
    open,
    title,
    confirmText,
    cancelText,
    onConfirm,
    onCancel,
  }: {
    open: boolean
    title: string
    confirmText: string
    cancelText: string
    onConfirm: () => void
    onCancel: () => void
  }) =>
    open ? (
      <div role="alertdialog" aria-label={title}>
        <button onClick={onCancel}>{cancelText}</button>
        <button onClick={onConfirm}>{confirmText}</button>
      </div>
    ) : null,
}))
vi.mock("@/components/ui/Snackbar", () => ({ default: () => null }))
vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))

vi.mock("@/components/events/EventsBackdrop", () => ({ EventsBackdrop: () => <div /> }))
vi.mock("@/components/events/EventDetailSkeleton", () => ({
  EventDetailSkeleton: () => <div data-testid="event-detail-skeleton" />,
}))
vi.mock("@/components/events/EventDetailHero", () => ({
  EventDetailHero: ({ imageUrl }: { imageUrl: string }) => <img alt="event" src={imageUrl} />,
}))
vi.mock("@/components/events/EventDetailBody", () => ({
  EventDetailBody: () => <div>event-body</div>,
}))
vi.mock("@/components/events/EventDetailNavigation", () => ({
  EventDetailNavigation: () => <div>event-navigation</div>,
}))
vi.mock("@/components/events/RelatedEvents", () => ({
  RelatedEvents: () => <div>related-events</div>,
}))
vi.mock("@/components/events/EventDetailEditDialog", () => ({
  EventDetailEditDialog: ({ open }: { open: boolean }) =>
    open ? <div>event-edit-dialog</div> : null,
}))
vi.mock("@/components/events/EventDetailHeader", () => ({
  EventDetailHeader: ({
    title,
    onEditOpen,
    onDeleteOpen,
  }: {
    title: string
    onEditOpen: () => void
    onDeleteOpen: () => void
  }) => (
    <header>
      <h1>{title}</h1>
      <button onClick={onEditOpen}>edit</button>
      <button onClick={onDeleteOpen}>delete</button>
    </header>
  ),
}))

describe("EventDetail", () => {
  beforeEach(() => {
    mocks.detail = { data: event, isLoading: false, error: null }
    mocks.navigate.mockReset()
    mocks.invalidateQueries.mockReset().mockResolvedValue(undefined)
    mocks.delete.mockReset().mockResolvedValue(undefined)
    mocks.setEventsHeroId.mockReset()
  })

  it("renders the skeleton while the event query is loading", () => {
    mocks.detail = { data: undefined, isLoading: true, error: null }

    render(<EventDetail />)

    expect(screen.getByTestId("event-detail-skeleton")).toBeInTheDocument()
  })

  it("renders a navigable not-found state for failed or absent data", () => {
    mocks.detail = { data: undefined, isLoading: false, error: new Error("not found") }

    render(<EventDetail />)

    expect(screen.getByText("events:detail.messages.notFound")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.back" }))
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/events" })
  })

  it("renders data and completes the administrator edit and delete flow", async () => {
    render(<EventDetail />)

    expect(screen.getByRole("heading", { name: event.title })).toBeInTheDocument()
    expect(screen.getByText(event.description)).toBeInTheDocument()
    expect(mocks.setEventsHeroId).toHaveBeenCalledWith(event.id)

    fireEvent.click(screen.getByRole("button", { name: "edit" }))
    expect(screen.getByText("event-edit-dialog")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "delete" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))

    await waitFor(() => {
      expect(mocks.delete).toHaveBeenCalledWith(`/events/${event.id}`)
      expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["events"] })
      expect(mocks.navigate).toHaveBeenCalledWith({ to: "/events" })
    })
  })
})
