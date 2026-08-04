import { fireEvent, render, screen } from "@testing-library/react"
import type { ElementType, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const {
  dashboardNewsMock,
  prefetchDashboardNewsMock,
  queryClient,
} = vi.hoisted(() => ({
  dashboardNewsMock: vi.fn(),
  prefetchDashboardNewsMock: vi.fn(),
  queryClient: { id: "dashboard-query-client" },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en" }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => queryClient,
}))

vi.mock("@/hooks/useDashboardNews", () => ({
  useDashboardNews: dashboardNewsMock,
  prefetchDashboardNews: prefetchDashboardNewsMock,
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <a href="/news" {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/components/ui", () => ({
  Card: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => (
    <section data-testid="dashboard-news-card" {...props}>
      {children}
    </section>
  ),
  Button: ({
    as: Component = "button",
    children,
    ...props
  }: {
    as?: ElementType
    children?: ReactNode
  } & Record<string, unknown>) => <Component {...props}>{children}</Component>,
}))

vi.mock("@/components/dashboard/NewsCardList", () => ({
  NewsCardList: ({ news, loading, locale }: { news: unknown[]; loading: boolean; locale: string }) => (
    <div data-testid="dashboard-news-list" data-count={news.length} data-loading={String(loading)}>
      {locale}
    </div>
  ),
}))

vi.mock("@/components/dashboard/NewsCardBackground", () => ({
  NewsCardBackground: () => <div data-testid="dashboard-news-background" />,
}))

import { NewsCard } from "../NewsCard"

beforeEach(() => {
  vi.clearAllMocks()
  dashboardNewsMock.mockReturnValue({ data: undefined, isLoading: true, isFetching: true })
})

describe("dashboard NewsCard closure paths", () => {
  it("prefetches on pointer and all supported keyboard activation keys", () => {
    render(<NewsCard locale="en-US" className="custom" data-fade="in" />)

    const viewAll = screen.getByRole("link", { name: "dashboard:aria.viewAllNews" })
    expect(screen.getByTestId("dashboard-news-card")).toHaveAttribute("aria-busy", "true")
    expect(screen.getByTestId("dashboard-news-list")).toHaveAttribute("data-loading", "true")

    fireEvent.pointerDown(viewAll)
    fireEvent.keyDown(viewAll, { key: "Enter" })
    fireEvent.keyDown(viewAll, { key: " " })
    fireEvent.keyDown(viewAll, { key: "Spacebar" })
    fireEvent.keyDown(viewAll, { key: "Escape" })

    expect(prefetchDashboardNewsMock).toHaveBeenCalledTimes(4)
    expect(prefetchDashboardNewsMock).toHaveBeenLastCalledWith(queryClient, "en")
  })

  it("forwards populated/refetching query state and presentation props", () => {
    dashboardNewsMock.mockReturnValue({
      data: [{ id: "news-1" }],
      isLoading: false,
      isFetching: true,
    })

    render(
      <NewsCard
        locale="ru-RU"
        style={{ opacity: 0.8 }}
        data-pop="true"
      />
    )

    const card = screen.getByTestId("dashboard-news-card")
    expect(card).toHaveAttribute("aria-busy", "false")
    expect(card).toHaveAttribute("data-refetching", "true")
    expect(card).toHaveAttribute("data-pop", "true")
    expect(card).toHaveStyle({ opacity: "0.8" })
    expect(screen.getByTestId("dashboard-news-list")).toHaveAttribute("data-count", "1")
    expect(screen.getByTestId("dashboard-news-list")).toHaveTextContent("ru-RU")
  })
})
