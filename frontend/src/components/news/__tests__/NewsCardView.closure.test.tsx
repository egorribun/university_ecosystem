import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("@/components/ui", () => ({
  ConfirmDialog: ({
    open,
    onConfirm,
    onCancel,
  }: {
    open: boolean
    onConfirm: () => void
    onCancel: () => void
  }) =>
    open ? (
      <div role="dialog">
        <button type="button" onClick={onConfirm}>
          confirm delete
        </button>
        <button type="button" onClick={onCancel}>
          cancel delete
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
      <div role="status">
        <span>{message}</span>
        <button type="button" onClick={onClose}>
          close error
        </button>
      </div>
    ) : null,
}))

vi.mock("@/components/ui/Spotlight", () => ({
  SpotlightOverlay: () => <div data-testid="spotlight" />,
}))

vi.mock("@/components/news/NewsQuickView", () => ({
  NewsQuickView: ({ visible, position }: { visible: boolean; position: string }) =>
    visible ? <div data-testid="quick-view">quick:{position}</div> : null,
}))

vi.mock("@/components/news/NewsCategoryBadge", () => ({
  NewsCategoryBadge: ({ category }: { category: string }) => <span>category:{category}</span>,
}))

vi.mock("@/components/news/NewsCardHero", () => ({
  default: ({ transitioning, priority }: { transitioning: boolean; priority?: boolean }) => (
    <div data-testid="hero" data-transitioning={transitioning} data-priority={priority ?? false} />
  ),
}))

vi.mock("@/components/news/NewsCardContent", () => ({
  default: ({
    onToggleLike,
    onToggleBookmark,
  }: {
    onToggleLike: () => void
    onToggleBookmark?: () => void
  }) => (
    <div>
      <button type="button" onClick={onToggleLike}>
        like card
      </button>
      <button type="button" onClick={onToggleBookmark}>
        bookmark card
      </button>
    </div>
  ),
}))

vi.mock("@/components/news/NewsCardActions", () => ({
  NewsCardActions: ({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) => (
    <div>
      <button type="button" onClick={onEdit}>
        edit card
      </button>
      <button type="button" onClick={onDelete}>
        delete card
      </button>
    </div>
  ),
}))

vi.mock("@/components/news/NewsCardEditDialog", () => ({
  NewsCardEditDialog: ({
    open,
    onClose,
    onSuccess,
  }: {
    open: boolean
    onClose: () => void
    onSuccess: () => void
  }) =>
    open ? (
      <div role="dialog">
        <button type="button" onClick={onClose}>
          close edit
        </button>
        <button type="button" onClick={onSuccess}>
          save edit
        </button>
      </div>
    ) : null,
}))

import { NewsCardView, type NewsCardViewProps } from "@/components/news/NewsCardView"

const createProps = (): NewsCardViewProps => ({
  id: "news-1",
  title: "Campus news",
  created_at: "2026-08-03T12:00:00Z",
  image_url: "https://example.test/news.png",
  previewText: "A preview",
  isLiked: false,
  likesCount: 3,
  commentsCount: 4,
  isBookmarked: false,
  isAdmin: false,
  loading: false,
  error: "",
  hoveringDisabled: false,
  readingTime: 2,
  category: "campus",
  editOpen: false,
  confirmDeleteOpen: false,
  editData: { title: "Campus news", content: "Body", title_en: "", content_en: "", image_url: "" },
  spotlight: {
    mouseX: { get: () => 0 } as never,
    mouseY: { get: () => 0 } as never,
    onMouseMove: vi.fn(),
  },
  onToggleLike: vi.fn(),
  onToggleBookmark: vi.fn(),
  onEditOpen: vi.fn(),
  onEditClose: vi.fn(),
  onDeleteOpen: vi.fn(),
  onDeleteClose: vi.fn(),
  onDeleteConfirm: vi.fn(),
  onEditSuccess: vi.fn(),
  onErrorClose: vi.fn(),
  t: {
    deleteTitle: "Delete news",
    deleteDesc: "Delete this news?",
    confirm: "Delete",
    cancel: "Cancel",
  },
  priority: true,
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("NewsCardView — interactions and optional overlays", () => {
  it("shows the bottom quick view near the viewport top and resets transitions", () => {
    const props = createProps()
    const { container } = render(<NewsCardView {...props} />)
    const article = screen.getByTestId("news-card")

    fireEvent.mouseMove(article)
    fireEvent.mouseEnter(article)
    expect(screen.getByTestId("quick-view")).toHaveTextContent("quick:bottom")
    expect(screen.getByTestId("hero")).toHaveAttribute("data-transitioning", "false")

    fireEvent.pointerDown(article)
    expect(screen.getByTestId("hero")).toHaveAttribute("data-transitioning", "true")
    expect(props.spotlight.onMouseMove).toHaveBeenCalled()

    fireEvent.mouseLeave(article)
    expect(screen.queryByTestId("quick-view")).not.toBeInTheDocument()
    expect(container.querySelector("article")).toBeInTheDocument()

    vi.spyOn(article, "getBoundingClientRect").mockReturnValue({ top: 400 } as DOMRect)
    fireEvent.mouseEnter(article)
    expect(screen.getByTestId("quick-view")).toHaveTextContent("quick:top")
  })

  it("does not open hover or transition interactions when disabled", () => {
    const props = createProps()
    props.hoveringDisabled = true
    render(<NewsCardView {...props} />)
    const article = screen.getByTestId("news-card")

    fireEvent.mouseEnter(article)
    fireEvent.pointerDown(article)
    expect(screen.queryByTestId("quick-view")).not.toBeInTheDocument()
    expect(screen.getByTestId("hero")).toHaveAttribute("data-transitioning", "false")
  })

  it("forwards content and admin callbacks and renders edit/delete/error overlays", async () => {
    const props = createProps()
    props.isAdmin = true
    props.error = "Save failed"
    const { rerender } = render(<NewsCardView {...props} />)

    fireEvent.click(screen.getByRole("button", { name: "like card" }))
    fireEvent.click(screen.getByRole("button", { name: "bookmark card" }))
    fireEvent.click(await screen.findByRole("button", { name: "edit card" }))
    expect(props.onToggleLike).toHaveBeenCalledOnce()
    expect(props.onToggleBookmark).toHaveBeenCalledOnce()
    expect(props.onEditOpen).toHaveBeenCalledOnce()

    rerender(<NewsCardView {...props} editOpen confirmDeleteOpen={false} />)
    fireEvent.click(screen.getByRole("button", { name: "close error" }))
    expect(props.onErrorClose).toHaveBeenCalledOnce()

    rerender(<NewsCardView {...props} editOpen={false} confirmDeleteOpen />)
    fireEvent.click(screen.getByRole("button", { name: "confirm delete" }))
    fireEvent.click(screen.getByRole("button", { name: "cancel delete" }))
    expect(props.onDeleteConfirm).toHaveBeenCalledOnce()
    expect(props.onDeleteClose).toHaveBeenCalledOnce()

    rerender(<NewsCardView {...props} editOpen />)
    fireEvent.click(await screen.findByRole("button", { name: "save edit" }))
    fireEvent.click(screen.getByRole("button", { name: "close edit" }))
    expect(props.onEditSuccess).toHaveBeenCalledOnce()
    expect(props.onEditClose).toHaveBeenCalledOnce()
    await waitFor(() => expect(screen.getByTestId("hero")).toHaveAttribute("data-priority", "true"))
  })
})
