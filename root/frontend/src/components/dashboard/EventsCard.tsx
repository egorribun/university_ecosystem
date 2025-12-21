import { useMemo, useState, type CSSProperties, type KeyboardEvent } from "react"
import { motion } from "framer-motion"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded"

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

  const warmEventsPage = () => import("../../pages/Events").catch(() => { })

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

  // Styles
  const panelBase =
    "group relative isolate overflow-hidden rounded-[2.4rem] border !border-[color:var(--dash-panel-border)] !bg-[color:var(--dash-panel-bg-muted)] text-page-foreground !shadow-[var(--dash-panel-shadow-soft)] transition-[transform,box-shadow] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)]"
  const panelHover =
    "hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] hover:shadow-[var(--dash-panel-hover-shadow)] motion-reduce:hover:transform-none motion-reduce:hover:shadow-[var(--dash-panel-shadow)]"
  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-ue-lg border border-[color:var(--dash-panel-item-divider)] bg-[color:var(--dash-panel-item-bg)] px-4 py-3 text-left transition-[background-color,transform,box-shadow,border-color] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)] sm:px-5 sm:py-4 group-even/list:bg-[color:var(--dash-panel-item-bg-alt)] hover:border-[color:var(--dash-panel-item-ring)] hover:bg-[color:var(--dash-panel-item-hover)] hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] focus-visible:border-[color:var(--dash-panel-item-ring)] focus-visible:outline-none focus-visible:shadow-focus motion-reduce:hover:transform-none motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:border before:border-[color:var(--dash-panel-item-ring)] before:opacity-0 before:scale-[0.96] before:transition-[transform,opacity,border-color] before:duration-[var(--dash-hover-duration)] before:ease-[var(--dash-hover-ease)] before:content-[''] hover:before:opacity-100 hover:before:scale-100"

  return (
    <Card
      className={cn(panelBase, panelHover, "dash-panel-events", className)}
      padding="lg"
      aria-busy={loadingEvents}
      style={style}
      {...props}
    >
      <div className="relative z-[1] space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-page-foreground">
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
            className="whitespace-nowrap transition-transform duration-300 hover:-translate-y-[1px]"
            onClick={() => setEventsScope("today")}
            aria-pressed={eventsScope === "today"}
          >
            {t("dashboard:scope.today")}
          </Button>
          <Button
            size="sm"
            variant={eventsScope === "week" ? "solid" : "outline"}
            className="whitespace-nowrap transition-transform duration-300 hover:-translate-y-[1px]"
            onClick={() => setEventsScope("week")}
            aria-pressed={eventsScope === "week"}
          >
            {t("dashboard:scope.week")}
          </Button>
        </div>

        {loadingEvents && (
          <div className="space-y-4" role="presentation">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex flex-col gap-2 rounded-ue-lg border border-[color:var(--dash-panel-item-divider)] bg-[color:var(--dash-panel-item-bg)] px-4 py-3 opacity-60">
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
          <p className="text-sm text-secondary">{t("dashboard:events.empty")}</p>
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
                <li key={e.id} className="dash-list-item">
                  <button
                    type="button"
                    className={cn(
                      listActionBase,
                      "flex flex-col items-start gap-3 text-left sm:gap-3"
                    )}
                    onClick={() => navigate(`/events/${e.id}`)}
                    aria-label={t("dashboard:aria.eventItem", { title: e.title })}
                  >
                    <span className="flex items-center gap-3">
                      <span className="text-base font-semibold text-page-foreground">
                        {e.title}
                      </span>
                      <span className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-full border border-[color:var(--dash-icon-halo-border)] bg-[color:var(--dash-icon-halo-bg)] text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-[color:var(--dash-icon-halo-text)] transition-colors duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)] group-hover:border-[color:var(--dash-icon-halo-border-active)] group-hover:text-[color:var(--dash-icon-halo-text-active)]">
                        <AutoAwesomeRoundedIcon
                          aria-hidden="true"
                          fontSize="inherit"
                          className="h-3.5 w-3.5"
                        />
                      </span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2 text-sm text-secondary">
                      <Badge
                        size="sm"
                        className="chip-time"
                        label={
                          d
                            ? d.toLocaleString(locale, {
                              day: "2-digit",
                              month: "long",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                            : ""
                        }
                      />
                      {!!e.location && <Badge size="sm" variant="outline" label={e.location} />}
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
          ease: "easeInOut"
        }}
        className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_left,var(--dash-card-events-radial),transparent_70%)] mix-blend-soft-light transition-opacity duration-500"
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
          ease: "easeInOut"
        }}
        className="pointer-events-none absolute -top-16 left-1/4 z-0 h-40 w-40 rounded-full bg-[radial-gradient(circle,var(--dash-card-events-orb),transparent)] blur-3xl mix-blend-soft-light transition-opacity duration-700"
      />
    </Card>
  )
}
