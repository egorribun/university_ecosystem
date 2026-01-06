import { expect, type Page } from "@playwright/test"
import type {
  MfaTotpEnrollment,
  PendingMfaResponse,
  TotpEnrollmentStartResponse,
} from "@/types/Mfa"
import type { User } from "@/types/User"

type NewsLogEntry = {
  header: string | undefined
  status: number
}

type TotpState = {
  pending: TotpEnrollmentStartResponse | null
  enrollments: MfaTotpEnrollment[]
  nextId: number
}

type MfaState = {
  loginChallenge: PendingMfaResponse | null
  stepUpChallenge: PendingMfaResponse | null
}

type AdminDeadLetterJob = {
  id: number
  kind: "event" | "news"
  record_id: number
  locale: string | null
  enqueued_at: string
  claimed_at: string | null
  attempts: number
  last_error: string | null
  next_retry_at: string | null
}

type SessionMock = {
  id: number
  user_id: number
  jti: string
  created_at: string
  expires_at: string
  revoked_at: string | null
  ip_address: string
  user_agent: string
  last_seen_at: string
  is_current?: boolean
}

type MockState = {
  loggedIn: boolean
  newsVersion: string
  offline: boolean
  newsLog: NewsLogEntry[]
  sessions: SessionMock[]
  profile: User
  totp: TotpState
  mfa: MfaState
  deadLetterJobs: AdminDeadLetterJob[]
}

const createBaseProfile = (): User => ({
  id: 1,
  email: "student@example.com",
  full_name: "Иван Иванов",
  role: "student",
  group_id: 1,
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  about: null,
  record_book_number: "IU-21-123",
  status: "active",
  institute: "ИТ",
  course: "2",
  education_level: "bachelor",
  track: null,
  program: null,
  telegram: "@ivan",
  achievements: null,
  department: "ИТ",
  position: "Student",
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: false,
  dnd_enabled: false,
  dnd_start: null,
  dnd_end: null,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  totp_enrollments: [],
  mfa_challenges: [],
})

const mockNews = [
  {
    id: 1,
    title: "Новость дня",
    title_en: "News of the day",
    content: "Кампус переходит на новую систему расписаний.",
    content_en: "The campus is switching to a new scheduling system.",
    created_at: "2025-01-01T10:00:00Z",
    image_url: "/fallbacks/news_placeholder.png",
    image_url_optimized: null,
  },
  {
    id: 2,
    title: "Библиотека открыта",
    title_en: "Library hours extended",
    content: "Расширены часы работы библиотечного центра.",
    content_en: "The library has extended its opening hours.",
    created_at: "2025-01-03T12:30:00Z",
    image_url: "/fallbacks/news_placeholder.png",
    image_url_optimized: null,
  },
]

const now = new Date()
const mockEvents = Array.from({ length: 50 }, (_, index) => {
  const id = index + 10
  const start = new Date(now.getTime() + (index + 1) * 24 * 60 * 60 * 1000)
  const end = new Date(start.getTime() + 2 * 60 * 60 * 1000)
  return {
    id,
    title: `Событие ${id}`,
    title_en: `Event ${id}`,
    description: `Описание события ${id}`,
    description_en: `Event description ${id}`,
    location: `Корпус A, зал ${index + 1}`,
    location_en: `Building A, hall ${index + 1}`,
    event_type: null,
    event_type_en: null,
    starts_at: start.toISOString(),
    ends_at: end.toISOString(),
    created_at: now.toISOString(),
    created_by: 1,
    is_active: true,
    speaker: null,
    image_url: null,
    about: null,
    about_en: null,
    files: [],
    participant_count: index * 5,
    is_registered: false,
    my_qr_code: null,
  }
})

const createDeadLetterJobs = (): AdminDeadLetterJob[] => [
  {
    id: 1,
    kind: "event",
    record_id: 1001,
    locale: "ru",
    enqueued_at: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
    claimed_at: null,
    attempts: 3,
    last_error: "Timeout",
    next_retry_at: null,
  },
  {
    id: 2,
    kind: "news",
    record_id: 2002,
    locale: "en",
    enqueued_at: new Date(now.getTime() - 2 * 60 * 1000).toISOString(),
    claimed_at: null,
    attempts: 2,
    last_error: "Webhook failed",
    next_retry_at: null,
  },
]

