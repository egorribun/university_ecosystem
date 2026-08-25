import { useState, useCallback, useEffect, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useDebounced } from "@/hooks/useDebounced"
import { useBookmarks } from "@/hooks/useBookmarks"
import { useNewsKeyboardNav } from "@/hooks/useNewsKeyboardNav"
import { useURLState } from "@/hooks/useURLState"
import { useNewsListQuery } from "@/api/hooks/news"
import { resetEtagCache } from "@/api/client"
import { NewsHeader } from "./components/NewsHeader"
import { NewsList } from "./components/NewsList"
import { NewsFormDialog } from "./components/NewsFormDialog"
import { NewsShortcutsOverlay } from "./components/NewsShortcutsOverlay"
import { inferCategory, type NewsCategory } from "./categories"

export type SortMode = "newest" | "popular"

type NewsCategoryFilter = NewsCategory | "all" | "saved"
type NewsURLParams = {
  q?: string
  cat?: NewsCategoryFilter
  sort?: SortMode
}

export const NewsFeature = () => {
  const { user } = useAuth()
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const isOnline = useOnlineStatus()

  const {
    news: rawNewsList,
    isLoading: isInitialLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useNewsListQuery({ language })

  const [addOpen, setAddOpen] = useState(false)

  // URL-synced filters — Wave 112 SW3 (mirror of EventsFeature convention).
  // Local-only state kept for dialog open flags and text-search debouncing
  // (debounced mirror avoids thrashing the URL on every keystroke).
  const { params, setParam } = useURLState<NewsURLParams>()
  const activeCategory: NewsCategoryFilter = params.cat ?? "all"
  const sortMode: SortMode = params.sort ?? "newest"
  const searchQuery = params.q ?? ""

  const setActiveCategory = useCallback(
    (next: NewsCategoryFilter) => setParam("cat", next === "all" ? "" : next),
    [setParam]
  )
  const setSortMode = useCallback(
    (next: SortMode) => setParam("sort", next === "newest" ? "" : next),
    [setParam]
  )
  const setSearchQuery = useCallback((next: string) => setParam("q", next), [setParam])

  const debouncedSearch = useDebounced(searchQuery, "search")
  const { bookmarks, bookmarkCount } = useBookmarks()

  const refreshNews = useCallback(() => {
    resetEtagCache()
    void queryClient.invalidateQueries({ queryKey: ["news", "list"] })
  }, [queryClient])

  /* ── Filter + sort + search ── */
  const filteredNews = useMemo(() => {
    let list = rawNewsList

    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase()
      list = list.filter(
        (n) =>
          n.title.toLowerCase().includes(q) ||
          n.content.toLowerCase().includes(q) ||
          (n.title_en?.toLowerCase().includes(q) ?? false) ||
          (n.content_en?.toLowerCase().includes(q) ?? false)
      )
    }

    if (activeCategory === "saved") {
      list = list.filter((n) => bookmarks.has(n.id))
    } else if (activeCategory !== "all") {
      list = list.filter((n) => inferCategory(n.title, n.content) === activeCategory)
    }

    if (sortMode === "popular") {
      list = [...list].sort((a, b) => (b.likes_count ?? 0) - (a.likes_count ?? 0))
    }

    return list
  }, [rawNewsList, debouncedSearch, activeCategory, sortMode, bookmarks])

  const requiresCompleteDataset =
    debouncedSearch.trim().length > 0 || activeCategory !== "all" || sortMode === "popular"
  useEffect(() => {
    if (
      requiresCompleteDataset &&
      hasNextPage &&
      !isInitialLoading &&
      !isFetchingNextPage &&
      isOnline
    ) {
      void fetchNextPage()
    }
  }, [
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isInitialLoading,
    isOnline,
    requiresCompleteDataset,
  ])

  /* ── Keyboard navigation ── */
  const { activeIndex, registerRef } = useNewsKeyboardNav(filteredNews)

  return (
    <div className="news-theme w-full text-text-primary py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14">
      <NewsHeader
        onAddClick={() => setAddOpen(true)}
        isAdmin={user?.role === "admin"}
        newsCount={filteredNews.length}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        activeCategory={activeCategory}
        onCategoryChange={setActiveCategory}
        sortMode={sortMode}
        onSortChange={setSortMode}
        bookmarkCount={bookmarkCount}
      />

      <NewsList
        newsList={filteredNews}
        isInitialLoading={isInitialLoading}
        isFetching={isFetching}
        isFetchingNextPage={isFetchingNextPage}
        hasNextPage={Boolean(hasNextPage)}
        fetchNextPage={fetchNextPage}
        refreshNews={refreshNews}
        onAddClick={() => setAddOpen(true)}
        isAdmin={user?.role === "admin"}
        isOnline={isOnline}
        activeKeyboardIndex={activeIndex}
        registerCardRef={registerRef}
      />

      <NewsFormDialog open={addOpen} onClose={() => setAddOpen(false)} onSuccess={refreshNews} />

      <NewsShortcutsOverlay />
    </div>
  )
}
