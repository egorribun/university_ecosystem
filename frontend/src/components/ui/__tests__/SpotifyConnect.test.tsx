import { render, screen } from "@testing-library/react"
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
  })

  it("refreshes now-playing via the refresh button", async () => {
    const user = userEvent.setup()
    mockState.user = { spotify_connected: true, spotify_display_name: "Egor's Spotify" }
    render(<SpotifyConnect />)
    mockState.refetch.mockClear()
    await user.click(screen.getByText("common:buttons.refresh"))
    expect(mockState.refetch).toHaveBeenCalled()
  })
})
