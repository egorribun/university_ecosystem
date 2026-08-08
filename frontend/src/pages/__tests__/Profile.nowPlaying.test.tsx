import { ThemeProvider } from "@/contexts/ThemeContext"
import { render, act } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { NowPlayingCard } from "@/components/profile"
import type { NowPlaying } from "@/types/spotify"
import i18n from "@/i18n/config"

vi.mock("framer-motion", async () => {
  const actual = await vi.importActual<typeof import("framer-motion")>("framer-motion")
  return { ...actual, useReducedMotion: () => false }
})

const baseTrack: NowPlaying = {
  is_playing: true,
  track_id: "play-1",
  track_name: "Test Track",
  artists: ["Tester"],
  album_name: "Album",
  album_image_url: "https://example.com/cover.jpg",
  track_url: "https://open.spotify.com/track/play-1",
  duration_ms: 180000,
  progress_ms: 30000,
  fetched_at: "2024-01-01T00:00:00.000Z",
}

const renderWithTheme = (track: NowPlaying) =>
  render(
    <ThemeProvider>
      <NowPlayingCard data={track} />
    </ThemeProvider>
  )

describe("NowPlayingCard", () => {
  beforeEach(() => {
    Object.defineProperty(global.Image.prototype, "complete", {
      writable: true,
      value: true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("matches snapshot when playing", async () => {
    const { container } = renderWithTheme(baseTrack)
    const img = container.querySelector("img")
    if (img) {
      act(() => {
        img.dispatchEvent(new Event("load"))
      })
    }
    expect(container.firstChild).toMatchSnapshot()
  })

  it("matches snapshot when paused", async () => {
    const paused: NowPlaying = { ...baseTrack, is_playing: false }
    const { container, getByText } = renderWithTheme(paused)
    const img = container.querySelector("img")
    if (img) {
      act(() => {
        img.dispatchEvent(new Event("load"))
      })
    }
    expect(getByText(i18n.t("profile:nowPlaying.paused"))).toBeInTheDocument()
    expect(container.firstChild).toMatchSnapshot()
  })

  it("reflects updated progress when data changes", () => {
    const { getByRole, rerender } = renderWithTheme(baseTrack)
    const progressBar = getByRole("progressbar")
    const initial = Number(progressBar.getAttribute("aria-valuenow"))

    const advanced: NowPlaying = {
      ...baseTrack,
      progress_ms: (baseTrack.progress_ms ?? 0) + 15000,
      fetched_at: "2024-01-01T00:00:15.000Z",
    }

    act(() => {
      rerender(
        <ThemeProvider>
          <NowPlayingCard data={advanced} />
        </ThemeProvider>
      )
    })

    const updated = Number(progressBar.getAttribute("aria-valuenow"))
    expect(updated).toBeGreaterThan(initial)
  })
})
