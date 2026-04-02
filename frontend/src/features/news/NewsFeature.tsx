import { useState, useCallback, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useDebounced } from "@/hooks/useDebounced"
import { useNewsListQuery } from "@/api/hooks/news"
import { resetEtagCache } from "@/api/client"
import { NewsHeader } from "./components/NewsHeader"
import { NewsList } from "./components/NewsList"
import { NewsFormDialog } from "./components/NewsFormDialog"
import { inferCategory, type NewsCategory } from "./categories"

export type SortMode = "newest" | "popular"

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
  const [activeCategory, setActiveCategory] = useState<NewsCategory | "all">("all")
  const [sortMode, setSortMode] = useState<SortMode>("newest")
  const [searchQuery, setSearchQuery] = useState("")
  const debouncedSearch = useDebounced(searchQuery, "search")

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

    if (activeCategory !== "all") {
      list = list.filter((n) => inferCategory(n.title, n.content) === activeCategory)
    }

    if (sortMode === "popular") {
      list = [...list].sort((a, b) => (b.likes_count ?? 0) - (a.likes_count ?? 0))
    }

    return list
  }, [rawNewsList, debouncedSearch, activeCategory, sortMode])

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
      />

      <NewsList
        newsList={filteredNews}
        isInitialLoading={isInitialLoading}
        isFetching={isFetching}
        isFetchingNextPage={isFetchingNextPage}
        hasNextPage={hasNextPage && activeCategory === "all" && !debouncedSearch.trim()}
        fetchNextPage={fetchNextPage}
        refreshNews={refreshNews}
        onAddClick={() => setAddOpen(true)}
        isAdmin={user?.role === "admin"}
        isOnline={isOnline}
      />

      <NewsFormDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSuccess={refreshNews}
      />
    </div>
  )
}
