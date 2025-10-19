import { expect, type Page } from "@playwright/test"

type NewsLogEntry = {
  header: string | undefined
  status: number
}

type MockState = {
  loggedIn: boolean
  newsVersion: string
  offline: boolean
  newsLog: NewsLogEntry[]
  sessions: SessionMock[]
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

const mockUser = {
  id: 1,
  full_name: "Иван Иванов",
  role: "student",
  group_id: "iu-21",
}

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

const mockEvents = [
  {
    id: 10,
    title: "Хакатон ГУУ",
    title_en: "GUU Hackathon",
    description: "Командные соревнования по разработке.",
    description_en: "A collaborative coding challenge.",
    starts_at: "2025-01-05T09:00:00",
    location: "Актовый зал",
    location_en: "Assembly Hall",
    event_type: "хакатон",
    event_type_en: "Hackathon",
    about: null,
    about_en: null,
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

export async function useMockApi(page: Page) {
  const state: MockState = {
    loggedIn: false,
    newsVersion: '"news-v1"',
    offline: false,
    newsLog: [],
    sessions: createMockSessions(),
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
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(mockUser),
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockEvents),
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
      await currentPage.getByRole("button", { name: "Войти" }).click()
      await expect(currentPage).toHaveURL(/\/dashboard$/)
    },
  }
}

export type { MockState }
