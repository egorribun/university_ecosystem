import { expect, type Page } from "@playwright/test"
import type { MfaTotpEnrollment, PendingMfaResponse, TotpEnrollmentStart } from "@/types/Mfa"
import type { User } from "@/types/User"
import { SSR_E2E_AUTH_COOKIE } from "../../../src/ssrAuth"
import { validateRequestBody, validateResponseBody } from "../../../src/tests/contractValidator"

type NewsLogEntry = {
  header: string | undefined
  status: number
}

const MOCK_NEWS_START_DATE = "2025-01-01T10:00:00Z"
const MOCK_NEWS_2_DATE = "2025-01-03T12:30:00Z"
const MOCK_IP_1 = "198.51.100.20"
const MOCK_IP_2 = "203.0.113.50"

type TotpState = {
  pending: TotpEnrollmentStart | null
  enrollments: MfaTotpEnrollment[]
  nextId: number
}

type MfaState = {
  loginChallenge: PendingMfaResponse | null
  stepUpChallenge: PendingMfaResponse | null
}

type AdminDeadLetterJob = {
  id: string
  kind: "event" | "news"
  record_id: string
  locale: string | null
  enqueued_at: string
  claimed_at: string | null
  attempts: number
  last_error: string | null
  next_retry_at: string | null
}

type SessionMock = {
  id: string
  user_id: string
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
  newsOffline: boolean
  offline: boolean
  newsLog: NewsLogEntry[]
  sessions: SessionMock[]
  profile: User
  totp: TotpState
  mfa: MfaState
  deadLetterJobs: AdminDeadLetterJob[]
}

type MockApiOptions = {
  serviceWorker?: "disabled" | "preserve"
  /** Start without the SSR auth cookie for public login/MFA flows. */
  authenticated?: boolean
}

const MOCK_TOTP_SECRET = "JBSW Y3DP EHJK" // pragma: allowlist secret
export const MOCK_NEWS_ID = "11111111-1111-4111-8111-111111111111"
const MOCK_SECOND_NEWS_ID = "22222222-2222-4222-8222-222222222222"
export const MOCK_DEAD_LETTER_ID_1 = "33333333-3333-4333-8333-333333333331"
export const MOCK_DEAD_LETTER_ID_2 = "33333333-3333-4333-8333-333333333332"

const createBaseProfile = (): User => ({
  id: "uuid-1",
  email: "student@example.com",
  full_name: "Иван Иванов",
  role: "student",
  group_id: "uuid-101",
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  profile_detail: {
    about: null,
    telegram: "@ivan",
    status: "active",
    achievements: null,
    department: "ИТ",
    position: "Student",
  },
  education_path: {
    record_book_number: "IU-21-123",
    institute: "ИТ",
    course: "2",
    education_level: "bachelor",
    track: null,
    program: null,
  },
  preferences: {
    dnd_enabled: false,
    dnd_start: null,
    dnd_end: null,
    timezone: null,
  },
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: false,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  recovery_codes_left: 0,
  totp_enrollments: [],
})

const mockNews = [
  {
    id: MOCK_NEWS_ID,
    title: "Новость дня",
    title_en: "News of the day",
    content: "Кампус переходит на новую систему расписаний.",
    content_en: "The campus is switching to a new scheduling system.",
    created_at: MOCK_NEWS_START_DATE,
    image_url: "/fallbacks/placeholder.png",
    image_url_optimized: null,
  },
  {
    id: MOCK_SECOND_NEWS_ID,
    title: "Библиотека открыта",
    title_en: "Library hours extended",
    content: "Расширены часы работы библиотечного центра.",
    content_en: "The library has extended its opening hours.",
    created_at: MOCK_NEWS_2_DATE,
    image_url: "/fallbacks/placeholder.png",
    image_url_optimized: null,
  },
]

const MOCK_EVENTS_COUNT = 50
const ONE_HOUR_MS = 60 * 60 * 1000
const ONE_DAY_MS = 24 * ONE_HOUR_MS

