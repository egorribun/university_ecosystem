import {
  useEffect,
  useMemo,
  useState,
  useCallback,
  type KeyboardEvent,
  type CSSProperties,
} from "react"
import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import DashboardStories from "@/components/DashboardStories"
import { useAuth } from "../contexts/AuthContext"
import { Link, useNavigate } from "react-router-dom"
import { Badge, Button, Card, ProgressBar, Skeleton, Tooltip } from "@/components/ui"
import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded"
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { useQueryClient } from "@tanstack/react-query"
import { useDashboardStories, prefetchDashboardStories } from "@/hooks/useDashboardStories"
import { useDashboardNews, prefetchDashboardNews } from "@/hooks/useDashboardNews"
import { useDashboardEvents, prefetchDashboardEvents } from "@/hooks/useDashboardEvents"
import { useDashboardSchedule } from "@/hooks/useDashboardSchedule"
import { EVENTS_PAGE_SIZE, prefetchEventsListQuery } from "@/api/hooks/events"
import type { StoryItem } from "@/types/Story"
import type { NewsItem } from "@/api/news"
import type { Event } from "@/types/Event"
import type { DashboardLesson } from "@/hooks/useDashboardSchedule"
import WeatherWidget from "@/components/WeatherWidget"

const pad = (n: number) => String(n).padStart(2, "0")
const fmtTime = (s?: string) =>
  !s ? "" : s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5)
const nowParity = () => {
  const onejan = new Date(new Date().getFullYear(), 0, 1)
  const week = Math.ceil(((+new Date() - +onejan) / 86400000 + onejan.getDay() + 1) / 7)
  return week % 2 === 0 ? "even" : "odd"
}
const parseMinutes = (s?: string) => {
  if (!s) return null
  const hhmm = s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5)
  const [hh, mm] = hhmm.split(":").map(Number)
  if (Number.isNaN(hh) || Number.isNaN(mm)) return null
  return hh * 60 + mm
}

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

