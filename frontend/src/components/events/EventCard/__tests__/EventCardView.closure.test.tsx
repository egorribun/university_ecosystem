import { fireEvent, render, screen, waitFor } from "@testing-library/react"
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
  default: ({ title }: { title: string }) => <div data-testid="event-card-content">{title}</div>,
}))

vi.mock("@/components/events/EventCard/EventCardHero", () => ({
  default: ({ transitioning }: { transitioning: boolean }) => (
    <div data-testid="event-card-hero" data-transitioning={String(transitioning)} />
  ),
}))

vi.mock("@/components/events/EventQuickView", () => ({
  EventQuickView: ({ visible, position }: { visible: boolean; position: string }) => (
    <div data-testid="event-quick-view" data-visible={String(visible)} data-position={position} />
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
  }: {
    open: boolean
    onClose: () => void
    onSave: () => void
  }) =>
    open ? (
      <div data-testid="event-edit-dialog">
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
  it("shows and hides the positioned quick view and tracks view transitions", () => {
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

    render(<EventCardView {...makeProps()} />)
    const card = screen.getByTestId("event-card")
    const quickView = screen.getByTestId("event-quick-view")
    const hero = screen.getByTestId("event-card-hero")

    expect(quickView).toHaveAttribute("data-visible", "false")
    fireEvent.mouseEnter(card)
    expect(quickView).toHaveAttribute("data-visible", "true")
    expect(quickView).toHaveAttribute("data-position", "bottom")

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
    render(
      <EventCardView
        {...makeProps({
          ...callbacks,
          isAdmin: true,
          editOpen: true,
          confirmDeleteOpen: true,
          error: "Save failed",
        })}
      />
    )

    await waitFor(() => expect(screen.getByTestId("event-admin-actions")).toBeInTheDocument())
    expect(screen.getByTestId("event-edit-dialog")).toBeInTheDocument()
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
})
