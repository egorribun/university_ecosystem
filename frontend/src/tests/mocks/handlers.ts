import { HttpResponse, http } from "msw"
import type { User } from "@/types/User"
import type { ActiveSession } from "@/types/Session"
import type { Event } from "@/types/Event"
import type { StoryItem } from "@/types/Story"
import type { NewsItem } from "@/api/news"
import type {
  MfaMethod,
  MfaTotpEnrollment,
  MfaVerifyPayload,
  PendingMfaResponse,
  TotpEnrollmentStartResponse,
} from "@/types/Mfa"

type RegisterPayload = {
  email?: string
  [key: string]: unknown
}

type ResetPasswordPayload = {
  token?: string
  [key: string]: unknown
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

export const testUser: User = {
  id: 1,
  email: "user@example.com",
  full_name: "Тестовый Пользователь",
  role: "student",
  group_id: null,
  avatar_url: null,
  avatar_url_optimized: null,
  cover_url: null,
  cover_url_optimized: null,
  about: null,
  record_book_number: null,
  status: null,
  institute: null,
  course: null,
  education_level: null,
  track: null,
  program: null,
  telegram: null,
  achievements: null,
  department: null,
  position: null,
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
}

const nowIso = () => new Date().toISOString()

const createTotpEnrollment = (overrides: Partial<MfaTotpEnrollment> = {}): MfaTotpEnrollment => {
  const createdAt = overrides.created_at ?? nowIso()
  return {
    id: overrides.id ?? Math.floor(Math.random() * 10_000) + 1,
    user_id: overrides.user_id ?? testUser.id,
    label: overrides.label ?? null,
    is_active: overrides.is_active ?? false,
    confirmed_at: overrides.confirmed_at ?? null,
    revoked_at: overrides.revoked_at ?? null,
    created_at: createdAt,
  }
}

const createChallengeExpiresAt = () => new Date(Date.now() + 5 * 60 * 1000).toISOString()

type ChallengeAttemptOverrides = {
  limit?: number | null
  count?: number
}

type ChallengeOptions = {
  includeTotp?: boolean
  defaultMethod?: MfaMethod | null
  sessionId?: number | null
  attempts?: Partial<Record<MfaMethod, ChallengeAttemptOverrides>>
}

const resolveAttemptMeta = (
  method: MfaMethod,
  overrides?: Partial<Record<MfaMethod, ChallengeAttemptOverrides>>
) => {
  const config = overrides?.[method]
  const defaultLimit = 5
  const limit =
    config && Object.prototype.hasOwnProperty.call(config, "limit")
      ? (config.limit ?? null)
      : defaultLimit
  const countRaw = config?.count ?? 0
  const count = Number.isFinite(countRaw) ? Math.max(0, Math.floor(countRaw)) : 0
  const remaining = typeof limit === "number" ? Math.max(limit - count, 0) : null
  return {
    attempt_limit: limit,
    attempt_count: count,
    remaining_attempts: remaining,
  }
}

const createMfaChallenge = ({
  includeTotp = true,
  defaultMethod = includeTotp ? "totp" : null,
  sessionId = 1,
  attempts,
}: ChallengeOptions = {}): PendingMfaResponse => {
  const methods: PendingMfaResponse["methods"] = []
  if (includeTotp) {
    const attemptMeta = resolveAttemptMeta("totp", attempts)
    methods.push({
      method: "totp",
      challenge_token: "totp-challenge-token",
      challenge_expires_at: createChallengeExpiresAt(),
      options: null,
      ...attemptMeta,
    })
  }
  return {
    status: "mfa_required",
    user_id: testUser.id,
    session_id: sessionId,
    default_method: defaultMethod,
    methods,
    challenges: methods,
  }
}

let totpDraft: TotpEnrollmentStartResponse | null = null
let totpEnrollmentCounter = 1
let loginChallenge: PendingMfaResponse | null = null
let stepUpChallenge: PendingMfaResponse | null = createMfaChallenge({
  includeTotp: true,
  sessionId: 42,
})

const resetUserEnrollments = () => {
  testUser.totp_enrollments!.splice(0, testUser.totp_enrollments!.length)
  testUser.mfa_challenges!.splice(0, testUser.mfa_challenges!.length)
}

export const resetTestMfa = () => {
  totpDraft = null
  totpEnrollmentCounter = 1
  loginChallenge = null
  stepUpChallenge = createMfaChallenge({
    includeTotp: true,
    sessionId: 42,
  })
  testUser.mfa_required = false
  testUser.mfa_default_method = null
  testUser.mfa_last_verified_at = null
  resetUserEnrollments()
}

const createBaseSessions = (): ActiveSession[] => {
  const now = Date.now()
  const currentIso = new Date(now).toISOString()
  return [
    {
      id: 1,
      user_id: 1,
      jti: "session-current",
      created_at: currentIso,
      expires_at: new Date(now + 60 * 60 * 1000).toISOString(),
      revoked_at: null,
      ip_address: "198.51.100.10",
      user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X)",
      last_seen_at: currentIso,
      mfa_required: false,
      mfa_completed_at: currentIso,
      mfa_method: null,
      mfa_verified_at: currentIso,
      is_current: true,
    },
    {
      id: 2,
      user_id: 1,
      jti: "session-secondary",
      created_at: new Date(now - 2 * 60 * 60 * 1000).toISOString(),
      expires_at: new Date(now + 2 * 60 * 60 * 1000).toISOString(),
      revoked_at: null,
      ip_address: "203.0.113.42",
      user_agent: "Safari/17.3 (iPhone; CPU iPhone OS)",
      last_seen_at: new Date(now - 10 * 60 * 1000).toISOString(),
      mfa_required: false,
      mfa_completed_at: currentIso,
      mfa_method: null,
      mfa_verified_at: currentIso,
      is_current: false,
    },
  ]
}

