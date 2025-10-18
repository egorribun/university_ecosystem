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
import { useAuth } from "../contexts/AuthContext"
import axios from "../api/client"
import {
  Box,
  Typography,
  Chip,
  Stack,
  Button,
  Divider,
  List,
  ListItem,
  ListItemText,
  Skeleton,
  useMediaQuery,
  Tooltip,
  LinearProgress,
} from "@mui/material"
import { Link, useNavigate } from "react-router-dom"
import { cardHoverSx } from "@/constants/cardHover"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"

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
    <Tooltip title={full} enterDelay={150}>
      <Box
        aria-label={t("ariaDatePublished", { date: full })}
        sx={{
          width: 44,
          height: 44,
          minWidth: 44,
          minHeight: 44,
          flex: "0 0 44px",
          borderRadius: "50%",
          background: "linear-gradient(120deg,#1d5fff,#65b2ff)",
          color: "#fff",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontWeight: 800,
          lineHeight: 1,
          userSelect: "none",
        }}
      >
        <Box sx={{ fontSize: 14 }}>{dd}</Box>
        <Box sx={{ fontSize: 10, opacity: 0.9 }}>{mm}</Box>
      </Box>
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

  const [loadingNews, setLoadingNews] = useState(true)
  const [loadingEvents, setLoadingEvents] = useState(true)
  const [loadingSched, setLoadingSched] = useState(true)

  const [news, setNews] = useState<NewsItem[]>([])
  const [events, setEvents] = useState<EventItem[]>([])
  const [schedule, setSchedule] = useState<Lesson[]>([])

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
      const r = await axios.get("/events", { params: { is_active: true } })
      const arr = Array.isArray(r.data) ? r.data : []
      const sorted = arr
        .filter((e) => e.starts_at)
        .sort((a, b) => String(a.starts_at).localeCompare(String(b.starts_at)))
      setEvents(sorted.slice(0, 30))
      setCache<EventItem[]>("dash:events", sorted.slice(0, 30))
    } catch {
      setEvents([])
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
  }, [fetchNews, fetchEvents])

  useEffect(() => {
    fetchSchedule()
  }, [fetchSchedule])

  const headerGradient = isNarrow
    ? "linear-gradient(100deg,var(--hero-grad-start) 50%,var(--hero-grad-end) 100%)"
    : "linear-gradient(100deg,var(--hero-grad-start) 40%,var(--hero-grad-end) 100%)"
  const focusRing = "0 0 0 3px #2563eb33, 0 0 0 6px #2563eb1f"
  const btnSx = {
    borderRadius: 2,
    fontWeight: 700,
    px: 1.8,
    py: 0.5,
    whiteSpace: "nowrap",
    transition: "background .16s,color .16s,border-color .16s,box-shadow .16s, transform .16s",
    "&:hover": {
      background: "linear-gradient(100deg,#1976d2 20%,#449aff 100%)",
      color: "#fff",
      borderColor: "transparent",
      transform: "translateY(-1px)",
    },
    "&:active": { transform: "translateY(0)" },
    "&:focus-visible": { boxShadow: focusRing, outline: "none" },
  }

  const warmNewsPage = () => import("../pages/News").catch(() => {})
  const warmEventsPage = () => import("../pages/Events").catch(() => {})
  const warmSchedulePage = () => import("../pages/Schedule").catch(() => {})
  const prefetchData = (type: "news" | "events") => {
    if (type === "news")
      axios
        .get("/news")
        .then((r) => setCache("prefetch:news", r.data))
        .catch(() => {})
    if (type === "events")
      axios
        .get("/events", { params: { is_active: true } })
        .then((r) => setCache("prefetch:events", r.data))
        .catch(() => {})
  }

  const prepareOnKey = (event: KeyboardEvent, callback: () => void) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      callback()
    }
  }

  const cardHoverBase = cardHoverSx()
  const homeCardSx = {
    ...cardHoverBase,
    p: 2.2,
    borderRadius: "2rem",
    background: "var(--card-bg)",
    boxShadow: {
      xs: "0 16px 40px rgba(0,0,0,.22), 0 6px 16px rgba(0,0,0,.12)",
      md: "var(--shadow-1)",
    },
    border: {
      xs: "1px solid color-mix(in srgb, var(--page-text) 12%, transparent)",
      md: "1px solid transparent",
    },
    backdropFilter: { xs: "saturate(110%)", md: "none" },
  } as const

  return (
    <Layout>
      <a
        href="#main"
        style={{
          position: "fixed",
          left: 8,
          top: 8,
          padding: "8px 12px",
          background: "#1d5fff",
          color: "#fff",
          borderRadius: 8,
          transform: "translateY(-200%)",
          transition: "transform .2s",
          zIndex: 5000,
        }}
        onFocus={(e) => {
          ;(e.currentTarget as HTMLAnchorElement).style.transform = "translateY(0)"
        }}
        onBlur={(e) => {
          ;(e.currentTarget as HTMLAnchorElement).style.transform = "translateY(-200%)"
        }}
      >
        {t("common:skipToMain")}
      </a>
      <PageFadeIn>
        <Box
          id="main"
          sx={{
            width: "100%",
            maxWidth: "min(1800px, 100%)",
            px: { xs: 2, sm: 3, md: 5, lg: 8 },
            py: { xs: 2, md: 3 },
            mx: "auto",
          }}
        >
          <Box
            data-fade
            style={{ "--fade-delay": "40ms" } as CSSProperties}
            sx={{
              background: headerGradient,
              borderRadius: "2rem",
              p: { xs: 2.2, md: 3 },
              boxShadow: "0 12px 36px #1d5fff16, 0 4px 14px #0000000a",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 2,
              ...cardHoverBase,
              border: { xs: "1px solid color-mix(in srgb, var(--page-text) 10%, transparent)" },
            }}
          >
            <Box>
              <Typography sx={{ fontSize: "clamp(1.4rem, 2.2vw, 2.4rem)", fontWeight: 800 }}>
                {greeting}
                {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
              </Typography>
              <Stack
                direction="row"
                alignItems="center"
                gap={1}
                mt={1}
                role="status"
                aria-live="polite"
              >
                <Chip
                  size="small"
                  className="chip-clock"
                  aria-label={t("common:ariaCurrentTime")}
                  label={
                    <Box
                      sx={{
                        display: "inline-flex",
                        alignItems: "baseline",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      <Box>{hh}</Box>
                      <Box sx={{ mx: 0.2, transition: "opacity .28s", opacity: showColon ? 1 : 0 }}>
                        :
                      </Box>
                      <Box>{mm}</Box>
                    </Box>
                  }
                />
                <Typography sx={{ opacity: 0.9 }}>{dateStr}</Typography>
              </Stack>
            </Box>
            <Box sx={{ display: { xs: "none", md: "flex" }, gap: 1 }}>
              <Button
                variant="outlined"
                onClick={() => navigate("/profile")}
                sx={{ ...btnSx, px: 2.2, py: 0.9 }}
                aria-label={t("navigation:aria.openProfile")}
              >
                {t("navigation:menu.profile")}
              </Button>
            </Box>
          </Box>

          <Box
            sx={{
              mt: 3,
              display: "grid",
              gridTemplateColumns: "repeat(12, 1fr)",
              gap: { xs: 2, md: 3 },
            }}
          >
            <Box
              data-fade
              style={{ "--fade-delay": "140ms" } as CSSProperties}
              sx={{ ...homeCardSx, gridColumn: { xs: "1 / -1", lg: "1 / span 4" } }}
              aria-busy={loadingSched}
            >
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1 }}
              >
                <Typography sx={{ fontWeight: 800, fontSize: "clamp(1.05rem, 2vw, 1.4rem)" }}>
                  {t("dashboard:todaySchedule")}
                </Typography>
                <Stack direction="row" gap={1}>
                  <Button
                    component={Link}
                    to="/schedule"
                    size="small"
                    variant="outlined"
                    sx={{ ...btnSx, px: 3, py: 0.9 }}
                    aria-label={t("dashboard:aria.openFullSchedule")}
                    onPointerDown={warmSchedulePage}
                    onKeyDown={(event) => prepareOnKey(event, warmSchedulePage)}
                  >
                    {t("dashboard:fullSchedule")}
                  </Button>
                </Stack>
              </Stack>
              {currentLesson && (
                <Box sx={{ mb: 1.5 }}>
                  <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1 }}>
                    <Chip size="small" color="primary" label={t("dashboard:now")} />
                    <Typography sx={{ fontWeight: 700 }}>{currentLesson.subject}</Typography>
                    <Chip
                      size="small"
                      className="chip-time"
                      label={`${fmtTime(currentLesson.start_time)}–${fmtTime(currentLesson.end_time)}`}
                    />
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={currentProgress}
                    sx={{ height: 8, borderRadius: 6 }}
                    aria-label={t("common:ariaCurrentLessonProgress")}
                  />
                </Box>
              )}
              {!currentLesson && nextLesson && (
                <Box sx={{ mb: 1.5 }}>
                  <Stack direction="row" alignItems="center" gap={1}>
                    <Chip
                      size="small"
                      label={t("dashboard:next")}
                      sx={(theme) => ({
                        fontWeight: 700,
                        bgcolor:
                          theme.palette.mode === "dark"
                            ? "rgba(99,102,241,.18)"
                            : "rgba(25,118,210,.08)",
                        color:
                          theme.palette.mode === "dark" ? "#a5b4fc" : theme.palette.primary.main,
                        border: "1px solid",
                        borderColor:
                          theme.palette.mode === "dark"
                            ? "rgba(99,102,241,.38)"
                            : "rgba(25,118,210,.3)",
                        "& .MuiChip-label": { px: 1.1 },
                      })}
                    />
                    <Typography sx={{ fontWeight: 700 }}>{nextLesson.subject}</Typography>
                    <Chip
                      size="small"
                      className="chip-time"
                      label={`${fmtTime(nextLesson.start_time)}–${fmtTime(nextLesson.end_time)}`}
                    />
                  </Stack>
                </Box>
              )}
              <Divider sx={{ my: 1.5 }} />
              {loadingSched && (
                <Stack spacing={1.2}>
                  <Skeleton height={22} />
                  <Skeleton height={22} />
                  <Skeleton height={22} />
                </Stack>
              )}
              {!loadingSched && todayLessons.length === 0 && (
                <Typography color="text.secondary">{t("dashboard:noClasses")}</Typography>
              )}
              {!loadingSched && todayLessons.length > 0 && (
                <List dense sx={{ py: 0 }}>
                  {todayLessons.map((l) => (
                    <ListItem key={l.id} disablePadding sx={{ mb: 0.5 }}>
                      <ListItemText
                        primary={
                          <Stack
                            direction="row"
                            alignItems="center"
                            gap={1}
                            sx={{ flexWrap: "wrap" }}
                          >
                            <Chip
                              size="small"
                              className="chip-time"
                              label={`${fmtTime(l.start_time)}–${fmtTime(l.end_time)}`}
                            />
                            <Typography sx={{ fontWeight: 700 }}>{l.subject}</Typography>
                            <Chip
                              size="small"
                              className="chip-type"
                              label={l.lesson_type}
                              variant="outlined"
                            />
                          </Stack>
                        }
                        secondary={
                          <Typography sx={{ opacity: 0.85 }}>
                            {t("dashboard:lessonMeta", { teacher: l.teacher, room: l.room })}
                          </Typography>
                        }
                        primaryTypographyProps={{ component: "div" }}
                        secondaryTypographyProps={{ component: "span" }}
                      />
                    </ListItem>
                  ))}
                </List>
              )}
            </Box>

            <Box
              data-fade
              style={{ "--fade-delay": "200ms" } as CSSProperties}
              sx={{ ...homeCardSx, gridColumn: { xs: "1 / -1", lg: "5 / span 4" } }}
              aria-busy={loadingNews}
            >
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Typography sx={{ fontWeight: 800, fontSize: "clamp(1.05rem, 2vw, 1.4rem)" }}>
                  {t("dashboard:news.heading")}
                </Typography>
                <Button
                  component={Link}
                  to="/news"
                  size="small"
                  variant="outlined"
                  sx={btnSx}
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
              </Stack>
              <Divider sx={{ my: 1.5 }} />
              {loadingNews && (
                <Stack spacing={1.2}>
                  <Stack direction="row" gap={1.2} alignItems="center">
                    <Skeleton variant="circular" width={44} height={44} />
                    <Box sx={{ flex: 1 }}>
                      <Skeleton height={22} />
                      <Skeleton height={18} width="60%" />
                    </Box>
                  </Stack>
                  <Stack direction="row" gap={1.2} alignItems="center">
                    <Skeleton variant="circular" width={44} height={44} />
                    <Box sx={{ flex: 1 }}>
                      <Skeleton height={22} width="80%" />
                      <Skeleton height={18} width="50%" />
                    </Box>
                  </Stack>
                </Stack>
              )}
              {!loadingNews && news.length === 0 && (
                <Typography color="text.secondary">{t("dashboard:news.empty")}</Typography>
              )}
              {!loadingNews && news.length > 0 && (
                <Stack
                  component="ul"
                  spacing={1.1}
                  sx={{ m: 0, p: 0, listStyle: "none" }}
                  aria-label={t("dashboard:aria.newsList")}
                >
                  {news.map((n) => (
                    <Stack
                      key={n.id}
                      component="li"
                      direction="row"
                      spacing={1.2}
                      alignItems="center"
                      style={{ textDecoration: "none", color: "inherit" }}
                      onClick={() => navigate(`/news/${n.id}`)}
                      role="link"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") navigate(`/news/${n.id}`)
                      }}
                      title={n.title}
                      aria-label={t("dashboard:aria.newsItem", { title: n.title })}
                    >
                      <DateBullet date={n.created_at} locale={locale} />
                      <Box>
                        <Typography
                          sx={{ fontWeight: 700, fontSize: "clamp(.98rem, .9rem + .4vw, 1.06rem)" }}
                        >
                          {n.title}
                        </Typography>
                        <Typography color="text.secondary" sx={{ fontSize: ".95rem" }}>
                          {(n.content || "").slice(0, 110)}
                          {(n.content || "").length > 110 ? "…" : ""}
                        </Typography>
                      </Box>
                    </Stack>
                  ))}
                </Stack>
              )}
            </Box>

            <Box
              data-fade
              style={{ "--fade-delay": "260ms" } as CSSProperties}
              sx={{ ...homeCardSx, gridColumn: { xs: "1 / -1", lg: "9 / span 4" } }}
              aria-busy={loadingEvents}
            >
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1 }}
              >
                <Typography sx={{ fontWeight: 800, fontSize: "clamp(1.05rem, 2vw, 1.4rem)" }}>
                  {t("dashboard:events.heading")}
                </Typography>
                <Button
                  component={Link}
                  to="/events"
                  size="small"
                  variant="outlined"
                  sx={btnSx}
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
              </Stack>
              <Stack direction="row" gap={1} sx={{ mb: 1 }}>
                <Button
                  size="small"
                  variant={eventsScope === "today" ? "contained" : "outlined"}
                  onClick={() => setEventsScope("today")}
                  sx={btnSx}
                  aria-pressed={eventsScope === "today"}
                >
                  {t("dashboard:scope.today")}
                </Button>
                <Button
                  size="small"
                  variant={eventsScope === "week" ? "contained" : "outlined"}
                  onClick={() => setEventsScope("week")}
                  sx={btnSx}
                  aria-pressed={eventsScope === "week"}
                >
                  {t("dashboard:scope.week")}
                </Button>
              </Stack>
              <Divider sx={{ my: 1.5 }} />
              {loadingEvents && (
                <Stack spacing={1.2}>
                  <Skeleton height={24} />
                  <Skeleton height={24} width="80%" />
                  <Skeleton height={24} width="70%" />
                </Stack>
              )}
              {!loadingEvents && scopedEvents.length === 0 && (
                <Typography color="text.secondary">{t("dashboard:events.empty")}</Typography>
              )}
              {!loadingEvents && scopedEvents.length > 0 && (
                <List
                  dense
                  sx={{ py: 0 }}
                  aria-label={
                    eventsScope === "today"
                      ? t("dashboard:aria.eventsToday")
                      : t("dashboard:aria.eventsWeek")
                  }
                >
                  {scopedEvents.map((e) => {
                    const d = parseLocalDate(String(e.starts_at))
                    return (
                      <ListItem
                        key={e.id}
                        disablePadding
                        sx={{ mb: 0.6, cursor: "pointer" }}
                        onClick={() => navigate(`/events/${e.id}`)}
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter") navigate(`/events/${e.id}`)
                        }}
                        tabIndex={0}
                        aria-label={t("dashboard:aria.eventItem", { title: e.title })}
                      >
                        <ListItemText
                          primary={<Typography sx={{ fontWeight: 700 }}>{e.title}</Typography>}
                          secondary={
                            <Stack direction="row" gap={1} flexWrap="wrap">
                              <Chip
                                size="small"
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
                              {!!e.location && <Chip size="small" label={e.location} />}
                            </Stack>
                          }
                          primaryTypographyProps={{ component: "div" }}
                          secondaryTypographyProps={{ component: "div" }}
                        />
                      </ListItem>
                    )
                  })}
                </List>
              )}
            </Box>
          </Box>
        </Box>
      </PageFadeIn>
    </Layout>
  )
}
