import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { state, mockResetEtagCache } = vi.hoisted(() => ({
  state: {
    auth: { current: { user: { role: "admin" } as { role: string } | null } },
    language: { current: "en" },
    online: { current: true },
    debounced: { current: "" },
    bookmarks: { current: new Set<string>() },
    url: { current: { params: { q: "", cat: "all", sort: "newest" } } },
    query: {
      current: {
        news: [] as Array<{ id: string; title: string }>,
        isLoading: false,
        isFetching: false,
        isFetchingNextPage: false,
        hasNextPage: true,
        fetchNextPage: vi.fn(),
      },
    },
    mockSetParam: vi.fn(),
    mockRegisterRef: vi.fn(),
    mockResetEtagCache: vi.fn(),
  },
  mockResetEtagCache: vi.fn(),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => state.auth.current,
}))
vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: state.language.current }),
}))
vi.mock("@/hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => state.online.current,
}))
vi.mock("@/hooks/useDebounced", () => ({
  useDebounced: () => state.debounced.current,
}))
vi.mock("@/hooks/useBookmarks", () => ({
  useBookmarks: () => ({
    bookmarks: state.bookmarks.current,
    bookmarkCount: state.bookmarks.current.size,
  }),
}))
vi.mock("@/hooks/useNewsKeyboardNav", () => ({
  useNewsKeyboardNav: () => ({ activeIndex: 1, registerRef: state.mockRegisterRef }),
}))
vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({ params: state.url.current.params, setParam: state.mockSetParam }),
}))
vi.mock("@/api/hooks/news", () => ({
  useNewsListQuery: () => state.query.current,
}))
vi.mock("@/api/client", () => ({
  resetEtagCache: mockResetEtagCache,
}))

vi.mock("@/features/news/components/NewsHeader", () => ({
  NewsHeader: (props: {
    isAdmin: boolean
    newsCount: number
    bookmarkCount: number
    onAddClick: () => void
    onSearchChange: (value: string) => void
    onCategoryChange: (value: string) => void
    onSortChange: (value: string) => void
  }) => (
    <div
      data-testid="news-header"
      data-admin={String(props.isAdmin)}
      data-count={String(props.newsCount)}
      data-bookmarks={String(props.bookmarkCount)}
    >
      <button data-testid="news-add" onClick={props.onAddClick} />
      <input
        data-testid="news-search"
        onChange={(event) => props.onSearchChange(event.currentTarget.value)}
      />
      <button data-testid="news-category-saved" onClick={() => props.onCategoryChange("saved")} />
      <button data-testid="news-category-all" onClick={() => props.onCategoryChange("all")} />
      <button data-testid="news-sort-popular" onClick={() => props.onSortChange("popular")} />
      <button data-testid="news-sort-newest" onClick={() => props.onSortChange("newest")} />
    </div>
  ),
}))

vi.mock("@/features/news/components/NewsList", () => ({
  NewsList: (props: {
    newsList: Array<{ id: string; title: string }>
    hasNextPage: boolean
    fetchNextPage: () => void
    refreshNews: () => void
    onAddClick: () => void
  }) => (
    <div
      data-testid="news-list"
      data-count={String(props.newsList.length)}
      data-next={String(props.hasNextPage)}
    >
      {props.newsList.map((item) => (
        <span key={item.id}>{item.title}</span>
      ))}
      <button data-testid="news-next" onClick={props.fetchNextPage} />
      <button data-testid="news-refresh" onClick={props.refreshNews} />
      <button data-testid="news-list-add" onClick={props.onAddClick} />
    </div>
  ),
}))

vi.mock("@/features/news/components/NewsFormDialog", () => ({
  NewsFormDialog: (props: { open: boolean; onClose: () => void; onSuccess: () => void }) => (
    <div data-testid="news-form" data-open={String(props.open)}>
      <button data-testid="news-form-close" onClick={props.onClose} />
      <button data-testid="news-form-success" onClick={props.onSuccess} />
    </div>
  ),
}))

vi.mock("@/features/news/components/NewsShortcutsOverlay", () => ({
  NewsShortcutsOverlay: () => <div data-testid="news-shortcuts" />,
}))

import { NewsFeature } from "@/features/news/NewsFeature"

