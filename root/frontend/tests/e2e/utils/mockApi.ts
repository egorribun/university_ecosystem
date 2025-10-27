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
  cover_url: null,
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
  mfa_recovery_codes_generated_at: null,
  totp_enrollments: [],
  webauthn_credentials: [],
  recovery_codes: [],
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
  },
  {
    id: 2,
    title: "Библиотека открыта",
    title_en: "Library hours extended",
    content: "Расширены часы работы библиотечного центра.",
    content_en: "The library has extended its opening hours.",
    created_at: "2025-01-03T12:30:00Z",
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
  includeRecovery = false,
  includeWebAuthn = false,
  defaultMethod = includeTotp ? "totp" : includeWebAuthn ? "webauthn" : null,
  sessionId = 1,
}: {
  includeTotp?: boolean
  includeRecovery?: boolean
  includeWebAuthn?: boolean
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
  if (includeRecovery) {
    methods.push({
      method: "recovery",
      challenge_token: "recovery-challenge-token",
      challenge_expires_at: challengeExpiresAt(),
      options: null,
    })
  }
  if (includeWebAuthn) {
    methods.push({
      method: "webauthn",
      challenge_token: "webauthn-challenge-token",
      challenge_expires_at: challengeExpiresAt(),
      options: {
        challenge: "c2FtcGxlLXdlYmF1dGhu",
        timeout: 60_000,
        rpId: "localhost",
        allowCredentials: [
          {
            type: "public-key",
            id: "credential-id",
            transports: ["internal"],
          },
        ],
        userVerification: "preferred",
      },
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
    newsVersion: '"news-v1"',
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
        includeRecovery: true,
        includeWebAuthn: true,
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
        window.localStorage.clear()
        window.sessionStorage.clear()
        window.name = "__mock_api_initialized__"
      }
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

  page.on("response", (response) => {
    const type = response.request().resourceType()
    const contentType = response.headers()["content-type"] ?? ""
    if (type === "script" && contentType.includes("text/html")) {
      console.log(
        `[response] unexpected HTML for script: ${response.url()} status=${response.status()}`
      )
    }
  })

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname.replace(/^\/+/u, "")
    const method = route.request().method().toUpperCase()

    if (!pathname.startsWith("api/")) {
      await route.continue()
      return
    }

    if (pathname === "api/auth/login") {
      const postData = route.request().postData() ?? ""
      const params = new URLSearchParams(postData)
      const username = params.get("username")
      const password = params.get("password")

      if (username === "student@example.com" && password === "Password123") {
        state.loggedIn = true
        console.log("[mock] login success")
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ access_token: "mock-token" }),
        })
        return
      }

      if (username === "mfa@example.com" && password === "Password123") {
        const challenge = createMfaChallenge({
          includeTotp: true,
          includeRecovery: true,
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

      if (username === "webauthn@example.com" && password === "Password123") {
        const challenge = createMfaChallenge({
          includeTotp: false,
          includeWebAuthn: true,
          defaultMethod: "webauthn",
          sessionId: 96,
        })
        state.profile.mfa_required = true
        state.profile.mfa_default_method = "webauthn"
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

    if (method === "OPTIONS") {
      await route.fulfill({
        status: 200,
        headers: {
          "access-control-allow-origin": url.origin,
          "access-control-allow-credentials": "true",
          "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
          "access-control-allow-headers": "*",
        },
      })
      return
    }

    if (pathname === "api/users/me") {
      const auth = route.request().headers()["authorization"]
      console.log(`[mock] /users/me -> loggedIn=${state.loggedIn} auth=${auth ?? "none"}`)
      if (state.loggedIn || auth?.includes("mock-token")) {
        const profile: User = {
          ...state.profile,
          totp_enrollments: state.totp.enrollments.map((entry) => ({ ...entry })),
        }
        state.profile.totp_enrollments = profile.totp_enrollments
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(profile),
        })
      } else {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
      }
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
      const sessions = state.sessions.map((session, index) => ({
        ...session,
        is_current: index === 0,
      }))
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(sessions),
      })
      return
    }

    if (pathname === "api/auth/mfa/totp/start") {
      if (!state.loggedIn) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }

      let payload: { label?: string } = {}
      try {
        payload = JSON.parse(route.request().postData() ?? "{}")
      } catch {
        payload = {}
      }

      const enrollment: MfaTotpEnrollment = {
        id: state.totp.nextId++,
        user_id: state.profile.id,
        label: typeof payload.label === "string" ? payload.label : null,
        is_active: false,
        confirmed_at: null,
        revoked_at: null,
        created_at: new Date().toISOString(),
      }

      const secret = "JBSW Y3DP EHJK"
      state.totp.pending = {
        enrollment,
        secret,
        otpauth_url: `otpauth://totp/University:user?secret=${secret.replace(/\s+/g, "")}&issuer=University`,
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.totp.pending),
      })
      return
    }

    if (pathname === "api/auth/mfa/totp/confirm") {
      if (!state.loggedIn) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }

      const raw = route.request().postData() ?? "{}"
      let body: { enrollment_id?: number; code?: string }
      try {
        body = JSON.parse(raw)
      } catch {
        body = {}
      }

      if (!state.totp.pending || body.enrollment_id !== state.totp.pending.enrollment.id) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Enrollment not found" }),
        })
        return
      }

      const code = String(body.code ?? "").replace(/\s+/g, "")
      if (code !== "123456") {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Invalid verification code" }),
        })
        return
      }

      const confirmed: MfaTotpEnrollment = {
        ...state.totp.pending.enrollment,
        is_active: true,
        confirmed_at: new Date().toISOString(),
      }
      state.totp.enrollments = [confirmed]
      state.totp.pending = null
      state.profile.totp_enrollments = [confirmed]
      state.profile.mfa_default_method = "totp"
      state.profile.mfa_last_verified_at = confirmed.confirmed_at

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(confirmed),
      })
      return
    }

    if (pathname === "api/auth/mfa/totp") {
      if (!state.loggedIn) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.totp.enrollments),
      })
      return
    }

    const totpDeleteMatch = pathname.match(/^api\/auth\/mfa\/totp\/(\d+)$/)
    if (totpDeleteMatch) {
      if (!state.loggedIn) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }
      const id = Number.parseInt(totpDeleteMatch[1] ?? "", 10)
      const index = state.totp.enrollments.findIndex((entry) => entry.id === id)
      if (index === -1) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Enrollment not found" }),
        })
        return
      }
      state.totp.enrollments.splice(index, 1)
      state.profile.totp_enrollments = [...state.totp.enrollments]
      if (!state.totp.enrollments.length && state.profile.mfa_default_method === "totp") {
        state.profile.mfa_default_method = null
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ disabled: true }),
      })
      return
    }

    if (pathname === "api/auth/mfa/step-up") {
      const challenge =
        state.mfa.stepUpChallenge ??
        createMfaChallenge({
          includeTotp: true,
          includeRecovery: true,
          includeWebAuthn: true,
          sessionId: 42,
        })
      state.mfa.stepUpChallenge = challenge
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(challenge),
      })
      return
    }

    if (pathname === "api/auth/mfa/verify") {
      const raw = route.request().postData() ?? "{}"
      let payload: {
        method?: string
        code?: string
        credential?: unknown
        challenge_token?: string
      }
      try {
        payload = JSON.parse(raw)
      } catch {
        payload = {}
      }

      const challengeToken = payload.challenge_token
      const method = payload.method as PendingMfaResponse["methods"][number]["method"] | undefined
      if (!challengeToken || !method) {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Invalid payload" }),
        })
        return
      }

      const matches = (challenge: PendingMfaResponse | null) =>
        Boolean(
          challenge?.methods.some(
            (entry: PendingMfaResponse["methods"][number]) =>
              entry.method === method && entry.challenge_token === challengeToken
          )
        )

      const matchedLogin = matches(state.mfa.loginChallenge)
      const matchedStepUp = matches(state.mfa.stepUpChallenge)

      if (!matchedLogin && !matchedStepUp) {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Challenge expired" }),
        })
        return
      }

      if (method === "webauthn") {
        if (!payload.credential || typeof payload.credential !== "object") {
          await route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Invalid credential" }),
          })
          return
        }
      } else {
        const code = String(payload.code ?? "").replace(/\s+/g, "")
        if (code !== "123456" && !(method === "recovery" && code === "RECOVERY-1")) {
          await route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Invalid verification code" }),
          })
          return
        }
      }

      state.profile.mfa_last_verified_at = new Date().toISOString()
      state.profile.mfa_required = false
      if (method !== "recovery") {
        state.profile.mfa_default_method = method
      }

      if (matchedLogin) {
        state.loggedIn = true
        state.mfa.loginChallenge = null
      }
      if (matchedStepUp) {
        state.mfa.stepUpChallenge = createMfaChallenge({
          includeTotp: true,
          includeRecovery: true,
          includeWebAuthn: true,
          sessionId: 42,
        })
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ access_token: "mock-token", token_type: "bearer" }),
      })
      return
    }

    const sessionDeleteMatch = pathname.match(/^api\/auth\/sessions\/(\d+)$/)
    if (sessionDeleteMatch) {
      if (!state.loggedIn) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }
      const id = Number.parseInt(sessionDeleteMatch[1], 10)
      const session = state.sessions.find((item) => item.id === id)
      if (!session) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Session not found" }),
        })
        return
      }
      const nowIso = new Date().toISOString()
      session.revoked_at = nowIso
      session.last_seen_at = nowIso
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...session, is_current: false }),
      })
      return
    }

    if (pathname.startsWith("api/events")) {
      if (pathname === "api/events/my") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(mockEvents.slice(0, 3)),
        })
        return
      }

      const limitParam = Number(url.searchParams.get("limit") ?? "")
      const limit = Number.isFinite(limitParam) && limitParam > 0 ? limitParam : 20
      const cursorParam = url.searchParams.get("cursor")

      const decodeCursor = (value: string | null) => {
        if (!value) return null
        try {
          const payload = JSON.parse(value) as { id?: number; starts_at?: string }
          if (typeof payload?.id !== "number") return null
          return payload
        } catch {
          return null
        }
      }

      const encodeCursor = (
        event: { id: number; starts_at?: string | null } | undefined
      ) => (event ? JSON.stringify({ id: event.id, starts_at: event.starts_at ?? null }) : null)

      const decodedCursor = decodeCursor(cursorParam)

      const sortedEvents = [...mockEvents].sort((a, b) => {
        const startsA = String(a.starts_at ?? "")
        const startsB = String(b.starts_at ?? "")
        const compareStarts = startsA.localeCompare(startsB)
        if (compareStarts !== 0) return compareStarts
        return a.id - b.id
      })

      const startIndex = decodedCursor
        ? (() => {
            const index = sortedEvents.findIndex((event) => event.id === decodedCursor.id)
            return index >= 0 ? index + 1 : 0
          })()
        : 0

      const slice = sortedEvents.slice(startIndex, startIndex + limit)
      const total = sortedEvents.length
      const lastItem = slice[slice.length - 1]
      const nextCursor = encodeCursor(lastItem)
      const hasMore = startIndex + slice.length < total

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: slice,
          total,
          limit,
          cursor: decodedCursor ? cursorParam : null,
          next_cursor: hasMore ? nextCursor : null,
          has_more: hasMore,
        }),
      })
      return
    }

    if (pathname.startsWith("api/schedule/ics")) {
      const body = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "BEGIN:VEVENT",
        "SUMMARY:Математика",
        "DTSTART:20240101T090000",
        "DTEND:20240101T103000",
        "END:VEVENT",
        "END:VCALENDAR",
      ].join("\r\n")

      await route.fulfill({
        status: 200,
        contentType: "text/calendar",
        headers: {
          "content-disposition": 'attachment; filename="schedule-iu-21.ics"',
        },
        body,
      })
      return
    }

    if (pathname.startsWith("api/schedule")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockSchedule),
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

    if (pathname.startsWith("api/news")) {
      const headers = route.request().headers()
      const ifNoneMatch = headers["if-none-match"]
      const acceptLanguage = headers["accept-language"]?.toLowerCase() ?? ""
      const locale = acceptLanguage.startsWith("en") ? "en" : "ru"

      const localize = (item: (typeof mockNews)[number]) => ({
        ...item,
        title: locale === "en" && item.title_en ? item.title_en : item.title,
        content: locale === "en" && item.content_en ? item.content_en : item.content,
      })

      const detailMatch = pathname.match(/^api\/news\/(\d+)$/)
      if (detailMatch) {
        const id = Number.parseInt(detailMatch[1], 10)
        const entry = mockNews.find((item) => item.id === id)
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
          headers: { "content-type": "application/json" },
          body: JSON.stringify(localize(entry)),
        })
        return
      }

      if (state.offline) {
        state.newsLog.push({ header: ifNoneMatch, status: 503 })
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "offline" }),
        })
        return
      }

      if (ifNoneMatch && ifNoneMatch === state.newsVersion) {
        state.newsLog.push({ header: ifNoneMatch, status: 304 })
        await route.fulfill({
          status: 304,
          headers: { etag: state.newsVersion },
        })
        return
      }

      state.newsLog.push({ header: ifNoneMatch, status: 200 })
      const localizedNews = mockNews.map(localize)
      await route.fulfill({
        status: 200,
        headers: { etag: state.newsVersion, "content-type": "application/json" },
        body: JSON.stringify(localizedNews),
      })
      return
    }

    if (pathname === "api/stats/attendance") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          percent: 82,
          present: 18,
          total: 22,
          trend: 6.5,
          window_label: "last 30 days",
          recent: [
            {
              date: new Date().toISOString(),
              status: "present",
              course: "Discrete Math",
            },
          ],
        }),
      })
      return
    }

    if (pathname === "api/stats/grades") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          average: 4.7,
          scale: "5",
          trend: 0.4,
          recent: [
            {
              course: "Physics",
              score: 5,
              max: 5,
              date: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
            },
          ],
        }),
      })
      return
    }

    if (pathname === "api/stats/participation") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          events: 4,
          hours: 12,
          groups: 3,
          trend: 1,
          recent: [
            {
              title: "Volunteer Day",
              date: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
              role: "volunteer",
            },
          ],
        }),
      })
      return
    }

    if (pathname === "api/notifications/admin/dead-letter") {
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
        body: JSON.stringify({
          items: state.deadLetterJobs,
          total: state.deadLetterJobs.length,
        }),
      })
      return
    }

    if (pathname === "api/notifications/admin/dead-letter/retry" && method === "POST") {
      if (!state.loggedIn || state.profile.role !== "admin") {
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Forbidden" }),
        })
        return
      }
      let payload: unknown = null
      try {
        const raw = route.request().postData() ?? "{}"
        payload = JSON.parse(raw)
      } catch {
        payload = null
      }
      const removed = mutateDeadLetterJobs((payload as { job_ids?: unknown } | null)?.job_ids)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ retried: removed }),
      })
      return
    }

    if (pathname === "api/notifications/admin/dead-letter/purge" && method === "POST") {
      if (!state.loggedIn || state.profile.role !== "admin") {
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Forbidden" }),
        })
        return
      }
      let payload: unknown = null
      try {
        const raw = route.request().postData() ?? "{}"
        payload = JSON.parse(raw)
      } catch {
        payload = null
      }
      const removed = mutateDeadLetterJobs((payload as { job_ids?: unknown } | null)?.job_ids)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ deleted: removed }),
      })
      return
    }

    if (pathname === "api/notifications") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], unread_count: 0, has_more: false, next_cursor: null }),
      })
      return
    }

    if (
      /^api\/notifications\/\d+\/read$/.test(pathname) ||
      pathname === "api/notifications/read-all"
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      })
      return
    }

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
      await currentPage.getByRole("button", { name: /Sign in|Войти/ }).click()
      await expect(currentPage).toHaveURL(/\/dashboard$/)
    },
  }
}

export type { MockState }
