import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { MotionValue } from "framer-motion"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("@/components/ui", () => ({
  ConfirmDialog: ({
    open,
    title,
    onConfirm,
    onCancel,
  }: {
    open: boolean
    title: string
    onConfirm: () => void
    onCancel: () => void
  }) =>
    open ? (
      <div role="alertdialog" data-testid="confirm-dialog">
        <h2>{title}</h2>
        <button type="button" onClick={onCancel}>
          cancel-delete
        </button>
        <button type="button" onClick={onConfirm}>
          confirm-delete
        </button>
      </div>
    ) : null,
  Snackbar: ({
    open,
    message,
    onClose,
  }: {
    open: boolean
    message: string
    onClose: () => void
  }) =>
    open ? (
      <button type="button" data-testid="snackbar" onClick={onClose}>
        {message}
      </button>
    ) : null,
}))

vi.mock("@/components/ui/Spotlight", () => ({
  SpotlightOverlay: () => <div data-testid="spotlight-overlay" />,
}))

vi.mock("@/components/events/EventCard/EventCardContent", () => ({
  default: (props: {
    id: string
    title: string
    speaker?: string
    startsAt: string
    endsAt?: string
    location?: string
    description?: string
    participantCount: number
    isRegistered: boolean
    isEnded: boolean
    hoveringDisabled?: boolean
  }) => (
    <div
      data-testid="event-card-content"
      data-id={props.id}
      data-speaker={props.speaker}
      data-starts={props.startsAt}
      data-ends={props.endsAt}
      data-location={props.location}
      data-description={props.description}
      data-participants={String(props.participantCount)}
      data-registered={String(props.isRegistered)}
      data-ended={String(props.isEnded)}
      data-hovering-disabled={String(props.hoveringDisabled)}
    >
      {props.title}
    </div>
  ),
}))

vi.mock("@/components/events/EventCard/EventCardHero", () => ({
  default: (props: {
    id?: string
    imageUrl?: string
    title?: string
    startsAt: string
    endsAt?: string
    timeStatus?: string
    transitioning?: boolean
    priority?: boolean
  }) => (
    <div
      data-testid="event-card-hero"
      data-id={props.id}
      data-image={props.imageUrl}
      data-title={props.title}
      data-starts={props.startsAt}
      data-ends={props.endsAt}
      data-time-status={props.timeStatus}
      data-transitioning={String(props.transitioning)}
      data-priority={String(props.priority)}
    />
  ),
}))

vi.mock("@/components/events/EventQuickView", () => ({
  EventQuickView: ({
    visible,
    position,
    description,
  }: {
    visible: boolean
    position: string
    description: string
  }) => (
    <div
      data-testid="event-quick-view"
      data-visible={String(visible)}
      data-position={position}
      data-description={description}
    />
  ),
}))

vi.mock("@/components/events/EventCategoryBadge", () => ({
  EventCategoryBadge: ({ category }: { category: string }) => (
    <span data-testid="event-category">{category}</span>
  ),
}))

