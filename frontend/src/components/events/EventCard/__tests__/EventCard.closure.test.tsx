import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const { useEventCardLogicMock } = vi.hoisted(() => ({
  useEventCardLogicMock: vi.fn(),
}))

vi.mock("@/hooks/useEventCardLogic", () => ({
  useEventCardLogic: useEventCardLogicMock,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@/components/events/EventCard/EventCardSkeleton", () => ({
  EventCardSkeleton: () => <div data-testid="event-card-skeleton" />,
}))

vi.mock("@/components/events/EventCard/EventCardView", () => ({
  EventCardView: (props: Record<string, unknown>) => {
    const onEditOpen = props.onEditOpen as () => void
    const onEditClose = props.onEditClose as () => void
    const onDeleteOpen = props.onDeleteOpen as () => void
    const onDeleteClose = props.onDeleteClose as () => void
    const onErrorClose = props.onErrorClose as () => void

    return (
      <div data-testid="event-card-view">
        <span>{String(props.title)}</span>
        <span data-testid="event-card-admin">{String(props.isAdmin)}</span>
        <span data-testid="event-card-loading">{String(props.loading)}</span>
        <span data-testid="event-card-image">{String(props.imageUrl)}</span>
        <span data-testid="event-card-starts">{String(props.startsAt)}</span>
        <span data-testid="event-card-location">{String(props.location)}</span>
        <button type="button" onClick={onEditOpen}>
          edit-open
        </button>
        <button type="button" onClick={onEditClose}>
          edit-close
        </button>
        <button type="button" onClick={onDeleteOpen}>
          delete-open
        </button>
        <button type="button" onClick={onDeleteClose}>
          delete-close
        </button>
        <button type="button" onClick={onErrorClose}>
          error-close
        </button>
      </div>
    )
  },
}))

import EventCard from "../EventCard"

const makeLogic = () => ({
  user: { id: "user-1", role: "admin" },
  spotlight: { mouseX: {}, mouseY: {}, onMouseMove: vi.fn() },
  menuId: "event-card-menu-event-1",
  timeStatus: { status: "soon" as const },
  eventEnded: false,
  cardImageUrl: "https://example.test/event.jpg",
  snackbar: "",
  setSnackbar: vi.fn(),
  loading: false,
  menuAnchor: null,
  setMenuAnchor: vi.fn(),
  editOpen: false,
  setEditOpen: vi.fn(),
  confirmDeleteOpen: false,
  setConfirmDeleteOpen: vi.fn(),
  editData: {},
  setEditData: vi.fn(),
  newImage: null,
  setNewImage: vi.fn(),
  imageLoading: false,
  previewUrl: null,
  registration: {
    participantCount: 4,
    isRegistered: true,
    isLoading: false,
  },
  handleEdit: vi.fn(),
  handleDelete: vi.fn(),
})

const baseProps = {
  id: "event-1",
  title: "Workshop",
  description: "Description",
  location: "Room 1",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  event_type: "workshop",
  participant_count: 1,
  is_registered: false,
}

afterEach(() => {
  vi.clearAllMocks()
})

describe("EventCard logic wrapper closure paths", () => {
  it("forwards logic state and invokes every wrapper callback", async () => {
    const logic = makeLogic()
    useEventCardLogicMock.mockReturnValue(logic)

    render(<EventCard {...baseProps} />)

    await waitFor(() => expect(screen.getByTestId("event-card-view")).toBeInTheDocument())
    expect(screen.getByText("Workshop")).toBeInTheDocument()
    expect(screen.getByTestId("event-card-admin")).toHaveTextContent("true")

    fireEvent.click(screen.getByRole("button", { name: "edit-open" }))
    fireEvent.click(screen.getByRole("button", { name: "edit-close" }))
    fireEvent.click(screen.getByRole("button", { name: "delete-open" }))
    fireEvent.click(screen.getByRole("button", { name: "delete-close" }))
    fireEvent.click(screen.getByRole("button", { name: "error-close" }))

    expect(logic.setEditOpen).toHaveBeenNthCalledWith(1, true)
    expect(logic.setEditOpen).toHaveBeenNthCalledWith(2, false)
    expect(logic.setConfirmDeleteOpen).toHaveBeenNthCalledWith(1, true)
    expect(logic.setConfirmDeleteOpen).toHaveBeenNthCalledWith(2, false)
    expect(logic.setSnackbar).toHaveBeenCalledWith("")
  })

  it("uses the memo comparator for unchanged cards and detects the last compared field", async () => {
    const logic = makeLogic()
    useEventCardLogicMock.mockReturnValue(logic)
    const { rerender } = render(<EventCard {...baseProps} />)

    await waitFor(() => expect(screen.getByTestId("event-card-view")).toBeInTheDocument())
    expect(useEventCardLogicMock).toHaveBeenCalledOnce()

    rerender(<EventCard {...baseProps} />)
    expect(useEventCardLogicMock).toHaveBeenCalledOnce()

    rerender(<EventCard {...baseProps} participant_count={2} />)
    expect(useEventCardLogicMock).toHaveBeenCalledTimes(2)
  })

  it("handles anonymous users, empty optional fields, and registration loading", async () => {
    const logic = {
      ...makeLogic(),
      user: null,
      cardImageUrl: "",
      loading: false,
      registration: {
        participantCount: 0,
        isRegistered: false,
        isLoading: true,
      },
    }
    useEventCardLogicMock.mockReturnValue(logic)

    render(
      <EventCard
        id="event-empty"
        title=""
        speaker={undefined}
        starts_at=""
        ends_at={undefined}
        location={undefined}
        description={undefined}
        event_type={undefined}
        event_type_en={undefined}
        priority={false}
      />
    )

    await waitFor(() => expect(screen.getByTestId("event-card-view")).toBeInTheDocument())
    expect(screen.getByTestId("event-card-admin")).toHaveTextContent("false")
    expect(screen.getByTestId("event-card-loading")).toHaveTextContent("true")
    expect(screen.getByTestId("event-card-image")).toHaveTextContent("undefined")
    expect(screen.getByTestId("event-card-starts")).toHaveTextContent("")
    expect(screen.getByTestId("event-card-location")).toHaveTextContent("undefined")
  })

  it("grants event administration controls to teachers", async () => {
    useEventCardLogicMock.mockReturnValue({
      ...makeLogic(),
      user: { id: "teacher-1", role: "teacher" },
    })

    render(<EventCard {...baseProps} />)

    await waitFor(() => expect(screen.getByTestId("event-card-admin")).toHaveTextContent("true"))
  })
})
