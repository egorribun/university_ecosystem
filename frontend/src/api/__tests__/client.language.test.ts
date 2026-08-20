import { describe, it, expect, beforeEach, afterEach } from "vitest"
import { http, HttpResponse } from "msw"
import api from "@/api/client"
import i18n from "@/i18n/config"
import { server } from "@/tests/mocks/server"
import type { PaginatedResponse } from "@/types/Pagination"

type NewsPayload = { id: number; title: string; content: string }
type EventPayload = { id: number; title: string; description: string }
type NotificationPayload = { id: number; message: string }

const isEnglishRequest = (request: Request) =>
  (request.headers.get("accept-language") ?? "").toLowerCase().startsWith("en")

const englishNews: NewsPayload[] = [
  { id: 1, title: "Campus renovation update", content: "Construction finishes this fall." },
]
const russianNews: NewsPayload[] = [
  { id: 1, title: "Обновление кампуса", content: "Строительство завершится осенью." },
]
const englishEvents: EventPayload[] = [
  { id: 1, title: "Career fair", description: "Meet top tech employers." },
]
const russianEvents: EventPayload[] = [
  { id: 1, title: "Ярмарка вакансий", description: "Встреча с ведущими работодателями." },
]
const englishNotifications: NotificationPayload[] = [
  { id: 1, message: "New grade posted in Calculus." },
]
const russianNotifications: NotificationPayload[] = [
  { id: 1, message: "Новая оценка по курсу 'Математический анализ'." },
]

describe("API language interceptor", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
  })

  afterEach(async () => {
    await i18n.changeLanguage("en")
  })

  it("requests English localized resources when the UI language is set to en", async () => {
    const observedLanguages: string[] = []

    server.use(
      http.get("*/news", ({ request }) => {
        const english = isEnglishRequest(request)
        observedLanguages.push(request.headers.get("accept-language") ?? "")
        return HttpResponse.json(english ? englishNews : russianNews)
      }),
      http.get("*/events", ({ request }) => {
        const english = isEnglishRequest(request)
        observedLanguages.push(request.headers.get("accept-language") ?? "")
        const payload = english ? englishEvents : russianEvents
        return HttpResponse.json({
          items: payload,
          total: payload.length,
          limit: payload.length,
          cursor: null,
          next_cursor: null,
          has_more: false,
        })
      }),
      http.get("*/notifications", ({ request }) => {
        const english = isEnglishRequest(request)
        observedLanguages.push(request.headers.get("accept-language") ?? "")
        return HttpResponse.json(english ? englishNotifications : russianNotifications)
      }),
      http.post("*/auth/login", async ({ request }) => {
        const english = isEnglishRequest(request)
        observedLanguages.push(request.headers.get("accept-language") ?? "")
        return HttpResponse.json(
          { detail: english ? "Invalid credentials" : "Неверные данные для входа" },
          { status: 401 }
        )
      })
    )

    const newsResponse = await api.get<NewsPayload[]>("/news")
    expect(newsResponse.data[0]!.title).toBe("Campus renovation update")

    const eventsResponse = await api.get<PaginatedResponse<EventPayload>>("/events")
    expect(eventsResponse.data.items[0]!.title).toBe("Career fair")

    const notificationsResponse = await api.get<NotificationPayload[]>("/notifications")
    expect(notificationsResponse.data[0]!.message).toBe("New grade posted in Calculus.")

    const loginResponse = await api.post<{ detail: string }>("/auth/login", new URLSearchParams(), {
      validateStatus: () => true,
    })
    expect(loginResponse.status).toBe(401)
    expect(loginResponse.data.detail).toBe("Invalid credentials")

    expect(new Set(observedLanguages)).toEqual(new Set(["en"]))
  })

  it("respects an explicit Accept-Language header override", async () => {
    server.use(
      http.get("*/news", ({ request }) =>
        HttpResponse.json([
          {
            id: 1,
            title: request.headers.get("accept-language") ?? "",
            content: "",
          },
        ])
      )
    )

    await i18n.changeLanguage("en")

    const response = await api.get<NewsPayload[]>("/news", {
      headers: { "Accept-Language": "ru" },
    })

    expect(response.data[0]!.title).toBe("ru")
  })

  it("falls back to the default locale for unsupported languages", async () => {
    const observedLanguages: string[] = []

    server.use(
      http.get("*/news", ({ request }) => {
        observedLanguages.push(request.headers.get("accept-language") ?? "")
        return HttpResponse.json(englishNews)
      })
    )

    await i18n.changeLanguage("kk")
    await api.get<NewsPayload[]>("/news")

    await i18n.changeLanguage("de")
    await api.get<NewsPayload[]>("/news")

    expect(observedLanguages).toEqual(["ru", "ru"])
  })
})