export const testSessions: ActiveSession[] = createBaseSessions()

export const resetTestSessions = () => {
  const fresh = createBaseSessions()
  testSessions.splice(0, testSessions.length, ...fresh)
}

const createBaseEvents = (): Event[] => {
  const now = Date.now()
  return Array.from({ length: 8 }, (_, index) => {
    const start = new Date(now + index * 24 * 60 * 60 * 1000)
    const end = new Date(start.getTime() + 90 * 60 * 1000)
    const isoStart = start.toISOString()
    const isoEnd = end.toISOString()
    const id = index + 1
    return {
      id,
      title: `Sample event ${id}`,
      description: `Event description ${id}`,
      title_en: `Sample event ${id}`,
      description_en: `Event description ${id}`,
      location: `Auditorium ${id}`,
      location_en: `Auditorium ${id}`,
      event_type: null,
      event_type_en: null,
      starts_at: isoStart,
      ends_at: isoEnd,
      created_by: 1,
      created_at: new Date(now - 60 * 60 * 1000).toISOString(),
      is_active: true,
      speaker: null,
      image_url: null,
      image_url_optimized: null,
      about: null,
      about_en: null,
      files: [],
      participant_count: 0,
      is_registered: null,
      my_qr_token: null,
    }
  })
}

export const testEvents: Event[] = createBaseEvents()

export const setTestEvents = (events: Event[]) => {
  testEvents.splice(0, testEvents.length, ...events)
}

export const resetTestEvents = () => {
  setTestEvents(createBaseEvents())
}

const createTestStories = (): StoryItem[] => {
  const now = new Date()
  return Array.from({ length: 4 }, (_, index) => {
    const id = index + 1
    const publishedAt = new Date(now.getTime() - index * 60 * 60 * 1000).toISOString()
    const expiresAt = new Date(now.getTime() + (index + 1) * 60 * 60 * 1000).toISOString()
    return {
      id,
      title: `Test story ${id}`,
      title_en: `Test story ${id}`,
      short_text: `Story preview ${id}`,
      short_text_en: `Story preview ${id}`,
      cover_url: null,
      cover_url_optimized: null,
      cta_url: null,
      published_at: publishedAt,
      expires_at: expiresAt,
      is_active: true,
      created_by: testUser.id,
      created_at: nowIso(),
    }
  })
}

