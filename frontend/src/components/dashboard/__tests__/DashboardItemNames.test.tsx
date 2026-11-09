import { createElement, type ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { LazyMotion, domAnimation } from "framer-motion"
import { describe, expect, it, vi } from "vitest"
import { NewsCardList } from "../NewsCardList"
import { EventsCard } from "../EventsCard"
import type { NewsItem } from "@/api/news"
import { checkA11y } from "@/tests/axeTest"
import enDashboard from "@/i18n/locales/en/dashboard.json"
import ruDashboard from "@/i18n/locales/ru/dashboard.json"
import enCommon from "@/i18n/locales/en/common.json"
import ruCommon from "@/i18n/locales/ru/common.json"

const state = vi.hoisted(() => ({ language: "en", navigate: vi.fn() }))
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => state.navigate,
  Link: ({ children, to, ...props }: { children: ReactNode; to: string }) =>
    createElement("a", { href: to, ...props }, children),
}))
vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: state.language }),
}))
vi.mock("@/contexts/CampusTimezoneContext", () => ({ useCampusTimezone: () => "UTC" }))
vi.mock("@/hooks/useMinuteClock", () => ({
  useMinuteClock: () => Date.parse("2026-11-08T09:00:00Z"),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => true }))
vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => ({
    data: [
      {
        id: "event-1",
        title: "Open laboratory",
        starts_at: "2026-11-08T10:30:00Z",
        location: "Room 204",
      },
    ],
    isPending: false,
    isLoading: false,
    isFetching: false,
    isError: false,
  }),
  prefetchDashboardEvents: vi.fn(),
}))

async function renderLocalized(language: string, children: ReactNode) {
  state.language = language
  state.navigate.mockClear()
  const i18n = createInstance()
  await i18n.init({
    lng: language,
    fallbackLng: "en",
    resources: {
      en: { dashboard: enDashboard, common: enCommon },
      ru: { dashboard: ruDashboard, common: ruCommon },
    },
    interpolation: { escapeValue: false },
  })
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={new QueryClient()}>
        <LazyMotion features={domAnimation}>{children}</LazyMotion>
      </QueryClientProvider>
    </I18nextProvider>
  )
}

describe.each(["en", "ru"])("Dashboard item names in %s", (language) => {
  it("includes the news preview in the accessible name", async () => {
    const news = [
      {
        id: "news-1",
        title: "Campus research",
        content: "Join our laboratory tour.",
        created_at: "2026-11-08T10:30:00Z",
      },
    ] as NewsItem[]
    await renderLocalized(language, <NewsCardList news={news} loading={false} locale={language} />)
    const button = screen.getByRole("button")
    expect(button).toHaveAccessibleName("Campus research")
    expect(button).toHaveAccessibleDescription(
      language === "en"
        ? "Published on November 08, 2026 at 10:30 AM Join our laboratory tour."
        : "Опубликовано: 08 ноября 2026 г. в 10:30 Join our laboratory tour."
    )
    fireEvent.click(button)
    expect(state.navigate).toHaveBeenCalledWith({ to: "/news/$id", params: { id: "news-1" } })
  })

  it("includes event time and location after the title", async () => {
    await renderLocalized(language, <EventsCard />)
    const button = screen.getByText("Open laboratory").closest("button")!
    expect(button).toHaveAccessibleName("Open laboratory")
    expect(button).toHaveAccessibleDescription(
      language === "en"
        ? "Published on November 08, 2026 at 10:30 AM 10:30 Room 204"
        : "Опубликовано: 08 ноября 2026 г. в 10:30 10:30 Room 204"
    )
    fireEvent.click(button)
    expect(state.navigate).toHaveBeenCalledWith({ to: "/events/$id", params: { id: "event-1" } })
  })

  it.each([undefined, "invalid-date"])(
    "keeps an unavailable date as a localized description (%s)",
    async (createdAt) => {
      const news = [
        { id: "unknown", title: "Campus research", content: "", created_at: createdAt },
      ] as NewsItem[]
      await renderLocalized(
        language,
        <NewsCardList news={news} loading={false} locale={language} />
      )
      const button = screen.getByRole("button")
      expect(button).toHaveAccessibleName("Campus research")
      expect(button).toHaveAccessibleDescription(
        language === "en" ? "Date unavailable" : "Дата недоступна"
      )
    }
  )

  it("keeps description targets unique for multiple rows and repeated lists", async () => {
    const first = {
      id: "same-id",
      title: "First bulletin",
      content: "First preview",
      created_at: "2026-11-08T10:30:00Z",
    } as NewsItem
    const second = {
      ...first,
      id: "second-id",
      title: "Second bulletin",
      created_at: "2026-11-09T11:45:00Z",
    }
    await renderLocalized(
      language,
      <main>
        <NewsCardList news={[first, second]} loading={false} locale={language} />
        <NewsCardList news={[first]} loading={false} locale={language} />
        <EventsCard />
      </main>
    )
    const rows = screen
      .getAllByRole("button")
      .filter((button) => button.hasAttribute("aria-describedby"))
    expect(rows).toHaveLength(4)
    await checkA11y(document.body.querySelector("main")!)
    // Each row lists its date tooltip first, then its excerpt or metadata.
    const ids = rows.map((button) => button.getAttribute("aria-describedby")!.split(" ")[0])
    expect(new Set(ids).size).toBe(4)
    expect(rows[0]).toHaveAccessibleDescription(
      language === "en"
        ? "Published on November 08, 2026 at 10:30 AM First preview"
        : "Опубликовано: 08 ноября 2026 г. в 10:30 First preview"
    )
    expect(rows[1]).toHaveAccessibleDescription(
      language === "en"
        ? "Published on November 09, 2026 at 11:45 AM First preview"
        : "Опубликовано: 09 ноября 2026 г. в 11:45 First preview"
    )
    for (const id of ids) {
      const target = document.getElementById(id!)!
      expect(target).not.toBeVisible()
      expect(target).toHaveAttribute("role", "tooltip")
    }
  })
})
