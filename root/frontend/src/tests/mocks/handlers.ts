import { HttpResponse, http } from "msw"
import type { User } from "@/types/User"
import type { ActiveSession } from "@/types/Session"
import type { Event } from "@/types/Event"
import type {
  MfaMethod,
  MfaTotpEnrollment,
  MfaVerifyPayload,
  PendingMfaResponse,
  TotpEnrollmentStartResponse,
} from "@/types/Mfa"

type NewUserPayload = {
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
  cover_url: null,
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
  mfa_recovery_codes_generated_at: null,
  totp_enrollments: [],
  webauthn_credentials: [],
  recovery_codes: [],
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

type ChallengeOptions = {
  includeTotp?: boolean
  includeRecovery?: boolean
  includeWebAuthn?: boolean
  defaultMethod?: MfaMethod | null
  sessionId?: number | null
}

const createMfaChallenge = ({
  includeTotp = true,
  includeRecovery = false,
  includeWebAuthn = false,
  defaultMethod = includeTotp ? "totp" : includeWebAuthn ? "webauthn" : null,
  sessionId = 1,
}: ChallengeOptions = {}): PendingMfaResponse => {
  const methods: PendingMfaResponse["methods"] = []
  if (includeTotp) {
    methods.push({
      method: "totp",
      challenge_token: "totp-challenge-token",
      challenge_expires_at: createChallengeExpiresAt(),
      options: null,
    })
  }
  if (includeRecovery) {
    methods.push({
      method: "recovery",
      challenge_token: "recovery-challenge-token",
      challenge_expires_at: createChallengeExpiresAt(),
      options: null,
    })
  }
  if (includeWebAuthn) {
    methods.push({
      method: "webauthn",
      challenge_token: "webauthn-challenge-token",
      challenge_expires_at: createChallengeExpiresAt(),
      options: {
        challenge: "c2FtcGxlLXdlYmF1dGhuLWNoYWxsZW5nZQ==",
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
    user_id: testUser.id,
    session_id: sessionId,
    default_method: defaultMethod,
    methods,
  }
}

let totpDraft: TotpEnrollmentStartResponse | null = null
let totpEnrollmentCounter = 1
let loginChallenge: PendingMfaResponse | null = null
let stepUpChallenge: PendingMfaResponse | null = createMfaChallenge({
  includeTotp: true,
  includeWebAuthn: true,
  includeRecovery: true,
  sessionId: 42,
})

const resetUserEnrollments = () => {
  testUser.totp_enrollments.splice(0, testUser.totp_enrollments.length)
  testUser.webauthn_credentials.splice(0, testUser.webauthn_credentials.length)
  testUser.recovery_codes.splice(0, testUser.recovery_codes.length)
  testUser.mfa_challenges.splice(0, testUser.mfa_challenges.length)
}

export const resetTestMfa = () => {
  totpDraft = null
  totpEnrollmentCounter = 1
  loginChallenge = null
  stepUpChallenge = createMfaChallenge({
    includeTotp: true,
    includeWebAuthn: true,
    includeRecovery: true,
    sessionId: 42,
  })
  testUser.mfa_required = false
  testUser.mfa_default_method = null
  testUser.mfa_last_verified_at = null
  testUser.mfa_recovery_codes_generated_at = null
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
      about: null,
      about_en: null,
      files: [],
      participant_count: 0,
      is_registered: null,
      my_qr_code: null,
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
  http.get("*/users/me", () => HttpResponse.json(testUser)),
  http.get("*/auth/sessions", () => HttpResponse.json(testSessions)),
  http.get("*/auth/mfa/totp", () => HttpResponse.json(testUser.totp_enrollments)),
  http.post("*/auth/mfa/totp/start", async ({ request }) => {
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
    testUser.totp_enrollments.splice(0, testUser.totp_enrollments.length, confirmed)
    return HttpResponse.json(confirmed)
  }),
  http.delete("*/auth/mfa/totp/:id", ({ params }) => {
    const id = Number(params.id)
    const index = testUser.totp_enrollments.findIndex((entry) => entry.id === id)
    if (index === -1) {
      return HttpResponse.json({ detail: "Enrollment not found" }, { status: 404 })
    }
    const entry = testUser.totp_enrollments[index]!
    entry.is_active = false
    entry.revoked_at = nowIso()
    testUser.totp_enrollments.splice(index, 1)
    if (!testUser.totp_enrollments.length && testUser.mfa_default_method === "totp") {
      testUser.mfa_default_method = null
    }
    return HttpResponse.json({ disabled: true })
  }),
  http.post("*/auth/mfa/step-up", () => {
    if (!stepUpChallenge) {
      stepUpChallenge = createMfaChallenge({
        includeTotp: true,
        includeRecovery: true,
        includeWebAuthn: true,
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

    if (body.method === "webauthn") {
      if (!body.credential || typeof body.credential !== "object") {
        return HttpResponse.json({ detail: "Invalid credential" }, { status: 400 })
      }
    } else {
      const code = body.code?.toString().replace(/\s+/g, "") ?? ""
      if (code !== "123456" && !(body.method === "recovery" && code === "RECOVERY-1")) {
        return HttpResponse.json({ detail: "Invalid verification code" }, { status: 400 })
      }
    }

    testUser.mfa_last_verified_at = nowIso()
    if (body.method !== "recovery") {
      testUser.mfa_default_method = body.method
    }
    testUser.mfa_required = false

    if (matchedLogin) {
      loginChallenge = null
    }
    if (matchedStepUp) {
      stepUpChallenge = createMfaChallenge({
        includeTotp: true,
        includeRecovery: true,
        includeWebAuthn: true,
        sessionId: 42,
      })
    }

    return HttpResponse.json({ access_token: "test-access-token", token_type: "bearer" })
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
    const cursorRaw = Number(url.searchParams.get("cursor") ?? "")
    const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : 20
    const cursor = Number.isFinite(cursorRaw) && cursorRaw >= 0 ? cursorRaw : 0
    const slice = testEvents.slice(cursor, cursor + limit)
    const total = testEvents.length
    const nextCursor = cursor + slice.length
    const hasMore = nextCursor < total
    return HttpResponse.json({
      items: slice,
      total,
      limit,
      cursor,
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
  http.post("*/users", async ({ request }) => {
    const body = (await request.json()) as NewUserPayload
    if (body.email === "taken@example.com") {
      return HttpResponse.json({ detail: "Email already used" }, { status: 400 })
    }
    return HttpResponse.json({ id: 2, ...body }, { status: 201 })
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
        includeRecovery: true,
        defaultMethod: "totp",
        sessionId: 84,
      })
      testUser.mfa_required = true
      testUser.mfa_default_method = "totp"
      return HttpResponse.json(loginChallenge, { status: 202 })
    }

    if (username === "webauthn@example.com" && password === "Password123") {
      loginChallenge = createMfaChallenge({
        includeTotp: false,
        includeRecovery: false,
        includeWebAuthn: true,
        defaultMethod: "webauthn",
        sessionId: 96,
      })
      testUser.mfa_required = true
      testUser.mfa_default_method = "webauthn"
      return HttpResponse.json(loginChallenge, { status: 202 })
    }

    return HttpResponse.json({ access_token: "test-access-token", username })
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