const createTestNews = (): NewsItem[] => {
  const now = new Date()
  return Array.from({ length: 5 }, (_, index) => {
    const id = index + 1
    return {
      id,
      title: `News item ${id}`,
      content: `News content ${id}`,
      title_en: `News item ${id}`,
      content_en: `News content ${id}`,
      image_url: null,
      image_url_optimized: null,
      created_at: new Date(now.getTime() - index * 24 * 60 * 60 * 1000).toISOString(),
      likes_count: 0,
      comments_count: 0,
      is_liked: false,
    }
  })
}

export const testStories = createTestStories()
export const testNewsItems = createTestNews()

export const resetTestStories = () => {
  const stories = createTestStories()
  testStories.splice(0, testStories.length, ...stories)
}

export const resetTestNews = () => {
  const news = createTestNews()
  testNewsItems.splice(0, testNewsItems.length, ...news)
}

const createAdminDeadLetterJobs = (): AdminDeadLetterJob[] => [
  {
    id: 1,
    kind: "event",
    record_id: 1001,
    locale: "ru",
    enqueued_at: nowIso(),
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
    enqueued_at: nowIso(),
    claimed_at: null,
    attempts: 2,
    last_error: "Webhook failed",
    next_retry_at: null,
  },
]

const adminDeadLetterJobs: AdminDeadLetterJob[] = createAdminDeadLetterJobs()

const applyAdminQueueMutation = (jobIds: unknown) => {
  const ids = Array.isArray(jobIds) ? new Set(jobIds.map((id) => Number(id))) : new Set<number>()
  let removed = 0
  for (let index = adminDeadLetterJobs.length - 1; index >= 0; index -= 1) {
    const job = adminDeadLetterJobs[index]
    if (!job) continue
    if (ids.has(job.id)) {
      adminDeadLetterJobs.splice(index, 1)
      removed += 1
    }
  }
  return removed
}

export const resetAdminDeadLetterJobs = () => {
  adminDeadLetterJobs.splice(0, adminDeadLetterJobs.length, ...createAdminDeadLetterJobs())
}

resetTestMfa()

