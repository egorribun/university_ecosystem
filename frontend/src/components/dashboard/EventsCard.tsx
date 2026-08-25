import { memo, useMemo, useState, useCallback, type CSSProperties, type KeyboardEvent } from "react"

import { Link, useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { m, AnimatePresence } from "framer-motion"
import { Sparkles } from "lucide-react"

import { Badge, Button, Card, Skeleton } from "@/components/ui"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"
import { useDashboardEvents, prefetchDashboardEvents } from "@/hooks/useDashboardEvents"
import { prefetchEventsListQuery, EVENTS_PAGE_SIZE } from "@/api/hooks/events"
import { useLanguage } from "@/contexts/LanguageContext"
import { useQueryClient } from "@tanstack/react-query"
import type { Event } from "@/types/Event"
import { formatDate, toDate } from "@/utils/date"
import { DateBullet } from "./DateBullet"

interface EventsCardProps {
  className?: string
  style?: CSSProperties
  "data-fade"?: string
  "data-pop"?: string
}

export const EventsCard = memo(function EventsCard({
  className,
  style,
  ...props
}: EventsCardProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const navigate = useNavigate()
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  // Wave 189 SW3 — migrated from framer-motion's `useReducedMotion()` (jsdom-
  // incompat per W184 SW6 Gotcha) to project's `useMediaQuery` DEFAULT export.
  // Behaviour preserved: hook returns boolean (was `boolean | null`).
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")
  const [eventsScope, setEventsScope] = useState<"today" | "week">("today")

  const dashboardEventsQuery = useDashboardEvents()
  const events: Event[] = useMemo(
    () => dashboardEventsQuery.data ?? [],
    [dashboardEventsQuery.data]
  )
  const loadingEvents = dashboardEventsQuery.isLoading && events.length === 0

  const prefetchEventsList = () => {
    void prefetchDashboardEvents(queryClient)
    void prefetchEventsListQuery(queryClient, {
      language,
      is_active: true,
      limit: EVENTS_PAGE_SIZE,
    })
  }

  const prepareOnKey = useCallback((event: KeyboardEvent, callback: () => void) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      callback()
    }
  }, [])

  const todayEvents = useMemo(() => {
    const from = new Date()
    from.setHours(0, 0, 0, 0)
    const to = new Date()
    to.setHours(23, 59, 59, 999)

    return events
      .filter((e) => e.starts_at)
      .map((e) => ({ ...e, d: toDate(e.starts_at!) }))
      .filter((e) => !isNaN(e.d.getTime()) && e.d >= from && e.d <= to)
      .sort((a, b) => a.d.getTime() - b.d.getTime())
      .slice(0, 6)
  }, [events])

  const weekEvents = useMemo(() => {
    const from = new Date()
    from.setHours(0, 0, 0, 0)
    const to = new Date()
    to.setDate(to.getDate() + 7)
    to.setHours(23, 59, 59, 999)

    return events
      .filter((e) => e.starts_at)
      .map((e) => ({ ...e, d: toDate(e.starts_at!) }))
      .filter((e) => !isNaN(e.d.getTime()) && e.d >= from && e.d <= to)
      .sort((a, b) => a.d.getTime() - b.d.getTime())
      .slice(0, 6)
  }, [events])

  const scopedEvents = eventsScope === "today" ? todayEvents : weekEvents

  return (
    <Card
      className={cn(
        "group glass-noise refetch-shimmer dash-border-shimmer transition-all duration-base ease-back-out p-6 md:p-7",
        "motion-reduce:hover:transform-none",
        "dash-panel-events",
        className
      )}
      padding="none"
      aria-busy={loadingEvents}
      data-refetching={dashboardEventsQuery.isFetching && !dashboardEventsQuery.isLoading}
      style={style}
      {...props}
    >
      <div className="relative z-base space-y-5">
        <div className="relative z-base flex items-center justify-between gap-3">
          <h2
            className="font-extrabold text-text-primary"
            style={{ fontSize: "clamp(1.35rem, 2.5vw, 1.75rem)" }}
          >
            {t("dashboard:events.heading")}
          </h2>
          <Button
            as={Link}
            to="/events"
            size="sm"
            variant="outline"
            className="btn-dash whitespace-nowrap px-5 transition-transform duration-base hover:-translate-y-0.5"
            aria-label={t("dashboard:aria.viewAllEvents")}
            onPointerDown={prefetchEventsList}
            onKeyDown={(event) => {
              prepareOnKey(event, prefetchEventsList)
            }}
          >
            {t("dashboard:viewAll")}
          </Button>
        </div>

        {/* Scope toggle — segment control, inline-flex so it doesn't stretch */}
        <div
          className="mb-4 inline-flex items-center gap-1 rounded-lg p-1"
          style={{ background: "var(--dash-btn-bg)" }}
        >
          {(["today", "week"] as const).map((scope) => (
            <button
              key={scope}
              type="button"
              className={cn(
                "rounded-md px-4 py-1.5 text-sm font-semibold transition-all duration-base focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1",
                eventsScope === scope
                  ? "bg-brand text-[var(--sched-on-accent,#fff)] shadow-sm"
                  : "text-text-secondary hover:text-text-primary"
              )}
              onClick={() => setEventsScope(scope)}
              aria-pressed={eventsScope === scope}
            >
              {t(`dashboard:scope.${scope}`)}
            </button>
          ))}
        </div>

        {loadingEvents && (
          <div className="space-y-3" role="presentation">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="flex flex-col gap-2 rounded-xl bg-(--bg-matte-list) px-4 py-3 opacity-medium"
              >
                <Skeleton width="60%" height={20} />
                <div className="flex items-center gap-2">
                  <Skeleton width={120} height={16} />
                  <Skeleton width={80} height={16} />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loadingEvents && scopedEvents.length === 0 && (
          <p className="text-sm text-(--text-secondary)">{t("dashboard:events.empty")}</p>
        )}

        {!loadingEvents && scopedEvents.length > 0 && (
          <ul
            className="space-y-2.5"
            aria-label={
              eventsScope === "today"
                ? t("dashboard:aria.eventsToday")
                : t("dashboard:aria.eventsWeek")
            }
          >
            <AnimatePresence mode="popLayout" initial={false}>
              {scopedEvents.map((e, idx) => {
                return (
                  <m.li
                    key={`${eventsScope}-${e.id}`}
                    initial={prefersReduced ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={prefersReduced ? { opacity: 0 } : { opacity: 0, y: -4 }}
                    transition={
                      prefersReduced ? { duration: 0 } : { duration: 0.2, delay: idx * 0.04 }
                    }
                    className="dash-list-item px-0 py-0"
                  >
                    <button
                      type="button"
                      className={cn(
                        "group list-item-blue list-item-blue-hover",
                        "flex items-center gap-4 sm:gap-5",
                        "active:scale-(--scale-active)"
                      )}
                      onClick={() => navigate({ to: "/events/$id", params: { id: String(e.id) } })}
                      aria-label={t("dashboard:aria.eventItem", { title: e.title })}
                      style={{ "--stagger-i": idx } as React.CSSProperties}
                    >
                      <DateBullet date={e.starts_at!} locale={language} size="compact" />
                      <span className="flex min-w-0 flex-1 flex-col gap-1 text-left">
                        <span className="text-base font-semibold leading-tight text-text-primary line-clamp-2">
                          {e.title}
                        </span>
                        <span className="flex flex-wrap items-center gap-2">
                          {!isNaN(e.d.getTime()) && (
                            <span className="font-mono text-sm font-medium text-brand">
                              {formatDate(e.d, {
                                hour: "2-digit",
                                minute: "2-digit",
                                hour12: false,
                              })}
                            </span>
                          )}
                          {!!e.location && (
                            <Badge
                              size="sm"
                              variant="outline"
                              className="max-w-32 truncate text-[0.625rem]"
                              label={e.location}
                            />
                          )}
                        </span>
                      </span>
                      <span
                        aria-hidden="true"
                        className="ml-auto inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-(--border-matte) bg-(--bg-matte-list) text-brand opacity-0 transition-all duration-base group-hover:opacity-100 group-hover:bg-brand/(--opacity-faint) group-hover:border-brand/(--opacity-soft)"
                      >
                        <Sparkles aria-hidden="true" className="h-3.5 w-3.5" />
                      </span>
                    </button>
                  </m.li>
                )
              })}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </Card>
  )
})

export default EventsCard
