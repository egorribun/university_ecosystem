import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"

const mockState = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  nowPlaying: null as Record<string, unknown> | null,
  isFetching: false,
  refetch: vi.fn(() => Promise.resolve({ data: null })),
  setUser: vi.fn(),
  invalidateQueries: vi.fn(() => Promise.resolve()),
  apiGet: vi.fn((..._args: unknown[]) =>
    Promise.resolve({ data: { url: "https://accounts.spotify.com/authorize?x=1" } })
  ),
  apiPost: vi.fn((..._args: unknown[]) => Promise.resolve({ data: {} })),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mockState.user, setUser: mockState.setUser }),
  currentUserQueryKey: ["users", "me"],
}))

vi.mock("@/hooks/useNowPlaying", () => ({
  nowPlayingQueryKey: ["spotify", "now-playing"],
  useNowPlaying: () => ({
    data: mockState.nowPlaying,
    isFetching: mockState.isFetching,
    refetch: mockState.refetch,
  }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockState.invalidateQueries }),
}))

vi.mock("@/api/client", () => ({
  default: {
    get: (...args: unknown[]) => mockState.apiGet(...args),
    post: (...args: unknown[]) => mockState.apiPost(...args),
  },
}))

vi.mock("@/utils/spotify", () => ({
  sanitizeSpotifyAuthorizeUrl: (url?: string) => url ?? null,
}))

import SpotifyConnect from "@/components/ui/SpotifyConnect"

describe("SpotifyConnect", () => {
  beforeEach(() => {
    mockState.user = null
    mockState.nowPlaying = null
    mockState.isFetching = false
    mockState.refetch.mockClear()
    mockState.setUser.mockClear()
    mockState.invalidateQueries.mockClear()
    mockState.apiGet.mockClear()
    mockState.apiPost.mockClear()
  })

  it("renders nothing when there is no user", () => {
    const { container } = render(<SpotifyConnect />)
    expect(container).toBeEmptyDOMElement()
  })

  it("shows the connect button when Spotify is not connected", () => {
    mockState.user = { spotify_connected: false }
    render(<SpotifyConnect />)
    expect(screen.getByText("settings:integrations.spotify.title")).toBeInTheDocument()
    expect(screen.getByText("settings:integrations.spotify.connect")).toBeInTheDocument()
  })

  it("shows the connected controls + display name when connected", () => {
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    render(<SpotifyConnect />)
    expect(screen.getByText("Egor's Spotify")).toBeInTheDocument()
    expect(screen.getByText("common:buttons.refresh")).toBeInTheDocument()
    expect(screen.getByText("settings:integrations.spotify.disconnect")).toBeInTheDocument()
    expect(screen.queryByText("settings:integrations.spotify.connect")).not.toBeInTheDocument()
  })

  it("renders safe fallbacks for an incomplete now-playing payload", () => {
    mockState.user = { spotify_connected: true }
    mockState.nowPlaying = { track_name: "", artists: undefined, album_name: "", track_url: "" }

    render(<SpotifyConnect />)

    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.queryByText("Album X")).not.toBeInTheDocument()
  })

  it("falls back to the status label when connected without a display name", () => {
    mockState.user = { spotify_is_connected: true }
    render(<SpotifyConnect />)
    expect(
      screen.getByText("settings:integrations.spotify.status.connectedFallback")
    ).toBeInTheDocument()
  })

  it("renders the now-playing card with track, album and external link", () => {
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    mockState.nowPlaying = {
      track_name: "Track One",
      artists: ["Artist A", "Artist B"],
      album_name: "Album X",
      track_url: "https://open.spotify.com/track/1",
    }
    render(<SpotifyConnect />)
    expect(screen.getByText("Track One")).toBeInTheDocument()
    expect(screen.getByText("Artist A, Artist B")).toBeInTheDocument()
    expect(screen.getByText("Album X")).toBeInTheDocument()
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("href", "https://open.spotify.com/track/1")
  })

  it("disconnects via the disconnect button, calling api + setUser + invalidateQueries", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    render(<SpotifyConnect />)
    await user.click(screen.getByText("settings:integrations.spotify.disconnect"))
    expect(mockState.apiPost).toHaveBeenCalledWith("/spotify/disconnect")
    expect(mockState.setUser).toHaveBeenCalled()
    expect(mockState.invalidateQueries).toHaveBeenCalled()

    const updater = mockState.setUser.mock.calls[0]?.[0] as (
      previous: Record<string, unknown>
    ) => Record<string, unknown> | null
    expect(updater(mockState.user ?? {})).toMatchObject({
      spotify_connected: false,
      spotify_is_connected: false,
      spotify_display_name: null,
    })
    expect(updater(null as never)).toBeNull()
  })

  it("refreshes now-playing via the refresh button", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    render(<SpotifyConnect />)
    mockState.refetch.mockClear()
    await user.click(screen.getByText("common:buttons.refresh"))
    expect(mockState.refetch).toHaveBeenCalled()
  })

  it("disables refresh and animates its icon while now-playing is fetching", () => {
    mockState.user = { spotify_connected: true }
    mockState.isFetching = true
    render(<SpotifyConnect />)

    const refreshButton = screen.getByText("common:buttons.refresh").closest("button")
    expect(refreshButton).toBeDisabled()
    expect(refreshButton?.querySelector("svg")).toHaveClass("animate-spin")
  })

  it("requests the authorization URL and follows a safe hash redirect", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockResolvedValueOnce({ data: { url: "#spotify" } })
    window.history.replaceState({}, "", "/settings")
    render(<SpotifyConnect />)

    await user.click(screen.getByText("settings:integrations.spotify.connect"))

    expect(mockState.apiGet).toHaveBeenCalledWith("/spotify/auth-url")
    expect(window.location.hash).toBe("#spotify")
    window.history.replaceState({}, "", "/")
  })

  it("stays on the settings page when no safe authorization URL is returned", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: false }
    mockState.apiGet.mockResolvedValueOnce({ data: { url: "" } })
    window.history.replaceState({}, "", "/settings")
    render(<SpotifyConnect />)
    const connectButton = screen.getByText("settings:integrations.spotify.connect")

    await user.click(connectButton)

    await waitFor(() => expect(connectButton).not.toBeDisabled())
    expect(window.location.pathname).toBe("/settings")
    window.history.replaceState({}, "", "/")
  })

  it("refetches now-playing when the Spotify callback query is present", () => {
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")

    render(<SpotifyConnect />)

    expect(mockState.refetch).toHaveBeenCalled()
    window.history.replaceState({}, "", "/")
  })

  it("refetches the Spotify callback only once when the query result identity changes", () => {
    mockState.user = { spotify_connected: true }
    window.history.replaceState({}, "", "/settings?spotify=connected")

    const { rerender } = render(<SpotifyConnect />)
    expect(mockState.refetch).toHaveBeenCalledOnce()

    mockState.isFetching = true
    rerender(<SpotifyConnect />)

    expect(mockState.refetch).toHaveBeenCalledOnce()
    window.history.replaceState({}, "", "/")
  })
})