export const handlers = [
  http.get("*/auth/session/signing-key", () =>
    HttpResponse.json({ signing_key: "test-session-signing-key" })
  ),
  http.get("https://api.open-meteo.com/v1/forecast", () =>
    HttpResponse.json({
      current: {
        temperature_2m: 18.2,
        weather_code: 1,
        time: nowIso(),
      },
    })
  ),
  http.get("*/users/me", () => HttpResponse.json(testUser)),
  http.get("*/stories", () => HttpResponse.json(testStories)),
  http.get("*/news", () => HttpResponse.json(testNewsItems)),
  http.get("*/auth/sessions", () => HttpResponse.json(testSessions)),
  http.get("*/auth/mfa/totp", () => HttpResponse.json(testUser.totp_enrollments ?? [])),
  http.get("*/auth/mfa/webauthn", () => HttpResponse.json([])),
  http.post("*/auth/mfa/totp/start", async ({ request }) => {
    const hasActiveTotp = Boolean(
      testUser.totp_enrollments?.some((entry) => entry.confirmed_at && !entry.revoked_at)
    )
    if (hasActiveTotp) {
      return HttpResponse.json(
        {
          detail:
            "Only one authenticator app can be connected at a time. Remove the existing app to start over.",
        },
        { status: 400 }
      )
    }
    let payload: unknown = {}
    try {
      payload = await request.json()
    } catch {
      payload = {}
    }

    const label =
      payload &&
      typeof payload === "object" &&
      typeof (payload as { label?: unknown }).label === "string"
        ? ((payload as { label?: string }).label as string)
        : null

    const enrollment = createTotpEnrollment({
      id: totpEnrollmentCounter++,
      label,
      created_at: nowIso(),
    })
    const secret = "JBSW Y3DP EHJK"
    const otpauthUrl = `otpauth://totp/University:user?secret=${secret.replace(/\s+/g, "")}&issuer=University`
    totpDraft = { enrollment, secret, otpauth_url: otpauthUrl }
    return HttpResponse.json(totpDraft)
  }),
  http.post("*/auth/mfa/totp/confirm", async ({ request }) => {
    if (!totpDraft) {
      return HttpResponse.json({ detail: "No pending enrollment" }, { status: 400 })
    }

    const body = (await request.json().catch(() => null)) as {
      enrollment_id?: number
      code?: string
    } | null

    if (!body || body.enrollment_id !== totpDraft.enrollment.id) {
      return HttpResponse.json({ detail: "Enrollment not found" }, { status: 404 })
    }

    const code = (body.code ?? "").toString().replace(/\s+/g, "")
    if (code !== "123456") {
      return HttpResponse.json({ detail: "Invalid verification code" }, { status: 400 })
    }

    const confirmed = {
      ...totpDraft.enrollment,
      is_active: true,
      confirmed_at: nowIso(),
    }
    totpDraft = null
    testUser.mfa_default_method = "totp"
    testUser.mfa_last_verified_at = nowIso()
    testUser.mfa_required = false
    testUser.totp_enrollments!.splice(0, testUser.totp_enrollments!.length, confirmed)
    return HttpResponse.json(confirmed)
  }),
  http.delete("*/auth/mfa/totp/pending/:id", ({ params }) => {
    const id = Number(params.id)
    if (!totpDraft || totpDraft.enrollment.id !== id) {
      return HttpResponse.json({ detail: "Enrollment not found" }, { status: 404 })
    }
    totpDraft = null
    return HttpResponse.json(null, { status: 204 })
  }),
  http.delete("*/auth/mfa/totp/:id", ({ params }) => {
    const id = Number(params.id)
    const index = testUser.totp_enrollments!.findIndex((entry) => entry.id === id)
    if (index === -1) {
      return HttpResponse.json({ detail: "Enrollment not found" }, { status: 404 })
    }
    const entry = testUser.totp_enrollments![index]!
    entry.is_active = false
    entry.revoked_at = nowIso()
    testUser.totp_enrollments!.splice(index, 1)
    if (!(testUser.totp_enrollments?.length ?? 0) && testUser.mfa_default_method === "totp") {
      testUser.mfa_default_method = null
    }
    return HttpResponse.json({ disabled: true })
  }),
  http.post("*/auth/mfa/step-up", () => {
    if (!stepUpChallenge) {
      stepUpChallenge = createMfaChallenge({
        includeTotp: true,
        sessionId: 42,
      })
    }
    return HttpResponse.json(stepUpChallenge, { status: 202 })
  }),
  http.post("*/auth/mfa/verify", async ({ request }) => {
    const body = (await request.json().catch(() => null)) as MfaVerifyPayload | null
    if (!body || typeof body !== "object") {
      return HttpResponse.json({ detail: "Invalid payload" }, { status: 400 })
    }

    const matchChallenge = (challenge: PendingMfaResponse | null) =>
      Boolean(
        challenge?.methods.some(
          (method) =>
            method.method === body.method && method.challenge_token === body.challenge_token
        )
      )

    const matchedLogin = matchChallenge(loginChallenge)
    const matchedStepUp = matchChallenge(stepUpChallenge)

    if (!matchedLogin && !matchedStepUp) {
      return HttpResponse.json({ detail: "Challenge expired" }, { status: 400 })
    }

    const code = body.code?.toString().replace(/\s+/g, "") ?? ""
    if (code !== "123456") {
      return HttpResponse.json({ detail: "Invalid verification code" }, { status: 400 })
    }

    testUser.mfa_last_verified_at = nowIso()
    testUser.mfa_default_method = body.method
    testUser.mfa_required = false

    if (matchedLogin) {
      loginChallenge = null
    }
    if (matchedStepUp) {
      stepUpChallenge = createMfaChallenge({
        includeTotp: true,
        sessionId: 42,
      })
    }

    return HttpResponse.json({
      access_token: "test-access-token",
      token_type: "bearer",
      user: testUser,
      session: { signing_key: "test-session-key" },
    })
  }),
  http.delete("*/auth/sessions/:id", ({ params }) => {
    const id = Number(params.id)
    const session = testSessions.find((item) => item.id === id)
    if (!session) {
      return HttpResponse.json({ detail: "Session not found" }, { status: 404 })
    }
    const now = new Date().toISOString()
    session.revoked_at = now
    session.last_seen_at = now
    session.is_current = false
    return HttpResponse.json(session)
  }),
  http.get("*/events", ({ request }) => {
    const url = new URL(request.url)
    if (url.pathname.endsWith("/events/my")) {
      return HttpResponse.json(testEvents.slice(0, 3))
    }

    const limitRaw = Number(url.searchParams.get("limit") ?? "")
    const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : 20
    const cursorParam = url.searchParams.get("cursor")

    const decodeCursor = (value: string | null) => {
      if (!value) return null
      try {
        const payload = JSON.parse(value) as { id?: number; starts_at?: string }
        if (typeof payload?.id !== "number") return null
        if (payload.starts_at != null && typeof payload.starts_at !== "string") {
          return null
        }
        return payload
      } catch {
        return null
      }
    }

    const encodeCursor = (event: Event | undefined) =>
      event ? JSON.stringify({ id: event.id, starts_at: event.starts_at ?? null }) : null

    const decodedCursor = decodeCursor(cursorParam)

    const sortedEvents = [...testEvents].sort((a, b) => {
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

    return HttpResponse.json({
      items: slice,
      total,
      limit,
      cursor: decodedCursor ? cursorParam : null,
      next_cursor: hasMore ? nextCursor : null,
      has_more: hasMore,
    })
  }),
  http.get("*/notifications/admin/dead-letter", () =>
    HttpResponse.json({
      items: adminDeadLetterJobs,
      total: adminDeadLetterJobs.length,
    })
  ),
  http.post("*/notifications/admin/dead-letter/retry", async ({ request }) => {
    let payload: unknown
    try {
      payload = await request.json()
    } catch {
      payload = null
    }
    const jobIds = (payload as { job_ids?: unknown } | null)?.job_ids
    const removed = applyAdminQueueMutation(jobIds)
    return HttpResponse.json({ retried: removed })
  }),
  http.post("*/notifications/admin/dead-letter/purge", async ({ request }) => {
    let payload: unknown
    try {
      payload = await request.json()
    } catch {
      payload = null
    }
    const jobIds = (payload as { job_ids?: unknown } | null)?.job_ids
    const removed = applyAdminQueueMutation(jobIds)
    return HttpResponse.json({ deleted: removed })
  }),
  http.post("*/auth/register", async ({ request }) => {
    const body = (await request.json()) as RegisterPayload
    if (body.email === "taken@example.com") {
      return HttpResponse.json({ detail: "Email already used" }, { status: 400 })
    }
    return HttpResponse.json({ status: "ok", id: 2, ...body })
  }),
  http.post("*/auth/login", async ({ request }) => {
    const raw = await request.text()
    const payload = new URLSearchParams(raw)
    const username = payload.get("username") || ""
    const password = payload.get("password") || ""

    if (!username || !password || username === "blocked@example.com") {
      return HttpResponse.json({ detail: "Неверные данные для входа" }, { status: 401 })
    }

    if (username === "mfa@example.com" && password === "Password123") {
      loginChallenge = createMfaChallenge({
        includeTotp: true,
        defaultMethod: "totp",
        sessionId: 84,
      })
      testUser.mfa_required = true
      testUser.mfa_default_method = "totp"
      return HttpResponse.json(loginChallenge, { status: 202 })
    }

    return HttpResponse.json({
      access_token: "test-access-token",
      token_type: "bearer",
      user: testUser,
      session: { signing_key: "test-session-key" },
    })
  }),
  http.post("*/password/forgot", async () => HttpResponse.json({ ok: true })),
  http.post("*/password/reset", async ({ request }) => {
    const body = (await request.json()) as ResetPasswordPayload
    if (body.token === "expired-token") {
      return HttpResponse.json({ detail: "Ссылка устарела" }, { status: 400 })
    }
    return HttpResponse.json({ ok: true })
  }),
  http.get("*/spotify/auth-url", () =>
    HttpResponse.json({ url: "https://spotify.example/connect" })
  ),
  http.post("*/spotify/disconnect", () => HttpResponse.json({ ok: true })),
  http.get("*/spotify/now-playing", () =>
    HttpResponse.json({
      is_playing: false,
      item: null,
      progress_ms: 0,
    })
  ),
  http.get("https://api.pwnedpasswords.com/range/:prefix", () =>
    HttpResponse.text("0000000000000000000000000000000000000:2")
  ),
]
