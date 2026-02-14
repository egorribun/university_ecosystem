import { useState, useCallback, useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import { useNewsListQuery } from "@/api/hooks/news"
import { resetEtagCache } from "@/api/client"
import { StorageItem } from "@/utils/storage"
import { NewsHeader } from "./components/NewsHeader"
import { NewsList } from "./components/NewsList"
import { NewsFormDialog } from "./components/NewsFormDialog"

export const NewsFeature = () => {
  const { user } = useAuth()
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const isOnline = useOnlineStatus()

  const {
    news: newsList,
    isLoading: isInitialLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useNewsListQuery({ language })

  const [addOpen, setAddOpen] = useState(false)

  const refreshNews = useCallback(() => {
    resetEtagCache()
    void queryClient.invalidateQueries({ queryKey: ["news", "list"] })
  }, [queryClient])

  // Persist to localStorage
  useEffect(() => {
    if (newsList.length > 0) {
      const storage = new StorageItem<typeof newsList>(`news:list:${language}`)
      storage.set(newsList)
    }
  }, [newsList, language])

  return (
    <div className="w-full min-h-full bg-transparent text-(--text-primary) py-8 sm:py-10">
      <div className="px-4">
        <NewsHeader onAddClick={() => setAddOpen(true)} isAdmin={user?.role === "admin"} />

        <NewsList
          newsList={newsList}
          isInitialLoading={isInitialLoading}
          isFetching={isFetching}
          isFetchingNextPage={isFetchingNextPage}
          hasNextPage={hasNextPage}
          fetchNextPage={fetchNextPage}
          refreshNews={refreshNews}
          onAddClick={() => setAddOpen(true)}
          isAdmin={user?.role === "admin"}
          isOnline={isOnline}
        />

        <NewsFormDialog open={addOpen} onClose={() => setAddOpen(false)} onSuccess={refreshNews} />
      </div>
    </div>
  )
}
