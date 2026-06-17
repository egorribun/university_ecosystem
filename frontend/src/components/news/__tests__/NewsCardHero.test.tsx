import type { ImgHTMLAttributes } from "react"
import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { title?: string }) => (opts?.title ? `${key}:${opts.title}` : key),
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

// Deterministic date strings — formatRelativeTime is now-relative otherwise.
vi.mock("@/utils/date", () => ({
  getMoscowDate: (_v: string) => "15 January 2026",
  formatRelativeTime: (_v: string, _locale?: string) => "5 months ago",
}))

// View-transition store is a no-op for rendering — keep it inert.
vi.mock("@/utils/newsTransition", () => ({
  getNewsHeroId: () => null,
  clearNewsHeroId: vi.fn(),
}))

// SmartImage routes through media proxy utils — stub to a plain <img>
// that surfaces alt + LCP overrides + the parallax data attribute.
vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    srcRaw,
    alt,
    ...rest
  }: { srcRaw?: string } & ImgHTMLAttributes<HTMLImageElement>) => (
    <img src={srcRaw ?? ""} alt={alt ?? ""} data-testid="smart-image" {...rest} />
  ),
}))

const mockOnline = vi.fn(() => true)
vi.mock("@/hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => mockOnline(),
}))

import NewsCardHero from "@/components/news/NewsCardHero"

const FIXED_DATE = "2026-01-15T10:00:00.000Z"

beforeEach(() => {
  mockOnline.mockReturnValue(true)
})

describe("NewsCardHero", () => {
  it("renders the image, relative date badge and no offline indicator when online", () => {
    render(
      <NewsCardHero
        id="a-1"
        image_url="https://picsum.photos/seed/news/800/450"
        title="Big Story"
        created_at={FIXED_DATE}
      />
    )
    const img = screen.getByTestId("smart-image")
    expect(img).toHaveAttribute("alt", "news:alt.hero:Big Story")
    expect(img).toHaveAttribute("data-parallax-img")

    const time = screen.getByText("5 months ago")
    expect(time.tagName.toLowerCase()).toBe("time")
    expect(time).toHaveAttribute("dateTime", FIXED_DATE)
    expect(time).toHaveAttribute("title", "15 January 2026")

    expect(screen.queryByText("common:statuses.cached")).not.toBeInTheDocument()
  })

  it("uses the fallback alt when no title is provided", () => {
    render(
      <NewsCardHero image_url="https://picsum.photos/seed/x/800/450" created_at={FIXED_DATE} />
    )
    expect(screen.getByTestId("smart-image")).toHaveAttribute("alt", "news:alt.heroFallback")
  })

  it("shows the offline cached badge when offline", () => {
    mockOnline.mockReturnValue(false)
    render(
      <NewsCardHero
        image_url="https://picsum.photos/seed/news/800/450"
        title="Offline Story"
        created_at={FIXED_DATE}
      />
    )
    expect(screen.getByText("common:statuses.cached")).toBeInTheDocument()
  })

  it("renders the article-icon placeholder when there is no image_url", () => {
    const { container } = render(<NewsCardHero title="No Image" created_at={FIXED_DATE} />)
    expect(screen.queryByTestId("smart-image")).not.toBeInTheDocument()
    // Fallback icon container is present instead.
    expect(container.querySelector("svg")).not.toBeNull()
    // Date badge still renders.
    expect(screen.getByText("5 months ago")).toBeInTheDocument()
  })

  it("applies eager loading + high fetchpriority when priority is set", () => {
    render(
      <NewsCardHero
        image_url="https://picsum.photos/seed/news/800/450"
        title="LCP Story"
        created_at={FIXED_DATE}
        priority
      />
    )
    const img = screen.getByTestId("smart-image")
    expect(img).toHaveAttribute("loading", "eager")
    expect(img).toHaveAttribute("fetchpriority", "high")
  })

  it("does not set LCP overrides when priority is omitted", () => {
    render(
      <NewsCardHero
        image_url="https://picsum.photos/seed/news/800/450"
        title="Normal Story"
        created_at={FIXED_DATE}
      />
    )
    const img = screen.getByTestId("smart-image")
    expect(img).not.toHaveAttribute("loading", "eager")
    expect(img).not.toHaveAttribute("fetchpriority", "high")
  })

  it("sets the hero view-transition name when transitioning is true", () => {
    const { container } = render(
      <NewsCardHero
        id="a-2"
        image_url="https://picsum.photos/seed/news/800/450"
        title="Morphing Story"
        created_at={FIXED_DATE}
        transitioning
      />
    )
    const root = container.firstElementChild as HTMLElement | null
    expect(root).not.toBeNull()
    expect(root!.style.viewTransitionName).toBe("news-hero")
  })

  it("does not set a view-transition name when transitioning is omitted", () => {
    const { container } = render(
      <NewsCardHero
        id="a-3"
        image_url="https://picsum.photos/seed/news/800/450"
        title="Static Story"
        created_at={FIXED_DATE}
      />
    )
    const root = container.firstElementChild as HTMLElement | null
    expect(root).not.toBeNull()
    expect(root!.style.viewTransitionName).toBe("")
  })

  it("renders without a date badge when created_at is empty", () => {
    render(<NewsCardHero image_url="https://picsum.photos/seed/news/800/450" created_at="" />)
    expect(screen.queryByText("5 months ago")).not.toBeInTheDocument()
  })
})
