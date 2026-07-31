import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import NewsDetail from "../NewsDetail"

const article = {
  id: "news-1",
  title: "Russian title",
  title_en: "English title",
  content: "Russian content",
  content_en: "English content",
  image_url: "https://example.test/article.jpg",
  created_at: "2026-08-01T10:00:00.000Z",
  likes_count: 4,
  comments_count: 2,
  is_liked: false,
}

const mocks = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
  navigate: vi.fn(),
  removeQueries: vi.fn(),
  invalidateQueries: vi.fn(),
  deleteNews: vi.fn(),
  toggleLike: vi.fn(),
  toggleBookmark: vi.fn(),
  interactions: {} as Record<string, unknown> | undefined,
  setNewsHeroId: vi.fn(),
  articleNavigation: {} as Record<string, unknown>,
  swipe: {} as Record<string, unknown>,
  share: {} as Record<string, unknown>,
  relatedArticles: [] as unknown[],
  t: (key: string) => key,
}))

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
  useParams: () => ({ id: "news-1" }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => mocks.query,
  useQueryClient: () => ({
    removeQueries: mocks.removeQueries,
    invalidateQueries: mocks.invalidateQueries,
  }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t }),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "admin-1", role: "admin" } }),
}))

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en" }),
}))

vi.mock("@/api/news", () => ({
  deleteNews: mocks.deleteNews,
}))

vi.mock("@/api/hooks/news", () => ({
  newsDetailQueryOptions: vi.fn(() => ({ queryKey: ["news", "news-1"] })),
}))

vi.mock("@/hooks/useNewsInteraction", () => ({
  useNewsInteraction: () => ({
    interactions: mocks.interactions,
    toggleLike: mocks.toggleLike,
    addComment: vi.fn(),
    isCommenting: false,
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
  }),
}))

vi.mock("@/hooks/useShare", () => ({
  useShare: () => mocks.share,
}))

vi.mock("@/hooks/useBookmarks", () => ({
  useBookmarks: () => ({
    isBookmarked: () => false,
    toggleBookmark: mocks.toggleBookmark,
  }),
}))

