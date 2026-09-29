import type { ImgHTMLAttributes } from "react"
import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  language: "en",
  namespaces: [] as unknown[],
  heroId: null as string | null,
  clearNewsHeroId: vi.fn(),
  formatRelativeTime: vi.fn((value: string, locale?: string) => `relative:${value}:${locale}`),
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: unknown) => {
    mocks.namespaces.push(namespaces)
    return {
      t: (key: string) => key,
      i18n: { language: mocks.language, changeLanguage: () => Promise.resolve() },
    }
  },
}))
vi.mock("@/utils/date", () => ({
  getMoscowDate: (value: string) => `moscow:${value}`,
  formatRelativeTime: mocks.formatRelativeTime,
}))
vi.mock("@/utils/newsTransition", () => ({
  getNewsHeroId: () => mocks.heroId,
  clearNewsHeroId: mocks.clearNewsHeroId,
}))
vi.mock("@/components/media/SmartImage", () => ({
  default: ({
    srcRaw,
    alt,
    ...rest
  }: { srcRaw?: string } & ImgHTMLAttributes<HTMLImageElement>) => (
    <img src={srcRaw ?? ""} alt={alt ?? ""} {...rest} />
  ),
}))
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => true }))

import NewsCardHero from "@/components/news/NewsCardHero"

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)"
const observers: Array<{ options?: IntersectionObserverInit; observe: ReturnType<typeof vi.fn> }> =
  []

class RecordingIntersectionObserver {
  readonly root = null
  readonly rootMargin = ""
  readonly thresholds: number[] = []
  observe = vi.fn()
  disconnect = vi.fn()
  unobserve = vi.fn()
  takeRecords = () => []

  constructor(_callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
    observers.push({ options, observe: this.observe })
  }
}

const stubReducedMotion = (reduced: boolean) => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({ matches: reduced && query === REDUCED_MOTION_QUERY }))
  )
}

beforeEach(() => {
  mocks.language = "en"
  mocks.namespaces.length = 0
  mocks.heroId = null
  mocks.clearNewsHeroId.mockReset()
  mocks.formatRelativeTime.mockClear()
  observers.length = 0
  vi.stubGlobal("IntersectionObserver", RecordingIntersectionObserver)
  stubReducedMotion(false)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const CREATED = "2026-01-15T10:00:00.000Z"
const LATER = "2026-02-20T08:30:00.000Z"

describe("NewsCardHero lifecycle", () => {
  it("loads the news and common namespaces", () => {
    render(<NewsCardHero created_at={CREATED} />)
    expect(mocks.namespaces.at(-1)).toEqual(["news", "common"])
  })

  it("follows image and date changes from the parent", () => {
    const { rerender } = render(
      <NewsCardHero image_url="https://example.test/a.png" title="Hero" created_at={CREATED} />
    )
    expect(screen.getByRole("img")).toHaveAttribute("src", "https://example.test/a.png")

    rerender(
      <NewsCardHero image_url="https://example.test/b.png" title="Hero" created_at={LATER} />
    )

    expect(screen.getByRole("img")).toHaveAttribute("src", "https://example.test/b.png")
    const time = screen.getByText(`relative:${LATER}:en-US`)
    expect(time).toHaveAttribute("datetime", LATER)
    expect(time).toHaveAttribute("title", `moscow:${LATER}`)
  })

  it("formats the relative date with the English locale outside Russian", () => {
    render(<NewsCardHero created_at={CREATED} />)
    expect(mocks.formatRelativeTime).toHaveBeenCalledWith(CREATED, "en-US")
    expect(mocks.formatRelativeTime).not.toHaveBeenCalledWith(CREATED, "ru-RU")
  })

  it("renders no date element at all when the creation date is missing", () => {
    const { container } = render(<NewsCardHero created_at="" />)
    expect(container.querySelector("time")).toBeNull()
  })

  it("does not claim the back-navigation transition without a card id", () => {
    mocks.heroId = ""
    const { container } = render(<NewsCardHero id="" created_at={CREATED} />)

    expect((container.firstElementChild as HTMLElement).style.viewTransitionName).toBe("")
    expect(mocks.clearNewsHeroId).not.toHaveBeenCalled()
  })

  it("claims the back-navigation transition when the card id starts matching", () => {
    mocks.heroId = "card-b"
    const { container, rerender } = render(<NewsCardHero id="card-a" created_at={CREATED} />)
    const root = container.firstElementChild as HTMLElement
    expect(root.style.viewTransitionName).toBe("")

    rerender(<NewsCardHero id="card-b" created_at={CREATED} />)

    expect(root.style.viewTransitionName).toBe("news-hero")
    expect(mocks.clearNewsHeroId).toHaveBeenCalledOnce()
  })

  it("drops the transition name and its pending timer when unmounted early", () => {
    vi.useFakeTimers()
    mocks.heroId = "card-a"
    const { container, unmount } = render(<NewsCardHero id="card-a" created_at={CREATED} />)
    const root = container.firstElementChild as HTMLElement
    expect(root.style.viewTransitionName).toBe("news-hero")

    unmount()

    expect(root.style.viewTransitionName).toBe("")
    expect(vi.getTimerCount()).toBe(0)
  })

  it("starts no parallax observer without an image", () => {
    render(<NewsCardHero created_at={CREATED} />)
    expect(observers).toHaveLength(0)
  })

  it("starts parallax once an image arrives, observing quarter visibility steps", () => {
    const { container, rerender } = render(<NewsCardHero created_at={CREATED} />)
    expect(observers).toHaveLength(0)

    rerender(<NewsCardHero image_url="https://example.test/a.png" created_at={CREATED} />)

    expect(observers).toHaveLength(1)
    expect(observers[0]!.options).toEqual({ threshold: [0, 0.25, 0.5, 0.75, 1] })
    expect(observers[0]!.observe).toHaveBeenCalledWith(container.firstElementChild)
  })

  it("skips parallax only for the reduced-motion media query", () => {
    stubReducedMotion(true)
    render(<NewsCardHero image_url="https://example.test/a.png" created_at={CREATED} />)

    expect(window.matchMedia).toHaveBeenCalledWith(REDUCED_MOTION_QUERY)
    expect(observers).toHaveLength(0)
  })

  it("keeps the timer-driven name cleanup when the transition completes", () => {
    vi.useFakeTimers()
    mocks.heroId = "card-a"
    const { container } = render(<NewsCardHero id="card-a" created_at={CREATED} />)

    act(() => {
      vi.runOnlyPendingTimers()
    })

    expect((container.firstElementChild as HTMLElement).style.viewTransitionName).toBe("")
  })
})
