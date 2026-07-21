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
  setNewsHeroId: vi.fn(),
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
    interactions: { is_liked: false, likes_count: 4, comments: [] },
    toggleLike: mocks.toggleLike,
    addComment: vi.fn(),
    isCommenting: false,
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
  }),
}))

vi.mock("@/hooks/useShare", () => ({
  useShare: () => ({
    sharing: false,
    shareDialogOpen: false,
    setShareDialogOpen: vi.fn(),
    copyingLink: false,
    copiedLink: false,
    shareOptions: [],
    handleShare: vi.fn(),
    handleCopyLink: vi.fn(),
  }),
}))

vi.mock("@/hooks/useBookmarks", () => ({
  useBookmarks: () => ({
    isBookmarked: () => false,
    toggleBookmark: mocks.toggleBookmark,
  }),
}))

vi.mock("@/hooks/useRelatedNews", () => ({ useRelatedNews: () => [] }))
vi.mock("@/hooks/useArticleNavigation", () => ({
  useArticleNavigation: () => ({
    prevId: null,
    nextId: null,
    prevTitle: null,
    nextTitle: null,
  }),
}))
vi.mock("@/hooks/useSwipe", () => ({ useSwipe: () => ({}) }))
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
vi.mock("@/components/news/RelatedNews", () => ({ RelatedNews: () => <div /> }))
vi.mock("@/components/news/NewsDetailNavigation", () => ({ NewsDetailNavigation: () => <div /> }))
vi.mock("@/components/news/NewsDetailEditDialog", () => ({
  NewsDetailEditDialog: ({ open }: { open: boolean }) => (open ? <div>edit-dialog</div> : null),
}))
vi.mock("@/components/news/NewsDetailHeader", () => ({
  NewsDetailHeader: ({
    displayTitle,
    onToggleLike,
    onToggleBookmark,
    onEditOpen,
    onDeleteOpen,
  }: {
    displayTitle: string
    onToggleLike: () => void
    onToggleBookmark: () => void
    onEditOpen: () => void
    onDeleteOpen: () => void
  }) => (
    <header>
      <h1>{displayTitle}</h1>
      <button onClick={onToggleLike}>like</button>
      <button onClick={onToggleBookmark}>bookmark</button>
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
    mocks.setNewsHeroId.mockReset()
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
    expect(screen.getByRole("button", { name: "common:buttons.back" })).toBeInTheDocument()
  })

  it("localizes article content and wires interaction, edit, and delete flows", async () => {
    render(<NewsDetail />)

    expect(screen.getByRole("heading", { name: "English title" })).toBeInTheDocument()
    expect(screen.getByText("body:English content")).toBeInTheDocument()
    expect(mocks.setNewsHeroId).toHaveBeenCalledWith("news-1")

    fireEvent.click(screen.getByRole("button", { name: "like" }))
    fireEvent.click(screen.getByRole("button", { name: "bookmark" }))
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
    })
  })
})
