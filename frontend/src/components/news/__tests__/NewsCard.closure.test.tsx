import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type InteractionState = {
  likes_count: number
  comments_count: number
  is_liked: boolean
}

const mocks = vi.hoisted(() => ({
  user: null as { role: string } | null,
  language: "en",
  translationNamespaces: [] as unknown[],
  interactions: undefined as InteractionState | undefined,
  toggleLike: vi.fn(),
  isBookmarked: vi.fn(() => false),
  toggleBookmark: vi.fn(),
  deleteNews: vi.fn(),
  onChange: vi.fn(),
  sanitizeNewsText: vi.fn(async (value: string) => `sanitized:${value}`),
  viewRender: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user }),
}))

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: mocks.language }),
}))

vi.mock("@/hooks/useNewsInteraction", () => ({
  useNewsInteraction: () => ({ interactions: mocks.interactions, toggleLike: mocks.toggleLike }),
}))

vi.mock("@/hooks/useBookmarks", () => ({
  useBookmarks: () => ({
    isBookmarked: mocks.isBookmarked,
    toggleBookmark: mocks.toggleBookmark,
  }),
}))

vi.mock("@/components/ui/Spotlight", () => ({
  useSpotlight: () => ({ mouseX: {}, mouseY: {}, onMouseMove: vi.fn() }),
}))

vi.mock("@/utils/sanitize", () => ({
  sanitizeNewsText: mocks.sanitizeNewsText,
}))

vi.mock("@/utils/localize", () => ({
  localizeField: (value: string, _english: string | null | undefined, language: string) =>
    `${language}:${value}`,
}))

vi.mock("@/features/news/categories", () => ({
  inferCategory: () => "general",
}))

vi.mock("@/utils/readingTime", () => ({
  estimateReadingTime: () => 3,
}))

vi.mock("@/api/client", () => ({
  default: { delete: mocks.deleteNews },
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: unknown) => {
    mocks.translationNamespaces.push(namespaces)
    return { t: (key: string) => key }
  },
}))

vi.mock("@/components/news/NewsCardView", () => ({
  NewsCardView: (props: {
    id: string
    title: string
    previewText: string
    isAdmin: boolean
    isLiked: boolean
    likesCount: number
    commentsCount: number
    isBookmarked: boolean
    editOpen: boolean
    confirmDeleteOpen: boolean
    onToggleLike: () => void
    onToggleBookmark: () => void
    onEditOpen: () => void
    onEditClose: () => void
    onDeleteOpen: () => void
    onDeleteClose: () => void
    onDeleteConfirm: () => void
    onEditSuccess: () => void
    onErrorClose: () => void
    error: string
    loading: boolean
    editData: {
      title: string
      content: string
      title_en: string
      content_en: string
      image_url: string
    }
    t: {
      deleteTitle: string
      deleteDesc: string
      confirm: string
      cancel: string
    }
    priority?: boolean
  }) => {
    mocks.viewRender(props)
    return (
      <div data-testid="news-card-view">
        <span data-testid="card-title">{props.title}</span>
        <span data-testid="card-preview">{props.previewText}</span>
        <span data-testid="card-stats">
          {props.isLiked ? "liked" : "not-liked"}:{props.likesCount}:{props.commentsCount}:
          {props.isBookmarked ? "bookmarked" : "not-bookmarked"}
        </span>
        <button type="button" onClick={props.onToggleLike}>
          toggle like
        </button>
        <button type="button" onClick={props.onToggleBookmark}>
          toggle bookmark
        </button>
        <button type="button" onClick={props.onEditOpen}>
          open edit
        </button>
        {props.editOpen && (
          <div role="dialog">
            <button type="button" onClick={props.onEditClose}>
              close edit
            </button>
            <button type="button" onClick={props.onEditSuccess}>
              edit success
            </button>
          </div>
        )}
        {props.isAdmin && (
          <button type="button" onClick={props.onDeleteOpen}>
            open delete
          </button>
        )}
        {props.confirmDeleteOpen && (
          <div role="alertdialog">
            <button type="button" onClick={props.onDeleteConfirm}>
              confirm delete
            </button>
            <button type="button" onClick={props.onDeleteClose}>
              close delete
            </button>
          </div>
        )}
        {props.error && (
          <div role="status">
            <span>{props.error}</span>
            <button type="button" onClick={props.onErrorClose}>
              close error
            </button>
          </div>
        )}
      </div>
    )
  },
}))

