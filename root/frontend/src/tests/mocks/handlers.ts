import { HttpResponse, http } from "msw"
import type { User } from "@/types/User"
import type { ActiveSession } from "@/types/Session"
import type { Event } from "@/types/Event"

type NewUserPayload = {
  email?: string
  [key: string]: unknown
}

type ResetPasswordPayload = {
  token?: string
  [key: string]: unknown
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

export const handlers = [
  http.get("*/auth/session/signing-key", () =>
    HttpResponse.json({ signing_key: "test-session-signing-key" })
  ),
  http.get("*/users/me", () => HttpResponse.json(testUser)),
  http.get("*/auth/sessions", () => HttpResponse.json(testSessions)),
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
