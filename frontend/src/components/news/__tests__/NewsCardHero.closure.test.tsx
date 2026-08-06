import type { ImgHTMLAttributes } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { act } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { mockClearNewsHeroId, mockFormatRelativeTime, mockGetNewsHeroId, mockLanguage } = vi.hoisted(
  () => ({
    mockClearNewsHeroId: vi.fn(),
    mockFormatRelativeTime: vi.fn(() => "relative"),
    mockGetNewsHeroId: vi.fn(() => null as string | null),
    mockLanguage: { value: "en" },
  })
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: mockLanguage.value, changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/utils/date", () => ({
  getMoscowDate: () => "date",
  formatRelativeTime: mockFormatRelativeTime,
}))
vi.mock("@/utils/newsTransition", () => ({
  clearNewsHeroId: mockClearNewsHeroId,
  getNewsHeroId: mockGetNewsHeroId,
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

const props = {
  id: "hero-1",
  image_url: "https://example.test/hero.png",
  title: "Hero",
  created_at: "2026-01-15T10:00:00.000Z",
}

let intersectionCallback: IntersectionObserverCallback | null = null
const observe = vi.fn()
const disconnect = vi.fn()
const constructObserver = vi.fn()

class FakeIntersectionObserver {
  readonly root = null
  readonly rootMargin = ""
  readonly thresholds: number[] = []

  constructor(callback: IntersectionObserverCallback) {
    constructObserver()
    intersectionCallback = callback
  }

  observe = observe
  disconnect = disconnect
  unobserve = vi.fn()
  takeRecords = () => []
}

beforeEach(() => {
  mockClearNewsHeroId.mockReset()
  mockGetNewsHeroId.mockReset()
  mockGetNewsHeroId.mockReturnValue(null)
  mockFormatRelativeTime.mockReset()
  mockFormatRelativeTime.mockReturnValue("relative")
  mockLanguage.value = "en"
  observe.mockReset()
  disconnect.mockReset()
  constructObserver.mockReset()
  intersectionCallback = null
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver)
})

describe("NewsCardHero closure", () => {
  it("runs the parallax observer and disconnects it on unmount", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false } as MediaQueryList)
    const { unmount } = render(<NewsCardHero {...props} />)

    expect(constructObserver).toHaveBeenCalledOnce()
    expect(observe).toHaveBeenCalledOnce()
    act(() => {
      intersectionCallback?.(
        [{ intersectionRatio: 0.25 } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
    })
    expect(screen.getByRole("img")).toHaveStyle({ transform: "translateY(4%) scale(1.12)" })

    unmount()
    expect(disconnect).toHaveBeenCalledOnce()
  })

  it("skips parallax when reduced motion is preferred", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList)
    render(<NewsCardHero {...props} />)
    expect(constructObserver).not.toHaveBeenCalled()
  })

  it("handles image load/error and uses the Russian relative-time locale", () => {
    mockLanguage.value = "ru"
    const { container } = render(<NewsCardHero {...props} />)
    const image = screen.getByRole("img")
    const shimmer = container.querySelector(".animate-pulse")
    expect(shimmer).toHaveClass("opacity-100")
    expect(mockFormatRelativeTime).toHaveBeenCalledWith(props.created_at, "ru-RU")

    fireEvent.load(image)
    expect(shimmer).toHaveClass("opacity-0")
    fireEvent.error(image)
    expect(shimmer).toHaveClass("opacity-0")
  })

  it("applies and then cleans a matching back-navigation transition name", () => {
    vi.useFakeTimers()
    mockGetNewsHeroId.mockReturnValue(props.id)
    const { container } = render(<NewsCardHero {...props} />)
    const root = container.firstElementChild as HTMLElement

    expect(root.style.viewTransitionName).toBe("news-hero")
    expect(mockClearNewsHeroId).toHaveBeenCalledOnce()
    act(() => {
      vi.runAllTimers()
    })
    expect(root.style.viewTransitionName).toBe("")
    vi.useRealTimers()
  })
})
