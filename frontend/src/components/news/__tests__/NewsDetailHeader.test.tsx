import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, it, expect, vi } from "vitest"

const { translationMock, namespaceMock } = vi.hoisted(() => ({
  translationMock: vi.fn((key: string, _options?: unknown) => key),
  namespaceMock: vi.fn(),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: (namespaces: unknown) => {
    namespaceMock(namespaces)
    return {
      t: (key: string, options?: unknown) => translationMock(key, options),
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    }
  },
}))

import { NewsDetailHeader } from "@/components/news/NewsDetailHeader"

const baseProps = {
  displayTitle: "University Announces New AI Research Center",
  createdAt: "2026-05-20T09:00:00Z",
  createdAtIso: "2026-05-20T09:00:00.000Z",
  createdAtLabel: "20 MAY 2026",
  readingTimeMinutes: 5,
  isLiked: false,
  likesCount: 42,
  bookmarked: false,
  isAdmin: false,
  saving: false,
  deleting: false,
  sharing: false,
  onShare: vi.fn(),
  onToggleLike: vi.fn(),
  onToggleBookmark: vi.fn(),
  onEditOpen: vi.fn(),
  onDeleteOpen: vi.fn(),
}

afterEach(() => {
  translationMock.mockImplementation((key: string) => key)
  namespaceMock.mockClear()
})

