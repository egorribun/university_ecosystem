import { fireEvent, render, screen } from "@testing-library/react"
import type { ElementType, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { dashboardNewsMock, prefetchDashboardNewsMock, queryClient } = vi.hoisted(() => ({
  dashboardNewsMock: vi.fn(),
  prefetchDashboardNewsMock: vi.fn(),
  queryClient: { id: "dashboard-query-client" },
}))
const useTranslationMock = vi.hoisted(() =>
  vi.fn((namespaces: string[]) => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    namespaces,
  }))
)

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
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
  NewsCardList: ({
    news,
    loading,
    locale,
  }: {
    news: unknown[]
    loading: boolean
    locale: string
  }) => (
    <div data-testid="dashboard-news-list" data-count={news.length} data-loading={String(loading)}>
      {locale}
    </div>
  ),
}))

vi.mock("@/components/dashboard/NewsCardBackground", () => ({
  NewsCardBackground: () => <div data-testid="dashboard-news-background" />,
}))

import { NewsCard, prepareOnKey } from "../NewsCard"

beforeEach(() => {
  vi.clearAllMocks()
  dashboardNewsMock.mockReturnValue({ data: undefined, isLoading: true, isFetching: true })
})

describe("dashboard NewsCard closure paths", () => {
  it("prefetches on pointer and all supported keyboard activation keys", () => {
    render(<NewsCard locale="en-US" className="custom" data-fade="in" />)

    const viewAll = screen.getByRole("link", { name: "dashboard:aria.viewAllNews" })
    const card = screen.getByTestId("dashboard-news-card")
    expect(useTranslationMock).toHaveBeenCalledWith(["dashboard", "common"])
    expect(card).toHaveClass(
      "group",
      "glass-noise",
      "refetch-shimmer",
      "dash-border-shimmer",
      "transition-all",
      "duration-base",
      "ease-back-out",
      "p-6",
      "md:p-7",
      "motion-reduce:hover:transform-none",
      "dash-panel-news",
      "custom"
    )
    expect(card).toHaveAttribute("aria-busy", "true")
    expect(screen.getByTestId("dashboard-news-list")).toHaveAttribute("data-loading", "true")
    expect(screen.getByText("dashboard:viewAll")).toBeInTheDocument()
    expect(screen.getByRole("heading")).toHaveTextContent("dashboard:news.heading")

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

    render(<NewsCard locale="ru-RU" style={{ opacity: 0.8 }} data-pop="true" />)

    const card = screen.getByTestId("dashboard-news-card")
    expect(card).toHaveAttribute("aria-busy", "false")
    expect(card).toHaveAttribute("data-refetching", "true")
    expect(card).toHaveAttribute("data-pop", "true")
    expect(card).toHaveStyle({ opacity: "0.8" })
    expect(screen.getByTestId("dashboard-news-list")).toHaveAttribute("data-count", "1")
    expect(screen.getByTestId("dashboard-news-list")).toHaveTextContent("ru-RU")
    expect(screen.getByRole("heading")).toHaveAttribute(
      "style",
      expect.stringContaining("font-size: clamp(1.35rem, 2.5vw, 1.75rem)")
    )
  })

  it("keeps cached news visible while loading and does not mark it refetching", () => {
    dashboardNewsMock.mockReturnValue({
      data: [{ id: "cached-news" }],
      isLoading: true,
      isFetching: true,
    })

    render(<NewsCard locale="en-US" />)

    expect(screen.getByTestId("dashboard-news-card")).toHaveAttribute("aria-busy", "false")
    expect(screen.getByTestId("dashboard-news-card")).toHaveAttribute("data-refetching", "false")
    expect(screen.getByTestId("dashboard-news-list")).toHaveAttribute("data-loading", "false")
    expect(screen.getByTestId("dashboard-news-list")).toHaveAttribute("data-count", "1")
  })

  it("absorbs a rejected route warmup while still prefetching dashboard data", async () => {
    vi.doMock("@/pages/News", () => {
      throw new Error("route chunk unavailable")
    })
    render(<NewsCard locale="en-US" />)

    fireEvent.pointerDown(screen.getByRole("link", { name: "dashboard:aria.viewAllNews" }))
    await vi.waitFor(() => expect(prefetchDashboardNewsMock).toHaveBeenCalledOnce())
  })

  it("supports the legacy Spacebar key and ignores unrelated keys", () => {
    const callback = vi.fn()

    prepareOnKey(new KeyboardEvent("keydown", { key: "Spacebar" }), callback)
    prepareOnKey(new KeyboardEvent("keydown", { key: "Escape" }), callback)

    expect(callback).toHaveBeenCalledOnce()
  })
})