const now = new Date("2026-06-27T10:00:00Z")
const mockEvents = Array.from({ length: MOCK_EVENTS_COUNT }, (_, index) => {
  const id = `uuid-${index + 10}`
  const start = new Date(now.getTime() + (index + 1) * ONE_DAY_MS)
  const end = new Date(start.getTime() + 2 * ONE_HOUR_MS)
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
    created_by: "uuid-1",
    is_active: true,
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
    id: MOCK_DEAD_LETTER_ID_1,
    kind: "event",
    record_id: "44444444-4444-4444-8444-444444444441",
    locale: "ru",
    enqueued_at: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
    claimed_at: null,
    attempts: 3,
    last_error: "Timeout",
    next_retry_at: null,
  },
  {
    id: MOCK_DEAD_LETTER_ID_2,
    kind: "news",
    record_id: "44444444-4444-4444-8444-444444444442",
    locale: "en",
    enqueued_at: new Date(now.getTime() - 2 * 60 * 1000).toISOString(),
    claimed_at: null,
    attempts: 2,
    last_error: "Webhook failed",
    next_retry_at: null,
  },
]

// Keep the fixture deterministic while making the page independent of the
// runner's calendar date. The Schedule page opens on today's weekday, so a
// single fixed-date lesson would disappear on any other day (as happened on
// hosted runners whose clock differed from the fixture clock). One lesson per
// supported weekday preserves the same payload shape and keeps every E2E run
// able to exercise the rendered schedule and its offline cache.
const mockSchedule = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"].map(
  (weekday, index) => ({
    id: `uuid-101-${index + 1}`,
    subject: "Математика",
    teacher: "Проф. Смирнов",
    room: "А-101",
    lesson_type: "Лекция",
    weekday,
    start_time: "00:00",
    end_time: "23:59",
    parity: "both" as const,
  })
)