const NEWS = [
  {
    id: "news-education",
    title: "Lecture schedule",
    content: "Semester timetable",
    title_en: null,
    content_en: null,
    likes_count: 2,
  },
  {
    id: "news-sport",
    title: "Campus update",
    content: "Football tournament",
    title_en: "Sports day",
    content_en: "Competition news",
    likes_count: 20,
  },
] as Array<{ id: string; title: string }> & Array<Record<string, unknown>>

function renderFeature() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NewsFeature />
    </QueryClientProvider>
  )
}

describe("NewsFeature closure", () => {
  beforeEach(() => {
    state.auth.current = { user: { role: "admin" } }
    state.language.current = "en"
    state.online.current = true
    state.debounced.current = ""
    state.bookmarks.current = new Set()
    state.url.current = { params: { q: "", cat: "all", sort: "newest" } }
    state.query.current = {
      news: NEWS,
      isLoading: false,
      isFetching: false,
      isFetchingNextPage: false,
      hasNextPage: true,
      fetchNextPage: vi.fn(),
    }
    state.mockSetParam.mockReset()
    state.mockRegisterRef.mockReset()
    mockResetEtagCache.mockReset()
  })

  it("filters, exposes controls, refreshes, paginates, and opens the form", () => {
    renderFeature()

    expect(screen.getByTestId("news-header")).toHaveAttribute("data-admin", "true")
    expect(screen.getByTestId("news-header")).toHaveAttribute("data-count", "2")
    expect(screen.getByTestId("news-list")).toHaveAttribute("data-next", "true")
    expect(screen.getByText("Lecture schedule")).toBeInTheDocument()

    fireEvent.change(screen.getByTestId("news-search"), { target: { value: "lecture" } })
    fireEvent.click(screen.getByTestId("news-category-saved"))
    fireEvent.click(screen.getByTestId("news-category-all"))
    fireEvent.click(screen.getByTestId("news-sort-popular"))
    fireEvent.click(screen.getByTestId("news-sort-newest"))
    expect(state.mockSetParam).toHaveBeenNthCalledWith(1, "q", "lecture")
    expect(state.mockSetParam).toHaveBeenCalledWith("cat", "saved")
    expect(state.mockSetParam).toHaveBeenCalledWith("cat", "")
    expect(state.mockSetParam).toHaveBeenCalledWith("sort", "popular")
    expect(state.mockSetParam).toHaveBeenCalledWith("sort", "")

    fireEvent.click(screen.getByTestId("news-next"))
    expect(state.query.current.fetchNextPage).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByTestId("news-refresh"))
    fireEvent.click(screen.getByTestId("news-add"))
    expect(screen.getByTestId("news-form")).toHaveAttribute("data-open", "true")
    fireEvent.click(screen.getByTestId("news-form-close"))
    fireEvent.click(screen.getByTestId("news-list-add"))
    fireEvent.click(screen.getByTestId("news-form-success"))
    expect(mockResetEtagCache).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId("news-shortcuts")).toBeInTheDocument()
  })

  it("applies saved/popular filters, translated search fields, and offline state", () => {
    state.auth.current = { user: null }
    state.online.current = false
    state.debounced.current = "sports"
    state.bookmarks.current = new Set(["news-sport"])
    state.url.current = { params: { q: "sports", cat: "saved", sort: "popular" } }
    state.query.current = { ...state.query.current, hasNextPage: true }

    renderFeature()

    expect(screen.getByTestId("news-header")).toHaveAttribute("data-admin", "false")
    expect(screen.getByTestId("news-header")).toHaveAttribute("data-count", "1")
    expect(screen.getByTestId("news-list")).toHaveAttribute("data-count", "1")
    expect(screen.getByTestId("news-list")).toHaveAttribute("data-next", "false")
    expect(screen.getByText("Campus update")).toBeInTheDocument()
    expect(screen.queryByText("Lecture schedule")).not.toBeInTheDocument()
  })

  it("filters by an inferred non-saved category", () => {
    state.debounced.current = ""
    state.url.current = { params: { q: "", cat: "sport", sort: "newest" } }
    renderFeature()

    expect(screen.getByTestId("news-list")).toHaveAttribute("data-count", "1")
    expect(screen.getByText("Campus update")).toBeInTheDocument()
  })
})
