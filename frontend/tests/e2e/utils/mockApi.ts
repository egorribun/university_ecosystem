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
}

const createBaseProfile = (): User => ({
  id: 1,
  email: "student@example.com",
  full_name: "Иван Иванов",
  role: "student",
  group_id: null,
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
const mockEvents = Array.from({ length: 18 }, (_, index) => {
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

const mockSchedule = [
  {
    id: 101,
    subject: "Математика",
    teacher: "Проф. Смирнов",
    room: "А-101",
    lesson_type: "Лекция",
    weekday: "Понедельник",
    start_time: "09:00",
    end_time: "10:30",
    parity: "both" as const,
  },
]

const mockGroups = [
  { id: 1, name: "ИУ-21", course: 1, faculty: "ИТ" },
  { id: 2, name: "БИ-22", course: 2, faculty: "Бизнес" },
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

  const mutateDeadLetterJobs = (jobIds: unknown): number => {
    const ids = Array.isArray(jobIds)
      ? jobIds.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0)
      : []
    if (!ids.length) return 0
    const before = state.deadLetterJobs.length
    const allowed = new Set(ids)
    state.deadLetterJobs = state.deadLetterJobs.filter((job) => !allowed.has(job.id))
    return before - state.deadLetterJobs.length
  }

  await page.addInitScript(() => {
    try {
      if (window.name !== "__mock_api_initialized__") {
        try {
          // @ts-expect-error: Force delete read-only property for E2E
          delete window.navigator.serviceWorker
        } catch {}
        window.name = "__mock_api_initialized__"
      }
      window.localStorage.setItem("ue:language", "ru")
      window.localStorage.setItem("ecosystem.pwa.install.dismissedAt", Date.now().toString())
      window.localStorage.setItem("ecosystem.push.education.dismissedAt", Date.now().toString())
    } catch {}
  })

  page.on("console", (msg) => {
    const location = msg.location()
    console.log(`[console:${msg.type()}] ${msg.text()}${location?.url ? ` (${location.url})` : ""}`)
  })

  page.on("pageerror", (error) => {
    console.log(`[pageerror] ${error.message}\n${error.stack ?? ""}`)
  })

  page.on("requestfailed", (request) => {
    console.log(`[requestfailed] ${request.url()} :: ${request.failure()?.errorText ?? "unknown"}`)
  })

  page.on("request", (request) => {
    const url = request.url()
    if (url.includes("/api/") || url.includes("/auth/")) {
      console.log(`[request] ${url}`)
    }
  })

  page.on("response", (response) => {
    const type = response.request().resourceType()
    const contentType = response.headers()["content-type"] ?? ""
    if (type === "script" && contentType.includes("text/html")) {
      console.log(
        `[response] unexpected HTML for script: ${response.url()} status=${response.status()}`
      )
    }
  })

  await page.route("**/*", async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()

    // Handle external APIs like weather
    if (url.hostname === "api.open-meteo.com") {
      console.log(`[mock] intercepted external API: ${url.href}`)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          current: {
            temperature_2m: 20,
            weather_code: 0,
          },
        }),
      })
      return
    }

    let pathname = url.pathname.replace(/^\/+/u, "")
    pathname = pathname.startsWith("api/v1/") ? pathname.replace(/^api\/v1\//u, "api/") : pathname

    console.log(`[mock] Intercepting ${method} ${url.pathname} (normalized: ${pathname})`)

    if (
      pathname === "auth/login" ||
      pathname === "api/auth/login" ||
      pathname === "api/auth/login-json"
    ) {
      console.log(`[mock] intercepted login at ${pathname}`)
      const postData = route.request().postData() ?? ""
      const headers = route.request().headers()

      let username: string | null = null
      let password: string | null = null

      if ((headers["content-type"] ?? "").includes("application/json")) {
        try {
          const parsed = JSON.parse(postData)
          if (parsed && typeof parsed === "object") {
            const payload = parsed as Record<string, unknown>
            username = typeof payload.username === "string" ? payload.username : null
            password = typeof payload.password === "string" ? payload.password : null
          }
        } catch {
          /* ignore malformed JSON */
        }
      }

      if (!username || !password) {
        const params = new URLSearchParams(postData)
        username = username ?? params.get("username")
        password = password ?? params.get("password")
      }

      if (!username && !password && postData.length === 0) {
        username = "student@example.com"
        password = "Password123"
      }

      if (username === "student@example.com" && password === "Password123") {
        state.loggedIn = true
        console.log("[mock] login success")
        const tokenResponse = {
          access_token: "mock-token",
          refresh_token: "mock-refresh",
          token_type: "bearer",
          user: state.profile,
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(tokenResponse),
        })
        return
      }

      if (username === "mfa@example.com" && password === "Password123") {
        const challenge = createMfaChallenge({
          includeTotp: true,
          defaultMethod: "totp",
          sessionId: 84,
        })
        state.profile.mfa_required = true
        state.profile.mfa_default_method = "totp"
        state.mfa.loginChallenge = challenge
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: JSON.stringify(challenge),
        })
        return
      }

      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unauthorized" }),
      })
      return
    }

    const proxiedPaths = ["api/", "auth/", "static/", "media/", "spotify", "notifications", "push/"]
    const isProxied = proxiedPaths.some((p) => pathname.startsWith(p))

    if (!isProxied) {
      await route.continue()
      return
    }

    if (pathname === "api/users/me") {
      const auth = route.request().headers()["authorization"]
      if (!state.loggedIn && !auth?.includes("mock-token")) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }
      if (method === "PUT" || method === "PATCH") {
        const updates = route.request().postDataJSON() ?? {}
        state.profile = { ...state.profile, ...updates }
      }
      const profile = { ...state.profile, totp_enrollments: state.totp.enrollments }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(profile),
      })
      return
    }

    // --- Admin Dead-Letter & Notifications ---
    if (
      pathname === "api/notifications/admin/dead-letter" ||
      pathname === "api/admin/dead-letter-jobs"
    ) {
      if (!state.loggedIn || state.profile.role !== "admin") {
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Forbidden" }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: state.deadLetterJobs, total: state.deadLetterJobs.length }),
      })
      return
    }

    if (
      (pathname === "api/notifications/admin/dead-letter/retry" ||
        pathname === "api/admin/notifications/retry") &&
      method === "POST"
    ) {
      const payload = route.request().postDataJSON() ?? {}
      const removed = mutateDeadLetterJobs(payload.job_ids)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ retried: removed, affected: removed }),
      })
      return
    }

    if (
      (pathname === "api/notifications/admin/dead-letter/purge" ||
        pathname === "api/admin/notifications/purge") &&
      method === "POST"
    ) {
      const payload = route.request().postDataJSON() ?? {}
      const jobIds = payload.job_ids ?? []
      const removed = mutateDeadLetterJobs(jobIds)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ deleted: removed, affected: removed, success: true }),
      })
      return
    }

    // --- News ---
    const newsDetailMatch = pathname.match(/^api\/news\/(\d+)$/)
    if (newsDetailMatch) {
      const id = parseInt(newsDetailMatch[1], 10)
      const entry = mockNews.find((n) => n.id === id)
      if (!entry) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Not found" }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(entry),
      })
      return
    }

    if (pathname === "api/news") {
      const headers = route.request().headers()
      const ifNoneMatch = headers["if-none-match"]
      const acceptLanguage = headers["accept-language"]?.toLowerCase() ?? ""
      const locale = acceptLanguage.startsWith("en") ? "en" : "ru"

      console.log(
        `[mock-news] Received request. If-None-Match: "${ifNoneMatch}", newsVersion: "${state.newsVersion}", offline: ${state.offline}`
      )

      // Strip quotes from If-None-Match header if present (HTTP ETags are quoted)
      const normalizedEtag = ifNoneMatch?.replace(/^"|"$/g, "")

      const localize = (item: any) => ({
        ...item,
        title: locale === "en" && item.title_en ? item.title_en : item.title,
        content: locale === "en" && item.content_en ? item.content_en : item.content,
      })

      if (state.offline) {
        state.newsLog.push({ header: ifNoneMatch, status: 503 })
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Offline" }),
        })
        return
      }

      if (normalizedEtag && normalizedEtag === state.newsVersion) {
        state.newsLog.push({ header: ifNoneMatch, status: 304 })
        await route.fulfill({ status: 304, headers: { etag: state.newsVersion } })
        return
      }

      state.newsLog.push({ header: ifNoneMatch, status: 200 })
      const localizedNews = mockNews.map(localize)
      await route.fulfill({
        status: 200,
        headers: {
          etag: state.newsVersion,
          "content-type": "application/json",
          "cache-control": "public, max-age=3600",
        },
        body: JSON.stringify({
          items: localizedNews,
          total: localizedNews.length,
          limit: 12,
          cursor: null,
          next_cursor: null,
          has_more: false,
        }),
      })
      return
    }

    // --- Events ---
    if (pathname === "api/events/my") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockEvents.slice(0, 3)),
      })
      return
    }

    if (pathname === "api/events") {
      const urlParams = new URLSearchParams(url.search)
      const limit = parseInt(urlParams.get("limit") ?? "20", 10)
      const cursorParam = urlParams.get("cursor")

      const decodeCursor = (value: string | null) => {
        if (!value) return null
        try {
          const payload = JSON.parse(value) as { id?: number }
          return typeof payload?.id === "number" ? payload : null
        } catch {
          return null
        }
      }
      const encodeCursor = (event: any) =>
        event ? JSON.stringify({ id: event.id, starts_at: event.starts_at }) : null

      const decodedCursor = decodeCursor(cursorParam)
      const sortedEvents = [...mockEvents].sort((a, b) => a.id - b.id)
      const startIndex = decodedCursor
        ? sortedEvents.findIndex((e) => e.id === decodedCursor.id) + 1
        : 0
      const slice = sortedEvents.slice(startIndex, startIndex + limit)
      const nextCursor =
        startIndex + slice.length < sortedEvents.length
          ? encodeCursor(slice[slice.length - 1])
          : null

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: slice,
          has_more: !!nextCursor,
          next_cursor: nextCursor,
          total: sortedEvents.length,
        }),
      })
      return
    }

    // --- Schedule & Groups ---
    if (pathname === "api/schedule") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockSchedule),
      })
      return
    }

    if (pathname.includes("export") || pathname.endsWith(".ics")) {
      const icsData = `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Math\r\nDTSTART:20250101T090000\r\nEND:VEVENT\r\nEND:VCALENDAR`
      await route.fulfill({
        status: 200,
        contentType: "text/calendar",
        headers: { "content-disposition": "attachment; filename=schedule.ics" },
        body: icsData,
      })
      return
    }

    if (pathname === "api/groups") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockGroups),
      })
      return
    }

    // --- Auth & MFA (Continued) ---
    if (pathname === "api/auth/mfa/webauthn") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "not_supported" }),
      })
      return
    }

    if (pathname === "api/auth/sessions") {
      if (!state.loggedIn) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }
      const sessions = state.sessions.map((s, i) => ({ ...s, is_current: i === 0 }))
      console.log(
        `[mock] GET /api/v1/auth/sessions: returning ${sessions.length} sessions. Sessions: ${JSON.stringify(sessions.map((s) => ({ id: s.id, revoked: !!s.revoked_at })))}`
      )
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "Cache-Control": "no-cache, no-store, must-revalidate" },
        body: JSON.stringify(sessions),
      })
      return
    }

    const sessionDeleteMatch = pathname.match(/^api\/auth\/sessions\/(\d+)\/?$/)
    if (sessionDeleteMatch) {
      if (method === "DELETE") {
        console.log(`[mock] Intercepted DELETE ${pathname}`)
        if (!state.loggedIn) {
          console.log(`[mock] Session DELETE failed: NOT LOGGED IN`)
          await route.fulfill({
            status: 401,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Unauthorized" }),
          })
          return
        }
        const id = parseInt(sessionDeleteMatch[1], 10)
        console.log(`[mock] Attempting to revoke session ${id}`)
        const session = state.sessions.find((s) => s.id === id)
        if (!session) {
          console.log(`[mock] Session DELETE failed: session ${id} not found`)
          await route.fulfill({
            status: 404,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Not found" }),
          })
          return
        }
        console.log(`[mock] Revoking session ${id}`)
        session.revoked_at = new Date().toISOString()
        const responseData = { ...session }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: { "Cache-Control": "no-cache, no-store, must-revalidate" },
          body: JSON.stringify(responseData),
        })
        return
      } else if (method === "GET") {
        // ... (optional GET individual session handler)
      }
    }

    if (pathname === "api/auth/mfa/totp/start") {
      const secret = "JBSW Y3DP EHJK"
      const enrollment: MfaTotpEnrollment = {
        id: state.totp.nextId++,
        user_id: state.profile.id,
        label: "App",
        is_active: false,
        confirmed_at: null,
        revoked_at: null,
        created_at: new Date().toISOString(),
      }
      state.totp.pending = { enrollment, secret, otpauth_url: `otpauth://totp/U?secret=${secret}` }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.totp.pending),
      })
      return
    }

    if (pathname === "api/auth/mfa/totp/confirm") {
      const payload = route.request().postDataJSON() ?? {}
      if (payload.code !== "123456") {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Invalid code" }),
        })
        return
      }
      const confirmed: MfaTotpEnrollment = {
        ...state.totp.pending!.enrollment,
        is_active: true,
        confirmed_at: new Date().toISOString(),
      }
      state.totp.enrollments = [confirmed]
      state.profile.totp_enrollments = [confirmed]
      state.profile.mfa_default_method = "totp"
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(confirmed),
      })
      return
    }

    if (pathname === "api/auth/mfa/totp") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.totp.enrollments),
      })
      return
    }

    if (pathname === "api/auth/mfa/verify") {
      const payload = route.request().postDataJSON() ?? {}
      if (payload.code !== "123456") {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Invalid verification code" }),
        })
        return
      }
      state.loggedIn = true
      state.profile.mfa_last_verified_at = new Date().toISOString()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "mock-token",
          token_type: "bearer",
          user: state.profile,
        }),
      })
      return
    }

    // --- Stats ---
    if (pathname.startsWith("api/stats/")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ percent: 85, average: 4.8, events: 5, recent: [] }),
      })
      return
    }

    if (pathname === "api/notifications") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], unread_count: 0, has_more: false }),
      })
      return
    }

    // --- Generic Fallback ---
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    })
  })

  return {
    state,
    goOffline(value: boolean) {
      state.offline = value
    },
    async login(currentPage: Page) {
      await currentPage.goto("/login", { waitUntil: "domcontentloaded" })
      await currentPage.waitForURL(/\/login$/)
      await currentPage.waitForSelector('input[name="username"]', { state: "visible" })
      const emailField = currentPage.locator('input[name="username"]')
      await emailField.fill("student@example.com")
      await currentPage.locator('input[name="password"]').fill("Password123")
      await currentPage.locator('button[type="submit"]').click()
      await expect(currentPage).toHaveURL(/\/dashboard$/)
    },
  }
}

export type { MockState }