import NewsCard, { type NewsCardProps } from "@/components/news/NewsCard"

const baseProps = {
  id: "news-1",
  title: "Campus update",
  content: "The campus library is open.",
  title_en: "Campus update",
  content_en: "The campus library is open.",
  created_at: "2026-08-03T12:00:00Z",
  image_url: "/news.png",
  likes_count: 4,
  comments_count: 2,
  is_liked: false,
  priority: true,
}

beforeEach(() => {
  mocks.user = null
  mocks.language = "en"
  mocks.translationNamespaces.length = 0
  mocks.interactions = { likes_count: 9, comments_count: 8, is_liked: true }
  mocks.deleteNews.mockResolvedValue(undefined)
  vi.clearAllMocks()
  mocks.deleteNews.mockResolvedValue(undefined)
  mocks.isBookmarked.mockReturnValue(false)
  mocks.sanitizeNewsText.mockImplementation(async (value: string) => `sanitized:${value}`)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("NewsCard — state orchestration", () => {
  it("localizes and sanitizes content, forwards interactions, and falls back to initial stats", async () => {
    mocks.interactions = undefined
    const { rerender } = render(<NewsCard {...baseProps} onChange={mocks.onChange} />)
    rerender(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    await waitFor(() => expect(screen.getByTestId("card-preview")).toHaveTextContent("sanitized:"))
    expect(mocks.translationNamespaces.at(-1)).toEqual(["news", "common"])
    expect(screen.getByTestId("card-title")).toHaveTextContent("en:Campus update")
    expect(screen.getByTestId("card-stats")).toHaveTextContent("not-liked:4:2:not-bookmarked")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "toggle like" }))
    fireEvent.click(screen.getByRole("button", { name: "toggle bookmark" }))
    expect(mocks.toggleLike).toHaveBeenCalledOnce()
    expect(mocks.toggleBookmark).toHaveBeenCalledWith("news-1")
  })

  it("uses interaction data when available and keeps bookmark callbacks bound to the current id", async () => {
    const { rerender } = render(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    await waitFor(() => expect(screen.getByTestId("card-stats")).toHaveTextContent("liked:9:8"))

    mocks.toggleBookmark.mockClear()
    rerender(<NewsCard {...baseProps} id="news-2" onChange={mocks.onChange} />)
    await waitFor(() => expect(screen.getByTestId("card-stats")).toHaveTextContent("liked:9:8"))
    fireEvent.click(screen.getByRole("button", { name: "toggle bookmark" }))

    expect(mocks.toggleBookmark).toHaveBeenCalledWith("news-2")
  })

  it("forwards normalized edit data, dialog translations, and default interaction state", async () => {
    mocks.user = { role: "admin" }
    mocks.interactions = undefined
    render(
      <NewsCard
        {...baseProps}
        title_en={null}
        content_en={null}
        image_url={undefined}
        likes_count={undefined}
        comments_count={undefined}
        is_liked={undefined}
        priority={undefined}
      />
    )

    await waitFor(() => expect(mocks.viewRender).toHaveBeenCalled())
    const props = mocks.viewRender.mock.calls.at(-1)?.[0] as {
      editData: Record<string, string>
      t: Record<string, string>
      isLiked: boolean
      likesCount: number
      commentsCount: number
      priority?: boolean
    }

    expect(props.editData).toEqual({
      title: "Campus update",
      content: "The campus library is open.",
      title_en: "",
      content_en: "",
      image_url: "",
    })
    expect(props.t).toEqual({
      deleteTitle: "news:dialogs.delete.title",
      deleteDesc: "news:dialogs.delete.description",
      confirm: "common:buttons.delete",
      cancel: "common:buttons.cancel",
    })
    expect(props.isLiked).toBe(false)
    expect(props.likesCount).toBe(0)
    expect(props.commentsCount).toBe(0)
    expect(props.priority).toBeUndefined()
  })

  it("keeps the loading state visible until an asynchronous delete settles", async () => {
    mocks.user = { role: "admin" }
    let resolveDelete!: () => void
    mocks.deleteNews.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveDelete = resolve
        })
    )
    render(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    await waitFor(() => expect(mocks.viewRender).toHaveBeenCalled())
    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "confirm delete" }))

    await waitFor(() => {
      const props = mocks.viewRender.mock.calls.at(-1)?.[0] as { loading: boolean }
      expect(props.loading).toBe(true)
    })
    resolveDelete()
    await waitFor(() => {
      const props = mocks.viewRender.mock.calls.at(-1)?.[0] as {
        loading: boolean
        confirmDeleteOpen: boolean
      }
      expect(props.loading).toBe(false)
      expect(props.confirmDeleteOpen).toBe(false)
    })
  })

  it("rerenders when identity props change but ignores interaction counters", async () => {
    const onChange = vi.fn()
    const { rerender } = render(<NewsCard {...baseProps} onChange={onChange} />)
    await waitFor(() => expect(mocks.viewRender).toHaveBeenCalled())

    const identityChanges: Array<[string, unknown]> = [
      ["id", "news-2"],
      ["title", "A new title"],
      ["title_en", "A new English title"],
      ["content", "A new body"],
      ["content_en", "A new English body"],
      ["created_at", "2026-08-04T12:00:00Z"],
      ["image_url", "/new-image.png"],
      ["onChange", vi.fn()],
      ["priority", false],
    ]

    for (const [key, value] of identityChanges) {
      const before = mocks.viewRender.mock.calls.length
      const changedProps = { ...baseProps, onChange, [key]: value } as NewsCardProps
      rerender(<NewsCard {...changedProps} />)
      await waitFor(() => expect(mocks.viewRender.mock.calls.length).toBeGreaterThan(before))

      const changed = mocks.viewRender.mock.calls.length
      rerender(<NewsCard {...baseProps} onChange={onChange} />)
      await waitFor(() => expect(mocks.viewRender.mock.calls.length).toBeGreaterThan(changed))
    }

    const beforeCounters = mocks.viewRender.mock.calls.length
    rerender(
      <NewsCard {...baseProps} onChange={onChange} likes_count={99} comments_count={77} is_liked />
    )
    await Promise.resolve()
    expect(mocks.viewRender.mock.calls.length).toBe(beforeCounters)
  })

  it("handles successful admin delete and edit callbacks", async () => {
    mocks.user = { role: "admin" }
    render(<NewsCard {...baseProps} onChange={mocks.onChange} />)

    fireEvent.click(screen.getByRole("button", { name: "open edit" }))
    fireEvent.click(screen.getByRole("button", { name: "edit success" }))
    fireEvent.click(screen.getByRole("button", { name: "close edit" }))
    expect(mocks.onChange).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "close delete" }))
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "confirm delete" }))
    await waitFor(() => expect(mocks.deleteNews).toHaveBeenCalledWith("/news/news-1"))
    expect(mocks.onChange).toHaveBeenCalledTimes(2)
  })

  it("surfaces delete errors and lets the caller close them", async () => {
    mocks.user = { role: "admin" }
    mocks.deleteNews.mockRejectedValue(new Error("delete failed"))
    render(<NewsCard {...baseProps} />)

    fireEvent.click(screen.getByRole("button", { name: "open delete" }))
    fireEvent.click(screen.getByRole("button", { name: "confirm delete" }))
    expect(await screen.findByRole("status")).toHaveTextContent("common:errors.generic")
    fireEvent.click(screen.getByRole("button", { name: "close error" }))
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("does not publish a late sanitizer result after unmount", async () => {
    let resolveSanitizer!: (value: string) => void
    mocks.sanitizeNewsText.mockReturnValueOnce(
      new Promise<string>((resolve) => {
        resolveSanitizer = resolve
      })
    )
    const { unmount } = render(<NewsCard {...baseProps} />)

    unmount()
    resolveSanitizer("late preview")
    await Promise.resolve()

    expect(screen.queryByTestId("news-card-view")).not.toBeInTheDocument()
  })
})