function DateBullet({ date, locale }: { date?: string; locale: string }) {
  const { t } = useTranslation("common")
  const d = date ? new Date(date) : null
  const dd = d ? pad(d.getDate()) : "—"
  const mm = d ? pad(d.getMonth() + 1) : "--"
  const fallback = t("dateUnknown")
  const full = d
    ? d.toLocaleString(locale, {
        day: "2-digit",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : fallback
  return (
    <Tooltip content={full}>
      <span
        aria-label={t("ariaDatePublished", { date: full })}
        className={cn(
          "chip-time flex h-11 w-11 min-h-11 min-w-11 flex-col items-center justify-center rounded-full text-[color:var(--dash-chip-time-text)]",
          "shadow-[var(--dash-date-shadow)]"
        )}
      >
        <span className="text-[0.85rem] font-black leading-none tracking-tight">{dd}</span>
        <span className="text-[0.65rem] font-semibold leading-tight text-[color:color-mix(in_srgb,var(--dash-chip-time-text)_70%,white_30%)]">
          {mm}
        </span>
      </span>
    </Tooltip>
  )
}

const getCurrentMinute = () => {
  const d = new Date()
  d.setSeconds(0, 0)
  return d
}

function useClock(locale: string) {
  const [time, setTime] = useState(getCurrentMinute)
  useEffect(() => {
    const tick = () => setTime(getCurrentMinute())
    let intervalId: number | null = null
    const now = new Date()
    const msUntilNextMinute = (60 - now.getSeconds()) * 1000 - now.getMilliseconds()
    const timeoutId = window.setTimeout(() => {
      tick()
      intervalId = window.setInterval(tick, 60_000)
    }, msUntilNextMinute)
    return () => {
      window.clearTimeout(timeoutId)
      if (intervalId) {
        window.clearInterval(intervalId)
      }
    }
  }, [])
  const hh = pad(time.getHours())
  const mm = pad(time.getMinutes())
  const dateStr = time.toLocaleDateString(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
  })
  return { hh, mm, dateStr, time }
}

function getGreetingKey(hour: number): "morning" | "afternoon" | "evening" | "night" {
  if (hour >= 4 && hour < 12) return "morning"
  if (hour >= 12 && hour < 17) return "afternoon"
  if (hour >= 17 && hour <= 23) return "evening"
  return "night"
}

const startOfDay = (d: Date) => {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}
const endOfDay = (d: Date) => {
  const x = new Date(d)
  x.setHours(23, 59, 59, 999)
  return x
}
const parseLocalDate = (s?: string) => {
  if (!s) return null
  const norm = s.replace(" ", "T")
  const d = new Date(norm)
  if (!Number.isNaN(+d)) return d
  const [datePart, timePart = "00:00"] = s.split(/[T ]/)
  const [Y, M, D] = (datePart || "").split("-").map(Number)
  const [h, m] = (timePart || "").split(":").map(Number)
  return new Date(Y || 1970, (M || 1) - 1, D || 1, h || 0, m || 0)
}

export default function Dashboard() {
  const { user } = useAuth()
  const isNarrow = useMediaQuery("(max-width:1100px)")
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const navigate = useNavigate()
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const { t } = useTranslation(["dashboard", "common", "navigation"])
  const { hh, mm, dateStr, time } = useClock(locale)
  const weekDaysDisplay = useMemo(() => {
    const result = t("dashboard:weekDays.display", { returnObjects: true }) as unknown
    if (Array.isArray(result) && result.length === 7) {
      return result as string[]
    }
    return ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
  }, [t])
  const weekDaysRaw = useMemo(() => {
    const result = t("dashboard:weekDays.raw", { returnObjects: true }) as unknown
    if (Array.isArray(result) && result.length === 7) {
      return result as string[]
    }
    return weekDaysDisplay
  }, [t, weekDaysDisplay])
  const weekdayIndex = useMemo(() => {
    const map = new Map<string, number>()
    weekDaysDisplay.forEach((name, index) => {
      map.set(name.toLowerCase(), index)
    })
    weekDaysRaw.forEach((name, index) => {
      map.set(name.toLowerCase(), index)
    })
    return map
  }, [weekDaysDisplay, weekDaysRaw])
  const greetingKey = useMemo(() => getGreetingKey(time.getHours()), [time])
  const greeting = t(`dashboard:greeting.${greetingKey}`)

  const queryClient = useQueryClient()

  const dashboardStoriesQuery = useDashboardStories()
  const stories: StoryItem[] = dashboardStoriesQuery.data ?? []
  const loadingStories = dashboardStoriesQuery.isLoading && stories.length === 0

  const dashboardNewsQuery = useDashboardNews(language)
  const news: NewsItem[] = dashboardNewsQuery.data ?? []
  const loadingNews = dashboardNewsQuery.isLoading && news.length === 0

  const dashboardEventsQuery = useDashboardEvents()
  const events: Event[] = dashboardEventsQuery.data ?? []
  const loadingEvents = dashboardEventsQuery.isLoading && events.length === 0

  const shouldLoadSchedule = user?.role === "student" && Boolean(user?.group_id)
  const dashboardScheduleQuery = useDashboardSchedule(user?.role ?? null, user?.group_id ?? null)
  const schedule: DashboardLesson[] = dashboardScheduleQuery.data ?? []
  const loadingSched = shouldLoadSchedule ? dashboardScheduleQuery.isLoading && schedule.length === 0 : false

  const [eventsScope, setEventsScope] = useState<"today" | "week">("today")

  const parity = useMemo(nowParity, [])
  const todayIndex = time.getDay()

  const todayLessons = useMemo(() => {
    return schedule
      .filter((l) => {
        const normalized = (l.weekday ?? "").toLowerCase()
        const lessonIndex = weekdayIndex.get(normalized)
        return (l.parity === "both" || l.parity === parity) && lessonIndex === todayIndex
      })
      .sort((a, b) => fmtTime(a.start_time).localeCompare(fmtTime(b.start_time)))
  }, [schedule, parity, todayIndex, weekdayIndex])

  const minutesNow = useMemo(() => time.getHours() * 60 + time.getMinutes(), [time])
  const currentLesson = useMemo(() => {
    return (
      todayLessons.find((l) => {
        const s = parseMinutes(l.start_time) ?? -1
        const e = parseMinutes(l.end_time) ?? -1
        return minutesNow >= s && minutesNow < e
      }) || null
    )
  }, [todayLessons, minutesNow])
  const nextLesson = useMemo(() => {
    if (currentLesson) {
      const endM = parseMinutes(currentLesson.end_time) ?? 0
      return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > endM) || null
    }
    return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > minutesNow) || null
  }, [todayLessons, currentLesson, minutesNow])
  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const s = parseMinutes(currentLesson.start_time) ?? 0
    const e = parseMinutes(currentLesson.end_time) ?? 0
    const span = Math.max(1, e - s)
    const passed = Math.min(Math.max(0, minutesNow - s), span)
    return Math.round((passed / span) * 100)
  }, [currentLesson, minutesNow])

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

  const headerGradientClass = cn(
    "transition-[background] duration-700",
    isNarrow
      ? "bg-[linear-gradient(135deg,var(--dash-header-grad-start),var(--dash-header-grad-end))]"
      : "bg-[linear-gradient(125deg,var(--dash-header-grad-start),var(--dash-header-grad-end))]"
  )

  const heroSectionClass = cn(
    "relative flex min-h-screen w-full flex-col overflow-hidden",
    "px-4 pb-16 pt-10 text-page-foreground sm:px-8 md:px-12 lg:px-16",
    "bg-[linear-gradient(145deg,var(--hero-grad-start),var(--hero-grad-end))]"
  )

  const heroBackdropLayers = useMemo(() => {
    const layers = [
      "absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top,var(--dash-hero-radial-top),transparent_78%)] mix-blend-soft-light",
      "absolute inset-0 -z-20 bg-[radial-gradient(circle_at_bottom,var(--dash-hero-radial-bottom),transparent_78%)]",
    ]

    const orbSize = isNarrow ? "h-[28rem] w-[28rem]" : "h-[46rem] w-[46rem]"
    layers.push(
      `absolute -top-56 left-1/2 ${orbSize} -translate-x-1/2 rounded-full bg-[radial-gradient(circle,var(--dash-hero-orb),transparent)] blur-[210px]`
    )

    if (!isNarrow) {
      layers.push(
        prefersReducedMotion
          ? "absolute bottom-[-16rem] right-[10%] h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,var(--dash-hero-pulse),transparent)] opacity-70 blur-[180px]"
          : "absolute bottom-[-18rem] right-[8%] h-[34rem] w-[34rem] animate-[pulse_14s_ease-in-out_infinite] rounded-full bg-[radial-gradient(circle,var(--dash-hero-pulse),transparent)] blur-[210px]"
      )
    }

    if (!prefersReducedMotion && !isNarrow) {
      layers.push(
        "absolute -left-28 top-1/2 h-[30rem] w-[30rem] -translate-y-1/2 animate-[spin_26s_linear_infinite] rounded-full bg-[conic-gradient(from_120deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),var(--dash-hero-conic-tertiary),var(--dash-hero-conic-accent))] opacity-80 blur-[220px]"
      )
    } else if (!isNarrow) {
      layers.push(
        "absolute -left-24 top-1/2 h-[26rem] w-[26rem] -translate-y-1/2 rounded-full bg-[conic-gradient(from_140deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),transparent_85%)] opacity-60 blur-[200px]"
      )
    }

    return layers
  }, [isNarrow, prefersReducedMotion])

  const showHeaderMotion = !prefersReducedMotion && !isNarrow

  const panelBase =
    "group relative isolate overflow-hidden rounded-[2.4rem] border !border-[color:var(--dash-panel-border)] !bg-[color:var(--dash-panel-bg-muted)] text-page-foreground !shadow-[var(--dash-panel-shadow-soft)] transition-[transform,box-shadow] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)]"
  const panelHover =
    "hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] hover:shadow-[var(--dash-panel-hover-shadow)] motion-reduce:hover:transform-none motion-reduce:hover:shadow-[var(--dash-panel-shadow)]"
  const listActionBase =
    "group relative isolate w-full overflow-hidden rounded-ue-lg border border-[color:var(--dash-panel-item-divider)] bg-[color:var(--dash-panel-item-bg)] px-4 py-3 text-left transition-[background-color,transform,box-shadow,border-color] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)] sm:px-5 sm:py-4 group-even/list:bg-[color:var(--dash-panel-item-bg-alt)] hover:border-[color:var(--dash-panel-item-ring)] hover:bg-[color:var(--dash-panel-item-hover)] hover:-translate-y-[var(--dash-hover-lift)] hover:scale-[var(--dash-hover-scale)] focus-visible:border-[color:var(--dash-panel-item-ring)] focus-visible:outline-none focus-visible:shadow-focus motion-reduce:hover:transform-none motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:border before:border-[color:var(--dash-panel-item-ring)] before:opacity-0 before:scale-[0.96] before:transition-[transform,opacity,border-color] before:duration-[var(--dash-hover-duration)] before:ease-[var(--dash-hover-ease)] before:content-[''] hover:before:opacity-100 hover:before:scale-100"

  const warmNewsPage = () => import("../pages/News").catch(() => {})
  const warmEventsPage = () => import("../pages/Events").catch(() => {})
  const warmSchedulePage = () => import("../pages/Schedule").catch(() => {})

  const prefetchStories = useCallback(() => {
    void prefetchDashboardStories(queryClient)
  }, [queryClient])

  const prefetchNewsList = useCallback(() => {
    warmNewsPage()
    void prefetchDashboardNews(queryClient, language)
  }, [language, queryClient])

  const prefetchEventsList = useCallback(() => {
    warmEventsPage()
    void prefetchDashboardEvents(queryClient)
    void prefetchEventsListQuery(queryClient, {
      language,
      is_active: true,
      limit: EVENTS_PAGE_SIZE,
    })
  }, [language, queryClient])

  const handleStoryOpen = useCallback(() => {
    prefetchStories()
  }, [prefetchStories])

  const prepareOnKey = (event: KeyboardEvent, callback: () => void) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      callback()
    }
  }

  return (
    <Layout>
      <a href="#main" className="skip-link">
        {t("common:skipToMain")}
      </a>
      <PageFadeIn>
        <section id="main" className={heroSectionClass}>
          <div aria-hidden="true" className="pointer-events-none absolute inset-0">
            {heroBackdropLayers.map((layer, index) => (
              <div key={index} className={layer} />
            ))}
          </div>
          <div className="relative z-[1] space-y-6">
            <header
              data-fade="up"
              data-pop="true"
              style={fadeDelayStyle("40ms")}
              className={cn(
                panelBase,
                panelHover,
                "p-6 md:p-9 focus-within:shadow-focus focus-visible:outline-none focus-visible:shadow-focus",
                headerGradientClass
              )}
            >
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 dash-highlight-veil bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--dash-hero-highlight-soft)_65%,transparent),transparent_60%)] transition-opacity duration-700"
              />
              {showHeaderMotion ? (
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -inset-y-24 -left-1/2 w-[170%] skew-x-[-18deg] bg-gradient-to-r from-transparent via-white/55 to-transparent opacity-0 transition-all duration-[2200ms] ease-out group-hover:translate-x-[35%] group-hover:opacity-70"
                >
                  <span className="block h-full w-full animate-skeleton-wave bg-gradient-to-r from-transparent via-white/70 to-transparent" />
                </span>
              ) : (
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -inset-y-20 -left-1/2 w-[160%] skew-x-[-14deg] bg-gradient-to-r from-transparent via-white/35 to-transparent opacity-0 transition-opacity duration-700 ease-out group-hover:opacity-45"
                />
              )}
              <div className="pointer-events-none absolute -right-24 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,var(--dash-hero-highlight),transparent)] dash-highlight-veil blur-3xl" />
              {showHeaderMotion ? (
                <div className="pointer-events-none absolute left-[-20%] top-[-40%] h-56 w-56 animate-[spin_18s_linear_infinite] rounded-full bg-[conic-gradient(from_90deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),var(--dash-hero-conic-tertiary),var(--dash-hero-conic-accent))] opacity-60 blur-[120px]" />
              ) : (
                <div className="pointer-events-none absolute left-[-18%] top-[-42%] h-48 w-48 rounded-full bg-[conic-gradient(from_130deg_at_50%_50%,var(--dash-hero-conic-primary),var(--dash-hero-conic-secondary),transparent_85%)] opacity-50 blur-[110px]" />
              )}
              <div className="relative grid gap-6 lg:grid-cols-12 lg:items-center">
                <div className="space-y-3 text-nav-text lg:col-span-8">
                  <h1 className="font-display text-[clamp(1.5rem,2.4vw,2.6rem)] font-extrabold leading-tight">
                    {greeting}
                    {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                  </h1>
                  <div
                    className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-nav-text/90"
                    role="status"
                    aria-live="polite"
                  >
                    <Badge
                      size="sm"
                      className="chip-clock flex-shrink-0 font-mono text-base"
                      aria-label={t("common:ariaCurrentTime")}
                    >
                      <span className="flex items-baseline gap-1 font-mono text-lg leading-none">
                        <span>{hh}</span>
                        <span aria-hidden="true" className="inline-block animate-dash-colon-blink">
                          :
                        </span>
                        <span>{mm}</span>
                      </span>
                    </Badge>
                    <WeatherWidget className="flex-shrink-0" />
                    <span className="text-sm font-medium tracking-tight leading-tight">
                      {dateStr}
                    </span>
                  </div>
                </div>
                <div className="hidden justify-end md:flex lg:col-span-4">
                  <Button
                    variant="outline"
                    size="md"
                    className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
                    onClick={() => navigate("/profile")}
                    aria-label={t("navigation:aria.openProfile")}
                  >
                    {t("navigation:menu.profile")}
                  </Button>
                </div>
              </div>
            </header>

            <div data-fade="up" data-pop="true" style={fadeDelayStyle("100ms")}> 
              <DashboardStories 
                stories={stories} 
                loading={loadingStories} 
                onPrefetch={prefetchStories} 
                onStoryOpen={handleStoryOpen} 
              /> 
            </div> 
            <section className="mt-6 grid grid-cols-1 gap-4 md:mt-8 md:gap-6 lg:grid-cols-12">
              <Card
                data-fade="left"
                data-pop="true"
                style={fadeDelayStyle("140ms")}
                className={cn(panelBase, panelHover, "dash-panel-schedule", "lg:col-span-4")}
                padding="lg"
                aria-busy={loadingSched}
              >
                <div className="relative z-[1] space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-page-foreground">
                      {t("dashboard:todaySchedule")}
                    </h2>
                    <div className="flex items-center gap-2">
                      <Button
                        as={Link}
                        to="/schedule"
                        size="sm"
                        variant="outline"
                        className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
                        aria-label={t("dashboard:aria.openFullSchedule")}
                        onPointerDown={warmSchedulePage}
                        onKeyDown={(event) => prepareOnKey(event, warmSchedulePage)}
                      >
                        {t("dashboard:fullSchedule")}
                      </Button>
                    </div>
                  </div>
                  {currentLesson && (
                    <div>
                      <div className="mb-3 flex flex-wrap items-center gap-2">
                        <Badge size="sm" tone="primary" label={t("dashboard:now")} />
                        <span className="text-base font-semibold text-page-foreground">
                          {currentLesson.subject}
                        </span>
                        <Badge
                          size="sm"
                          className="chip-time"
                          label={`${fmtTime(currentLesson.start_time)}–${fmtTime(currentLesson.end_time)}`}
                        />
                      </div>
                      <ProgressBar
                        value={currentProgress}
                        className="h-2.5"
                        ariaLabel={t("common:ariaCurrentLessonProgress")}
                      />
                    </div>
                  )}
                  {!currentLesson && nextLesson && (
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          size="sm"
                          variant="outline"
                          tone="primary"
                          className="font-bold uppercase tracking-wide"
                          label={t("dashboard:next")}
                        />
                        <span className="text-base font-semibold text-page-foreground">
                          {nextLesson.subject}
                        </span>
                        <Badge
                          size="sm"
                          className="chip-time"
                          label={`${fmtTime(nextLesson.start_time)}–${fmtTime(nextLesson.end_time)}`}
                        />
                      </div>
                    </div>
                  )}
                  {loadingSched && (
                    <div className="space-y-3" role="presentation">
                      <Skeleton height={22} />
                      <Skeleton height={22} />
                      <Skeleton height={22} />
                    </div>
                  )}
                  {!loadingSched && todayLessons.length === 0 && (
                    <p className="text-sm text-secondary">{t("dashboard:noClasses")}</p>
                  )}
                  {!loadingSched && todayLessons.length > 0 && (
                    <ul className="space-y-3">
                      {todayLessons.map((l) => (
                        <li key={l.id} className="dash-list-item">
                          <div
                            className={cn(
                              listActionBase,
                              "flex flex-col gap-2 text-left sm:gap-2.5",
                              "cursor-default"
                            )}
                          >
                            <div className="flex flex-wrap items-center gap-2 text-sm">
                              <Badge
                                size="sm"
                                className="chip-time"
                                label={`${fmtTime(l.start_time)}–${fmtTime(l.end_time)}`}
                              />
                              <span className="text-base font-semibold text-page-foreground">
                                {l.subject}
                              </span>
                              <Badge
                                size="sm"
                                className="chip-type"
                                variant="outline"
                                label={l.lesson_type}
                              />
                            </div>
                            <p className="text-sm leading-relaxed text-secondary">
                              {t("dashboard:lessonMeta", { teacher: l.teacher, room: l.room })}
                            </p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top,var(--dash-card-schedule-radial),transparent_72%)] opacity-0 mix-blend-soft-light transition-opacity duration-500 group-hover:opacity-80"
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -top-24 right-10 z-0 h-36 w-36 rounded-full bg-[radial-gradient(circle,var(--dash-card-schedule-orb),transparent)] opacity-30 blur-3xl mix-blend-soft-light transition duration-700 group-hover:opacity-70"
                />
              </Card>

              <Card
                data-fade="up"
                data-pop="true"
                style={fadeDelayStyle("200ms")}
                className={cn(panelBase, panelHover, "dash-panel-news", "lg:col-span-4")}
                padding="lg"
                aria-busy={loadingNews}
              >
                <div className="relative z-[1] space-y-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-page-foreground">
                      {t("dashboard:news.heading")}
                    </h2>
                    <Button
                      as={Link}
                      to="/news"
                      size="sm"
                      variant="outline"
                      className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
                      aria-label={t("dashboard:aria.viewAllNews")}
                      onPointerDown={prefetchNewsList}
                      onKeyDown={(event) => {
                        prepareOnKey(event, prefetchNewsList)
                      }}
                    >
                      {t("dashboard:viewAll")}
                    </Button>
                  </div>

                  {loadingNews && (
                    <div className="space-y-4" role="presentation">
                      <div className="flex items-center gap-3">
                        <Skeleton width={44} height={44} rounded="9999px" />
                        <div className="flex-1 space-y-2">
                          <Skeleton height={22} />
                          <Skeleton height={18} width="60%" />
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Skeleton width={44} height={44} rounded="9999px" />
                        <div className="flex-1 space-y-2">
                          <Skeleton height={22} width="80%" />
                          <Skeleton height={18} width="50%" />
                        </div>
                      </div>
                    </div>
                  )}
                  {!loadingNews && news.length === 0 && (
                    <p className="text-sm text-secondary">{t("dashboard:news.empty")}</p>
                  )}
                  {!loadingNews && news.length > 0 && (
                    <ul className="space-y-3" aria-label={t("dashboard:aria.newsList")}>
                      {news.map((n) => (
                        <li key={n.id} className="dash-list-item">
                          <button
                            type="button"
                            className={cn(
                              listActionBase,
                              "flex items-start gap-4 text-left sm:gap-5"
                            )}
                            onClick={() => navigate(`/news/${n.id}`)}
                            title={n.title}
                            aria-label={t("dashboard:aria.newsItem", { title: n.title })}
                          >
                            <DateBullet date={n.created_at} locale={locale} />
                            <div className="flex flex-col gap-1">
                              <span className="text-[clamp(.98rem,.9rem+.4vw,1.06rem)] font-bold leading-snug text-page-foreground">
                                {n.title}
                              </span>
                              <span className="text-sm text-secondary">
                                {(n.content || "").slice(0, 110)}
                                {(n.content || "").length > 110 ? "…" : ""}
                              </span>
                            </div>
                            <span
                              aria-hidden="true"
                              className="ml-auto inline-flex h-9 w-9 flex-none items-center justify-center rounded-full border border-[color:var(--dash-arrow-pill-border)] bg-[color:var(--dash-arrow-pill-bg)] text-base text-[color:var(--dash-arrow-pill-text)] opacity-0 transition-[transform,opacity,background-color,border-color] duration-[var(--dash-hover-duration)] ease-[var(--dash-hover-ease)] group-hover:-translate-y-[calc(var(--dash-hover-lift)/2)] group-hover:opacity-100 group-hover:border-[color:var(--dash-arrow-pill-border-active)] group-hover:bg-[color:var(--dash-arrow-pill-bg-active)] group-hover:text-[color:var(--dash-arrow-pill-text-active)]"
                            >
                              <ArrowForwardRoundedIcon
                                aria-hidden="true"
                                fontSize="inherit"
                                className="h-4 w-4"
                              />
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_right,var(--dash-card-news-radial),transparent_68%)] opacity-0 mix-blend-soft-light transition-opacity duration-500 group-hover:opacity-80"
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -bottom-20 left-1/3 z-0 h-44 w-44 rounded-full bg-[radial-gradient(circle,var(--dash-card-news-orb),transparent)] opacity-30 blur-3xl mix-blend-soft-light transition duration-700 group-hover:opacity-70"
                />
              </Card>

              <Card
                data-fade="right"
                data-pop="true"
                style={fadeDelayStyle("260ms")}
                className={cn(panelBase, panelHover, "dash-panel-events", "lg:col-span-4")}
                padding="lg"
                aria-busy={loadingEvents}
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
                    <div className="space-y-3" role="presentation">
                      <Skeleton height={24} />
                      <Skeleton height={24} width="80%" />
                      <Skeleton height={24} width="70%" />
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
                                {!!e.location && (
                                  <Badge size="sm" variant="outline" label={e.location} />
                                )}
                              </span>
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_left,var(--dash-card-events-radial),transparent_70%)] opacity-0 mix-blend-soft-light transition-opacity duration-500 group-hover:opacity-80"
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -top-16 left-1/4 z-0 h-40 w-40 rounded-full bg-[radial-gradient(circle,var(--dash-card-events-orb),transparent)] opacity-30 blur-3xl mix-blend-soft-light transition duration-700 group-hover:opacity-65"
                />
              </Card>
            </section>
          </div>
        </section>
      </PageFadeIn>
    </Layout>
  )
}
