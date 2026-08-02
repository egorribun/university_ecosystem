import { act, render, screen } from "@testing-library/react"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

const mediaState = vi.hoisted(() => ({ reduced: false }))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => mediaState.reduced,
}))

type NowPlayingCardComponent = typeof import("@/components/profile/NowPlayingCard").NowPlayingCard

let NowPlayingCard: NowPlayingCardComponent

function makeData(
  overrides: Partial<import("@/types/spotify").NowPlaying> = {}
): import("@/types/spotify").NowPlaying {
  return {
    is_playing: true,
    progress_ms: 1_000,
    duration_ms: 180_000,
    track_id: "track-1",
    track_name: "Production track",
    album_name: "Production album",
    album_image_url: null,
    artists: ["Artist"],
    track_url: null,
    ...overrides,
  } as import("@/types/spotify").NowPlaying
}

beforeAll(async () => {
  vi.stubEnv("MODE", "production")
  vi.resetModules()
  ;({ NowPlayingCard } = await import("@/components/profile/NowPlayingCard"))
})

beforeEach(() => {
  mediaState.reduced = false
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

afterAll(() => {
  vi.unstubAllEnvs()
})

describe("NowPlayingCard — production animation and defensive paths", () => {
  it("advances and cancels the production RAF loop", () => {
    const callbacks: FrameRequestCallback[] = []
    let nextFrameId = 0
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      callbacks.push(callback)
      nextFrameId += 1
      return nextFrameId
    })
    const cancelFrame = vi.fn()
    vi.stubGlobal("requestAnimationFrame", requestFrame)
    vi.stubGlobal("cancelAnimationFrame", cancelFrame)

    const now = vi.spyOn(Date, "now")
    now.mockReturnValue(1_000)
    const { rerender, unmount } = render(<NowPlayingCard data={makeData()} />)

    expect(requestFrame).toHaveBeenCalledTimes(1)
    now.mockReturnValue(2_000)
    act(() => callbacks.shift()?.(2_000))
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2000")
    expect(requestFrame).toHaveBeenCalledTimes(2)

    rerender(<NowPlayingCard data={makeData({ is_playing: false, progress_ms: 2_000 })} />)
    expect(cancelFrame).toHaveBeenCalled()
    unmount()
  })

  it("covers production motion-disabled modes without starting RAF", () => {
    const requestFrame = vi.fn(() => 1)
    vi.stubGlobal("requestAnimationFrame", requestFrame)

    mediaState.reduced = true
    const { rerender } = render(<NowPlayingCard data={makeData()} />)
    expect(requestFrame).not.toHaveBeenCalled()

    mediaState.reduced = false
    rerender(<NowPlayingCard data={makeData({ duration_ms: 0 })} />)
    expect(requestFrame).not.toHaveBeenCalled()

    rerender(<NowPlayingCard data={makeData({ is_playing: false })} />)
    expect(requestFrame).not.toHaveBeenCalled()
  })

  it("cancels an active RAF when reduced motion disables playback animation", () => {
    const requestFrame = vi.fn(() => 1)
    const cancelFrame = vi.fn()
    vi.stubGlobal("requestAnimationFrame", requestFrame)
    vi.stubGlobal("cancelAnimationFrame", cancelFrame)

    const { rerender } = render(<NowPlayingCard data={makeData()} />)
    expect(requestFrame).toHaveBeenCalledOnce()

    mediaState.reduced = true
    rerender(<NowPlayingCard data={makeData()} />)

    expect(cancelFrame).toHaveBeenCalledWith(1)
  })

  it("handles a playing track changing to a nullable track id while paused", () => {
    const { rerender } = render(
      <NowPlayingCard data={makeData({ is_playing: false, progress_ms: 1_000 })} />
    )

    rerender(
      <NowPlayingCard data={makeData({ is_playing: false, progress_ms: 1_000, track_id: null })} />
    )

    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1000")
  })

  it("normalizes nullable duration, track id, and progress inputs", () => {
    render(
      <NowPlayingCard
        data={makeData({ duration_ms: undefined, track_id: null, progress_ms: null })}
      />
    )

    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuemax", "0")
  })
})
