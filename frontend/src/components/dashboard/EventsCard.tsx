import { memo, useMemo, useState, useCallback, type CSSProperties, type KeyboardEvent } from "react"
import { motion } from "framer-motion"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Sparkles } from "lucide-react"

import { Badge, Button, Card, Skeleton } from "@/components/ui"
import { cn } from "@/utils/cn"
import { useDashboardEvents, prefetchDashboardEvents } from "@/hooks/useDashboardEvents"
import { prefetchEventsListQuery, EVENTS_PAGE_SIZE } from "@/api/hooks/events"
import { useLanguage } from "@/contexts/LanguageContext"
import { useQueryClient } from "@tanstack/react-query"
import type { Event } from "@/types/Event"
import { formatDate, toDate } from "@/utils/date"

interface EventsCardProps {
  className?: string
  style?: CSSProperties
  "data-fade"?: string
  "data-pop"?: string
}

// TD-23-02 (audit 2026-03-25 Wave 23): Wrap in React.memo to prevent re-render
// when parent Dashboard state changes (e.g. schedule tab switch, news reload).
export const EventsCard = memo(function EventsCard({ className, style, ...props }: EventsCardProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const navigate = useNavigate()
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const [eventsScope, setEventsScope] = useState<"today" | "week">("today")

  const dashboardEventsQuery = useDashboardEvents()
  const events: Event[] = useMemo(
    () => dashboardEventsQuery.data ?? [],
    [dashboardEventsQuery.data]
  )
  const loadingEvents = dashboardEventsQuery.isLoading && events.length === 0

  const warmEventsPage = () => import("../../pages/Events").catch(() => {})

  const prefetchEventsList = () => {
    warmEventsPage()
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

  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-sm border border-border-subtle bg-(--bg-surface-hover)/(--opacity-subtle) px-4 py-3 text-left transition-all duration-base ease-out hover:bg-(--bg-surface-hover)/(--opacity-dim) hover:border-border-strong hover:-translate-y-0.5 hover:shadow-premium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/(--opacity-medium)"

  return (
    <Card
      className={cn(
        "group bg-glass backdrop-blur-3xl transition-all duration-base ease-back-out",
        "hover:-translate-y-1 hover:scale-(--scale-hover-subtle) hover:shadow-glass motion-reduce:hover:transform-none motion-reduce:hover:shadow-none",
        "dash-panel-events border-glass-border",
        className
      )}
      padding="lg"
      aria-busy={loadingEvents}
      style={style}
      {...props}
    >
      <div className="relative z-base space-y-5">
        <div className="relative z-base flex items-center justify-between gap-3">
          <h2 className="text-fluid-h2 font-extrabold text-text-primary">
            {t("dashboard:events.heading")}
          </h2>
          <Button
            as={Link}
            to="/events"
            size="sm"
            variant="outline"
            className="whitespace-nowrap px-5 transition-transform duration-base hover:-translate-y-0.5"
            aria-label={t("dashboard:aria.viewAllEvents")}
            onPointerDown={prefetchEventsList}
            onKeyDown={(event) => {
              prepareOnKey(event, prefetchEventsList)
            }}
          >
            {t("dashboard:viewAll")}
          </Button>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={eventsScope === "today" ? "solid" : "outline"}
            className="whitespace-nowrap transition-transform duration-base hover:-translate-y-0.5"
            onClick={() => setEventsScope("today")}
            aria-pressed={eventsScope === "today"}
          >
            {t("dashboard:scope.today")}
          </Button>
          <Button
            size="sm"
            variant={eventsScope === "week" ? "solid" : "outline"}
            className="whitespace-nowrap transition-transform duration-base hover:-translate-y-0.5"
            onClick={() => setEventsScope("week")}
            aria-pressed={eventsScope === "week"}
          >
            {t("dashboard:scope.week")}
          </Button>
        </div>

        {loadingEvents && (
          <div className="space-y-4" role="presentation">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="flex flex-col gap-2 rounded-sm border border-border-subtle bg-(--bg-surface)/(--opacity-dim) px-4 py-3 opacity-medium"
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
            className="space-y-3"
            aria-label={
              eventsScope === "today"
                ? t("dashboard:aria.eventsToday")
                : t("dashboard:aria.eventsWeek")
            }
          >
            {scopedEvents.map((e) => {
              // e.d is now a dayjs object from the useMemo above
              return (
                <li key={e.id} className="dash-list-item px-0 py-0">
                  <button
                    type="button"
                    className={cn(
                      listActionBase,
                      "flex min-h-18 flex-col justify-center gap-2 border-0 bg-transparent px-4 py-3 hover:bg-white/(--opacity-faint) active:scale-(--scale-active) sm:gap-3"
                    )}
                    onClick={() => navigate(`/events/${e.id}`)}
                    aria-label={t("dashboard:aria.eventItem", { title: e.title })}
                  >
                    <span className="flex w-full items-start justify-between gap-3">
                      <span className="text-base font-semibold leading-tight text-text-primary line-clamp-2">
                        {e.title}
                      </span>
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-glass-border bg-(--bg-surface)/(--opacity-dim) text-brand transition-all duration-base group-hover:bg-brand/(--opacity-subtle)">
                        <Sparkles aria-hidden="true" className="h-3.5 w-3.5" />
                      </span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2 text-sm text-(--text-secondary)">
                      <Badge
                        size="sm"
                        className="border-brand/(--opacity-dim) bg-brand/(--opacity-faint) font-mono text-xs font-medium text-brand dark:bg-brand/(--opacity-subtle)"
                        label={
                          !isNaN(e.d.getTime())
                            ? formatDate(e.d, {
                                day: "2-digit",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                                hour12: false,
                              })
                            : ""
                        }
                      />
                      {!!e.location && (
                        <Badge
                          size="sm"
                          variant="outline"
                          className="max-w-32 truncate"
                          label={e.location}
                        />
                      )}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
      <motion.span
        aria-hidden="true"
        initial={{ opacity: 0 }}
        whileHover={{ opacity: "var(--opacity-hover)" }}
        animate={{
          scale: [1, 1.12, 1],
          rotate: [0, 5, 0],
        }}
        transition={{
          duration: 5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="pointer-events-none absolute inset-0 z-hide mix-blend-soft-light transition-opacity duration-slow"
        style={{
          background:
            "radial-gradient(circle at top left, var(--dash-card-events-radial), transparent 70%)",
        }}
      />
      <motion.span
        aria-hidden="true"
        initial={{ opacity: "var(--opacity-soft)" }}
        whileHover={{ opacity: "var(--opacity-strong)" }}
        animate={{
          scale: [1, 1.2, 1],
          x: [0, -10, 0],
          y: [0, 10, 0],
        }}
        transition={{
          duration: 7,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="pointer-events-none absolute inset-0 z-hide bg-(--grad-events-flare) mix-blend-soft-light transition-opacity duration-slow"
      />
    </Card>
  )
})
