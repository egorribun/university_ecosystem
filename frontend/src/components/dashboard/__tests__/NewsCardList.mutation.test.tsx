import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const navigate = vi.hoisted(() => vi.fn())

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { title?: string }) =>
      options?.title ? `${key}:${options.title}` : key,
  }),
}))

vi.mock("lucide-react", () => ({
  ArrowRight: ({ className }: { className?: string }) => (
    <svg data-testid="news-arrow" className={className} />
  ),
}))

vi.mock("@/components/ui", () => ({
  Skeleton: () => <div data-testid="news-skeleton" />,
}))

vi.mock("@/components/dashboard/DateBullet", () => ({
  DateBullet: ({ date, locale }: { date: string; locale: string }) => (
    <time dateTime={date} data-locale={locale} />
  ),
}))

import { NewsCardList } from "@/components/dashboard/NewsCardList"
import type { NewsItem } from "@/api/news"

describe("NewsCardList mutation contracts", () => {
  it("keeps the truncation boundary ellipsis exact and navigates by item id", () => {
    const longContent = "x".repeat(111)
    render(
      <NewsCardList
        news={
          [
            {
              id: "news-1",
              title: "Long article",
              content: longContent,
              created_at: "2026-08-01T10:00:00.000Z",
            },
          ] as unknown as NewsItem[]
        }
        loading={false}
        locale="en"
      />
    )

    const button = screen.getByRole("button", { name: "dashboard:aria.newsItem:Long article" })
    const content = button.querySelector("span.text-sm.leading-relaxed")
    expect(content).not.toBeNull()
    expect(content?.textContent).toBe(`${longContent.slice(0, 110)}…`)
    expect(content?.textContent).not.toContain("Stryker was here!")

    button.click()
    expect(navigate).toHaveBeenCalledWith({ to: "/news/$id", params: { id: "news-1" } })
  })
})