vi.mock("@/hooks/useRelatedNews", () => ({ useRelatedNews: () => mocks.relatedArticles }))
vi.mock("@/hooks/useArticleNavigation", () => ({
  useArticleNavigation: () => mocks.articleNavigation,
}))
vi.mock("@/hooks/useSwipe", () => ({
  useSwipe: (options: Record<string, unknown>) => {
    mocks.swipe = options
    return {}
  },
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/utils/newsTransition", () => ({ setNewsHeroId: mocks.setNewsHeroId }))

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

vi.mock("@/components/ui/SEO", () => ({ SEO: () => null }))

vi.mock("@/components/settings", () => ({
  Alert: ({ children }: { children: ReactNode }) => <div role="alert">{children}</div>,
  Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
  DialogActions: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
  Snackbar: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock("@/components/news/NewsBackdrop", () => ({ NewsBackdrop: () => <div /> }))
vi.mock("@/components/news/NewsDetailSkeleton", () => ({
  NewsDetailSkeleton: () => <div data-testid="news-detail-skeleton" />,
}))
vi.mock("@/components/news/NewsDetailHero", () => ({
  NewsDetailHero: ({ displayTitle }: { displayTitle: string }) => (
    <div>{`hero:${displayTitle}`}</div>
  ),
}))
vi.mock("@/components/news/NewsDetailBody", () => ({
  NewsDetailBody: ({ content }: { content: string }) => <div>{`body:${content}`}</div>,
}))
vi.mock("@/components/news/NewsComments", () => ({ NewsComments: () => <div /> }))
vi.mock("@/components/news/RelatedNews", () => ({
  RelatedNews: ({ items }: { items: unknown[] }) => (
    <div data-testid="related-news">{items.length}</div>
  ),
}))
vi.mock("@/components/news/NewsDetailNavigation", () => ({ NewsDetailNavigation: () => <div /> }))
vi.mock("@/components/news/NewsDetailEditDialog", () => ({
  NewsDetailEditDialog: ({ open }: { open: boolean }) => (open ? <div>edit-dialog</div> : null),
}))
vi.mock("@/components/news/NewsDetailHeader", () => ({
  NewsDetailHeader: ({
    displayTitle,
    onToggleLike,
    onToggleBookmark,
    onShare,
    onEditOpen,
    onDeleteOpen,
  }: {
    displayTitle: string
    onToggleLike: () => void
    onToggleBookmark: () => void
    onShare: () => void
    onEditOpen: () => void
    onDeleteOpen: () => void
  }) => (
    <header>
      <h1>{displayTitle}</h1>
      <button onClick={onToggleLike}>like</button>
      <button onClick={onToggleBookmark}>bookmark</button>
      <button onClick={onShare}>share</button>
      <button onClick={onEditOpen}>edit</button>
      <button onClick={onDeleteOpen}>delete</button>
    </header>
  ),
}))

describe("NewsDetail", () => {
  beforeEach(() => {
    mocks.query = { isLoading: false, isError: false, data: article }
    mocks.navigate.mockReset()
    mocks.removeQueries.mockReset()
    mocks.invalidateQueries.mockReset().mockResolvedValue(undefined)
    mocks.deleteNews.mockReset().mockResolvedValue(undefined)
    mocks.toggleLike.mockReset()
    mocks.toggleBookmark.mockReset()
    mocks.interactions = { is_liked: false, likes_count: 4, comments: [] }
    mocks.setNewsHeroId.mockReset()
    mocks.articleNavigation = {
      prevId: null,
      nextId: null,
      prevTitle: null,
      nextTitle: null,
    }
    mocks.relatedArticles = []
    mocks.swipe = {}
    mocks.share = {
      sharing: false,
      shareDialogOpen: false,
      setShareDialogOpen: vi.fn(),
      copyingLink: false,
      copiedLink: false,
      shareOptions: [],
      handleShare: vi.fn(),
      handleCopyLink: vi.fn(),
    }
  })

  it("renders the loading skeleton without attempting the article layout", () => {
    mocks.query = { isLoading: true, isError: false, data: undefined }

    render(<NewsDetail />)

    expect(screen.getByTestId("news-detail-skeleton")).toBeInTheDocument()
    expect(screen.queryByRole("heading")).not.toBeInTheDocument()
  })

  it("renders a recoverable error state when the article is absent", () => {
    mocks.query = { isLoading: false, isError: true, data: undefined }

    render(<NewsDetail />)

    expect(screen.getByText("news:states.loadError")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.back" }))
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/news" })
  })

  it("uses browser history when a previous page exists", () => {
    const back = vi.spyOn(window.history, "back").mockImplementation(() => undefined)
    window.history.pushState({}, "", "/news/news-1")
    mocks.query = { isLoading: false, isError: true, data: undefined }

    render(<NewsDetail />)

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.back" }))

    expect(back).toHaveBeenCalledOnce()
    back.mockRestore()
  })

  it("navigates through swipe callbacks and updates the reading progress fallback", () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
    const animationFrames: FrameRequestCallback[] = []
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        animationFrames.push(callback)
        return animationFrames.length
      })
    const scrollHeight = vi
      .spyOn(document.documentElement, "scrollHeight", "get")
      .mockReturnValue(1000)
    const innerHeight = vi.spyOn(window, "innerHeight", "get").mockReturnValue(100)
    const scrollY = vi.spyOn(window, "scrollY", "get").mockReturnValue(450)
    mocks.articleNavigation = {
      prevId: "news-0",
      nextId: "news-2",
      prevTitle: "Previous",
      nextTitle: "Next",
    }

    render(<NewsDetail />)

    const swipe = mocks.swipe as {
      onSwipeLeft: () => void
      onSwipeRight: () => void
    }
    swipe.onSwipeLeft()
    swipe.onSwipeRight()
    expect(scrollTo).toHaveBeenCalledTimes(2)
    expect(mocks.navigate).toHaveBeenNthCalledWith(1, {
      to: "/news/$id",
      params: { id: "news-2" },
    })
    expect(mocks.navigate).toHaveBeenNthCalledWith(2, {
      to: "/news/$id",
      params: { id: "news-0" },
    })

    const progress = document.querySelector<HTMLDivElement>(".news-reading-progress")
    expect(progress).not.toBeNull()
    window.dispatchEvent(new Event("scroll"))
    window.dispatchEvent(new Event("scroll"))
    expect(requestAnimationFrame).toHaveBeenCalledOnce()
    animationFrames[0]?.(0)
    expect(progress?.style.transform).toBe("scaleX(0.5)")

    requestAnimationFrame.mockRestore()
    scrollTo.mockRestore()
    scrollHeight.mockRestore()
    innerHeight.mockRestore()
    scrollY.mockRestore()
  })

  it("keeps the reading progress at zero when the document has no scrollable range", () => {
    const animationFrames: FrameRequestCallback[] = []
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        animationFrames.push(callback)
        return animationFrames.length
      })

    render(<NewsDetail />)
    const progress = document.querySelector<HTMLDivElement>(".news-reading-progress")
    window.dispatchEvent(new Event("scroll"))
    animationFrames[0]?.(0)

    expect(progress?.style.transform).toBe("scaleX(0)")
    requestAnimationFrame.mockRestore()
  })

  it("localizes article content and wires interaction, edit, and delete flows", async () => {
    const historyLength = vi.spyOn(window.history, "length", "get").mockReturnValue(1)
    render(<NewsDetail />)

    expect(screen.getByRole("heading", { name: "English title" })).toBeInTheDocument()
    expect(screen.getByText("body:English content")).toBeInTheDocument()
    expect(mocks.setNewsHeroId).toHaveBeenCalledWith("news-1")

    fireEvent.click(screen.getByRole("button", { name: "like" }))
    fireEvent.click(screen.getByRole("button", { name: "bookmark" }))
    fireEvent.click(screen.getByRole("button", { name: "share" }))
    expect(mocks.toggleLike).toHaveBeenCalledOnce()
    expect(mocks.toggleBookmark).toHaveBeenCalledWith("news-1")

    fireEvent.click(screen.getByRole("button", { name: "edit" }))
    expect(screen.getByText("edit-dialog")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "delete" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))

    await waitFor(() => {
      expect(mocks.deleteNews).toHaveBeenCalledWith("news-1")
      expect(mocks.removeQueries).toHaveBeenCalledWith({ queryKey: ["news", "news-1"] })
      expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["news", "list"] })
      expect(mocks.navigate).toHaveBeenCalledWith({ to: "/news" })
    })
    historyLength.mockRestore()
  })

  it("renders share options and invokes copy/link-close actions", async () => {
    const setShareDialogOpen = vi.fn()
    const handleCopyLink = vi.fn()
    mocks.share = {
      sharing: false,
      shareDialogOpen: true,
      setShareDialogOpen,
      copyingLink: false,
      copiedLink: false,
      shareOptions: [
        {
          id: "telegram",
          href: "https://t.me/share",
          label: "Telegram",
          accent: "text-brand",
          icon: () => <span data-testid="telegram-icon" />,
        },
      ],
      handleShare: vi.fn(),
      handleCopyLink,
    }

    render(<NewsDetail />)

    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Telegram" })).toHaveAttribute(
      "href",
      "https://t.me/share"
    )
    fireEvent.click(screen.getByRole("link", { name: "Telegram" }))
    expect(setShareDialogOpen).toHaveBeenCalledWith(false)

    fireEvent.click(screen.getByRole("button", { name: "news:shareDialog.copy" }))
    expect(handleCopyLink).toHaveBeenCalledOnce()
  })

  it("renders related articles, shows copied-link state, and ignores missing neighbors", () => {
    mocks.articleNavigation = {
      prevId: null,
      nextId: null,
      prevTitle: null,
      nextTitle: null,
    }
    mocks.relatedArticles = [{ id: "related-1" }]
    const handleCopyLink = vi.fn()
    mocks.share = {
      sharing: false,
      shareDialogOpen: true,
      setShareDialogOpen: vi.fn(),
      copyingLink: false,
      copiedLink: true,
      shareOptions: [],
      handleShare: vi.fn(),
      handleCopyLink,
    }

    render(<NewsDetail />)

    expect(screen.getByTestId("related-news")).toHaveTextContent("1")
    expect(screen.getByRole("button", { name: "news:shareDialog.copySuccess" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "news:shareDialog.copySuccess" }))
    expect(handleCopyLink).toHaveBeenCalledOnce()

    const swipe = mocks.swipe as {
      onSwipeLeft: () => void
      onSwipeRight: () => void
    }
    swipe.onSwipeLeft()
    swipe.onSwipeRight()
    expect(mocks.navigate).not.toHaveBeenCalled()
  })

  it("shows a snackbar when deleting the article fails", async () => {
    mocks.deleteNews.mockRejectedValueOnce(new Error("delete failed"))

    render(<NewsDetail />)

    fireEvent.click(screen.getByRole("button", { name: "delete" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))

    await waitFor(() => {
      expect(screen.getByText("news:notifications.deleteError")).toBeInTheDocument()
    })
  })

  it("uses browser history after a successful delete when a previous page exists", async () => {
    const back = vi.spyOn(window.history, "back").mockImplementation(() => undefined)
    const historyLength = vi.spyOn(window.history, "length", "get").mockReturnValue(2)

    render(<NewsDetail />)

    fireEvent.click(screen.getByRole("button", { name: "delete" }))
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.delete" }))

    await waitFor(() => expect(back).toHaveBeenCalledOnce())
    historyLength.mockRestore()
    back.mockRestore()
  })

  it("falls back to empty interaction values when the interaction snapshot is absent", () => {
    mocks.interactions = undefined

    render(<NewsDetail />)

    expect(screen.getByRole("button", { name: "like" })).toBeInTheDocument()
  })
})
