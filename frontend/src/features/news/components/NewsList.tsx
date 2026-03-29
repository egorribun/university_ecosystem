import { Newspaper as ArticleIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import FadeSection from "@/components/motion/FadeSection"
import NewsCard from "@/components/news/NewsCard"
import NewsCardSkeleton from "@/components/ui/NewsCardSkeleton"
import OfflineFallback from "@/components/feedback/OfflineFallback"
import { Button } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
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
                <EmptyState
                  icon={<ArticleIcon className="h-8 w-8" />}
                  title={t("news:states.empty")}
                  description={t("news:states.checkLater", {
                    defaultValue: "Check back later for updates",
                  })}
                  action={
                    isAdmin ? (
                      <Button
                        id="news-empty-add-btn"
                        size="lg"
                        onClick={onAddClick}
                        className="px-6"
                      >
                        {t("news:actions.add")}
                      </Button>
                    ) : undefined
                  }
                />
              )}
            </div>
          )}
        </FadeSection>
      </section>

      {/* Load more */}
      {hasNextPage && (
        <div className="mt-8 mb-8 flex justify-center">
          <Button
            id="news-load-more-btn"
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
