import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { SettingsIntegrations } from "../SettingsIntegrations"
import { rotateBrowserSession } from "@/stores/sessionEpoch"

type SpotifyUser = {
  id: string
  spotify_connected: boolean
  spotify_is_connected: boolean
  spotify_display_name: string | null
}

const mocks = vi.hoisted(() => ({
  user: {
    id: "user-1",
    spotify_connected: false,
    spotify_is_connected: false,
    spotify_display_name: null,
  } as SpotifyUser | null,
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
  useAuth: () => ({ user: mocks.user, loading: false, setUser: mocks.setUser }),
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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((resolveRequest, rejectRequest) => {
    resolve = resolveRequest
    reject = rejectRequest
  })
  return { promise, resolve, reject }
}

describe("SettingsIntegrations", () => {
  beforeEach(() => {
    rotateBrowserSession()
    window.history.replaceState({}, "", "/settings")
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
    mocks.user = { ...mocks.user!, spotify_connected: true, spotify_display_name: "Student" }
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
      expect(mocks.setUser).toHaveBeenCalledOnce()
      const update = mocks.setUser.mock.calls[0]?.[0] as (
        previous: typeof mocks.user
      ) => typeof mocks.user
      expect(update(mocks.user)).toEqual(refreshedUser)
      expect(setSnackbar).toHaveBeenCalledWith({
        text: "settings:integrations.spotify.snackbar.disconnected",
        severity: "success",
      })
    })
  })

  it.each(["refreshed", "fallback"])(
    "suppresses the success toast when the %s profile setter synchronously replaces the session",
    async (source) => {
      const setSnackbar = vi.fn()
      mocks.user = { ...mocks.user!, spotify_connected: true }
      const nextAccount = { ...mocks.user, id: "user-2", spotify_display_name: "Next account" }
      const refreshedProfile = { ...mocks.user, spotify_connected: false }
      let adoptedProfile: SpotifyUser | null = null
      mocks.post.mockResolvedValue(undefined)
      if (source === "refreshed") mocks.fetchCurrentUser.mockResolvedValue(refreshedProfile)
      else mocks.fetchCurrentUser.mockRejectedValue(new Error("profile unavailable"))
      mocks.setUser.mockImplementationOnce(
        (update: (previous: typeof mocks.user) => typeof mocks.user) => {
          adoptedProfile = update(mocks.user)
          // A synchronous auth observer may rotate the session while the
          // initiating handler is still inside its profile setter.
          rotateBrowserSession()
          mocks.user = nextAccount
        }
      )
      const { rerender } = render(<SettingsIntegrations setSnackbar={setSnackbar} />)

      fireEvent.click(screen.getByRole("button", { name: "disconnect" }))
      await act(async () => undefined)

      expect(adoptedProfile).toMatchObject({ id: "user-1", spotify_connected: false })
      expect(mocks.invalidateQueries).toHaveBeenCalledTimes(2)
      expect(mocks.user).toBe(nextAccount)
      expect(setSnackbar).not.toHaveBeenCalled()
      rerender(<SettingsIntegrations setSnackbar={setSnackbar} />)
      expect(screen.getByText("Next account")).toBeInTheDocument()
      expect(screen.getByText("connected")).toBeInTheDocument()
    }
  )

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
    mocks.user = { ...mocks.user!, spotify_is_connected: true, spotify_display_name: "Fallback" }
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

  it.each(["success", "error"])(
    "ignores a stale authorization %s after switching accounts",
    async (outcome) => {
      const pending = deferred<{ data: { url: string } }>()
      const setSnackbar = vi.fn()
      mocks.get.mockReturnValueOnce(pending.promise)
      mocks.sanitize.mockReturnValue("#stale-authorization")
      const { rerender } = render(<SettingsIntegrations setSnackbar={setSnackbar} />)
      fireEvent.click(screen.getByRole("button", { name: "connect" }))
      rotateBrowserSession()
      mocks.user = { ...mocks.user!, id: "user-2" }
      rerender(<SettingsIntegrations setSnackbar={setSnackbar} />)
      await act(async () => {
        if (outcome === "success")
          pending.resolve({ data: { url: "https://accounts.spotify.com/authorize" } })
        else pending.reject(new Error("stale authorization"))
      })

      expect(window.location.hash).toBe("")
      expect(setSnackbar).not.toHaveBeenCalled()
    }
  )

  it.each([
    ["disconnect", "success"],
    ["disconnect", "error"],
    ["invalidation", "success"],
    ["invalidation", "error"],
    ["profile", "success"],
    ["profile", "error"],
  ])("stops stale work at the %s %s boundary", async (stage, outcome) => {
    const pending = deferred<unknown>()
    const setSnackbar = vi.fn()
    const initialUser = { ...mocks.user!, spotify_connected: false }
    mocks.post.mockResolvedValue(undefined)
    mocks.fetchCurrentUser.mockResolvedValue(initialUser)
    if (stage === "disconnect") mocks.post.mockReturnValueOnce(pending.promise)
    if (stage === "invalidation") mocks.invalidateQueries.mockReturnValueOnce(pending.promise)
    if (stage === "profile") mocks.fetchCurrentUser.mockReturnValueOnce(pending.promise)
    const { rerender } = render(<SettingsIntegrations setSnackbar={setSnackbar} />)
    fireEvent.click(screen.getByRole("button", { name: "disconnect" }))
    if (stage === "invalidation")
      await waitFor(() => expect(mocks.invalidateQueries).toHaveBeenCalled())
    if (stage === "profile") await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalled())
    rotateBrowserSession()
    mocks.user = { ...mocks.user!, id: "user-2", spotify_connected: true }
    rerender(<SettingsIntegrations setSnackbar={setSnackbar} />)
    await act(async () => {
      if (outcome === "success") pending.resolve(initialUser)
      else pending.reject(new Error("stale response"))
    })

    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
    if (stage === "disconnect") expect(mocks.invalidateQueries).not.toHaveBeenCalled()
    if (stage !== "profile") expect(mocks.fetchCurrentUser).not.toHaveBeenCalled()
  })

  it.each(["logout", "unmount", "same-account-session"])(
    "does not adopt a profile after %s",
    async (boundary) => {
      const pending = deferred<SpotifyUser>()
      const setSnackbar = vi.fn()
      const previous = mocks.user!
      mocks.post.mockResolvedValue(undefined)
      mocks.fetchCurrentUser.mockReturnValueOnce(pending.promise)
      const { rerender, unmount } = render(<SettingsIntegrations setSnackbar={setSnackbar} />)
      fireEvent.click(screen.getByRole("button", { name: "disconnect" }))
      await waitFor(() => expect(mocks.fetchCurrentUser).toHaveBeenCalled())
      rotateBrowserSession()
      if (boundary === "logout") mocks.user = null
      if (boundary === "unmount") unmount()
      else rerender(<SettingsIntegrations setSnackbar={setSnackbar} />)
      await act(async () => pending.resolve(previous))

      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(setSnackbar).not.toHaveBeenCalled()
    }
  )

  it.each(["success", "fallback"])(
    "rechecks account and session inside the %s profile updater",
    async (outcome) => {
      const setSnackbar = vi.fn()
      mocks.post.mockResolvedValue(undefined)
      if (outcome === "success")
        mocks.fetchCurrentUser.mockResolvedValue({ ...mocks.user!, spotify_connected: false })
      else mocks.fetchCurrentUser.mockRejectedValue(new Error("profile unavailable"))
      render(<SettingsIntegrations setSnackbar={setSnackbar} />)
      fireEvent.click(screen.getByRole("button", { name: "disconnect" }))
      await waitFor(() => expect(mocks.setUser).toHaveBeenCalledOnce())
      const update = mocks.setUser.mock.calls[0]?.[0] as (
        previous: typeof mocks.user
      ) => typeof mocks.user
      const nextAccount = { ...mocks.user!, id: "user-2", spotify_connected: true }
      expect(update(nextAccount)).toBe(nextAccount)
      expect(update(null)).toBeNull()
      rotateBrowserSession()
      expect(update(mocks.user)).toBe(mocks.user)
    }
  )

  it("does not adopt a profile for a different account even within the same session", async () => {
    const setSnackbar = vi.fn()
    mocks.post.mockResolvedValue(undefined)
    mocks.fetchCurrentUser.mockResolvedValue({ ...mocks.user!, id: "user-2" })
    render(<SettingsIntegrations setSnackbar={setSnackbar} />)
    fireEvent.click(screen.getByRole("button", { name: "disconnect" }))
    await act(async () => undefined)

    expect(mocks.setUser).not.toHaveBeenCalled()
    expect(setSnackbar).not.toHaveBeenCalled()
  })

  it.each(["connect", "disconnect"])(
    "does not start %s from an obsolete browser session",
    async (action) => {
      const setSnackbar = vi.fn()
      render(<SettingsIntegrations setSnackbar={setSnackbar} />)
      window.localStorage.setItem(
        "ecosystem.session.generation.v1",
        JSON.stringify({ nonce: "other-tab", hash: null })
      )
      fireEvent.click(screen.getByRole("button", { name: action }))
      await act(async () => undefined)

      expect(mocks.get).not.toHaveBeenCalled()
      expect(mocks.post).not.toHaveBeenCalled()
      expect(mocks.setUser).not.toHaveBeenCalled()
      expect(setSnackbar).not.toHaveBeenCalled()
    }
  )

  it.each([null, "ssr-stub"])(
    "does not start actions for an unconfirmed identity %s",
    async (id) => {
      const setSnackbar = vi.fn()
      mocks.user = id === null ? null : { ...mocks.user!, id }
      render(<SettingsIntegrations setSnackbar={setSnackbar} />)
      fireEvent.click(screen.getByRole("button", { name: "connect" }))
      fireEvent.click(screen.getByRole("button", { name: "disconnect" }))
      await act(async () => undefined)

      expect(mocks.get).not.toHaveBeenCalled()
      expect(mocks.post).not.toHaveBeenCalled()
      expect(setSnackbar).not.toHaveBeenCalled()
    }
  )
})