const createMockSessions = (): SessionMock[] => {
  const nowTime = now.getTime()
  return [
    {
      id: "session-1",
      user_id: "uuid-1",
      jti: "mock-session-current",
      created_at: new Date(nowTime).toISOString(),
      expires_at: new Date(nowTime + 60 * 60 * 1000).toISOString(),
      revoked_at: null,
      ip_address: MOCK_IP_1,
      user_agent: "Playwright Test Browser",
      last_seen_at: new Date(nowTime).toISOString(),
      is_current: true,
    },
    {
      id: "session-2",
      user_id: "uuid-1",
      jti: "mock-session-secondary",
      created_at: new Date(nowTime - 2 * 60 * 60 * 1000).toISOString(),
      expires_at: new Date(nowTime + 2 * 60 * 60 * 1000).toISOString(),
      revoked_at: null,
      ip_address: MOCK_IP_2,
      user_agent: "Safari/17.0 (iPhone; CPU iPhone OS)",
      last_seen_at: new Date(nowTime - 15 * 60 * 1000).toISOString(),
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
  sessionId?: string | number
} = {}): PendingMfaResponse => {
  const methods: PendingMfaResponse["methods"] = []
  if (includeTotp) {
    methods.push({
      method: "totp",
      challenge_token: "totp-challenge-token-32-characters-long",
      challenge_expires_at: challengeExpiresAt(),
    })
  }

  return {
    status: "mfa_required",
    user_id: "uuid-1",
    session_id: typeof sessionId === "number" ? `session-${sessionId}` : sessionId,
    default_method: defaultMethod,
    methods,
  }
}

const decodeCursor = (value: string | null): number => {
  if (!value) return 0
  const index = Number.parseInt(value, 10)
  return Number.isSafeInteger(index) && index >= 0 ? index : 0
}

const encodeCursor = (index: number): string => index.toString()

export async function useMockApi(page: Page, options: MockApiOptions = {}) {
  const state: MockState = {
    loggedIn: false,
    newsVersion: "news-v1",
    newsOffline: false,
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
        sessionId: "session-42",
      }),
    },
    deadLetterJobs: createDeadLetterJobs(),
  }

  const preserveServiceWorker = options.serviceWorker === "preserve"
  const authenticated = options.authenticated ?? true

  await page.addInitScript(
    ({ preserveServiceWorker, authenticated }) => {
      try {
        if (!preserveServiceWorker) {
          // Most API-mock specs disable Service Workers so browser-level routes
          // stay the single deterministic request owner. PWA/push specs opt in
          // to preserving either the real worker or their hermetic SW double.
          Object.defineProperty(navigator, "serviceWorker", {
            get: () => ({
              register: () => Promise.resolve({ unregister: () => Promise.resolve(true) }),
              getRegistrations: () => Promise.resolve([]),
              addEventListener: () => {},
              removeEventListener: () => {},
              ready: new Promise(() => {}),
            }),
          })
        }

        if (window.name !== "__mock_api_initialized__") {
          window.name = "__mock_api_initialized__"
        }
        // Force Russian language for every page visit. Authentication is
        // opt-in so public login/MFA tests exercise the real unauthenticated
        // route instead of being redirected by a fixture cookie.
        window.localStorage.setItem("ue:language", "ru")
        if (authenticated) {
          window.localStorage.setItem("access_token", "mock-token")
          window.localStorage.setItem("refresh_token", "mock-refresh")
        } else {
          window.localStorage.removeItem("access_token")
          window.localStorage.removeItem("refresh_token")
        }
        // API-focused specs must not be occluded by the unrelated push
        // education overlay. Dedicated component tests cover that onboarding.
        window.localStorage.setItem("ecosystem.push.education.dismissedAt", String(Date.now()))

        window.addEventListener("unhandledrejection", (event) => {
          const error = event.reason
          if (error && typeof error === "object" && error.isAxiosError) {
            console.error(
              `[GlobalErrors] Axios error: ${error.message} (${error.config?.url}) status=${error.response?.status} data=${JSON.stringify(error.response?.data)}`
            )
          } else {
            const errMsg = String(error?.message || error)
            if (
              errMsg.includes("Old view transition aborted") ||
              errMsg.includes("ViewTransition") ||
              (error && typeof error === "object" && error.name === "AbortError")
            ) {
              // Ignore normal view transition aborts to prevent test flakes in WebKit
              return
            }
            console.error(`[GlobalErrors] Unhandled rejection: ${errMsg}`)
          }
        })
      } catch {
        // ignore
      }
    },
    { preserveServiceWorker, authenticated }
  )

  // SSR runs before browser init scripts, so mirror the mocked auth state with
  // a test-only cookie for protected direct navigations.
  const e2eBaseUrl =
    process.env["PLAYWRIGHT_BASE_URL"] ||
    process.env["URL_STATE_E2E_BASE"] ||
    "http://127.0.0.1:5173"
  const e2eOrigin = new URL(e2eBaseUrl).origin
  await page.context().addCookies([
    ...(authenticated ? [{ name: SSR_E2E_AUTH_COOKIE, value: "mock", url: e2eOrigin }] : []),
    // Keep the SSR shell and the browser-side LanguageProvider on the same
    // locale so hydration tests exercise real UI behavior without React #418.
    { name: "ue:language", value: "ru", url: e2eOrigin },
  ])

  // Keep authenticated mock pages from opening a real socket against the
  // preview server. The ticket endpoint is mocked below, but the preview has
  // no WebSocket upgrade handler; a real socket therefore receives 403 or
  // fails DNS resolution for the service host and starts a reconnect loop.
  // Playwright's WebSocket routing applies to every document, including the
  // initial about:blank page, so it also covers direct socket smoke tests.
  await page.routeWebSocket("**/ws/**", () => {})

  page.on("console", (msg) => {
    const location = msg.location()
    if (
      msg.type() === "error" ||
      msg.text().includes("[sw]") ||
      msg.text().includes("[mock]") ||
      msg.text().includes("[test]") ||
      msg.text().includes("LivePushToasts") ||
      msg.text().includes("[usePushSync]")
    ) {
      // eslint-disable-next-line no-console
      console.log(
        `[console:${msg.type()}] ${msg.text()}${location?.url ? ` (${location.url})` : ""}`
      )
    }
  })

  // ── Contract validation hook (Phase 3 QA) ─────────────────────────────────
  // Validates every API JSON response observed by the page against openapi.json.
  // Also validates request bodies for mutation methods via postData().
  // Disabled when CONTRACT_VALIDATION_DISABLED=1 (e.g. in draft PR environments
  // where the schema and mocks may temporarily be out of sync).
  if (process.env["CONTRACT_VALIDATION_DISABLED"] !== "1") {
    page.on("response", async (response) => {
      const url = new URL(response.url())
      const path = url.pathname
      const method = response.request().method().toUpperCase()

      // Only validate backend API paths
      if (!path.startsWith("/api/")) return

      const contentType = response.headers()["content-type"] ?? ""

      // ── Validate response body ────────────────────────────────────────────
      if (contentType.includes("application/json")) {
        const body: unknown = await response.json().catch(() => null)
        if (body !== null) {
          validateResponseBody({
            path,
            method,
            statusCode: response.status(),
            body,
          })
        }
      }

      // ── Validate request body for mutations ───────────────────────────────
      // postData() returns the raw request body string sent by the page.
      // This gives us request schema coverage without needing a separate
      // route intercept.
      if (["POST", "PUT", "PATCH"].includes(method)) {
        const requestContentType = response.request().headers()["content-type"] ?? ""
        if (requestContentType.includes("application/json")) {
          const postData = response.request().postData()
          if (postData) {
            try {
              const requestBody: unknown = JSON.parse(postData)
              validateRequestBody({ path, method, body: requestBody })
            } catch (parseError) {
              // JSON.parse failure means the body was not valid JSON —
              // surface as a warning so the response-level error stays primary.
              console.warn(
                "[ContractValidator] Could not parse request body for",
                method,
                path,
                parseError
              )
            }
          }
        }
      }
      // Errors from validateResponseBody / validateRequestBody propagate
      // naturally as unhandled Promise rejections, which Playwright surfaces
      // as test failures via its default unhandledRejection listener.
    })
  }

  await page.context().route("**/*", async (requestRoute) => {
    const request = requestRoute.request()
    const url = new URL(request.url())
    const method = request.method().toUpperCase()
    const requestOrigin = request.headers()["origin"]
    const corsHeaders: Record<string, string> = requestOrigin
      ? {
          "Access-Control-Allow-Origin": requestOrigin,
          "Access-Control-Allow-Credentials": "true",
          "Access-Control-Allow-Headers":
            request.headers()["access-control-request-headers"] ??
            "Authorization, Content-Type, X-CSRF-Token, X-Requested-With, Traceparent, Tracestate, Baggage",
          "Access-Control-Allow-Methods":
            request.headers()["access-control-request-method"] ??
            "GET, POST, PUT, PATCH, DELETE, OPTIONS",
          Vary: "Origin",
        }
      : {}
    const fulfill = async (options: Parameters<typeof requestRoute.fulfill>[0] = {}) =>
      requestRoute.fulfill({
        ...options,
        headers: {
          ...(options.headers ?? {}),
          ...corsHeaders,
        },
      })
    const route = {
      request: () => request,
      fulfill,
      abort: (error?: Parameters<typeof requestRoute.abort>[0]) => requestRoute.abort(error),
      continue: (options?: Parameters<typeof requestRoute.continue>[0]) =>
        requestRoute.continue(options),
    }

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
    // Normalize both the browser-relative `/api/v1/...` form and the CI
    // service-host `http://api/v1/...` form to the same mock path.
    const normPath = pathname.replace(/^api\/v1\//u, "api/").replace(/^v1\//u, "api/")
    // Production E2E builds use the explicit `/api/v1` Axios base (and the
    // service-host compatibility form `/v1/...` handled above). Do not
    // reinterpret arbitrary bare fetch/XHR paths as API calls: TanStack
    // Router uses fetch for client route data such as `/dashboard`, and
    // turning that navigation into `api/dashboard` returns `{}` from the
    // generic mock instead of allowing the real SSR/SPA response through.
    const isBackendRequest = normPath.startsWith("api/") || normPath.startsWith("auth/")

    if (method === "OPTIONS" && isBackendRequest) {
      await route.fulfill({ status: 204 })
      return
    }

    // Development module URLs such as `/src/api/news.ts` contain API-like
    // substrings but are frontend assets, not backend requests.
    if (!isBackendRequest) {
      await route.continue()
      return
    }

    if (
      (state.offline || (state.newsOffline && normPath.includes("api/news"))) &&
      isBackendRequest
    ) {
      // eslint-disable-next-line no-console
      console.log(`[mock] Simulating OFFLINE for ${normPath}`)

      await route.abort("failed")
      return
    }

    // --- Authentication ---
    if (normPath.includes("auth/login")) {
      const postData = route.request().postData() ?? ""
      const headers = route.request().headers()
      let username = ""

      try {
        if ((headers["content-type"] ?? "").includes("application/json")) {
          const parsed = JSON.parse(postData)
          username = parsed.username || parsed.email || ""
        } else {
          const params = new URLSearchParams(postData)
          username = params.get("username") || params.get("email") || ""
        }
      } catch {
        // ignore
      }

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
          sessionId: "session-84",
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
        const authHeader = request.headers()["authorization"] || request.headers()["Authorization"]
        const cookieHeader = request.headers()["cookie"] || request.headers()["Cookie"] || ""
        const hasAuth =
          state.loggedIn ||
          Boolean(authHeader && authHeader.toLowerCase().includes("bearer")) ||
          cookieHeader.includes(SSR_E2E_AUTH_COOKIE)
        if (!hasAuth) {
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
          body: JSON.stringify(state.profile),
        })
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
      const interactionsMatch = normPath.match(/^api\/news\/([a-zA-Z0-9-]+)\/interactions$/u)
      if (interactionsMatch) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            likes_count: 0,
            is_liked: false,
            comments: [],
            comments_count: 0,
          }),
        })
        return
      }

      const detailMatch = normPath.match(/^api\/news\/([a-zA-Z0-9-]+)$/u)
      if (detailMatch) {
        const id = detailMatch[1]
        const entry = mockNews.find((newsItem) => newsItem.id === id)
        if (!entry) {
          await route.fulfill({
            status: 404,
            contentType: "application/json",
            body: JSON.stringify({ detail: "News item not found" }),
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

      const ifNoneMatch = request.headers()["if-none-match"] || request.headers()["If-None-Match"]
      const is304 = ifNoneMatch === state.newsVersion
      // eslint-disable-next-line no-console
      console.log(
        `[mock] News request: If-None-Match="${ifNoneMatch}", state.newsVersion="${state.newsVersion}", is304=${is304}`
      )

      state.newsLog.push({
        header: ifNoneMatch,
        status: is304 ? 304 : 200,
      })

      if (is304) {
        // Playwright rejects route.fulfill({ status: 304 }) because 304 is a
        // browser-generated cache status, not a response that can carry a
        // fulfilled body. Preserve the conditional-hit assertion in state,
        // and return the same JSON representation with the ETag so the client
        // still exercises its conditional request path without an unsupported
        // network primitive.
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: {
            "Access-Control-Expose-Headers": "ETag",
            ETag: state.newsVersion,
            "Cache-Control": "no-cache",
          },
          body: JSON.stringify({
            items: mockNews,
            has_more: false,
            next_cursor: null,
          }),
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
        contentType: "application/json",
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Credentials": "true",
          "Access-Control-Expose-Headers": "ETag",
          ETag: state.newsVersion,
          "Cache-Control": "no-cache",
        },
        body: JSON.stringify({
          items: localized,
          has_more: false,
          next_cursor: null,
        }),
      })
      return
    }

    // --- Events ---
    if (normPath.includes("api/events")) {
      const detailMatch = normPath.match(/api\/events\/(uuid-\d+)/)
      if (detailMatch) {
        const eventId = detailMatch[1]
        const ev = mockEvents.find((e) => e.id === eventId)
        if (ev) {
          const locale = (request.headers()["accept-language"] || "").startsWith("en") ? "en" : "ru"
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              ...ev,
              title: locale === "en" ? ev.title_en : ev.title,
              description: locale === "en" ? ev.description_en : ev.description,
            }),
          })
          return
        }
      }

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
        body: JSON.stringify([{ id: "uuid-1", name: "ИУ-21", faculty: "ИТ" }]),
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
        const idMatch = normPath.match(/sessions\/([a-zA-Z0-9-]+)/)
        if (idMatch) {
          const id = idMatch[1]
          const session = state.sessions.find((s) => String(s.id) === id)
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

    if (normPath.includes("auth/mfa/totp/start")) {
      const secret = MOCK_TOTP_SECRET
      const enrollment: MfaTotpEnrollment = {
        id: `uuid-${state.totp.nextId++}`,
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
      if (code === "000000" || code === "INVALID-RECOVERY") {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Неверный код" }),
        })
        return
      }
      state.loggedIn = true
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

    if (normPath.includes("auth/mfa/totp")) {
      await route.fulfill({ status: 200, body: JSON.stringify(state.totp.enrollments) })
      return
    }

    if (normPath.includes("auth/session/signing-key")) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          key: "mock-key-123",
          expires_at: new Date(Date.now() + ONE_HOUR_MS).toISOString(),
        }),
      })
      return
    }

    if (normPath.includes("auth/mfa/challenge")) {
      await route.fulfill({ status: 200, body: JSON.stringify(state.mfa.stepUpChallenge) })
      return
    }

    // The chat hook requests its upgrade ticket outside the /api/v1 prefix.
    // Keep the E2E session fully mocked so the preview's /ws proxy cannot
    // answer with a 403 and trigger reconnect/auth-error side effects.
    if (normPath === "ws/ticket") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ticket: "mock-ws-ticket", expires_in: 15 }),
      })
      return
    }

    // --- Stories ---
    if (normPath.includes("api/stories")) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          items: [
            {
              id: "uuid-1",
              user_id: "uuid-1",
              type: "image",
              url: "/fallbacks/placeholder.png",
              thumbnail_url: "/fallbacks/placeholder.png",
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
      const authHeader = request.headers()["authorization"] || request.headers()["Authorization"]
      const cookieHeader = request.headers()["cookie"] || request.headers()["Cookie"] || ""
      const hasAuth =
        state.loggedIn ||
        Boolean(authHeader && authHeader.toLowerCase().includes("bearer")) ||
        cookieHeader.includes(SSR_E2E_AUTH_COOKIE)
      if (!hasAuth) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        })
        return
      }
      if (state.profile.role !== "admin") {
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Forbidden" }),
        })
        return
      }

      if (normPath.includes("retry")) {
        const body = route.request().postDataJSON() as { job_ids?: unknown }
        const jobIds = Array.isArray(body.job_ids) ? body.job_ids : []
        const uniqueJobIds = new Set(jobIds)
        const selectionIsValid =
          jobIds.length >= 1 &&
          jobIds.length <= 100 &&
          uniqueJobIds.size === jobIds.length &&
          jobIds.every((id) => state.deadLetterJobs.some((job) => job.id === id))
        if (!selectionIsValid) {
          await route.fulfill({
            status: jobIds.length >= 1 && jobIds.length <= 100 ? 409 : 422,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Dead-letter selection is stale" }),
          })
          return
        }
        state.deadLetterJobs = state.deadLetterJobs.filter((job) => !uniqueJobIds.has(job.id))
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            affected_count: jobIds.length,
            job_ids: jobIds,
          }),
        })
        return
      }
      if (normPath.includes("purge")) {
        const body = route.request().postDataJSON() as { job_ids?: unknown }
        const jobIds = Array.isArray(body.job_ids) ? body.job_ids : []
        const uniqueJobIds = new Set(jobIds)
        const selectionIsValid =
          jobIds.length >= 1 &&
          jobIds.length <= 100 &&
          uniqueJobIds.size === jobIds.length &&
          jobIds.every((id) => state.deadLetterJobs.some((job) => job.id === id))
        if (!selectionIsValid) {
          await route.fulfill({
            status: jobIds.length >= 1 && jobIds.length <= 100 ? 409 : 422,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Dead-letter selection is stale" }),
          })
          return
        }
        state.deadLetterJobs = state.deadLetterJobs.filter((job) => !uniqueJobIds.has(job.id))
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            affected_count: jobIds.length,
            job_ids: jobIds,
          }),
        })
        return
      }

      const limit = Number(url.searchParams.get("limit") ?? "20")
      const offset = Number(url.searchParams.get("offset") ?? "0")
      if (
        !Number.isSafeInteger(limit) ||
        limit < 1 ||
        limit > 100 ||
        !Number.isSafeInteger(offset) ||
        offset < 0 ||
        offset > 10_000
      ) {
        await route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Validation error" }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: state.deadLetterJobs.slice(offset, offset + limit),
          total: state.deadLetterJobs.length,
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
          next_cursor: null,
        }),
      })
      return
    }

    // --- Catch-all for API/Auth to prevent external hits during tests ---

    if (normPath.startsWith("api/") || normPath.startsWith("auth/")) {
      // eslint-disable-next-line no-console
      console.log(`[mock] Generic 200 for unhandled path: ${normPath}`)
      await route.fulfill({ status: 200, body: "{}" })
      return
    }

    await route.continue()
  })

  return {
    state,
    async login(p: Page) {
      state.loggedIn = true
      await p.context().addCookies([{ name: SSR_E2E_AUTH_COOKIE, value: "mock", url: e2eOrigin }])
      // Start from the public route. The mock session is installed by the
      // init script before navigation, so AuthProvider performs the normal
      // client-side redirect to /dashboard without a second SSR navigation.
      // Navigating / -> /dashboard directly can leave the preview's protected
      // SSR request pending under CI load.
      await p.goto("/login", { waitUntil: "commit", timeout: 45_000 })
      await expect(p).toHaveURL(/\/dashboard$/, { timeout: 45_000 })
    },
    async setOffline(p: Page, offline: boolean) {
      state.offline = offline
      await p.context().setOffline(offline)
    },
    async setApiOffline(offline: boolean) {
      state.offline = offline
    },
    async setNewsOffline(offline: boolean) {
      state.newsOffline = offline
    },
  }
}
