import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import type { NowPlaying } from "@/types/spotify"

/**
 * Mutation contracts for the Spotify profile card.  The ordinary component
 * tests exercise the visible happy paths; this suite keeps the values that
 * are otherwise consumed by Framer Motion and inline styles observable so a
 * surviving replacement cannot silently change accessibility or motion
 * behaviour.
 */
const state = vi.hoisted(() => ({
  mediaValues: [false, false] as boolean[],
  mediaCallIndex: 0,
  mediaCalls: [] as string[],
}))

vi.mock("framer-motion", async () => {
  const React = await import("react")
  type Props = Record<string, unknown> & { children?: ReactNode }
  const motionOnly = new Set(["initial", "animate", "exit", "transition", "whileHover", "whileTap"])
  const serialise = (value: unknown) => (value === undefined ? "undefined" : JSON.stringify(value))
  const Motion = React.forwardRef<HTMLElement, Props>(function Motion({ children, ...props }, ref) {
    const tag = (props["data-motion-tag"] as string | undefined) ?? "div"
    const cleaned: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(props)) {
      if (key === "data-motion-tag" || motionOnly.has(key)) continue
      cleaned[key] = value
    }
    return React.createElement(
      tag,
      {
        ...cleaned,
        ref,
        "data-motion-initial": serialise(props.initial),
        "data-motion-animate": serialise(props.animate),
        "data-motion-transition": serialise(props.transition),
        "data-motion-while-hover": serialise(props.whileHover),
        "data-motion-while-tap": serialise(props.whileTap),
      },
      children as ReactNode
    )
  })
  const motion = new Proxy(
    {},
    {
      get: (_target, key) =>
        typeof key === "string"
          ? React.forwardRef<HTMLElement, Props>(function MotionElement(props, ref) {
              return React.createElement(Motion, { ...props, ref, "data-motion-tag": key })
            })
          : undefined,
    }
  )
  return {
    m: motion,
    motion,
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  }
})

vi.mock("@/hooks/useMediaQuery", () => ({
  default: (query: string) => {
    state.mediaCalls.push(query)
    const value =
      state.mediaValues[Math.min(state.mediaCallIndex, state.mediaValues.length - 1)] ?? false
    state.mediaCallIndex += 1
    return value
  },
}))

