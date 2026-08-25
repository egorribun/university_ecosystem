import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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
  id: "event-1",
  user: { id: "admin-1", role: "admin" } as { id: string; role: string } | null,
  language: "en",
  media: { reduced: false, narrow: false },
  navigation: {
    prevId: null as string | null,
    nextId: null as string | null,
    prevTitle: null as string | null,
    nextTitle: null as string | null,
  },
  relatedEvents: [] as unknown[],
  registration: {
    participantCount: 8,
    isRegistered: false,
    isLoading: false,
    register: vi.fn(),
    unregister: vi.fn(),
  },
  swipeOptions: null as { onSwipeLeft: () => void; onSwipeRight: () => void } | null,
  navigate: vi.fn(),
  invalidateQueries: vi.fn(),
  delete: vi.fn(),
  setEventsHeroId: vi.fn(),
  t: (key: string) => key,
}))

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ id: mocks.id }),
  useNavigate: () => mocks.navigate,
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t, i18n: { language: mocks.language } }),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user }),
}))

vi.mock("@/api/hooks/events", () => ({
  useEventDetailQuery: () => mocks.detail,
  useEventNavigation: () => mocks.navigation,
}))

vi.mock("@/api/client", () => ({ default: { delete: mocks.delete } }))
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) =>
    query.includes("prefers") ? mocks.media.reduced : mocks.media.narrow,
}))
vi.mock("@/hooks/useSwipe", () => ({
  useSwipe: (options: { onSwipeLeft: () => void; onSwipeRight: () => void }) => {
    mocks.swipeOptions = options
    return {}
  },
}))
vi.mock("@/hooks/useRelatedEvents", () => ({ useRelatedEvents: () => mocks.relatedEvents }))
vi.mock("@/hooks/useEventRegistration", () => ({
  useEventRegistration: () => mocks.registration,
}))
vi.mock("@/features/events/categories", () => ({ inferEventCategory: () => "lecture" }))
vi.mock("@/utils/eventsTransition", () => ({ setEventsHeroId: mocks.setEventsHeroId }))

vi.mock("@/components/ui", () => ({
  Button: ({
    children,
    onClick,
    disabled,
    leadingIcon,
  }: {
    children: ReactNode
    onClick?: () => void
    disabled?: boolean
    leadingIcon?: ReactNode
  }) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {leadingIcon}
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
    isLoading,
  }: {
    open: boolean
    title: string
    confirmText: string
    cancelText: string
    onConfirm: () => void
    onCancel: () => void
    isLoading?: boolean
  }) =>
    open ? (
      <div role="alertdialog" aria-label={title}>
        <span data-testid="delete-loading">{String(Boolean(isLoading))}</span>
        <button type="button" onClick={onCancel}>
          {cancelText}
        </button>
        <button type="button" onClick={onConfirm}>
          {confirmText}
        </button>
      </div>
    ) : null,
}))
vi.mock("@/components/ui/Snackbar", () => ({
  default: ({ open, message, onClose }: { open: boolean; message: string; onClose: () => void }) =>
    open ? (
      <div role="status">
        <span>{message}</span>
        <button type="button" onClick={onClose}>
          close snackbar
        </button>
      </div>
    ) : null,
}))
vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))

vi.mock("@/components/events/EventsBackdrop", () => ({ EventsBackdrop: () => <div /> }))
vi.mock("@/components/events/EventDetailSkeleton", () => ({
  EventDetailSkeleton: () => <div data-testid="event-detail-skeleton" />,
}))
vi.mock("@/components/events/EventDetailHero", () => ({
  EventDetailHero: ({ imageUrl }: { imageUrl: string }) => <img alt="event" src={imageUrl} />,
}))
vi.mock("@/components/events/EventDetailBody", () => ({
  EventDetailBody: ({
    onRefresh,
    onError,
    onSuccess,
  }: {
    onRefresh: () => void
    onError: (message: string) => void
    onSuccess: (message: string) => void
  }) => (
    <div>
      <span>event-body</span>
      <button type="button" onClick={() => void onRefresh()}>
        refresh body
      </button>
      <button type="button" onClick={() => onError("body error")}>
        body error
      </button>
      <button type="button" onClick={() => onSuccess("body success")}>
        body success
      </button>
    </div>
  ),
}))
vi.mock("@/components/events/EventDetailNavigation", () => ({
  EventDetailNavigation: () => <div>event-navigation</div>,
}))
vi.mock("@/components/events/RelatedEvents", () => ({
  RelatedEvents: () => <div>related-events</div>,
}))
vi.mock("@/components/events/EventDetailEditDialog", () => ({
  EventDetailEditDialog: ({
    open,
    onClose,
    onSuccess,
    onError,
  }: {
    open: boolean
    onClose: () => void
    onSuccess: (message: string) => void
    onError: (message: string) => void
  }) =>
    open ? (
      <div>
        <span>event-edit-dialog</span>
        <button type="button" onClick={onSuccess.bind(null, "edit success")}>
          edit success
        </button>
        <button type="button" onClick={onError.bind(null, "edit error")}>
          edit error
        </button>
        <button type="button" onClick={onClose}>
          close edit
        </button>
      </div>
    ) : null,
}))
vi.mock("@/components/events/EventDetailHeader", () => ({
  EventDetailHeader: ({
    title,
    onShare,
    onRegister,
    onUnregister,
    onEditOpen,
    onDeleteOpen,
  }: {
    title: string
    onShare: () => void
    onRegister: () => void
    onUnregister: () => void
    onEditOpen: () => void
    onDeleteOpen: () => void
  }) => (
    <header>
      <h1>{title}</h1>
      <button type="button" onClick={onShare}>
        share
      </button>
      <button type="button" onClick={onRegister}>
        register
      </button>
      <button type="button" onClick={onUnregister}>
        unregister
      </button>
      <button onClick={onEditOpen}>edit</button>
      <button onClick={onDeleteOpen}>delete</button>
    </header>
  ),
}))

