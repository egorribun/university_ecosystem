import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, it, expect, vi } from "vitest"

const transitions = vi.hoisted(() => ({
  getEventsHeroId: vi.fn(() => null as string | null),
  clearEventsHeroId: vi.fn(),
}))

const {
  useTranslationMock,
  translationMock,
  translationState,
  formatDateMock,
  formatRelativeTimeMock,
} = vi.hoisted(() => {
  const translationMock = vi.fn((key: string) => key)
  const translationState = { language: "en" }
  return {
    useTranslationMock: vi.fn(() => ({
      t: translationMock,
      i18n: { language: translationState.language, changeLanguage: () => Promise.resolve() },
    })),
    translationMock,
    translationState,
    formatDateMock: vi.fn((value: string) => `date:${value}`),
    formatRelativeTimeMock: vi.fn((value: string, locale: string) => `${locale}:${value}`),
  }
})

vi.mock("@/utils/eventsTransition", () => transitions)

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => true }))
vi.mock("@/utils/date", () => ({
  formatDate: formatDateMock,
  formatRelativeTime: formatRelativeTimeMock,
}))

import EventCardHero from "@/components/events/EventCard/EventCardHero"

const baseProps = {
  id: "evt-1",
  imageUrl: "https://picsum.photos/seed/ue-hero/800/450",
  title: "Annual Conference",
  startsAt: "2026-01-15T10:00:00.000Z",
  endsAt: "2026-01-15T12:00:00.000Z",
}

