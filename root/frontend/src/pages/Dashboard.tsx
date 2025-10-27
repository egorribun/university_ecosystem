import {
  useEffect,
  useMemo,
  useState,
  useCallback,
  useRef,
  type KeyboardEvent,
  type CSSProperties,
  type MediaQueryListEvent,
} from "react"
import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import DashboardStories from "@/components/DashboardStories"
import { useAuth } from "../contexts/AuthContext"
import axios from "../api/client"
import { Link, useNavigate } from "react-router-dom"
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
    <span
      className="flex h-11 w-11 flex-none select-none flex-col items-center justify-center rounded-full bg-[linear-gradient(120deg,#1d5fff,#65b2ff)] text-sm font-extrabold leading-none text-white"
      aria-label={t("ariaDatePublished", { date: full })}
      title={full}
      style={{ minWidth: 44, minHeight: 44 }}
    >
      <span className="text-sm leading-none">{dd}</span>
      <span className="text-[10px] leading-tight opacity-90">{mm}</span>
    </span>
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
  const [isNarrow, setIsNarrow] = useState(() => {
    if (typeof window === "undefined") return false
    return window.matchMedia("(max-width:1100px)").matches
  })
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

  useEffect(() => {
    if (typeof window === "undefined") return undefined
    const media = window.matchMedia("(max-width:1100px)")
    const handleChange = (event: MediaQueryListEvent | MediaQueryList) => {
      setIsNarrow(event.matches)
    }
    handleChange(media)
    if (typeof media.addEventListener === "function") {
      const listener = (event: MediaQueryListEvent) => handleChange(event)
      media.addEventListener("change", listener)
      return () => media.removeEventListener("change", listener)
    }
    if (typeof media.addListener === "function") {
      const legacyListener = (event: MediaQueryListEvent) => handleChange(event)
      media.addListener(legacyListener)
      return () => media.removeListener(legacyListener)
    }
    return undefined
  }, [])

  const headerGradient = isNarrow
    ? "linear-gradient(100deg,var(--hero-grad-start) 50%,var(--hero-grad-end) 100%)"
    : "linear-gradient(100deg,var(--hero-grad-start) 40%,var(--hero-grad-end) 100%)"
  const cardBaseClasses =
    "rounded-[2rem] bg-[var(--card-bg)] p-6 shadow-[0_16px_40px_rgba(0,0,0,0.22)] transition-all duration-300 ease-out will-change-transform hover:-translate-y-0.5 hover:shadow-[0_20px_48px_rgba(0,0,0,0.18)] md:p-8 md:shadow-[var(--shadow-1)]"
  const buttonClasses =
    "inline-flex items-center justify-center whitespace-nowrap rounded-2xl border border-transparent px-4 py-2 font-semibold tracking-wide text-[color:var(--page-text)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-transparent hover:bg-[linear-gradient(100deg,#1976d2_20%,#449aff_100%)] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb55] focus-visible:ring-offset-2 focus-visible:ring-offset-transparent active:translate-y-0"
  const pillButtonClasses =
    "inline-flex items-center justify-center whitespace-nowrap rounded-full border border-transparent px-4 py-1.5 text-sm font-semibold tracking-wide text-[color:var(--page-text)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:bg-[linear-gradient(100deg,#1976d2_20%,#449aff_100%)] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb55] focus-visible:ring-offset-2 focus-visible:ring-offset-transparent active:translate-y-0"
  const softBorderColor = "color-mix(in srgb, var(--page-text) 12%, transparent)"
  const mutedSurface = "color-mix(in srgb, var(--page-text) 8%, transparent)"
  const skeletonBase: CSSProperties = {
    background: "color-mix(in srgb, var(--page-text) 14%, transparent)",
  }

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
        <div
          id="main"
          className="mx-auto flex w-full max-w-[min(1800px,100%)] flex-col gap-6 px-4 py-4 sm:px-6 md:gap-8 md:px-10 md:py-6 lg:px-16"
        >
          <div
            data-fade
            style={
              {
                "--fade-delay": "40ms",
                background: headerGradient,
                borderColor: isNarrow ? softBorderColor : "transparent",
                borderWidth: 1,
                borderStyle: "solid",
              } as CSSProperties
            }
            className={`${cardBaseClasses} flex flex-col gap-5 md:flex-row md:items-center md:justify-between`}
          >
            <div className="space-y-3">
              <h1 className="text-[clamp(1.4rem,2.2vw,2.4rem)] font-extrabold leading-snug text-[color:var(--page-text)]">
                {greeting}
                {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
              </h1>
              <div
                className="flex flex-wrap items-center gap-3 text-[color:var(--secondary-text)]"
                role="status"
                aria-live="polite"
              >
                <span
                  className="chip-clock inline-flex items-baseline gap-2 rounded-full px-3 py-1 text-sm font-semibold tracking-wide"
                  aria-label={t("common:ariaCurrentTime")}
                >
                  <span
                    className="flex items-baseline gap-1"
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    <span>{hh}</span>
                    <span
                      aria-hidden="true"
                      className="transition-opacity duration-300"
                      style={{ opacity: showColon ? 1 : 0 }}
                    >
                      :
                    </span>
                    <span>{mm}</span>
                  </span>
                </span>
                <span className="text-base opacity-90">{dateStr}</span>
              </div>
            </div>
            <div className="hidden items-center gap-3 md:flex">
              <Link
                to="/profile"
                className={buttonClasses}
                style={{ borderColor: softBorderColor }}
                aria-label={t("navigation:aria.openProfile")}
              >
                {t("navigation:menu.profile")}
              </Link>
            </div>
          </div>

          <div data-fade style={{ "--fade-delay": "90ms" } as CSSProperties}>
            <DashboardStories
              stories={stories}
              loading={loadingStories}
              onPrefetch={triggerStoriesPrefetch}
              onStoryOpen={handleStoryOpen}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:gap-8">
            <section
              data-fade
              style={{ "--fade-delay": "140ms" } as CSSProperties}
              className={`${cardBaseClasses} lg:col-span-4`}
              aria-busy={loadingSched}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-[color:var(--page-text)]">
                  {t("dashboard:todaySchedule")}
                </h2>
                <Link
                  to="/schedule"
                  className={buttonClasses}
                  style={{ borderColor: softBorderColor }}
                  aria-label={t("dashboard:aria.openFullSchedule")}
                  onPointerDown={warmSchedulePage}
                  onKeyDown={(event) => prepareOnKey(event, warmSchedulePage)}
                >
                  {t("dashboard:fullSchedule")}
                </Link>
              </div>

              {currentLesson && (
                <div className="mt-5">
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                    <span
                      className="inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide"
                      style={{ background: mutedSurface, borderColor: softBorderColor }}
                    >
                      {t("dashboard:now")}
                    </span>
                    <span className="text-base font-semibold text-[color:var(--page-text)]">
                      {currentLesson.subject}
                    </span>
                    <span className="chip-time inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold">
                      {`${fmtTime(currentLesson.start_time)}–${fmtTime(currentLesson.end_time)}`}
                    </span>
                  </div>
                  <div
                    role="progressbar"
                    aria-label={t("common:ariaCurrentLessonProgress")}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={currentProgress}
                    className="relative h-2 w-full overflow-hidden rounded-full bg-[var(--progress-track)]"
                  >
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-[var(--progress-bar)] transition-[width] duration-500 ease-out"
                      style={{ width: `${currentProgress}%` }}
                    />
                  </div>
                </div>
              )}

              {!currentLesson && nextLesson && (
                <div className="mt-5">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span
                      className="inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide"
                      style={{ background: mutedSurface, borderColor: softBorderColor }}
                    >
                      {t("dashboard:next")}
                    </span>
                    <span className="text-base font-semibold text-[color:var(--page-text)]">
                      {nextLesson.subject}
                    </span>
                    <span className="chip-time inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold">
                      {`${fmtTime(nextLesson.start_time)}–${fmtTime(nextLesson.end_time)}`}
                    </span>
                  </div>
                </div>
              )}

              <hr className="my-6 h-px border-none" style={{ background: mutedSurface }} />

              {loadingSched && (
                <div className="flex flex-col gap-3">
                  <div className="h-5 w-full animate-pulse rounded-lg" style={skeletonBase} />
                  <div className="h-5 w-11/12 animate-pulse rounded-lg" style={skeletonBase} />
                  <div className="h-5 w-10/12 animate-pulse rounded-lg" style={skeletonBase} />
                </div>
              )}

              {!loadingSched && todayLessons.length === 0 && (
                <p className="text-[color:var(--secondary-text)]">{t("dashboard:noClasses")}</p>
              )}

              {!loadingSched && todayLessons.length > 0 && (
                <ul className="flex flex-col gap-3">
                  {todayLessons.map((l) => (
                    <li key={l.id} className="flex flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="chip-time inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold">
                          {`${fmtTime(l.start_time)}–${fmtTime(l.end_time)}`}
                        </span>
                        <span className="text-base font-semibold text-[color:var(--page-text)]">
                          {l.subject}
                        </span>
                        <span className="chip-type inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide">
                          {l.lesson_type}
                        </span>
                      </div>
                      <span className="text-sm text-[color:var(--secondary-text)]">
                        {t("dashboard:lessonMeta", { teacher: l.teacher, room: l.room })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section
              data-fade
              style={{ "--fade-delay": "200ms" } as CSSProperties}
              className={`${cardBaseClasses} lg:col-span-4`}
              aria-busy={loadingNews}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-[color:var(--page-text)]">
                  {t("dashboard:news.heading")}
                </h2>
                <Link
                  to="/news"
                  className={buttonClasses}
                  style={{ borderColor: softBorderColor }}
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
                </Link>
              </div>

              <hr className="my-6 h-px border-none" style={{ background: mutedSurface }} />

              {loadingNews && (
                <div className="flex flex-col gap-4">
                  {[0, 1].map((key) => (
                    <div key={key} className="flex items-center gap-3">
                      <div className="h-11 w-11 rounded-full animate-pulse" style={skeletonBase} />
                      <div className="flex-1 space-y-2">
                        <div className="h-5 w-4/5 rounded-lg animate-pulse" style={skeletonBase} />
                        <div className="h-4 w-3/5 rounded-lg animate-pulse" style={skeletonBase} />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!loadingNews && news.length === 0 && (
                <p className="text-[color:var(--secondary-text)]">{t("dashboard:news.empty")}</p>
              )}

              {!loadingNews && news.length > 0 && (
                <ul className="flex flex-col gap-4" aria-label={t("dashboard:aria.newsList")}>
                  {news.map((n) => (
                    <li key={n.id}>
                      <div
                        className="flex cursor-pointer items-start gap-3 rounded-2xl p-2 transition-transform duration-200 ease-out hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb55]"
                        onClick={() => navigate(`/news/${n.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") navigate(`/news/${n.id}`)
                        }}
                        role="link"
                        tabIndex={0}
                        title={n.title}
                        aria-label={t("dashboard:aria.newsItem", { title: n.title })}
                      >
                        <DateBullet date={n.created_at} locale={locale} />
                        <div className="space-y-1">
                          <h3 className="text-[clamp(.98rem,.9rem+.4vw,1.06rem)] font-semibold text-[color:var(--page-text)]">
                            {n.title}
                          </h3>
                          <p className="text-sm text-[color:var(--secondary-text)]">
                            {(n.content || "").slice(0, 110)}
                            {(n.content || "").length > 110 ? "…" : ""}
                          </p>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section
              data-fade
              style={{ "--fade-delay": "260ms" } as CSSProperties}
              className={`${cardBaseClasses} lg:col-span-4`}
              aria-busy={loadingEvents}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-[clamp(1.05rem,2vw,1.4rem)] font-extrabold text-[color:var(--page-text)]">
                  {t("dashboard:events.heading")}
                </h2>
                <Link
                  to="/events"
                  className={buttonClasses}
                  style={{ borderColor: softBorderColor }}
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
                </Link>
              </div>

              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  className={pillButtonClasses}
                  style={
                    eventsScope === "today"
                      ? {
                          background: "linear-gradient(100deg,#1976d2 20%,#449aff 100%)",
                          color: "#fff",
                          borderColor: "transparent",
                        }
                      : { background: mutedSurface, borderColor: softBorderColor }
                  }
                  onClick={() => setEventsScope("today")}
                  aria-pressed={eventsScope === "today"}
                >
                  {t("dashboard:scope.today")}
                </button>
                <button
                  type="button"
                  className={pillButtonClasses}
                  style={
                    eventsScope === "week"
                      ? {
                          background: "linear-gradient(100deg,#1976d2 20%,#449aff 100%)",
                          color: "#fff",
                          borderColor: "transparent",
                        }
                      : { background: mutedSurface, borderColor: softBorderColor }
                  }
                  onClick={() => setEventsScope("week")}
                  aria-pressed={eventsScope === "week"}
                >
                  {t("dashboard:scope.week")}
                </button>
              </div>

              <hr className="my-6 h-px border-none" style={{ background: mutedSurface }} />

              {loadingEvents && (
                <div className="flex flex-col gap-3">
                  <div className="h-6 w-full animate-pulse rounded-lg" style={skeletonBase} />
                  <div className="h-6 w-5/6 animate-pulse rounded-lg" style={skeletonBase} />
                  <div className="h-6 w-4/6 animate-pulse rounded-lg" style={skeletonBase} />
                </div>
              )}

              {!loadingEvents && scopedEvents.length === 0 && (
                <p className="text-[color:var(--secondary-text)]">{t("dashboard:events.empty")}</p>
              )}

              {!loadingEvents && scopedEvents.length > 0 && (
                <ul
                  className="flex flex-col gap-3"
                  aria-label={
                    eventsScope === "today"
                      ? t("dashboard:aria.eventsToday")
                      : t("dashboard:aria.eventsWeek")
                  }
                >
                  {scopedEvents.map((e) => {
                    const d = parseLocalDate(String(e.starts_at))
                    return (
                      <li key={e.id}>
                        <div
                          className="flex cursor-pointer flex-col gap-2 rounded-2xl p-2 transition-transform duration-200 ease-out hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb55]"
                          onClick={() => navigate(`/events/${e.id}`)}
                          onKeyDown={(ev) => {
                            if (ev.key === "Enter") navigate(`/events/${e.id}`)
                          }}
                          tabIndex={0}
                          role="link"
                          aria-label={t("dashboard:aria.eventItem", { title: e.title })}
                        >
                          <h3 className="text-base font-semibold text-[color:var(--page-text)]">
                            {e.title}
                          </h3>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="chip-time inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold">
                              {d
                                ? d.toLocaleString(locale, {
                                    day: "2-digit",
                                    month: "long",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })
                                : ""}
                            </span>
                            {!!e.location && (
                              <span
                                className="inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold"
                                style={{ background: mutedSurface, borderColor: softBorderColor }}
                              >
                                {e.location}
                              </span>
                            )}
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>
          </div>
        </div>
      </PageFadeIn>
    </Layout>
  )
}