describe("EventDetail", () => {
  beforeEach(() => {
    mocks.id = "event-1"
    mocks.detail = { data: event, isLoading: false, error: null }
    mocks.user = { id: "admin-1", role: "admin" }
    mocks.language = "en"
    mocks.media.reduced = false
    mocks.media.narrow = false
    mocks.navigation = { prevId: null, nextId: null, prevTitle: null, nextTitle: null }
    mocks.relatedEvents = []
    mocks.registration.participantCount = 8
    mocks.registration.isRegistered = false
    mocks.registration.isLoading = false
    mocks.registration.register.mockReset()
    mocks.registration.unregister.mockReset()
    mocks.swipeOptions = null
    mocks.navigate.mockReset()
    mocks.invalidateQueries.mockReset().mockResolvedValue(undefined)
    mocks.delete.mockReset().mockResolvedValue(undefined)
    mocks.setEventsHeroId.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    window.history.replaceState(null, "", "/")
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

  it("wires registration, swipe navigation, body actions, and edit callbacks", async () => {
    mocks.navigation = {
      prevId: "event-0",
      nextId: "event-2",
      prevTitle: "Previous",
      nextTitle: "Next",
    }
    mocks.relatedEvents = [{ id: "related-1" }]
    render(<EventDetail />)

    fireEvent.click(screen.getByRole("button", { name: "register" }))
    fireEvent.click(screen.getByRole("button", { name: "unregister" }))
    expect(mocks.registration.register).toHaveBeenCalledOnce()
    expect(mocks.registration.unregister).toHaveBeenCalledOnce()

    expect(mocks.swipeOptions).not.toBeNull()
    mocks.swipeOptions?.onSwipeLeft()
    mocks.swipeOptions?.onSwipeRight()
    expect(mocks.navigate).toHaveBeenCalledWith({
      to: "/events/$id",
      params: { id: "event-2" },
    })
    expect(mocks.navigate).toHaveBeenCalledWith({
      to: "/events/$id",
      params: { id: "event-0" },
    })

    fireEvent.click(screen.getByRole("button", { name: "refresh body" }))
    await waitFor(() =>
      expect(mocks.invalidateQueries).toHaveBeenCalledWith({
        queryKey: ["events", "detail", "event-1"],
      })
    )

    fireEvent.click(screen.getByRole("button", { name: "body error" }))
    expect(screen.getByRole("status")).toHaveTextContent("body error")
    fireEvent.click(screen.getByRole("button", { name: "close snackbar" }))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "body success" }))
    expect(screen.getByRole("status")).toHaveTextContent("body success")
    fireEvent.click(screen.getByRole("button", { name: "close snackbar" }))

    fireEvent.click(screen.getByRole("button", { name: "edit" }))
    fireEvent.click(screen.getByRole("button", { name: "edit success" }))
    expect(screen.getByRole("status")).toHaveTextContent("edit success")
    fireEvent.click(screen.getByRole("button", { name: "close snackbar" }))
    fireEvent.click(screen.getByRole("button", { name: "edit" }))
    fireEvent.click(screen.getByRole("button", { name: "edit error" }))
    expect(screen.getByRole("status")).toHaveTextContent("edit error")
    fireEvent.click(screen.getByRole("button", { name: "close edit" }))
    expect(screen.queryByText("event-edit-dialog")).not.toBeInTheDocument()
  })

  it("uses native share when available and ignores a cancelled share", async () => {
    const share = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { share })
    mocks.detail = {
      data: { ...event, title: undefined },
      isLoading: false,
      error: null,
    }
    render(<EventDetail />)

    fireEvent.click(screen.getByRole("button", { name: "share" }))
    await waitFor(() =>
      expect(share).toHaveBeenCalledWith({
        title: "",
        url: window.location.href,
      })
    )

    share.mockRejectedValueOnce(new Error("cancelled"))
    fireEvent.click(screen.getByRole("button", { name: "share" }))
    await waitFor(() => expect(share).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("copies the link when native share is unavailable and handles clipboard failure", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { clipboard: { writeText } })
    render(<EventDetail />)

    fireEvent.click(screen.getByRole("button", { name: "share" }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.href))
    expect(screen.getByRole("status")).toHaveTextContent("events:detail.messages.linkCopied")
    fireEvent.click(screen.getByRole("button", { name: "close snackbar" }))

    writeText.mockRejectedValueOnce(new Error("clipboard unavailable"))
    fireEvent.click(screen.getByRole("button", { name: "share" }))
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("handles failed deletion and cancellation without navigating", async () => {
    mocks.delete.mockRejectedValueOnce(new Error("delete failed"))
    render(<EventDetail />)

    fireEvent.click(screen.getByRole("button", { name: "delete" }))
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "delete" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))
    await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith(`/events/${event.id}`))
    expect(await screen.findByRole("status")).toHaveTextContent(
      "events:card.messages.deleteFailure"
    )
    expect(mocks.navigate).not.toHaveBeenCalledWith({ to: "/events" })
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
  })

  it("uses history back when available and renders narrow inactive events for non-admins", () => {
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {})
    window.history.replaceState({ idx: 1 }, "", "/events/event-1")
    mocks.user = { id: "student-1", role: "student" }
    mocks.media.narrow = true
    mocks.language = "ru"
    mocks.detail = {
      data: {
        id: "event-2",
        title: "Inactive seminar",
        event_type_en: "seminar",
        is_active: false,
      },
      isLoading: false,
      error: null,
    }
    render(<EventDetail />)

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.back" }))
    expect(back).toHaveBeenCalledOnce()
    expect(screen.queryByAltText("event")).not.toBeInTheDocument()
    expect(screen.queryByText("event-edit-dialog")).not.toBeInTheDocument()
  })

  it("falls back to the events route when browser history has no index and user is absent", () => {
    mocks.user = null
    window.history.replaceState(null, "", "/events/event-1")
    mocks.detail = { data: { id: "event-sparse" }, isLoading: false, error: null }
    render(<EventDetail />)

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.back" }))

    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/events" })
  })

  it("updates the Firefox reading-progress fallback on scroll", () => {
    let frameCallback: FrameRequestCallback | undefined
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frameCallback = callback
      return 1
    })
    Object.defineProperty(document.documentElement, "scrollHeight", {
      value: 2000,
      configurable: true,
    })
    Object.defineProperty(window, "innerHeight", { value: 1000, configurable: true })
    Object.defineProperty(window, "scrollY", { value: 500, configurable: true })
    const { container } = render(<EventDetail />)

    fireEvent.scroll(window)
    fireEvent.scroll(window)
    frameCallback?.(0)

    expect(container.querySelector(".events-reading-progress")).toHaveStyle(
      "transform: scaleX(0.5)"
    )

    Object.defineProperty(document.documentElement, "scrollHeight", {
      value: 1000,
      configurable: true,
    })
    fireEvent.scroll(window)
    frameCallback?.(0)
    expect(container.querySelector(".events-reading-progress")).toHaveStyle("transform: scaleX(0)")
  })

  it("ignores unavailable navigation and a detached progress element", () => {
    let frameCallback: FrameRequestCallback | undefined
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frameCallback = callback
      return 1
    })
    const cancelAnimationFrame = vi.fn()
    vi.stubGlobal("cancelAnimationFrame", cancelAnimationFrame)
    mocks.id = ""

    const { unmount } = render(<EventDetail />)

    mocks.swipeOptions?.onSwipeLeft()
    mocks.swipeOptions?.onSwipeRight()
    expect(mocks.navigate).not.toHaveBeenCalled()
    expect(mocks.setEventsHeroId).not.toHaveBeenCalled()

    fireEvent.scroll(window)
    unmount()
    expect(cancelAnimationFrame).toHaveBeenCalledWith(1)
    expect(() => frameCallback?.(0)).not.toThrow()
  })
})
