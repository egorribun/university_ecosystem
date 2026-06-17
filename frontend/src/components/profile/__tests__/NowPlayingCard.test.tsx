import { render, screen } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))

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