describe("NewsDetailHeader", () => {
  it("renders title, meta pills, and primary actions", () => {
    render(<NewsDetailHeader {...baseProps} />)
    expect(namespaceMock).toHaveBeenCalledWith(["news", "common"])
    expect(
      screen.getByRole("heading", { level: 1, name: baseProps.displayTitle })
    ).toBeInTheDocument()
    expect(screen.getByText("20 MAY 2026")).toBeInTheDocument()
    expect(screen.getByText("news:meta.readingTime")).toBeInTheDocument()
    expect(translationMock).toHaveBeenCalledWith("news:meta.readingTime", { count: 5 })
    expect(screen.getByText("news:actions.share")).toBeInTheDocument()
    expect(screen.getByText("42")).toBeInTheDocument()
    expect(screen.getByText("news:actions.bookmark")).toBeInTheDocument()
  })

  it("omits the reading-time pill when readingTimeMinutes is null", () => {
    render(<NewsDetailHeader {...baseProps} readingTimeMinutes={null} createdAt={undefined} />)
    expect(screen.queryByText("news:meta.readingTime")).not.toBeInTheDocument()
    expect(screen.queryByText("20 MAY 2026")).not.toBeInTheDocument()
  })

  it("hides admin actions for non-admins", () => {
    render(<NewsDetailHeader {...baseProps} />)
    expect(screen.queryByLabelText("news:aria.editNews")).not.toBeInTheDocument()
    expect(screen.queryByLabelText("news:aria.deleteNews")).not.toBeInTheDocument()
  })

  it("shows admin edit/delete and fires their callbacks", async () => {
    const user = userEvent.setup()
    const onEditOpen = vi.fn()
    const onDeleteOpen = vi.fn()
    render(
      <NewsDetailHeader
        {...baseProps}
        isAdmin
        onEditOpen={onEditOpen}
        onDeleteOpen={onDeleteOpen}
      />
    )
    await user.click(screen.getByLabelText("news:aria.editNews"))
    await user.click(screen.getByLabelText("news:aria.deleteNews"))
    expect(onEditOpen).toHaveBeenCalledOnce()
    expect(onDeleteOpen).toHaveBeenCalledOnce()
  })

  it("reflects liked + bookmarked state and fires share/like/bookmark callbacks", async () => {
    const user = userEvent.setup()
    const onShare = vi.fn()
    const onToggleLike = vi.fn()
    const onToggleBookmark = vi.fn()
    render(
      <NewsDetailHeader
        {...baseProps}
        isLiked
        bookmarked
        likesCount={43}
        onShare={onShare}
        onToggleLike={onToggleLike}
        onToggleBookmark={onToggleBookmark}
      />
    )
    expect(screen.getByRole("button", { name: "news:aria.shareNews" })).toBeInTheDocument()
    expect(screen.getByText("43").closest("button")).toHaveClass(
      "transition-colors",
      "duration-fast"
    )
    expect(screen.getByRole("button", { name: "news:actions.removeBookmark" })).toHaveClass(
      "transition-colors",
      "duration-fast"
    )
    expect(screen.getByText("news:actions.saved")).toBeInTheDocument()
    await user.click(screen.getByText("news:actions.share"))
    await user.click(screen.getByText("news:actions.saved"))
    await user.click(screen.getByText("43"))
    expect(onShare).toHaveBeenCalledOnce()
    expect(onToggleBookmark).toHaveBeenCalledOnce()
    expect(onToggleLike).toHaveBeenCalledOnce()
  })

  it("keeps the localized like toggle name stable across pressed states", () => {
    const { rerender } = render(<NewsDetailHeader {...baseProps} />)
    let likeButton = screen.getByRole("button", {
      name: "common:aria.like",
      pressed: false,
    })

    expect(likeButton).toHaveAttribute("aria-pressed", "false")

    rerender(<NewsDetailHeader {...baseProps} isLiked />)
    likeButton = screen.getByRole("button", {
      name: "common:aria.like",
      pressed: true,
    })

    expect(likeButton).toHaveAttribute("aria-pressed", "true")
  })

  it("describes the visible like count and updates it when the count changes", () => {
    const { rerender } = render(<NewsDetailHeader {...baseProps} />)
    let likeButton = screen.getByRole("button", {
      name: "common:aria.like",
      description: "42",
    })
    const countId = likeButton.getAttribute("aria-describedby")

    expect(countId).toBeTruthy()
    expect(document.getElementById(countId!)).toHaveTextContent("42")

    rerender(<NewsDetailHeader {...baseProps} isLiked likesCount={43} />)
    likeButton = screen.getByRole("button", {
      name: "common:aria.like",
      pressed: true,
      description: "43",
    })

    expect(likeButton).toHaveAttribute("aria-describedby", countId)
    expect(document.getElementById(countId!)).toHaveTextContent("43")
  })

  it("keeps inactive action styling neutral and applies active state classes", () => {
    const { rerender } = render(<NewsDetailHeader {...baseProps} />)
    const inactiveLikeButton = screen.getByText("42").closest("button")!
    const inactiveLikeIcon = inactiveLikeButton.querySelector("svg")!
    const inactiveBookmarkButton = screen.getByText("news:actions.bookmark").closest("button")!
    const inactiveBookmarkIcon = inactiveBookmarkButton.querySelector("svg")!

    expect(inactiveLikeButton).not.toHaveClass(
      "border-(--error-text)/[calc(var(--opacity-dim)*100%)]",
      "bg-(--error-text)/[calc(var(--opacity-subtle)*100%)]"
    )
    expect(inactiveLikeIcon).toHaveClass("text-(--text-secondary)")
    expect(inactiveBookmarkButton).not.toHaveClass(
      "border-brand/[calc(var(--opacity-dim)*100%)]",
      "bg-brand/[calc(var(--opacity-subtle)*100%)]"
    )
    expect(inactiveBookmarkIcon).not.toHaveClass("fill-brand", "text-brand")

    rerender(<NewsDetailHeader {...baseProps} isLiked bookmarked />)
    const activeLikeButton = screen.getByText("42").closest("button")!
    const activeLikeIcon = activeLikeButton.querySelector("svg")!
    const activeBookmarkButton = screen.getByText("news:actions.saved").closest("button")!
    const activeBookmarkIcon = activeBookmarkButton.querySelector("svg")!

    expect(activeLikeButton).toHaveClass(
      "border-(--error-text)/[calc(var(--opacity-dim)*100%)]",
      "bg-(--error-text)/[calc(var(--opacity-subtle)*100%)]"
    )
    expect(activeLikeIcon).toHaveClass("fill-(--error-text)", "text-(--error-text)")
    expect(activeBookmarkButton).toHaveClass(
      "border-brand/[calc(var(--opacity-dim)*100%)]",
      "bg-brand/[calc(var(--opacity-subtle)*100%)]"
    )
    expect(activeBookmarkIcon).toHaveClass("fill-brand", "text-brand")
  })

  it("disables both admin actions while either save or delete is pending", () => {
    const { rerender } = render(<NewsDetailHeader {...baseProps} isAdmin saving />)
    const editButton = screen.getByLabelText("news:aria.editNews")
    const deleteButton = screen.getByLabelText("news:aria.deleteNews")

    expect(editButton).toBeDisabled()
    expect(deleteButton).toBeDisabled()
    expect(editButton).toHaveClass("inline-flex", "h-10", "w-10", "matte-chip")
    expect(deleteButton).toHaveClass("text-(--error-text)", "hover:text-(--error-text)")

    rerender(<NewsDetailHeader {...baseProps} isAdmin deleting />)
    expect(editButton).toBeDisabled()
    expect(deleteButton).toBeDisabled()

    rerender(<NewsDetailHeader {...baseProps} isAdmin />)
    expect(editButton).toBeEnabled()
    expect(deleteButton).toBeEnabled()
  })

  it("keeps aria labels empty when the corresponding translations are unavailable", () => {
    translationMock.mockImplementation((key: string) =>
      ["news:aria.shareNews", "news:aria.editNews", "news:aria.deleteNews"].includes(key) ? "" : key
    )

    render(<NewsDetailHeader {...baseProps} isAdmin />)
    expect(screen.getByRole("heading", { name: baseProps.displayTitle })).toBeInTheDocument()
    expect(screen.getAllByRole("button").length).toBeGreaterThan(0)
  })
})