const getWeekdayName = (): string => {
  const names = ["Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
  return names[new Date().getDay()]
}

const mockSchedule = [
  {
    id: 101,
    subject: "Математика",
    teacher: "Проф. Смирнов",
    room: "А-101",
    lesson_type: "Лекция",
    weekday: getWeekdayName(),
    start_time: "00:00",
    end_time: "23:59",
    parity: "both" as const,
  },
]

const createMockSessions = (): SessionMock[] => {
  const now = Date.now()
  return [
    {
      id: 1,
      user_id: 1,
      jti: "mock-session-current",
      created_at: new Date(now).toISOString(),
      expires_at: new Date(now + 60 * 60 * 1000).toISOString(),
      revoked_at: null,
      ip_address: "198.51.100.20",
      user_agent: "Playwright Test Browser",
      last_seen_at: new Date(now).toISOString(),
      is_current: true,
    },
    {
      id: 2,
      user_id: 1,
      jti: "mock-session-secondary",
      created_at: new Date(now - 2 * 60 * 60 * 1000).toISOString(),
      expires_at: new Date(now + 2 * 60 * 60 * 1000).toISOString(),
      revoked_at: null,
      ip_address: "203.0.113.50",
      user_agent: "Safari/17.0 (iPhone; CPU iPhone OS)",
      last_seen_at: new Date(now - 15 * 60 * 1000).toISOString(),
      is_current: false,
    },
  ]
}

const challengeExpiresAt = () => new Date(Date.now() + 5 * 60 * 1000).toISOString()

const createMfaChallenge = ({
  includeTotp = true,
  defaultMethod = includeTotp ? "totp" : null,
  sessionId = 1,
}: {
  includeTotp?: boolean
  defaultMethod?: PendingMfaResponse["default_method"]
  sessionId?: number
} = {}): PendingMfaResponse => {
  const methods: PendingMfaResponse["methods"] = []
  if (includeTotp) {
    methods.push({
      method: "totp",
      challenge_token: "totp-challenge-token",
      challenge_expires_at: challengeExpiresAt(),
      options: null,
    })
  }

  return {
    status: "mfa_required",
    user_id: 1,
    session_id: sessionId,
    default_method: defaultMethod,
    methods,
  }
}

const decodeCursor = (value: string | null): number => {
  if (!value) return 0
  try {
    return parseInt(value, 10) || 0
  } catch {
    return 0
  }
}

const encodeCursor = (index: number): string => index.toString()

export async function useMockApi(page: Page) {
  const state: MockState = {
    loggedIn: false,
    newsVersion: "news-v1",
    offline: false,
    newsLog: [],
    sessions: createMockSessions(),
    profile: createBaseProfile(),
    totp: {
      pending: null,
      enrollments: [],
      nextId: 1,
    },
    mfa: {
      loginChallenge: null,
      stepUpChallenge: createMfaChallenge({
        includeTotp: true,
        sessionId: 42,
      }),
    },
    deadLetterJobs: createDeadLetterJobs(),
  }

  await page.addInitScript(() => {
    try {
      // Unregister all service workers
      if ("serviceWorker" in navigator) {
        navigator.serviceWorker.getRegistrations().then((registrations) => {
          for (const registration of registrations) {
            registration.unregister()
          }
        })
      }
      // Clear all caches
      if ("caches" in window) {
        caches.keys().then((keys) => {
          keys.forEach((key) => caches.delete(key))
        })
      }

      if (window.name !== "__mock_api_initialized__") {
        window.name = "__mock_api_initialized__"
      }
      window.localStorage.setItem("ue:language", "ru")

      window.addEventListener("unhandledrejection", (event) => {
        const error = event.reason
        if (error && typeof error === "object" && error.isAxiosError) {
          console.error(
            `[GlobalErrors] Axios error: ${error.message} (${error.config?.url}) status=${error.response?.status} data=${JSON.stringify(error.response?.data)}`
          )
        } else {
          console.error(`[GlobalErrors] Unhandled rejection: ${error?.message || error}`)
        }
      })
    } catch {}
  })

  page.on("console", (msg) => {
    const location = msg.location()
    if (
      msg.type() === "error" ||
      msg.text().includes("[sw]") ||
      msg.text().includes("[mock]") ||
      msg.text().includes("[usePushSync]")
    ) {
      console.log(
        `[console:${msg.type()}] ${msg.text()}${location?.url ? ` (${location.url})` : ""}`
      )
    }
  })

  await page.context().route("**/*", async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    // Handle external APIs
    if (url.hostname === "api.open-meteo.com") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ current: { temperature_2m: 20, weather_code: 0 } }),
      })
      return
    }

    const pathname = url.pathname.replace(/^\/+/u, "")
    // Normalize v1 paths ONLY for matching, but keep it permissive
    const normPath = pathname.replace(/^api\/v1\//u, "api/")

    if (state.offline && (normPath.startsWith("api/") || normPath.startsWith("auth/"))) {
      console.log(`[mock] Simulating OFFLINE for ${normPath}`)

      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Offline" }),
      })
      return
    }

    // --- Authentication ---
    if (normPath.includes("auth/login")) {
      const postData = route.request().postData() ?? ""
      const headers = route.request().headers()
      let username = ""
      let password = ""

      try {
        if ((headers["content-type"] ?? "").includes("application/json")) {
          const parsed = JSON.parse(postData)
          username = parsed.username || ""
          password = parsed.password || ""
        } else {
          const params = new URLSearchParams(postData)
          username = params.get("username") || ""
          password = params.get("password") || ""
        }
      } catch {}

      if (username === "student@example.com" || username === "student") {
        state.loggedIn = true
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            access_token: "mock-token",
            refresh_token: "mock-refresh",
            token_type: "bearer",
            user: state.profile,
          }),
        })
        return
      }

      if (username === "mfa@example.com") {
        const challenge = createMfaChallenge({
          includeTotp: true,
          defaultMethod: "totp",
          sessionId: 84,
        })
        state.mfa.loginChallenge = challenge
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify(challenge),
        })
        return
      }

      await route.fulfill({ status: 401, body: JSON.stringify({ detail: "Unauthorized" }) })
      return
    }

    // --- Profile ---
    if (normPath.includes("api/users/me")) {
      if (method === "GET") {
        await route.fulfill({ status: 200, body: JSON.stringify(state.profile) })
        return
      }
      if (method === "PUT" || method === "PATCH") {
        const updates = route.request().postDataJSON() ?? {}
        state.profile = { ...state.profile, ...updates }
        await route.fulfill({ status: 200, body: JSON.stringify(state.profile) })
        return
      }
    }

    // --- News ---
    if (normPath.includes("api/news")) {
      const detailMatch = normPath.match(/api\/news\/(\d+)/)
      if (detailMatch) {
        const id = parseInt(detailMatch[1], 10)
        const entry = mockNews.find((n) => n.id === id) || mockNews[0]
        await route.fulfill({ status: 200, body: JSON.stringify(entry) })
        return
      }

      const ifNoneMatch = request.headers()["if-none-match"] || request.headers()["If-None-Match"]
      const is304 = ifNoneMatch === state.newsVersion

      state.newsLog.push({
        header: ifNoneMatch,
        status: is304 ? 304 : 200,
      })

      if (is304) {
        await route.fulfill({
          status: 304,
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
            ETag: state.newsVersion,
            "Cache-Control": "no-cache",
          },
        })
        return
      }

      const headers = request.headers()
      const locale = (headers["accept-language"] || "").startsWith("en") ? "en" : "ru"
      const localized = mockNews.map((n) => ({
        ...n,
        title: locale === "en" ? n.title_en : n.title,
        content: locale === "en" ? n.content_en : n.content,
      }))

      await route.fulfill({
        status: 200,
        headers: { ETag: state.newsVersion },
        body: JSON.stringify({
          items: localized,
          total: localized.length,
          limit: 12,
          has_more: false,
        }),
      })
      return
    }

    // --- Events ---
    if (normPath.includes("api/events")) {
      if (normPath.includes("api/events/my")) {
        await route.fulfill({ status: 200, body: JSON.stringify(mockEvents.slice(0, 3)) })
        return
      }

      const urlParams = new URLSearchParams(url.search)
      const limit = parseInt(urlParams.get("limit") ?? "12", 10)
      const cursorParam = urlParams.get("cursor")
      const locale = (request.headers()["accept-language"] || "").startsWith("en") ? "en" : "ru"

      const startIndex = decodeCursor(cursorParam)
      const slice = mockEvents.slice(startIndex, startIndex + limit)
      const nextCursor =
        startIndex + slice.length < mockEvents.length
          ? encodeCursor(startIndex + slice.length)
          : null

      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          items: slice.map((e) => ({
            ...e,
            title: locale === "en" ? e.title_en : e.title,
            description: locale === "en" ? e.description_en : e.description,
          })),
          total: mockEvents.length,
          limit,
          cursor: cursorParam,
          next_cursor: nextCursor,
          has_more: nextCursor !== null,
        }),
      })
      return
    }

    // --- Groups ---
    if (normPath.includes("api/groups")) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([{ id: 1, name: "ИУ-21", faculty: "ИТ" }]),
      })
      return
    }

    // --- Schedule ---
    if (normPath.includes("api/schedule")) {
      await route.fulfill({ status: 200, body: JSON.stringify(mockSchedule) })
      return
    }

    // --- Sessions ---
    if (normPath.includes("auth/sessions")) {
      if (method === "GET") {
        await route.fulfill({ status: 200, body: JSON.stringify(state.sessions) })
        return
      }
      if (method === "DELETE") {
        const idMatch = normPath.match(/sessions\/(\d+)/)
        if (idMatch) {
          const id = parseInt(idMatch[1], 10)
          const session = state.sessions.find((s) => s.id === id)
          if (session) {
            session.revoked_at = new Date().toISOString()
            await route.fulfill({ status: 200, body: JSON.stringify(session) })
            return
          }
        }
        await route.fulfill({ status: 404, body: JSON.stringify({ detail: "Session not found" }) })
        return
      }
    }

    // --- MFA ---
    if (normPath.includes("auth/mfa/totp/start")) {
      const secret = "JBSW Y3DP EHJK"
      const enrollment: MfaTotpEnrollment = {
        id: state.totp.nextId++,
        user_id: state.profile.id,
        label: "Приложение 1",
        is_active: false,
        confirmed_at: null,
        revoked_at: null,
        created_at: new Date().toISOString(),
      }
      state.totp.pending = { enrollment, secret, otpauth_url: `otpauth://totp/U?secret=${secret}` }
      await route.fulfill({ status: 200, body: JSON.stringify(state.totp.pending) })
      return
    }

    if (normPath.includes("auth/mfa/totp/confirm")) {
      const confirmed: MfaTotpEnrollment = {
        ...state.totp.pending!.enrollment,
        is_active: true,
        confirmed_at: new Date().toISOString(),
      }
      state.totp.enrollments = [confirmed]
      state.profile.totp_enrollments = [confirmed]
      await route.fulfill({ status: 200, body: JSON.stringify(confirmed) })
      return
    }

    if (normPath.includes("auth/mfa/verify") || normPath.includes("auth/mfa/totp/confirm")) {
      const data = request.postDataJSON() ?? {}
      const code = data.code || data.otp_code
      if (code === "000000") {
        await route.fulfill({
          status: 401,
          body: JSON.stringify({ detail: "Invalid verification code" }),
        })
        return
      }
      state.loggedIn = true
      await route.fulfill({ status: 200, body: JSON.stringify({ status: "success" }) })
      return
    }

    if (normPath.includes("auth/mfa/totp")) {
      await route.fulfill({ status: 200, body: JSON.stringify(state.totp.enrollments) })
      return
    }

    if (normPath.includes("auth/mfa/challenge")) {
      await route.fulfill({ status: 200, body: JSON.stringify(state.mfa.stepUpChallenge) })
      return
    }

    // --- Stories ---
    if (normPath.includes("api/stories")) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          items: [
            {
              id: 1,
              user_id: 1,
              type: "image",
              url: "/fallbacks/news_placeholder.png",
              thumbnail_url: "/fallbacks/news_placeholder.png",
              duration: 5,
              created_at: new Date().toISOString(),
              expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
              is_viewed: false,
              user: state.profile,
            },
          ],
          total: 1,
        }),
      })
      return
    }

    // --- Notifications & Admin ---
    if (normPath.includes("api/notifications/admin/dead-letter")) {
      if (normPath.includes("retry")) {
        // Retry removes the first job (simulating successful retry)
        if (state.deadLetterJobs.length > 0) {
          state.deadLetterJobs = state.deadLetterJobs.slice(1)
        }
        await route.fulfill({ status: 200, body: JSON.stringify({ success: true }) })
        return
      }
      if (normPath.includes("purge")) {
        // Purge removes remaining jobs
        state.deadLetterJobs = []
        await route.fulfill({ status: 200, body: JSON.stringify({ success: true }) })
        return
      }

      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          items: state.deadLetterJobs,

          total: state.deadLetterJobs.length,
          notifications: [],
        }),
      })
      return
    }

    if (
      normPath.startsWith("api/notifications") ||
      normPath.startsWith("api/notifications/check-schedule")
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          unread_count: 0,
          has_more: false,
          notifications: [],
        }),
      })
      return
    }

    // --- Catch-all for API/Auth to prevent external hits during tests ---

    if (normPath.startsWith("api/") || normPath.startsWith("auth/")) {
      console.log(`[mock] Generic 200 for unhandled path: ${normPath}`)
      await route.fulfill({ status: 200, body: "{}" })
      return
    }

    await route.continue()
  })

  return {
    state,
    async login(p: Page) {
      await p.goto("/login")
      await p.fill('input[name="username"]', "student@example.com")
      await p.fill('input[name="password"]', "Password123")
      await p.click('button[type="submit"]')
      await expect(p).toHaveURL(/\/dashboard$|\/$/)
      state.loggedIn = true
    },
    async setOffline(p: Page, offline: boolean) {
      state.offline = offline
      await p.context().setOffline(offline)
    },
  }
}
