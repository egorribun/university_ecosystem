import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && "title" in opts ? `${key}:${String(opts.title)}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}))

import { NewsCardList } from "@/components/dashboard/NewsCardList"
import type { NewsItem } from "@/api/news"

const NEWS = [
  {
    id: "n1",
    title: "Открытие новой лаборатории",
    content:
      "Очень длинный текст новости, который точно превышает сто десять символов, чтобы покрыть ветку усечения с многоточием в конце предложения.",
    created_at: "2026-01-15T10:00:00.000Z",
  },
  {
    id: "n2",
    title: "Короткая новость",
    content: "Коротко.",
    created_at: "2026-01-10T09:00:00.000Z",
  },
] as unknown as NewsItem[]

describe("NewsCardList", () => {
  beforeEach(() => {
    mockNavigate.mockClear()
  })

  it("renders skeleton placeholders while loading", () => {
    const { container } = render(<NewsCardList news={[]} loading locale="en" />)
    expect(container.querySelector('[role="presentation"]')).toBeInTheDocument()
    // No interactive news rows during loading.
    expect(screen.queryByRole("list")).not.toBeInTheDocument()
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("renders the empty-state message when there is no news and not loading", () => {
    render(<NewsCardList news={[]} loading={false} locale="en" />)
    expect(screen.getByText("dashboard:news.empty")).toBeInTheDocument()
    expect(screen.queryByRole("list")).not.toBeInTheDocument()
  })

  it("renders one row per news item with truncated long content", () => {
    render(<NewsCardList news={NEWS} loading={false} locale="en" />)
    const items = screen.getAllByRole("button")
    expect(items).toHaveLength(NEWS.length)
    expect(screen.getByText(NEWS[0]!.title)).toBeInTheDocument()
    expect(screen.getByText(NEWS[1]!.title)).toBeInTheDocument()
    // Long content gets an ellipsis suffix.
    expect(screen.getByText(/…$/)).toBeInTheDocument()
    // Short content has no ellipsis.
    expect(screen.getByText("Коротко.")).toBeInTheDocument()
  })

  it("navigates to the news detail route when a row is clicked", async () => {
    const user = userEvent.setup()
    render(<NewsCardList news={NEWS} loading={false} locale="en" />)
    await user.click(screen.getByText(NEWS[0]!.title))
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/news/$id", params: { id: "n1" } })
  })

  it("falls back to empty string when content is missing", () => {
    const missing = [
      { id: "n3", title: "Без контента", created_at: "2026-01-01T00:00:00.000Z" },
    ] as unknown as NewsItem[]
    render(<NewsCardList news={missing} loading={false} locale="en" />)
    expect(screen.getByText("Без контента")).toBeInTheDocument()
    expect(screen.getByRole("button")).toBeInTheDocument()
  })
})
