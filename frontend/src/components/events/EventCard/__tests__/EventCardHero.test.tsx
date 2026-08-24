import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, it, expect, vi } from "vitest"

const transitions = vi.hoisted(() => ({
  getEventsHeroId: vi.fn(() => null as string | null),
  clearEventsHeroId: vi.fn(),
}))

vi.mock("@/utils/eventsTransition", () => transitions)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useOnlineStatus", () => ({ useOnlineStatus: () => true }))

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
  })

  it("renders the hero image with alt text and a date <time> element", () => {
    const { container } = render(<EventCardHero {...baseProps} />)
    expect(screen.getByAltText("events:alt.image")).toBeInTheDocument()
    const time = container.querySelector("time")
    expect(time).not.toBeNull()
    // FIXED ISO start → deterministic dateTime attribute
    expect(time?.getAttribute("dateTime")).toBe("2026-01-15T10:00:00.000Z")
    fireEvent.load(screen.getByAltText("events:alt.image"))
  })

  it("shows the LIVE badge for timeStatus='live'", () => {
    render(<EventCardHero {...baseProps} timeStatus="live" />)
    expect(screen.getByText("events:card.statuses.live")).toBeInTheDocument()
    expect(screen.queryByText("events:card.statuses.soon")).not.toBeInTheDocument()
  })

  it("shows the SOON badge for timeStatus='soon'", () => {
    render(<EventCardHero {...baseProps} timeStatus="soon" />)
    expect(screen.getByText("events:card.statuses.soon")).toBeInTheDocument()
    expect(screen.queryByText("events:card.statuses.live")).not.toBeInTheDocument()
  })

  it("shows no status badge for the default timeStatus='none'", () => {
    render(<EventCardHero {...baseProps} timeStatus="none" />)
    expect(screen.queryByText("events:card.statuses.live")).not.toBeInTheDocument()
    expect(screen.queryByText("events:card.statuses.soon")).not.toBeInTheDocument()
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
    vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList)

    render(<EventCardHero {...baseProps} />)

    expect(observer).not.toHaveBeenCalled()
  })

  it("uses an empty image alt when the event has no title", () => {
    const { container } = render(<EventCardHero {...baseProps} title={undefined} />)
    expect(container.querySelector('img[alt=""]')).toBeInTheDocument()
  })
})