vi.mock("react-i18next", () => ({
  useTranslation: (namespaces?: string[]) => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key}|${JSON.stringify(options)}` : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    namespaces,
  }),
}))

import { NowPlayingCard } from "@/components/profile/NowPlayingCard"

const makeData = (overrides: Partial<NowPlaying> = {}): NowPlaying =>
  ({
    is_playing: false,
    progress_ms: 61_000,
    duration_ms: 125_000,
    track_id: "track-1",
    track_name: "Track name",
    album_name: "Album name",
    album_image_url: "https://example.test/cover.jpg",
    artists: ["Artist one", "Artist two"],
    track_url: "https://open.spotify.com/track/track-1",
    ...overrides,
  }) as NowPlaying

beforeEach(() => {
  state.mediaValues = [false, false]
  state.mediaCallIndex = 0
  state.mediaCalls.length = 0
})

describe("NowPlayingCard mutation contracts", () => {
  it("passes the exact media queries and profile translation namespace", () => {
    render(<NowPlayingCard data={makeData({ album_image_url: null })} />)

    expect(state.mediaCalls.length).toBeGreaterThanOrEqual(2)
    expect(state.mediaCalls.every((query) => query === "(prefers-reduced-motion: reduce)")).toBe(
      true
    )
    expect(screen.getByRole("link")).toHaveAttribute(
      "aria-label",
      'profile:nowPlaying.openSpotifyWithTrack|{"track":"Track name"}'
    )
  })

  it("keeps progress clamping, percentage geometry and time formatting exact", () => {
    const { container, rerender } = render(
      <NowPlayingCard data={makeData({ progress_ms: 61_000, duration_ms: 125_000 })} />
    )
    const bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuenow", "61000")
    expect(bar).toHaveAttribute("aria-valuemin", "0")
    expect(bar).toHaveAttribute("aria-valuemax", "125000")
    expect(bar).toHaveStyle({
      transform: "scaleX(0.488)",
      transition: "transform 0.2s ease-out",
    })
    expect(screen.getByText("1:01 / 2:05")).toBeInTheDocument()
    expect(bar).toHaveClass(
      "h-full",
      "bg-brand",
      "rounded-full",
      "origin-left",
      "will-change-transform"
    )
    expect(bar).toHaveAttribute("aria-label", "profile:nowPlaying.progress")
    expect(container.querySelector(".np-time")?.getAttribute("style")).toContain("width: 6.6ch")

    rerender(<NowPlayingCard data={makeData({ progress_ms: Number.POSITIVE_INFINITY })} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")
    rerender(<NowPlayingCard data={makeData({ progress_ms: -5_000 })} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")
  })

  it("handles zero and negative durations without invalid progress percentages", () => {
    const { rerender } = render(
      <NowPlayingCard data={makeData({ duration_ms: 0, progress_ms: 5_000 })} />
    )
    let bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuemax", "0")
    expect(bar).toHaveAttribute("aria-valuenow", "5000")
    expect(bar).toHaveStyle({ transform: "scaleX(0)" })
    expect(screen.getByText("0:05 / 0:00")).toBeInTheDocument()

    rerender(<NowPlayingCard data={makeData({ duration_ms: -1, progress_ms: -5 })} />)
    bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuemax", "-1")
    expect(bar).toHaveAttribute("aria-valuenow", "0")
    expect(bar).toHaveStyle({ transform: "scaleX(0)" })
  })

  it("exposes the link, card, overlay and image contracts", () => {
    const { container } = render(<NowPlayingCard data={makeData()} />)
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("href", "https://open.spotify.com/track/track-1")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")

    const card = container.querySelector(".nowplaying--spotify")!
    expect(card).toHaveClass(
      "card-glass",
      "card-glass-interactive",
      "w-full",
      "grid",
      "items-center",
      "gap-x-4",
      "gap-y-2",
      "px-4",
      "py-3.5",
      "rounded-2xl",
      "relative",
      "overflow-hidden"
    )
    expect(card).toHaveStyle({ gridTemplateColumns: "auto 1fr" })
    const overlay = card.querySelector(".absolute.inset-0")!
    expect(overlay).toHaveClass("z-base", "pointer-events-none")
    const image = screen.getByRole("img")
    expect(image).toHaveAttribute("alt", "Album name")
    expect(image).toHaveAttribute("loading", "eager")
    expect(image).toHaveAttribute("decoding", "async")
    expect(image).toHaveAttribute("referrerpolicy", "no-referrer")
    expect(image).toHaveClass("w-full", "h-full", "rounded-lg", "object-cover")
    expect(screen.getByText("Artist one, Artist two")).toHaveClass("np-art", "text-sm", "truncate")
  })

  it("renders paused and fallback metadata with accessible labels", () => {
    const { rerender, container } = render(
      <NowPlayingCard data={makeData({ is_playing: false, track_name: null, track_url: null })} />
    )
    expect(screen.getByRole("link")).toHaveAttribute("aria-label", "profile:nowPlaying.openSpotify")
    expect(screen.getByRole("link")).toHaveAttribute("href", "https://open.spotify.com")
    expect(screen.getByText("—")).toHaveClass("np-title", "font-bold", "leading-tight")
    const paused = screen.getByText("profile:nowPlaying.paused")
    expect(paused).toHaveClass(
      "inline-flex",
      "self-start",
      "px-2",
      "py-0.5",
      "text-label-xs",
      "rounded-full",
      "border",
      "border-glass-border"
    )
    expect(paused).toHaveAttribute("aria-hidden", "true")

    rerender(
      <NowPlayingCard
        data={makeData({ album_image_url: null, track_name: null, album_name: null, artists: [] })}
      />
    )
    expect(screen.getByText("♪")).toHaveClass("text-text-tertiary", "text-xs")
    expect(container.querySelector(".relative.w-14.h-14")).toHaveClass(
      "rounded-lg",
      "overflow-hidden",
      "shadow-premium"
    )
    expect(screen.queryByRole("img")).toBeNull()
  })

  it("keeps the independent reduced-motion guards exact for card and image", () => {
    state.mediaValues = [true, false]
    const first = render(<NowPlayingCard data={makeData()} />)
    const firstCard = first.container.querySelector(".nowplaying--spotify")!
    const firstImage = screen.getByRole("img")
    expect(firstCard).toHaveAttribute("data-motion-while-hover", "{}")
    expect(firstCard).toHaveAttribute("data-motion-while-tap", "{}")
    expect(firstImage).not.toHaveStyle({ transform: "scale(1.012)" })
    fireEvent.mouseEnter(firstImage)
    fireEvent.mouseLeave(firstImage)
    expect(firstImage).not.toHaveStyle({ transform: "scale(1.02)" })
    first.unmount()

    state.mediaValues = [false, true]
    state.mediaCallIndex = 0
    const second = render(<NowPlayingCard data={makeData()} />)
    const secondCard = second.container.querySelector(".nowplaying--spotify")!
    const secondImage = screen.getByRole("img")
    expect(secondCard).toHaveAttribute("data-motion-while-hover", "{}")
    expect(secondCard).toHaveAttribute("data-motion-while-tap", "{}")
    expect(secondImage).not.toHaveStyle({ transform: "scale(1.012)" })
    second.unmount()

    state.mediaValues = [false, false]
    state.mediaCallIndex = 0
    render(<NowPlayingCard data={makeData()} />)
    const normalCard = document.querySelector(".nowplaying--spotify")!
    const normalImage = screen.getByRole("img")
    expect(normalCard).toHaveAttribute("data-motion-while-hover", '{"y":-1,"scale":1.002}')
    expect(normalCard).toHaveAttribute("data-motion-while-tap", '{"scale":0.997}')
    expect(normalImage).toHaveStyle({ transform: "scale(1.012)" })
  })

  it("updates image state and progress atomically when tracks or playback change", () => {
    const { rerender } = render(
      <NowPlayingCard data={makeData({ is_playing: false, progress_ms: 10_000 })} />
    )
    const image = screen.getByRole("img")
    fireEvent.load(image)
    expect(screen.getByRole("img")).toHaveClass("opacity-100")

    rerender(<NowPlayingCard data={makeData({ is_playing: false, progress_ms: 20_000 })} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20000")
    expect(screen.getByRole("img")).toHaveClass("opacity-100")

    rerender(
      <NowPlayingCard
        data={makeData({ track_id: "track-2", is_playing: true, progress_ms: 30_000 })}
      />
    )
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "30000")
    expect(screen.getByRole("img")).toHaveClass("opacity-0")

    rerender(
      <NowPlayingCard
        data={makeData({ track_id: "track-2", is_playing: false, progress_ms: 40_000 })}
      />
    )
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40000")
  })

  it("handles image load/error and cleans the production-style RAF loop contract", () => {
    const callbacks: FrameRequestCallback[] = []
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      callbacks.push(callback)
      return callbacks.length
    })
    const cancelFrame = vi.fn()
    vi.stubGlobal("requestAnimationFrame", requestFrame)
    vi.stubGlobal("cancelAnimationFrame", cancelFrame)

    const { rerender, unmount } = render(<NowPlayingCard data={makeData({ is_playing: false })} />)
    const image = screen.getByRole("img")
    fireEvent.error(image)
    expect(screen.getByText("♪")).toBeInTheDocument()
    expect(screen.queryByRole("img")).toBeNull()
    fireEvent.load(screen.queryByRole("img") ?? image)

    rerender(<NowPlayingCard data={makeData({ is_playing: false, album_image_url: null })} />)
    expect(requestFrame).not.toHaveBeenCalled()
    expect(cancelFrame).not.toHaveBeenCalled()
    unmount()
    vi.unstubAllGlobals()
  })

  it("observes the complete-image preload and bounded progress transition", () => {
    vi.stubGlobal(
      "Image",
      class {
        complete = true
        src = ""
      }
    )
    render(<NowPlayingCard data={makeData({ is_playing: false })} />)
    expect(screen.getByRole("img")).toHaveClass("opacity-100")
    expect(screen.getByRole("progressbar")).toHaveStyle({ transition: "transform 0.2s ease-out" })
    vi.unstubAllGlobals()
  })

  it("does not throw when image events arrive after the component is unmounted", () => {
    const { unmount } = render(<NowPlayingCard data={makeData()} />)
    const image = screen.getByRole("img")
    unmount()
    expect(() => {
      act(() => {
        fireEvent.load(image)
        fireEvent.error(image)
      })
    }).not.toThrow()
  })
})
