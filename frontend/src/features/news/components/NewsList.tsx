import { useRef, useEffect, useCallback, type CSSProperties } from "react"
import { Newspaper as ArticleIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import NewsCard from "@/components/news/NewsCard"
import NewsCardSkeleton from "@/components/ui/NewsCardSkeleton"
import OfflineFallback from "@/components/feedback/OfflineFallback"
import { Button } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import { type NewsItem as News } from "@/api/news"
import { FeatureErrorBoundary } from "@/components/error"
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
  const showEmptyState =
    !isInitialLoading && !isFetchingNextPage && !hasNextPage && newsList.length === 0

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
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5">
        {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
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
            description={t("news:states.checkLater")}
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
        <div
          className="h-0.5 w-full rounded-full bg-brand/(--opacity-medium) mb-4 animate-pulse"
          aria-hidden="true"
        />
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5">
        {/* Wave 117 SW4 — mirrors Events PERF-77-01 pattern: plain <div>
            wrappers with css-stagger-item + --stagger-index CSS custom
            property (@starting-style-driven entrance) instead of
            AnimatePresence + motion.div per card. Phase 0 chrome-devtools
            traces on /news showed the Framer Motion settle timeout
            contributed ~800-1500 ms of LCP delay on mobile 4x CPU + Slow 4G.
            News list has no sort/filter reorder UX, so the Framer `layout`
            prop FLIP behavior was unused. Admin-delete exit animation is
            lost (minor UX regression — Events already shipped this with
            zero complaints). Bookmark toggle lives in NewsCardContent,
            unaffected by list-level wrapper change. `priority` prop
            threading to first-card SmartImage (Wave 113 PERF-113-01) is
            preserved — plain <div> doesn't interfere with child props. */}
        {newsList.map((news, index) => (
          <div
            key={news.id}
            ref={(el) => registerCardRef?.(index, el)}
            style={{ "--stagger-index": Math.min(index, 12) } as CSSProperties}
            className={cn(
              "css-stagger-item",
              activeKeyboardIndex === index && "ring-2 ring-brand rounded-2xl"
            )}
          >
            <FeatureErrorBoundary>
              <NewsCard
                {...news}
                image_url={news.image_url ?? undefined}
                onChange={handleRetry}
                priority={index === 0}
              />
            </FeatureErrorBoundary>
          </div>
        ))}

        {/* Next-page loading skeletons */}
        {isFetchingNextPage &&
          Array.from({ length: NEXT_PAGE_SKELETON_COUNT }).map((_, i) => (
            <div key={`next-skel-${i}`}>
              <NewsCardSkeleton />
            </div>
          ))}
      </div>

      {/* Infinite scroll sentinel */}
      {hasNextPage && <div ref={sentinelRef} className="h-1" aria-hidden="true" />}
    </section>
  )
}
