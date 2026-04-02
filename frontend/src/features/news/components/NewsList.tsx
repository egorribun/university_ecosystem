import { useRef, useEffect, useCallback } from "react"
import { Newspaper as ArticleIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion } from "framer-motion"
import NewsCard from "@/components/news/NewsCard"
import NewsCardSkeleton from "@/components/ui/NewsCardSkeleton"
import OfflineFallback from "@/components/feedback/OfflineFallback"
import { Button } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import { type NewsItem as News } from "@/api/news"
import { cn } from "@/utils/cn"

interface NewsListProps {
  newsList: News[]
  isInitialLoading: boolean
  isFetching: boolean
  isFetchingNextPage: boolean
  hasNextPage: boolean
  fetchNextPage: () => void
  refreshNews: () => void
  onAddClick: () => void
  isAdmin: boolean
  isOnline: boolean
  activeKeyboardIndex?: number
  registerCardRef?: (index: number, el: HTMLElement | null) => void
}

const SKELETON_COUNT = 6
const NEXT_PAGE_SKELETON_COUNT = 3

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
  activeKeyboardIndex = -1,
  registerCardRef,
}: NewsListProps) => {
  const { t } = useTranslation(["news", "common"])
  const showEmptyState = !isInitialLoading && newsList.length === 0

  /* ── Infinite scroll ── */
  const sentinelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || !hasNextPage || isFetchingNextPage) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          void fetchNextPage()
        }
      },
      { rootMargin: "300px" }
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const handleRetry = useCallback(() => refreshNews(), [refreshNews])

  /* ── Loading skeleton ── */
  if (isInitialLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        <div className="sm:col-span-2 lg:col-span-2 lg:row-span-2">
          <NewsCardSkeleton featured />
        </div>
        {Array.from({ length: SKELETON_COUNT - 1 }).map((_, i) => (
          <div key={`skel-${i}`}>
            <NewsCardSkeleton />
          </div>
        ))}
      </div>
    )
  }

  /* ── Empty state ── */
  if (showEmptyState) {
    return (
      <div className="w-full flex justify-center py-20">
        {!isOnline ? (
          <OfflineFallback onRetry={handleRetry} />
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
                  variant="glass"
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
    )
  }

  /* ── Card grid ── */
  const showRefetchBar = isFetching && !isInitialLoading && !isFetchingNextPage

  return (
    <section aria-label={t("news:pageTitle")}>
      {/* Refetch indicator — thin bar during background refresh */}
      {showRefetchBar && (
        <div className="h-0.5 w-full rounded-full bg-brand/(--opacity-medium) mb-4 animate-pulse" aria-hidden />
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        <AnimatePresence mode="popLayout">
          {newsList.map((news, index) => (
            <motion.div
              key={news.id}
              ref={(el) => registerCardRef?.(index, el)}
              layout
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className={cn(
                index === 0 && "sm:col-span-2 lg:col-span-2 lg:row-span-2",
                activeKeyboardIndex === index && "ring-2 ring-brand rounded-2xl"
              )}
            >
              <NewsCard
                {...news}
                image_url={news.image_url ?? undefined}
                featured={index === 0}
                onChange={handleRetry}
              />
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Next-page loading skeletons */}
        {isFetchingNextPage &&
          Array.from({ length: NEXT_PAGE_SKELETON_COUNT }).map((_, i) => (
            <div key={`next-skel-${i}`}>
              <NewsCardSkeleton />
            </div>
          ))}
      </div>

      {/* Infinite scroll sentinel */}
      {hasNextPage && <div ref={sentinelRef} className="h-1" aria-hidden />}
    </section>
  )
}
