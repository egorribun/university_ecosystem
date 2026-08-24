import { useRef, useEffect, useCallback, type CSSProperties } from "react"
import { Calendar as EventIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import EventCard from "@/components/events/EventCard/EventCard"
import { EventCardSkeleton } from "@/components/events/EventCard/EventCardSkeleton"
import OfflineFallback from "@/components/feedback/OfflineFallback"
import { Button } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import { FeatureErrorBoundary } from "@/components/error"
import type { Event } from "@/types/Event"
import type { EventTabKey } from "../types"
import { cn } from "@/utils/cn"

interface EventsListProps {
  eventsList: Event[]
  isInitialLoading: boolean
  isFetching: boolean
  isFetchingNextPage: boolean
  hasNextPage: boolean
  fetchNextPage: () => void
  refreshEvents: () => void
  onAddClick: () => void
  isAdmin: boolean
  isOnline: boolean
  tab: EventTabKey
  onTabChange: (t: EventTabKey) => void
  activeKeyboardIndex?: number
  registerCardRef?: (index: number, el: HTMLElement | null) => void
}

const SKELETON_COUNT = 6
const NEXT_PAGE_SKELETON_COUNT = 3

export const EventsList = ({
  eventsList,
  isInitialLoading,
  isFetching,
  isFetchingNextPage,
  hasNextPage,
  fetchNextPage,
  refreshEvents,
  onAddClick,
  isAdmin,
  isOnline,
  tab,
  onTabChange,
  activeKeyboardIndex = -1,
  registerCardRef,
}: EventsListProps) => {
  const { t } = useTranslation(["events", "common"])
  const showEmptyState = !isInitialLoading && eventsList.length === 0

  /* ── Infinite scroll sentinel ── */
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

  const handleRetry = useCallback(() => refreshEvents(), [refreshEvents])

  /* ── Card grid ── */
  const showRefetchBar = isFetching && !isInitialLoading && !isFetchingNextPage

  /**
   * Wave 116 polish — ALWAYS render the `<section id="events-tabpanel">`
   * wrapper so `aria-controls="events-tabpanel"` on the EventsHeader tabs
   * always resolves to a real element. Previously the loading + empty-state
   * early returns rendered a plain `<div>` without the tabpanel id, which
   * made Lighthouse `aria-valid-attr-value` fire (weight 10, dropping
   * /events a11y to 0.95). All three variants (skeleton / empty state / card
   * grid) now render INSIDE the same section wrapper.
   */
  return (
    <section
      aria-label={t("events:pageTitle")}
      role="tabpanel"
      id="events-tabpanel"
      aria-labelledby={`events-tab-${tab}`}
      aria-busy={isInitialLoading || undefined}
    >
      {/* ── Loading skeleton ── */}
      {isInitialLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5">
          {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
            <div key={`event-skel-${i}`}>
              <EventCardSkeleton />
            </div>
          ))}
        </div>
      )}

      {/* ── Empty state (offline fallback or zero events) ── */}
      {!isInitialLoading && showEmptyState && (
        <div className="w-full flex justify-center py-20">
          {!isOnline ? (
            <OfflineFallback onRetry={handleRetry} />
          ) : (
            <EmptyState
              icon={<EventIcon className="h-8 w-8" />}
              title={t("events:states.empty")}
              description={
                tab === "my"
                  ? t("events:states.emptyHint.my")
                  : tab === "active"
                    ? t("events:states.emptyHint.active")
                    : t("events:states.emptyHint.archive")
              }
              action={
                tab !== "my" ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onTabChange(tab === "active" ? "archive" : "active")}
                    className="text-brand hover:bg-brand/(--opacity-subtle)"
                  >
                    {tab === "active" ? t("events:tabs.archive") : t("events:tabs.active")}
                  </Button>
                ) : isAdmin ? (
                  <Button
                    id="events-empty-add-btn"
                    variant="glass"
                    size="lg"
                    onClick={onAddClick}
                    className="px-6"
                  >
                    {t("events:actions.openCreate")}
                  </Button>
                ) : undefined
              }
            />
          )}
        </div>
      )}

      {/* ── Card grid (populated feed) ── */}
      {!isInitialLoading && !showEmptyState && (
        <>
          {/* Refetch indicator */}
          {showRefetchBar && (
            <div
              className="h-0.5 w-full rounded-full bg-brand/(--opacity-medium) mb-4 animate-pulse"
              aria-hidden="true"
            />
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5">
            {eventsList.map((event, index) => (
              <div
                key={event.id}
                ref={(el) => registerCardRef?.(index, el)}
                style={{ "--stagger-index": Math.min(index, 12) } as CSSProperties}
                className={cn(
                  "css-stagger-item",
                  activeKeyboardIndex === index && "ring-2 ring-brand rounded-2xl"
                )}
              >
                <FeatureErrorBoundary>
                  <EventCard
                    {...event}
                    onChange={handleRetry}
                    maxWidth="100%"
                    animationIndex={index}
                    priority={index === 0}
                  />
                </FeatureErrorBoundary>
              </div>
            ))}

            {/* Next-page loading skeletons */}
            {isFetchingNextPage &&
              Array.from({ length: NEXT_PAGE_SKELETON_COUNT }).map((_, i) => (
                <div key={`next-skel-${i}`}>
                  <EventCardSkeleton />
                </div>
              ))}
          </div>

          {/* Infinite scroll sentinel */}
          {hasNextPage && (
            <div
              ref={sentinelRef}
              data-testid="events-next-page-sentinel"
              className="h-1"
              aria-hidden="true"
            />
          )}
        </>
      )}
    </section>
  )
}
