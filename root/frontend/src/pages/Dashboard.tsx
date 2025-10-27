import {
  useEffect,
  useMemo,
  useState,
  useCallback,
  useRef,
  type KeyboardEvent,
  type CSSProperties,
} from "react"
import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import DashboardStories from "@/components/DashboardStories"
import { useAuth } from "../contexts/AuthContext"
import axios from "../api/client"
import { Link, useNavigate } from "react-router-dom"
import { Badge, Button, Card, ProgressBar, Skeleton, Tooltip } from "@/components/ui"
import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import type { PaginatedResponse } from "@/types/Pagination"
import type { StoryItem } from "@/types/Story"
import { fetchStories as fetchStoriesRequest } from "@/api/stories"

type NewsItem = {
  id: number
  title: string
  content: string
  created_at?: string
  pinned?: boolean
}
type EventItem = {
  id: number
  title: string
  description?: string
  starts_at?: string
  location?: string
}
type Lesson = {
  id: number
  subject: string
  teacher: string
  room: string
  lesson_type: string
  weekday: string
  start_time: string
  end_time: string
  parity: "odd" | "even" | "both"
}

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
        className="flex h-11 w-11 min-h-11 min-w-11 flex-col items-center justify-center rounded-full border border-white/70 bg-[conic-gradient(at_50%_50%,rgba(255,255,255,0.95),rgba(148,163,184,0.35),rgba(59,130,246,0.82),rgba(255,255,255,0.95))] text-slate-900 shadow-[0_18px_40px_-22px_rgba(30,64,175,0.55)] backdrop-blur-md"
      >
        <span className="text-[0.85rem] font-black leading-none tracking-tight">{dd}</span>
        <span className="text-[0.65rem] font-semibold leading-tight text-slate-700">{mm}</span>
      </span>
    </Tooltip>
  )
}

function useClock(locale: string) {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const hh = pad(time.getHours())
  const mm = pad(time.getMinutes())
  const showColon = time.getSeconds() % 2 === 0
  const dateStr = time.toLocaleDateString(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
  })
  return { hh, mm, showColon, dateStr, time }
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

const CACHE_TTL = 120000
function getCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const { t, data } = JSON.parse(raw)
    if (Date.now() - t > CACHE_TTL) return null
    return data as T
  } catch {
    return null
  }
}
function setCache<T>(key: string, data: T) {
  try {
    localStorage.setItem(key, JSON.stringify({ t: Date.now(), data }))
  } catch {}
}