vi.mock("@/components/events/EventCard/EventAdminActions", () => ({
  EventAdminActions: ({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) => (
    <div data-testid="event-admin-actions">
      <button type="button" onClick={onEdit}>
        admin-edit
      </button>
      <button type="button" onClick={onDelete}>
        admin-delete
      </button>
    </div>
  ),
}))

vi.mock("@/components/events/EventEditDialog", () => ({
  EventEditDialog: ({
    open,
    onClose,
    onSave,
    normalizedLocation,
  }: {
    open: boolean
    onClose: () => void
    onSave: () => void
    normalizedLocation: string
  }) =>
    open ? (
      <div data-testid="event-edit-dialog">
        <span data-testid="normalized-location">{normalizedLocation}</span>
        <button type="button" onClick={onClose}>
          close-edit
        </button>
        <button type="button" onClick={onSave}>
          save-edit
        </button>
      </div>
    ) : null,
}))

vi.mock("@/utils/eventsTransition", () => ({
  clearEventsHeroId: vi.fn(),
}))

import { EventCardView, type EventCardViewProps } from "../EventCardView"
import { clearEventsHeroId } from "@/utils/eventsTransition"

const makeProps = (overrides: Partial<EventCardViewProps> = {}): EventCardViewProps => ({
  id: "event-1",
  title: "Workshop",
  speaker: "Speaker",
  startsAt: "2026-06-15T14:00:00Z",
  endsAt: "2026-06-15T16:00:00Z",
  location: "Room 1",
  description: "Description",
  imageUrl: "https://example.test/event.jpg",
  participantCount: 3,
  isRegistered: false,
  isEnded: false,
  isAdmin: false,
  loading: false,
  error: "",
  hoveringDisabled: false,
  timeStatus: "soon",
  category: "workshop",
  editOpen: false,
  confirmDeleteOpen: false,
  editData: {},
  spotlight: {
    mouseX: {} as MotionValue<number>,
    mouseY: {} as MotionValue<number>,
    onMouseMove: vi.fn(),
  },
  menuAnchor: null,
  setMenuAnchor: vi.fn(),
  menuId: "event-menu-1",
  onEditOpen: vi.fn(),
  onEditClose: vi.fn(),
  onDeleteOpen: vi.fn(),
  onDeleteClose: vi.fn(),
  onDeleteConfirm: vi.fn(),
  onEditSave: vi.fn(),
  editDraft: {},
  setEditDraft: vi.fn(),
  imageLoading: false,
  newImage: null,
  setNewImage: vi.fn(),
  previewUrl: null,
  onErrorClose: vi.fn(),
  t: {
    deleteTitle: "Delete event",
    deleteDesc: "Cannot undo",
    confirm: "Delete",
    cancel: "Cancel",
  },
  ...overrides,
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("EventCardView closure paths", () => {
  it("shows and hides the positioned quick view and tracks view transitions", async () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 120,
      bottom: 420,
      left: 0,
      right: 300,
      width: 300,
      height: 300,
      x: 0,
      y: 120,
      toJSON: () => ({}),
    } as DOMRect)

    await act(async () => {
      render(<EventCardView {...makeProps()} />)
    })
    const card = screen.getByTestId("event-card")
    const quickView = screen.getByTestId("event-quick-view")
    const hero = screen.getByTestId("event-card-hero")

    expect(quickView).toHaveAttribute("data-visible", "false")
    expect(quickView).toHaveAttribute("data-position", "top")
    expect(card).toHaveClass("events-card-container", "cursor-pointer")
    fireEvent.mouseEnter(card)
    expect(quickView).toHaveAttribute("data-visible", "true")
    expect(quickView).toHaveAttribute("data-position", "bottom")
    expect(quickView).toHaveAttribute("data-description", "Description")

    fireEvent.pointerDown(card)
    expect(clearEventsHeroId).toHaveBeenCalledOnce()
    expect(hero).toHaveAttribute("data-transitioning", "true")

    fireEvent.mouseLeave(card)
    expect(quickView).toHaveAttribute("data-visible", "false")
    expect(hero).toHaveAttribute("data-transitioning", "false")
  })

  it("keeps hover and transition behavior disabled when requested", () => {
    render(<EventCardView {...makeProps({ hoveringDisabled: true })} />)
    const card = screen.getByTestId("event-card")

    expect(card).toHaveClass("cursor-default")

    fireEvent.mouseEnter(card)
    fireEvent.pointerDown(card)

    expect(screen.getByTestId("event-quick-view")).toHaveAttribute("data-visible", "false")
    expect(screen.getByTestId("event-card-hero")).toHaveAttribute("data-transitioning", "false")
    expect(clearEventsHeroId).not.toHaveBeenCalled()
  })

  it("uses the top quick-view position and empty description fallback for sparse cards", () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 420,
      bottom: 720,
      left: 0,
      right: 300,
      width: 300,
      height: 300,
      x: 0,
      y: 420,
      toJSON: () => ({}),
    } as DOMRect)

    render(<EventCardView {...makeProps({ description: undefined })} />)
    fireEvent.mouseEnter(screen.getByTestId("event-card"))

    expect(screen.getByTestId("event-quick-view")).toHaveAttribute("data-visible", "true")
    expect(screen.getByTestId("event-quick-view")).toHaveAttribute("data-position", "top")
    expect(screen.getByTestId("event-quick-view")).toHaveAttribute("data-description", "")
  })

  it("keeps the quick-view boundary strict at the 280px threshold", () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 280,
      bottom: 580,
      left: 0,
      right: 300,
      width: 300,
      height: 300,
      x: 0,
      y: 280,
      toJSON: () => ({}),
    } as DOMRect)

    render(<EventCardView {...makeProps()} />)
    fireEvent.mouseEnter(screen.getByTestId("event-card"))

    expect(screen.getByTestId("event-quick-view")).toHaveAttribute("data-position", "top")
  })

  it("refreshes hover and transition callbacks when the disabled state changes", () => {
    const clear = vi.mocked(clearEventsHeroId)
    const { rerender } = render(<EventCardView {...makeProps()} />)
    const card = screen.getByTestId("event-card")

    fireEvent.mouseEnter(card)
    expect(screen.getByTestId("event-quick-view")).toHaveAttribute("data-visible", "true")
    fireEvent.mouseLeave(card)

    rerender(<EventCardView {...makeProps({ hoveringDisabled: true })} />)
    fireEvent.mouseEnter(card)
    fireEvent.pointerDown(card)

    expect(screen.getByTestId("event-quick-view")).toHaveAttribute("data-visible", "false")
    expect(clear).not.toHaveBeenCalled()
  })

  it("forwards card metadata to the hero and content presenters", () => {
    render(<EventCardView {...makeProps({ isRegistered: true, isEnded: true, priority: true })} />)

    const hero = screen.getByTestId("event-card-hero")
    expect(hero).toHaveAttribute("data-id", "event-1")
    expect(hero).toHaveAttribute("data-image", "https://example.test/event.jpg")
    expect(hero).toHaveAttribute("data-time-status", "soon")
    expect(hero).toHaveAttribute("data-priority", "true")

    const content = screen.getByTestId("event-card-content")
    expect(content).toHaveAttribute("data-speaker", "Speaker")
    expect(content).toHaveAttribute("data-ends", "2026-06-15T16:00:00Z")
    expect(content).toHaveAttribute("data-location", "Room 1")
    expect(content).toHaveAttribute("data-description", "Description")
    expect(content).toHaveAttribute("data-participants", "3")
    expect(content).toHaveAttribute("data-registered", "true")
    expect(content).toHaveAttribute("data-ended", "true")
  })

  it("renders lazy admin/edit flows plus delete and error callbacks", async () => {
    const user = userEvent.setup()
    const callbacks = {
      onEditOpen: vi.fn(),
      onEditClose: vi.fn(),
      onDeleteOpen: vi.fn(),
      onDeleteClose: vi.fn(),
      onDeleteConfirm: vi.fn(),
      onEditSave: vi.fn(),
      onErrorClose: vi.fn(),
    }
    await act(async () => {
      render(
        <EventCardView
          {...makeProps({
            ...callbacks,
            isAdmin: true,
            editOpen: true,
            confirmDeleteOpen: true,
            error: "Save failed",
            location: "Room 2",
          })}
        />
      )
    })

    await waitFor(() => expect(screen.getByTestId("event-admin-actions")).toBeInTheDocument())
    expect(screen.getByTestId("event-edit-dialog")).toBeInTheDocument()
    expect(screen.getByTestId("normalized-location")).toHaveTextContent("Room 2")
    expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument()
    expect(screen.getByTestId("snackbar")).toHaveTextContent("Save failed")

    await user.click(screen.getByRole("button", { name: "admin-edit" }))
    await user.click(screen.getByRole("button", { name: "admin-delete" }))
    await user.click(screen.getByRole("button", { name: "close-edit" }))
    await user.click(screen.getByRole("button", { name: "save-edit" }))
    await user.click(screen.getByRole("button", { name: "cancel-delete" }))
    await user.click(screen.getByRole("button", { name: "confirm-delete" }))
    await user.click(screen.getByTestId("snackbar"))

    expect(callbacks.onEditOpen).toHaveBeenCalledOnce()
    expect(callbacks.onDeleteOpen).toHaveBeenCalledOnce()
    expect(callbacks.onEditClose).toHaveBeenCalledOnce()
    expect(callbacks.onEditSave).toHaveBeenCalledOnce()
    expect(callbacks.onDeleteClose).toHaveBeenCalledOnce()
    expect(callbacks.onDeleteConfirm).toHaveBeenCalledOnce()
    expect(callbacks.onErrorClose).toHaveBeenCalledOnce()
  })

  it("normalizes a missing admin location before opening the edit dialog", async () => {
    await act(async () => {
      render(<EventCardView {...makeProps({ isAdmin: true, editOpen: true, location: "" })} />)
    })

    await waitFor(() => expect(screen.getByTestId("event-edit-dialog")).toBeInTheDocument())
    expect(screen.getByTestId("normalized-location").textContent).toBe("")
  })
})
