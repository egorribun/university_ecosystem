import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, it, expect, vi } from "vitest"

const { translationMock } = vi.hoisted(() => ({
  translationMock: vi.fn((key: string) => key),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => translationMock(key),
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
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
})

describe("NewsDetailHeader", () => {
  it("renders title, meta pills, and primary actions", () => {
    render(<NewsDetailHeader {...baseProps} />)
    expect(
      screen.getByRole("heading", { level: 1, name: baseProps.displayTitle })
    ).toBeInTheDocument()
    expect(screen.getByText("20 MAY 2026")).toBeInTheDocument()
    expect(screen.getByText("news:meta.readingTime")).toBeInTheDocument()
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
    expect(screen.getByText("news:actions.saved")).toBeInTheDocument()
    await user.click(screen.getByText("news:actions.share"))
    await user.click(screen.getByText("news:actions.saved"))
    await user.click(screen.getByText("43"))
    expect(onShare).toHaveBeenCalledOnce()
    expect(onToggleBookmark).toHaveBeenCalledOnce()
    expect(onToggleLike).toHaveBeenCalledOnce()
  })

  it("keeps aria labels empty when the corresponding translations are unavailable", () => {
    translationMock.mockImplementation((key: string) =>
      ["news:aria.shareNews", "news:aria.editNews", "news:aria.deleteNews"].includes(key)
        ? undefined
        : key
    )

    render(<NewsDetailHeader {...baseProps} isAdmin />)
    expect(screen.getByRole("heading", { name: baseProps.displayTitle })).toBeInTheDocument()
    expect(screen.getAllByRole("button").length).toBeGreaterThan(0)
  })
})
