import { useMemo, useState, type CSSProperties, type KeyboardEvent } from "react"
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
import { startOfDay, endOfDay, parseLocalDate } from "@/utils/dateUtils"

interface EventsCardProps {
  locale: string
  className?: string
  style?: CSSProperties
  "data-fade"?: string
  "data-pop"?: string
}

export function EventsCard({ locale, className, style, ...props }: EventsCardProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const navigate = useNavigate()
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const [eventsScope, setEventsScope] = useState<"today" | "week">("today")

  const dashboardEventsQuery = useDashboardEvents()
  const events: Event[] = dashboardEventsQuery.data ?? []
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

  const prepareOnKey = (event: KeyboardEvent, callback: () => void) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      callback()
    }
  }

  const todayEvents = useMemo(() => {
    const now = new Date()
    const from = startOfDay(now)
    const to = endOfDay(now)
    return events
      .filter((e) => e.starts_at)
      .map((e) => ({ ...e, d: parseLocalDate(String(e.starts_at))! }))
      .filter((e) => e.d && e.d >= from && e.d <= to)
      .sort((a, b) => +a.d - +b.d)
      .slice(0, 6)
  }, [events])

  const weekEvents = useMemo(() => {
    const now = new Date()
    const from = startOfDay(now)
    const to = endOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7))
    return events
      .filter((e) => e.starts_at)
      .map((e) => ({ ...e, d: parseLocalDate(String(e.starts_at))! }))
      .filter((e) => e.d && e.d >= from && e.d <= to)
      .sort((a, b) => +a.d - +b.d)
      .slice(0, 6)
  }, [events])

  const scopedEvents = eventsScope === "today" ? todayEvents : weekEvents

  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-xl border border-border-subtle bg-(--bg-surface-hover)/10 px-4 py-3 text-left transition-all duration-300 ease-out hover:bg-(--bg-surface-hover)/20 hover:border-border-strong hover:-translate-y-0.5 hover:shadow-premium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"

  return (
    <Card
      className={cn(
        "group bg-glass backdrop-blur-3xl transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
        "hover:-translate-y-1 hover:scale-[1.01] hover:shadow-glass motion-reduce:hover:transform-none motion-reduce:hover:shadow-none",
        "dash-panel-events border-glass-border",
        className
      )}
      padding="lg"
      aria-busy={loadingEvents}
      style={style}
      {...props}
    >
      <div className="relative z-(--z-base) space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[clamp(1.1rem,2vw,1.5rem)] font-extrabold text-(--text-primary)">
            {t("dashboard:events.heading")}
          </h2>
          <Button
            as={Link}
            to="/events"
            size="sm"
            variant="outline"
            className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
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
            className="whitespace-nowrap transition-transform duration-300 hover:-translate-y-px"
            onClick={() => setEventsScope("today")}
            aria-pressed={eventsScope === "today"}
          >
            {t("dashboard:scope.today")}
          </Button>
          <Button
            size="sm"
            variant={eventsScope === "week" ? "solid" : "outline"}
            className="whitespace-nowrap transition-transform duration-300 hover:-translate-y-px"
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
                className="flex flex-col gap-2 rounded-xl border border-border-subtle bg-(--bg-surface)/20 px-4 py-3 opacity-60"
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
              const d = parseLocalDate(String(e.starts_at))
              return (
                <li key={e.id} className="dash-list-item px-0 py-0">
                  <button
                    type="button"
                    className={cn(
                      listActionBase,
                      "flex min-h-(--space-18) flex-col justify-center gap-2 border-0 bg-transparent px-4 py-3 hover:bg-white/5 active:scale-[0.99] sm:gap-2.5"
                    )}
                    onClick={() => navigate(`/events/${e.id}`)}
                    aria-label={t("dashboard:aria.eventItem", { title: e.title })}
                  >
                    <span className="flex w-full items-start justify-between gap-3">
                      <span className="text-base font-semibold leading-tight text-(--text-primary) line-clamp-2">
                        {e.title}
                      </span>
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-glass-border bg-(--bg-surface)/20 text-brand transition-all duration-300 group-hover:bg-brand/10">
                        <Sparkles aria-hidden="true" className="h-3.5 w-3.5" />
                      </span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2 text-sm text-(--text-secondary)">
                      <Badge
                        size="sm"
                        className="border-brand/20 bg-brand/5 font-mono text-xs font-medium text-brand dark:bg-brand/10"
                        label={
                          d
                            ? d.toLocaleString(locale, {
                                day: "2-digit",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                              })
                            : ""
                        }
                      />
                      {!!e.location && (
                        <Badge
                          size="sm"
                          variant="outline"
                          className="max-w-[120px] truncate"
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
        whileHover={{ opacity: 0.8 }}
        animate={{
          scale: [1, 1.12, 1],
          rotate: [0, 5, 0],
        }}
        transition={{
          duration: 5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="pointer-events-none absolute inset-0 z-(--z-hide) bg-[radial-gradient(circle_at_top_left,var(--dash-card-events-radial),transparent_70%)] mix-blend-soft-light transition-opacity duration-500"
      />
      <motion.span
        aria-hidden="true"
        initial={{ opacity: 0.3 }}
        whileHover={{ opacity: 0.65 }}
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
        className="pointer-events-none absolute -top-16 left-1/4 z-(--z-hide) h-40 w-40 rounded-full bg-[radial-gradient(circle,var(--dash-card-events-orb),transparent)] blur-3xl mix-blend-soft-light transition-opacity duration-700"
      />
    </Card>
  )
}
