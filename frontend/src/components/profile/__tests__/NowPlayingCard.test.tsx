import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, it, expect, vi } from "vitest"

const mediaState = vi.hoisted(() => ({ reduced: false }))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => mediaState.reduced }))

import { NowPlayingCard } from "@/components/profile/NowPlayingCard"
import type { NowPlaying } from "@/types/spotify"

function makeData(overrides: Partial<NowPlaying> = {}): NowPlaying {
  return {
    is_playing: true,
    progress_ms: 60_000,
    duration_ms: 180_000,
    track_id: "track-1",
    track_name: "Bohemian Rhapsody",
    album_name: "A Night at the Opera",
    album_image_url: "https://example.com/cover.jpg",
    artists: ["Queen"],
    track_url: "https://open.spotify.com/track/track-1",
    ...overrides,
  } as NowPlaying
}

describe("NowPlayingCard", () => {
  beforeEach(() => {
    mediaState.reduced = false
  })

  it("renders the playing track with name, artists and a track-aware aria label", () => {
    render(<NowPlayingCard data={makeData()} />)
    expect(screen.getByText("Bohemian Rhapsody")).toBeInTheDocument()
    expect(screen.getByText("Queen")).toBeInTheDocument()
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("aria-label", "profile:nowPlaying.openSpotifyWithTrack")
    expect(link).toHaveAttribute("href", "https://open.spotify.com/track/track-1")
    // No paused badge while playing.
    expect(screen.queryByText("profile:nowPlaying.paused")).not.toBeInTheDocument()
  })

  it("shows the paused badge and computes progressbar bounds when not playing", () => {
    render(<NowPlayingCard data={makeData({ is_playing: false })} />)
    expect(screen.getByText("profile:nowPlaying.paused")).toBeInTheDocument()
    const bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuenow", "60000")
    expect(bar).toHaveAttribute("aria-valuemin", "0")
    expect(bar).toHaveAttribute("aria-valuemax", "180000")
  })

  it("clamps progress to duration and reflects it on the progressbar", () => {
    render(<NowPlayingCard data={makeData({ is_playing: false, progress_ms: 999_999 })} />)
    const bar = screen.getByRole("progressbar")
    // clampProgress caps at duration (180000) since progress > duration.
    expect(bar).toHaveAttribute("aria-valuenow", "180000")
  })

  it("normalizes null, non-finite, and negative progress safely", () => {
    const { rerender } = render(
      <NowPlayingCard data={makeData({ is_playing: false, progress_ms: Number.NaN })} />
    )
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")

    rerender(
      <NowPlayingCard data={makeData({ is_playing: false, duration_ms: -1, progress_ms: -5 })} />
    )
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")
  })

  it("uses the generic spotify aria label and fallback href when track info is missing", () => {
    render(<NowPlayingCard data={makeData({ track_name: null, track_url: null, artists: [] })} />)
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("aria-label", "profile:nowPlaying.openSpotify")
    expect(link).toHaveAttribute("href", "https://open.spotify.com")
    // Title falls back to the em-dash placeholder.
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("renders the music-note fallback when there is no album image", () => {
    render(<NowPlayingCard data={makeData({ album_image_url: null })} />)
    expect(screen.getByText("♪")).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("renders the album image with an alt when an image url is present", () => {
    render(<NowPlayingCard data={makeData()} />)
    const img = screen.getByRole("img")
    expect(img).toHaveAttribute("src", "https://example.com/cover.jpg")
    expect(img).toHaveAttribute("alt", "A Night at the Opera")
  })

  it("uses the track and translation fallbacks for missing album metadata", () => {
    const { rerender } = render(
      <NowPlayingCard data={makeData({ album_name: null, track_name: "Track fallback" })} />
    )
    expect(screen.getByRole("img")).toHaveAttribute("alt", "Track fallback")

    rerender(<NowPlayingCard data={makeData({ album_name: null, track_name: null })} />)
    expect(screen.getByRole("img")).toHaveAttribute("alt", "profile:nowPlaying.albumFallback")
  })

  it("marks an already-complete image loaded during the preload effect", () => {
    vi.stubGlobal(
      "Image",
      class {
        complete = true
        src = ""
      }
    )

    render(<NowPlayingCard data={makeData()} />)
    expect(screen.getByRole("img").className).toContain("opacity-100")
    vi.unstubAllGlobals()
  })

  it("resets progress on changed data and resumes playback", () => {
    const { rerender } = render(
      <NowPlayingCard data={makeData({ is_playing: false, progress_ms: 30_000 })} />
    )

    rerender(<NowPlayingCard data={makeData({ is_playing: false, progress_ms: 90_000 })} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "90000")

    rerender(<NowPlayingCard data={makeData({ is_playing: true, progress_ms: 90_000 })} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "90000")
  })

  it("disables image hover styling when reduced motion is preferred", () => {
    mediaState.reduced = true
    render(<NowPlayingCard data={makeData()} />)
    const image = screen.getByRole("img")

    expect(image).not.toHaveStyle({ transform: "scale(1.012)" })
    fireEvent.mouseEnter(image)
    fireEvent.mouseLeave(image)
    expect(image).not.toHaveStyle({ transform: "scale(1.02)" })
  })

  it("handles image load, hover transitions, errors, and track changes", async () => {
    const { rerender } = render(<NowPlayingCard data={makeData()} />)
    const image = screen.getByRole("img")

    expect(image.className).toContain("opacity-0")
    fireEvent.load(image)
    expect(image.className).toContain("opacity-100")

    fireEvent.mouseEnter(image)
    expect(image).toHaveStyle({ transform: "scale(1.02)" })
    fireEvent.mouseLeave(image)
    expect(image).toHaveStyle({ transform: "scale(1.012)" })

    fireEvent.error(image)
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
    expect(screen.getByText("♪")).toBeInTheDocument()

    rerender(<NowPlayingCard data={makeData({ track_id: "track-2" })} />)
    await waitFor(() => expect(screen.getByRole("img")).toBeInTheDocument())
    expect(screen.getByRole("img").className).toContain("opacity-0")
  })

  it("treats zero duration as 0% progress without crashing", () => {
    render(
      <NowPlayingCard data={makeData({ is_playing: false, duration_ms: 0, progress_ms: 5_000 })} />
    )
    const bar = screen.getByRole("progressbar")
    expect(bar).toHaveAttribute("aria-valuemax", "0")
    // duration <= 0 → pct is 0, component still renders.
    expect(screen.getByText("Bohemian Rhapsody")).toBeInTheDocument()
  })
})