describe("EventCardHero", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
    transitions.getEventsHeroId.mockReset()
    transitions.getEventsHeroId.mockReturnValue(null)
    transitions.clearEventsHeroId.mockReset()
    translationState.language = "en"
  })

  it("renders the hero image with alt text and a date <time> element", () => {
    const { container } = render(<EventCardHero {...baseProps} />)
    expect(screen.getByAltText("events:alt.image")).toBeInTheDocument()
    const time = container.querySelector("time")
    expect(time).not.toBeNull()
    // FIXED ISO start → deterministic dateTime attribute
    expect(time?.getAttribute("dateTime")).toBe("2026-01-15T10:00:00.000Z")
    expect(time).toHaveAttribute("title", "date:2026-01-15T10:00:00.000Z")
    expect(formatRelativeTimeMock).toHaveBeenCalledWith(baseProps.startsAt, "en-US")
    fireEvent.load(screen.getByAltText("events:alt.image"))
  })

  it("defaults an omitted time status to the neutral state", () => {
    render(<EventCardHero {...baseProps} timeStatus={undefined} />)

    expect(screen.queryByText("events:card.statuses.live")).not.toBeInTheDocument()
    expect(screen.queryByText("events:card.statuses.soon")).not.toBeInTheDocument()
  })

  it("shows the LIVE badge for timeStatus='live'", () => {
    render(<EventCardHero {...baseProps} timeStatus="live" />)
    expect(screen.getByText("events:card.statuses.live")).toBeInTheDocument()
    expect(screen.queryByText("events:card.statuses.soon")).not.toBeInTheDocument()
    expect(translationMock).toHaveBeenCalledWith("events:card.statuses.live")
  })

  it("shows the SOON badge for timeStatus='soon'", () => {
    render(<EventCardHero {...baseProps} timeStatus="soon" />)
    expect(screen.getByText("events:card.statuses.soon")).toBeInTheDocument()
    expect(screen.queryByText("events:card.statuses.live")).not.toBeInTheDocument()
    expect(translationMock).toHaveBeenCalledWith("events:card.statuses.soon")
  })

  it("shows no status badge for the default timeStatus='none'", () => {
    render(<EventCardHero {...baseProps} timeStatus="none" />)
    expect(screen.queryByText("events:card.statuses.live")).not.toBeInTheDocument()
    expect(screen.queryByText("events:card.statuses.soon")).not.toBeInTheDocument()
    expect(useTranslationMock).toHaveBeenCalledWith(["events", "common"])
  })

  it("renders the priority eager/high-fetchpriority image", () => {
    render(<EventCardHero {...baseProps} priority />)
    const img = screen.getByAltText("events:alt.image")
    expect(img).toHaveAttribute("loading", "eager")
    expect(img).toHaveAttribute("fetchpriority", "high")
  })

  it("renders the placeholder calendar icon when no imageUrl is provided", () => {
    const { container } = render(<EventCardHero {...baseProps} imageUrl={undefined} />)
    // No image → fallback branch (no <img>), but date badge still present
    expect(screen.queryByAltText("events:alt.image")).not.toBeInTheDocument()
    expect(container.querySelector("svg")).not.toBeNull()
    expect(container.querySelector("time")).not.toBeNull()
    expect(container.querySelector(".animate-pulse")).toHaveClass(
      "opacity-0",
      "pointer-events-none"
    )
  })

  it("omits the date badge when startsAt is empty", () => {
    const { container } = render(<EventCardHero {...baseProps} startsAt="" />)
    expect(container.querySelector("time")).toBeNull()
  })

  it("skips view-transition lookup when no event id is available", () => {
    render(<EventCardHero {...baseProps} id={undefined} />)

    expect(transitions.getEventsHeroId).not.toHaveBeenCalled()
  })

  it("renders the transitioning view-transition variant without crashing", () => {
    render(<EventCardHero {...baseProps} transitioning />)
    expect(screen.getByAltText("events:alt.image")).toBeInTheDocument()
  })

  it("shows the cached offline badge when offline", async () => {
    vi.resetModules()
    vi.doMock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => false }))
    vi.doMock("react-i18next", () => ({
      useTranslation: () => ({
        t: (key: string) => key,
        i18n: { language: "ru", changeLanguage: () => Promise.resolve() },
      }),
    }))
    const { default: OfflineHero } = await import("@/components/events/EventCard/EventCardHero")
    render(<OfflineHero {...baseProps} />)
    expect(screen.getByText("common:statuses.cached")).toBeInTheDocument()
    vi.doUnmock("@/hooks/useOnlineStatus")
    vi.doUnmock("react-i18next")
  })

  it("applies and cleans up the back-navigation view transition name", () => {
    vi.useFakeTimers()
    transitions.getEventsHeroId.mockReturnValue("evt-1")
    const { container, unmount } = render(<EventCardHero {...baseProps} />)
    const hero = container.firstElementChild as HTMLElement

    expect(hero.style.viewTransitionName).toBe("events-hero")
    expect(transitions.clearEventsHeroId).toHaveBeenCalledOnce()

    act(() => {
      vi.runAllTimers()
    })
    expect(hero.style.viewTransitionName).toBe("")
    unmount()
    expect(hero.style.viewTransitionName).toBe("")
  })

  it("cleans the view-transition name when unmounted before the deferred cleanup", () => {
    vi.useFakeTimers()
    transitions.getEventsHeroId.mockReturnValue("evt-1")
    const { container, unmount } = render(<EventCardHero {...baseProps} />)
    const hero = container.firstElementChild as HTMLElement

    expect(hero.style.viewTransitionName).toBe("events-hero")
    unmount()
    expect(hero.style.viewTransitionName).toBe("")
    vi.runOnlyPendingTimers()
  })

  it("updates the parallax transform from intersection changes", () => {
    let callback: IntersectionObserverCallback | undefined
    const observe = vi.fn()
    const disconnect = vi.fn()
    class MockIntersectionObserver {
      constructor(next: IntersectionObserverCallback) {
        callback = next
      }

      observe = observe
      disconnect = disconnect
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)

    const { container, unmount } = render(<EventCardHero {...baseProps} />)
    const img = container.querySelector("[data-parallax-img]") as HTMLElement
    expect(observe).toHaveBeenCalled()

    callback?.([] as IntersectionObserverEntry[], {} as IntersectionObserver)
    callback?.(
      [{ intersectionRatio: 0.25 } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
    expect(img.style.transform).toBe("translateY(4%) scale(1.12)")

    unmount()
    expect(disconnect).toHaveBeenCalledOnce()
  })

  it("skips parallax work when reduced motion is requested", () => {
    const observer = vi.fn()
    vi.stubGlobal("IntersectionObserver", observer)
    const matchMedia = vi
      .spyOn(window, "matchMedia")
      .mockImplementation(
        (query) => ({ matches: query === "(prefers-reduced-motion: reduce)" }) as MediaQueryList
      )

    render(<EventCardHero {...baseProps} />)

    expect(observer).not.toHaveBeenCalled()
    expect(matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
  })

  it("uses an empty image alt when the event has no title", () => {
    const { container } = render(<EventCardHero {...baseProps} title={undefined} />)
    expect(container.querySelector('img[alt=""]')).toBeInTheDocument()
  })

  it("hides the shimmer after either a successful or failed image load", () => {
    const { container } = render(<EventCardHero {...baseProps} />)
    const image = screen.getByAltText("events:alt.image")
    const shimmer = container.querySelector(".animate-pulse") as HTMLElement

    expect(shimmer).toHaveClass("opacity-100")
    fireEvent.load(image)
    expect(shimmer).toHaveClass("opacity-0", "pointer-events-none")

    const { container: secondContainer } = render(<EventCardHero {...baseProps} />)
    fireEvent.error(screen.getAllByAltText("events:alt.image")[1]!)
    expect(secondContainer.querySelector(".animate-pulse")).toHaveClass("opacity-0")
  })

  it("rebinds parallax observers when the image source changes", () => {
    const observers: Array<{
      observe: ReturnType<typeof vi.fn>
      disconnect: ReturnType<typeof vi.fn>
    }> = []
    class MockIntersectionObserver {
      observe = vi.fn()
      disconnect = vi.fn()

      constructor(_callback: IntersectionObserverCallback) {
        observers.push(this)
      }
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false } as MediaQueryList)

    const { rerender } = render(<EventCardHero {...baseProps} />)
    expect(observers).toHaveLength(1)
    expect(observers[0]?.observe).toHaveBeenCalledOnce()

    rerender(<EventCardHero {...baseProps} imageUrl="https://example.test/next.jpg" />)
    expect(observers).toHaveLength(2)
    expect(observers[0]?.disconnect).toHaveBeenCalledOnce()
    expect(observers[1]?.observe).toHaveBeenCalledOnce()
  })

  it("passes the complete parallax threshold configuration to the observer", () => {
    let observerOptions: IntersectionObserverInit | undefined
    class MockIntersectionObserver {
      observe = vi.fn()
      disconnect = vi.fn()

      constructor(_callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
        observerOptions = options
      }
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver)
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false } as MediaQueryList)

    render(<EventCardHero {...baseProps} />)

    expect(observerOptions).toEqual({ threshold: [0, 0.25, 0.5, 0.75, 1] })
  })

  it("recomputes readiness when the image source changes", () => {
    const { container, rerender } = render(<EventCardHero {...baseProps} />)
    const image = screen.getByAltText("events:alt.image")
    fireEvent.load(image)
    expect(container.querySelector(".animate-pulse")).toHaveClass("opacity-0")

    rerender(<EventCardHero {...baseProps} imageUrl="https://example.test/next.jpg" />)
    expect(container.querySelector(".animate-pulse")).toHaveClass("opacity-100")
  })

  it("exposes the transition name on the transitioning hero container", () => {
    const { container } = render(<EventCardHero {...baseProps} transitioning />)

    expect((container.firstElementChild as HTMLElement).style.viewTransitionName).toBe(
      "events-hero"
    )
  })

  it("formats the relative date with the active Russian locale", () => {
    translationState.language = "ru"
    render(<EventCardHero {...baseProps} />)

    expect(formatRelativeTimeMock).toHaveBeenCalledWith(baseProps.startsAt, "ru-RU")
  })

  it("does not claim a back transition for a different stored hero id", () => {
    transitions.getEventsHeroId.mockReturnValue("other-event")
    const { container } = render(<EventCardHero {...baseProps} />)

    expect(transitions.clearEventsHeroId).not.toHaveBeenCalled()
    expect((container.firstElementChild as HTMLElement).style.viewTransitionName).toBe("")
  })
})
