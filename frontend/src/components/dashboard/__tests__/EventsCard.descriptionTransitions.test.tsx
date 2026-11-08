import { createElement, type ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createInstance } from "i18next"
import { I18nextProvider } from "react-i18next"
import { LazyMotion, domAnimation } from "framer-motion"
import { describe, expect, it, vi } from "vitest"
import { EventsCard } from "../EventsCard"
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
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useDashboardEvents", () => ({
  useDashboardEvents: () => ({
    data: [
      {
        id: "event-1",
        title: "Open laboratory",
        starts_at: "2026-11-08T10:30:00Z",
        location: "Room 204",
      },
      {
        id: "event-2",
        title: "Tomorrow laboratory",
        starts_at: "2026-11-09T11:45:00Z",
        location: "Room 205",
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

describe("Event description references during animated transitions", () => {
  it("keeps exiting and entering scope rows uniquely linked to their dates", async () => {
    await renderLocalized("en", <EventsCard />)
    expect(document.querySelectorAll("[data-event-key]")).toHaveLength(1)

    fireEvent.click(screen.getByRole("button", { name: /week/i }))

    // Real AnimatePresence retains today's exiting row alongside both week rows.
    const rows = Array.from(document.querySelectorAll("[data-event-key]"))
    expect(rows.map((row) => row.getAttribute("data-event-key"))).toEqual([
      "today-event-1",
      "week-event-1",
      "week-event-2",
    ])
    // The first id in each row is its date tooltip; the second is the time and location.
    const dateIds = rows.map(
      (row) => row.querySelector("button")!.getAttribute("aria-describedby")!.split(" ")[0]
    )
    expect(new Set(dateIds).size).toBe(3)
    for (const row of rows) {
      const button = row.querySelector("button")!
      const [dateId, metaId] = button.getAttribute("aria-describedby")!.split(" ")
      const dateTargets = Array.from(document.querySelectorAll("[id]")).filter(
        (node) => node.id === dateId
      )
      expect(dateTargets).toHaveLength(1)
      expect(row.contains(dateTargets[0]!)).toBe(true)
      expect(dateTargets[0]).toHaveAttribute("hidden")
      const metaTargets = Array.from(document.querySelectorAll("[id]")).filter(
        (node) => node.id === metaId
      )
      expect(metaTargets).toHaveLength(1)
      expect(row.contains(metaTargets[0]!)).toBe(true)
      const isSecondWeekEvent = row.getAttribute("data-event-key") === "week-event-2"
      expect(button).toHaveAccessibleDescription(
        isSecondWeekEvent
          ? "Published on November 09, 2026 at 11:45 AM 11:45 Room 205"
          : "Published on November 08, 2026 at 10:30 AM 10:30 Room 204"
      )
    }
  })
})
