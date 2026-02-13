import { Newspaper as ArticleIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import FadeSection from "@/components/FadeSection"
import NewsCard from "@/components/NewsCard"
import NewsCardSkeleton from "@/components/NewsCardSkeleton"
import OfflineFallback from "@/components/OfflineFallback"
import { Button } from "@/components/ui"
import { type NewsItem as News } from "@/api/news"

interface NewsListProps {
  newsList: News[]
  isInitialLoading: boolean
  isFetching: boolean // used for empty state check context
  isFetchingNextPage: boolean
  hasNextPage: boolean
  fetchNextPage: () => void
  refreshNews: () => void
  onAddClick: () => void
  isAdmin: boolean
  isOnline: boolean
}

export const NewsList = ({
  newsList,
  isInitialLoading,
  isFetching,
  isFetchingNextPage,
  hasNextPage,
  fetchNextPage,
  refreshNews,
  onAddClick,
  isAdmin,
  isOnline,
}: NewsListProps) => {
  const { t } = useTranslation(["news", "common"])
  const skeletonCount = 6
  // Logic from News.tsx: showEmptyState = !isInitialLoading && !isFetching && newsList.length === 0
  // But wait, if isFetching is true (background update), we still show list if we have it?
  // In News.tsx: const showEmptyState = !isInitialLoading && !isFetching && newsList.length === 0
  const showEmptyState = !isInitialLoading && !isFetching && newsList.length === 0

  return (
    <>
      <section aria-label={t("news:pageTitle")}>
        <FadeSection delay="200ms" className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {isInitialLoading
            ? Array.from({ length: skeletonCount }).map((_, index) => (
                <div key={`news-skeleton-${index}`} className="flex h-full w-full">
                  <NewsCardSkeleton />
                </div>
              ))
            : newsList.map((news) => (
                <div key={news.id} className="flex h-full w-full">
                  <NewsCard
                    {...news}
                    image_url={news.image_url ?? undefined}
                    onChange={() => {
                      void refreshNews()
                    }}
                  />
                </div>
              ))}

          {showEmptyState && (
            <div className="col-span-full mt-12 flex w-full justify-center">
              {!isOnline && newsList.length === 0 ? (
                <OfflineFallback onRetry={refreshNews} />
              ) : (
                <div className="flex w-full max-w-md flex-col items-center gap-5 rounded-lg border border-glass-border/(--opacity-soft) bg-(--bg-surface)/(--opacity-medium) px-8 py-14 text-center shadow-glass backdrop-blur-md">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) shadow-brand/(--opacity-subtle) shadow-lg">
                    <ArticleIcon className="h-8 w-8 text-brand" />
                  </div>
                  <div className="space-y-2">
                    <p className="text-lg font-semibold text-(--text-primary)">
                      {t("news:states.empty")}
                    </p>
                    <p className="text-sm text-(--text-secondary)">
                      {t("news:states.checkLater", {
                        defaultValue: "Check back later for updates",
                      })}
                    </p>
                  </div>
                  {isAdmin && (
                    <Button size="lg" onClick={onAddClick} className="mt-2 px-6">
                      {t("news:actions.add")}
                    </Button>
                  )}
                </div>
              )}
            </div>
          )}
        </FadeSection>
      </section>

      {/* Load more */}
      {hasNextPage && (
        <div className="mt-8 mb-8 flex justify-center">
          <Button
            variant="outline"
            size="lg"
            onClick={() => void fetchNextPage()}
            disabled={isFetchingNextPage}
            className="px-6"
          >
            {isFetchingNextPage
              ? t("common:statuses.loading")
              : t("common:buttons.loadMore", { defaultValue: "Load more" })}
          </Button>
        </div>
      )}
    </>
  )
}