export default function Dashboard() {
  const { user } = useAuth()
  const isNarrow = useMediaQuery("(max-width:1100px)")
  const navigate = useNavigate()
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const { t } = useTranslation(["dashboard", "common", "navigation"])
  const { hh, mm, showColon, dateStr, time } = useClock(locale)
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

  const [loadingStories, setLoadingStories] = useState(true)
  const [loadingNews, setLoadingNews] = useState(true)
  const [loadingEvents, setLoadingEvents] = useState(true)
  const [loadingSched, setLoadingSched] = useState(true)

  const [stories, setStories] = useState<StoryItem[]>([])
  const [news, setNews] = useState<NewsItem[]>([])
  const [events, setEvents] = useState<EventItem[]>([])
  const [schedule, setSchedule] = useState<Lesson[]>([])

  const [eventsScope, setEventsScope] = useState<"today" | "week">("today")
  const storiesEtagRef = useRef<string | null>(null)
  const eventsEtagRef = useRef<string | null>(null)
  const storiesPrefetchedRef = useRef(false)

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

  const minutesNow = time.getHours() * 60 + time.getMinutes()
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

  const fetchStories = useCallback(async () => {
    try {
      const previousTag = storiesEtagRef.current
      const response = await fetchStoriesRequest(previousTag)
      const responseTag = response.headers?.etag
      storiesEtagRef.current = responseTag ?? null
      if (response.status === 304) {
        return
      }
      const arr = Array.isArray(response.data) ? response.data : []
      setStories(arr)
      setCache<StoryItem[]>("dash:stories", arr)
    } catch {
      const cached = getCache<StoryItem[]>("dash:stories")
      if (cached) {
        setStories(cached)
      } else {
        setStories([])
      }
      storiesEtagRef.current = null
    } finally {
      setLoadingStories(false)
    }
  }, [])

  const fetchNews = useCallback(async () => {
    try {
      const r = await axios.get("/news")
      const arr = Array.isArray(r.data) ? r.data : []
      const sorted = [...arr].sort(
        (a: any, b: any) => (b.pinned === true ? 1 : 0) - (a.pinned === true ? 1 : 0)
      )
      const sliced = sorted.slice(0, 4)
      setNews(sliced)
      setCache<NewsItem[]>("dash:news", sliced)
    } catch {
      const cached = getCache<NewsItem[]>("dash:news")
      if (cached) {
        setNews(cached)
      } else {
        setNews([])
      }
    } finally {
      setLoadingNews(false)
    }
  }, [])

  const fetchEvents = useCallback(async () => {
    try {
      const previousTag = eventsEtagRef.current
      const r = await axios.get<PaginatedResponse<EventItem>>("/events", {
        params: { is_active: true, limit: 50 },
        headers: previousTag ? { "If-None-Match": previousTag } : undefined,
        validateStatus: (status: number) => status >= 200 && status < 400,
      })
      const responseTag = r.headers?.etag
      if (responseTag) {
        eventsEtagRef.current = responseTag
      } else {
        eventsEtagRef.current = null
      }
      if (r.status === 304) {
        return
      }
      const arr = Array.isArray(r.data?.items) ? r.data.items : []
      const sorted = arr
        .filter((e) => e.starts_at)
        .sort((a, b) => String(a.starts_at).localeCompare(String(b.starts_at)))
      setEvents(sorted.slice(0, 30))
      setCache<EventItem[]>("dash:events", sorted.slice(0, 30))
    } catch {
      setEvents([])
      eventsEtagRef.current = null
    } finally {
      setLoadingEvents(false)
    }
  }, [])

  const fetchSchedule = useCallback(async () => {
    if (!user) return
    setLoadingSched(true)
    try {
      if (user.role === "student" && user.group_id) {
        const r = await axios.get(`/schedule/${user.group_id}`)
        setSchedule(Array.isArray(r.data) ? r.data : [])
      } else {
        setSchedule([])
      }
    } catch {
      setSchedule([])
    } finally {
      setLoadingSched(false)
    }
  }, [user])

  useEffect(() => {
    const cachedStories = getCache<StoryItem[]>("dash:stories")
    if (cachedStories) {
      setStories(cachedStories)
      setLoadingStories(false)
    }
    fetchStories()
    const cachedN = getCache<NewsItem[]>("dash:news")
    if (cachedN) {
      setNews(cachedN)
      setLoadingNews(false)
    }
    fetchNews()
    const cachedE = getCache<EventItem[]>("dash:events")
    if (cachedE) {
      setEvents(cachedE)
      setLoadingEvents(false)
    }
    fetchEvents()
  }, [fetchStories, fetchNews, fetchEvents])

  useEffect(() => {
    fetchSchedule()
  }, [fetchSchedule])

  const headerGradientClass = isNarrow
    ? "bg-[radial-gradient(circle_at_top,rgba(99,102,241,0.32),rgba(15,23,42,0.72))]"
    : "bg-[radial-gradient(circle_at_top_right,rgba(191,219,254,0.32),rgba(15,23,42,0.78))]"

  const glassPanelBase =
    "group relative isolate overflow-hidden rounded-[2.5rem] border border-white/15 bg-white/[0.08] backdrop-blur-[32px] shadow-[0_55px_140px_-80px_rgba(15,23,42,0.85)] transition-all duration-500"
  const glassPanelHover =
    "hover:-translate-y-[6px] hover:shadow-[0_70px_170px_-90px_rgba(59,130,246,0.65)] motion-reduce:hover:translate-y-0 motion-reduce:hover:shadow-[0_55px_140px_-80px_rgba(15,23,42,0.85)]"
  const glassSheen =
    "before:pointer-events-none before:absolute before:inset-px before:rounded-[inherit] before:bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.55),rgba(255,255,255,0.08))] before:opacity-80 before:transition-opacity before:duration-700 before:content-[''] group-hover:before:opacity-100"

  const warmNewsPage = () => import("../pages/News").catch(() => {})
  const warmEventsPage = () => import("../pages/Events").catch(() => {})
  const warmSchedulePage = () => import("../pages/Schedule").catch(() => {})
  const prefetchData = (type: "news" | "events" | "stories") => {
    if (type === "news")
      axios
        .get("/news")
        .then((r) => setCache("prefetch:news", r.data))
        .catch(() => {})
    if (type === "events")
      axios
        .get<PaginatedResponse<EventItem>>("/events", { params: { is_active: true, limit: 20 } })
        .then((r) => setCache("prefetch:events", Array.isArray(r.data?.items) ? r.data.items : []))
        .catch(() => {})
    if (type === "stories")
      axios
        .get<StoryItem[]>("/stories")
        .then((r) => setCache("prefetch:stories", Array.isArray(r.data) ? r.data : []))
        .catch(() => {})
  }

  const triggerStoriesPrefetch = () => {
    if (storiesPrefetchedRef.current) return
    storiesPrefetchedRef.current = true
    prefetchData("stories")
  }

  const handleStoryOpen = useCallback(() => {
    triggerStoriesPrefetch()
  }, [])

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
        <section
          id="main"
          className="relative mx-auto flex min-h-screen w-full max-w-[min(1800px,100%)] flex-col overflow-hidden rounded-[2rem] px-4 pb-16 pt-10 text-slate-100 shadow-[0_45px_120px_-60px_rgba(15,23,42,0.75)] sm:px-6 sm:rounded-[2.5rem] md:px-10 lg:px-16 lg:rounded-[3rem]"
        >
          <div aria-hidden="true" className="pointer-events-none absolute inset-0">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(15,23,42,0.75),rgba(15,23,42,0.55))]" />
            <div className="absolute -top-48 left-1/2 h-[38rem] w-[38rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(120,162,255,0.32),rgba(120,162,255,0))] blur-[160px]" />
            <div className="absolute bottom-[-10rem] right-[8%] h-[30rem] w-[30rem] rounded-full bg-[radial-gradient(circle,rgba(125,211,252,0.32),rgba(125,211,252,0))] blur-[160px]" />
            <div className="absolute -left-24 top-1/2 h-[28rem] w-[28rem] -translate-y-1/2 animate-[pulse_10s_ease-in-out_infinite] rounded-full bg-[radial-gradient(circle,rgba(244,114,182,0.28),rgba(244,114,182,0))] blur-[140px]" />
            <div className="absolute left-1/2 top-10 h-64 w-64 -translate-x-1/2 rounded-full bg-[conic-gradient(from_45deg_at_50%_50%,rgba(255,255,255,0.35),rgba(125,211,252,0.45),rgba(255,255,255,0.15),rgba(192,132,252,0.4),rgba(255,255,255,0.35))] opacity-50 blur-[180px]" />
          </div>
          <div className="relative z-[1] space-y-8">
            <header
              data-fade
              style={fadeDelayStyle("40ms")}
              className={cn(
                glassPanelBase,
                glassPanelHover,
                glassSheen,
                "p-6 md:p-9 focus-within:shadow-focus focus-visible:outline-none focus-visible:shadow-focus",
                headerGradientClass
              )}
            >
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.45),transparent_60%)] opacity-80 mix-blend-soft-light transition-opacity duration-700 group-hover:opacity-100"
              />
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -inset-y-24 -left-1/2 w-[170%] skew-x-[-18deg] bg-gradient-to-r from-transparent via-white/55 to-transparent opacity-0 transition-all duration-[2200ms] ease-out group-hover:translate-x-[35%] group-hover:opacity-70"
              >
                <span className="block h-full w-full animate-skeleton-wave bg-gradient-to-r from-transparent via-white/70 to-transparent" />
              </span>
              <div className="pointer-events-none absolute -right-24 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.45),rgba(14,165,233,0))] opacity-70 blur-3xl" />
              <div className="pointer-events-none absolute left-[-20%] top-[-40%] h-56 w-56 animate-[spin_18s_linear_infinite] rounded-full bg-[conic-gradient(from_90deg_at_50%_50%,rgba(59,130,246,0.45),rgba(59,130,246,0.1),rgba(14,165,233,0.38),rgba(59,130,246,0.45))] opacity-60 blur-[120px]" />
              <div className="relative grid gap-6 lg:grid-cols-12 lg:items-center">
                <div className="space-y-3 text-nav-text lg:col-span-8">
                  <h1 className="font-display text-[clamp(1.5rem,2.4vw,2.6rem)] font-extrabold leading-tight">
                    {greeting}
                    {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                  </h1>
                  <div
                    className="flex flex-wrap items-center gap-3 text-sm text-nav-text/90"
                    role="status"
                    aria-live="polite"
                  >
                    <Badge
                      size="sm"
                      className="chip-clock font-mono text-base"
                      aria-label={t("common:ariaCurrentTime")}
                    >
                      <span className="flex items-baseline gap-1 font-mono text-lg leading-none">
                        <span>{hh}</span>
                        <span
                          aria-hidden="true"
                          className={cn(
                            "transition-opacity duration-300 ease-out",
                            showColon ? "opacity-100" : "opacity-0"
                          )}
                        >
                          :
                        </span>
                        <span>{mm}</span>
                      </span>
                    </Badge>
                    <span className="text-sm font-medium tracking-tight">{dateStr}</span>
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

            <div
              data-fade
              style={fadeDelayStyle("100ms")}
              className={cn(
                glassPanelBase,
                glassPanelHover,
                glassSheen,
                "p-2 md:p-3"
              )}
            >
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(191,219,254,0.28),transparent_65%)] opacity-80"
              />
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-10 top-0 h-2 bg-gradient-to-r from-transparent via-white/40 to-transparent opacity-60"
              />
              <div className="relative z-[1]">
                <DashboardStories
                  stories={stories}
                  loading={loadingStories}
                  onPrefetch={triggerStoriesPrefetch}
                  onStoryOpen={handleStoryOpen}
                />
              </div>
            </div>
            <section className="mt-6 grid grid-cols-1 gap-4 md:mt-8 md:gap-6 lg:grid-cols-12">
              <Card
                data-fade
                style={fadeDelayStyle("140ms")}
                className={cn(
                  glassPanelBase,
                  glassPanelHover,
                  glassSheen,
                  "lg:col-span-4"
                )}
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
                  <div className="my-4 h-px w-full bg-[color:var(--slate-10)]" aria-hidden="true" />
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
                        <li key={l.id} className="flex flex-col gap-1">
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
                          <p className="text-sm text-secondary">
                            {t("dashboard:lessonMeta", { teacher: l.teacher, room: l.room })}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.18),transparent_72%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100"
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -top-24 right-10 z-0 h-36 w-36 rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.45),transparent)] opacity-40 blur-3xl transition duration-700 group-hover:opacity-80"
                />
              </Card>

              <Card
                data-fade
                style={fadeDelayStyle("200ms")}
                className={cn(
                  glassPanelBase,
                  glassPanelHover,
                  glassSheen,
                  "lg:col-span-4"
                )}
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
                      onPointerDown={() => {
                        warmNewsPage()
                        prefetchData("news")
                      }}
                      onKeyDown={(event) => {
                        prepareOnKey(event, () => {
                          warmNewsPage()
                          prefetchData("news")
                        })
                      }}
                    >
                      {t("dashboard:viewAll")}
                    </Button>
                  </div>
                  <div className="my-4 h-px w-full bg-[color:var(--slate-10)]" aria-hidden="true" />
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
                    <ul
                      className="divide-y divide-[color:var(--slate-10)]"
                      aria-label={t("dashboard:aria.newsList")}
                    >
                      {news.map((n) => (
                        <li key={n.id} className="py-3 first:pt-0 last:pb-0">
                          <button
                            type="button"
                            className="group flex w-full items-center gap-3 rounded-ue-lg px-2 py-3 text-left transition-all duration-300 ease-out hover:-translate-y-[1px] hover:bg-white/5 focus-visible:outline-none focus-visible:shadow-focus"
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
                              className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-xs font-semibold uppercase tracking-[0.2em] text-white/70 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                            >
                              →
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.18),transparent_68%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100"
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -bottom-20 left-1/3 z-0 h-44 w-44 rounded-full bg-[radial-gradient(circle,rgba(129,140,248,0.45),transparent)] opacity-45 blur-3xl transition duration-700 group-hover:opacity-80"
                />
              </Card>

              <Card
                data-fade
                style={fadeDelayStyle("260ms")}
                className={cn(
                  glassPanelBase,
                  glassPanelHover,
                  glassSheen,
                  "lg:col-span-4"
                )}
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
                      onPointerDown={() => {
                        warmEventsPage()
                        prefetchData("events")
                      }}
                      onKeyDown={(event) => {
                        prepareOnKey(event, () => {
                          warmEventsPage()
                          prefetchData("events")
                        })
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
                  <div className="my-4 h-px w-full bg-[color:var(--slate-10)]" aria-hidden="true" />
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
                      className="divide-y divide-[color:var(--slate-10)]"
                      aria-label={
                        eventsScope === "today"
                          ? t("dashboard:aria.eventsToday")
                          : t("dashboard:aria.eventsWeek")
                      }
                    >
                      {scopedEvents.map((e) => {
                        const d = parseLocalDate(String(e.starts_at))
                        return (
                          <li key={e.id} className="py-3 first:pt-0 last:pb-0">
                            <button
                              type="button"
                              className="group flex w-full flex-col gap-2 rounded-ue-lg px-3 py-3 text-left transition-all duration-300 ease-out hover:-translate-y-[1px] hover:bg-white/5 focus-visible:outline-none focus-visible:shadow-focus"
                              onClick={() => navigate(`/events/${e.id}`)}
                              aria-label={t("dashboard:aria.eventItem", { title: e.title })}
                            >
                              <span className="flex items-center gap-3">
                                <span className="text-base font-semibold text-page-foreground">
                                  {e.title}
                                </span>
                                <span className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-full border border-white/20 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-white/70 transition-colors duration-300 group-hover:border-white/60 group-hover:text-white">
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
                  className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.16),transparent_70%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100"
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute -top-16 left-1/4 z-0 h-40 w-40 rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.5),transparent)] opacity-45 blur-3xl transition duration-700 group-hover:opacity-85"
                />
              </Card>
            </section>
          </div>
        </section>
      </PageFadeIn>
    </Layout>
  )
}
