import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { SettingsIntegrations } from "../SettingsIntegrations"

const mocks = vi.hoisted(() => ({
  user: {
    id: "user-1",
    spotify_connected: false,
    spotify_is_connected: false,
    spotify_display_name: null as string | null,
  },
  setUser: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  invalidateQueries: vi.fn(),
  fetchCurrentUser: vi.fn(),
  sanitize: vi.fn(),
  t: (key: string) => key,
}))

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user, setUser: mocks.setUser }),
}))
vi.mock("@/api/client", () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["profile"],
  fetchCurrentUser: mocks.fetchCurrentUser,
}))
vi.mock("@/hooks/useNowPlaying", () => ({ nowPlayingQueryKey: ["spotify", "now-playing"] }))
vi.mock("@/utils/spotify", () => ({ sanitizeSpotifyAuthorizeUrl: mocks.sanitize }))
vi.mock("../sections", () => ({
  SpotifySection: ({
    connected,
    displayName,
    onConnect,
    onDisconnect,
  }: {
    connected: boolean
    displayName: string
    onConnect: () => void
    onDisconnect: () => void
  }) => (
    <section>
      <span>{connected ? "connected" : "disconnected"}</span>
      <span>{displayName}</span>
      <button onClick={onConnect}>connect</button>
      <button onClick={onDisconnect}>disconnect</button>
    </section>
  ),
}))

describe("SettingsIntegrations", () => {
  beforeEach(() => {
    mocks.user = {
      id: "user-1",
      spotify_connected: false,
      spotify_is_connected: false,
      spotify_display_name: null,
    }
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.invalidateQueries.mockReset().mockResolvedValue(undefined)
    mocks.fetchCurrentUser.mockReset()
    mocks.sanitize.mockReset()
    mocks.setUser.mockReset()
  })

  it("fails closed when the Spotify authorization URL is unsafe", async () => {
    const setSnackbar = vi.fn()
    mocks.get.mockResolvedValue({ data: { url: "javascript:alert(1)" } })
    mocks.sanitize.mockReturnValue(null)
    render(<SettingsIntegrations setSnackbar={setSnackbar} />)

    fireEvent.click(screen.getByRole("button", { name: "connect" }))

    await waitFor(() => {
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:integrations.spotify.snackbar.openFailed",
        severity: "error",
      })
    })
  })

  it("navigates to a sanitized Spotify authorization URL", async () => {
    const setSnackbar = vi.fn()
    mocks.get.mockResolvedValue({ data: { url: "https://accounts.spotify.com/authorize" } })
    mocks.sanitize.mockReturnValue("#spotify-authorized")
    render(<SettingsIntegrations setSnackbar={setSnackbar} />)

    fireEvent.click(screen.getByRole("button", { name: "connect" }))

    await waitFor(() => {
      expect(mocks.get).toHaveBeenCalledWith("/spotify/auth-url")
      expect(mocks.sanitize).toHaveBeenCalledWith("https://accounts.spotify.com/authorize")
      expect(window.location.hash).toBe("#spotify-authorized")
    })
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it("disconnects Spotify, invalidates both caches, and refreshes the user profile", async () => {
    const setSnackbar = vi.fn()
    const refreshedUser = { id: "user-1", spotify_connected: false }
    mocks.user = { ...mocks.user, spotify_connected: true, spotify_display_name: "Student" }
    mocks.post.mockResolvedValue(undefined)
    mocks.fetchCurrentUser.mockResolvedValue(refreshedUser)
    render(<SettingsIntegrations setSnackbar={setSnackbar} />)

    expect(screen.getByText("connected")).toBeInTheDocument()
    expect(screen.getByText("Student")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "disconnect" }))

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith("/spotify/disconnect")
      expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["profile"] })
      expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["spotify", "now-playing"] })
      expect(mocks.setUser).toHaveBeenCalledWith(refreshedUser)
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:integrations.spotify.snackbar.disconnected",
        severity: "success",
      })
    })
  })

  it("reports a failed disconnect instead of claiming a successful state change", async () => {
    const setSnackbar = vi.fn()
    mocks.post.mockRejectedValue(new Error("network"))
    render(<SettingsIntegrations setSnackbar={setSnackbar} />)

    fireEvent.click(screen.getByRole("button", { name: "disconnect" }))

    await waitFor(() => {
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:integrations.spotify.snackbar.disconnectFailed",
        severity: "error",
      })
    })
  })

  it("clears the local Spotify state when profile refresh fails", async () => {
    const setSnackbar = vi.fn()
    mocks.user = { ...mocks.user, spotify_is_connected: true, spotify_display_name: "Fallback" }
    mocks.post.mockResolvedValue(undefined)
    mocks.fetchCurrentUser.mockRejectedValue(new Error("profile unavailable"))
    render(<SettingsIntegrations setSnackbar={setSnackbar} />)

    fireEvent.click(screen.getByRole("button", { name: "disconnect" }))

    await waitFor(() => expect(mocks.setUser).toHaveBeenCalledOnce())
    const update = mocks.setUser.mock.calls[0]?.[0] as (
      previous: typeof mocks.user | null
    ) => typeof mocks.user | null

    expect(update(mocks.user)).toMatchObject({
      spotify_connected: false,
      spotify_is_connected: false,
      spotify_display_name: null,
    })
    expect(update(null)).toBeNull()
    expect(setSnackbar).toHaveBeenCalledWith({
      text: "settings:integrations.spotify.snackbar.disconnected",
      severity: "success",
    })
  })
})
