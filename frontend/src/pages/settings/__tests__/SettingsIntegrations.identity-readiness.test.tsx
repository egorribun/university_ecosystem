import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { rotateBrowserSession } from "@/stores/sessionEpoch"
import { SettingsIntegrations } from "../SettingsIntegrations"

const state = vi.hoisted(() => ({
  user: null as {
    id: string
    spotify_connected: boolean
    spotify_is_connected: boolean
    spotify_display_name: string | null
  } | null,
  loading: false,
  setUser: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  invalidateQueries: vi.fn(),
}))

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: state.invalidateQueries }),
}))
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: state.user, loading: state.loading, setUser: state.setUser }),
}))
vi.mock("@/api/client", () => ({ default: { get: state.get, post: state.post } }))
vi.mock("@/hooks/auth/useProfileSync", () => ({
  currentUserQueryKey: ["profile"],
  fetchCurrentUser: vi.fn(),
}))
vi.mock("@/hooks/useNowPlaying", () => ({ nowPlayingQueryKey: ["spotify", "now-playing"] }))
vi.mock("../sections", async () => ({
  SpotifySection: (await import("../sections/SpotifySection")).SpotifySection,
}))

describe("SettingsIntegrations identity readiness", () => {
  beforeEach(() => {
    rotateBrowserSession()
    state.loading = false
    state.get.mockReset()
    state.post.mockReset()
    state.setUser.mockReset()
    state.invalidateQueries.mockReset()
  })

  it.each([
    ["SSR stub", "ssr-stub", false],
    ["encrypted-cache placeholder", "-1", false],
    ["loading account", "user-1", true],
  ])(
    "disables both connection states for %s until the account is confirmed",
    async (_label, id, loading) => {
      const user = userEvent.setup()
      const setSnackbar = vi.fn()
      state.user = {
        id,
        spotify_connected: false,
        spotify_is_connected: false,
        spotify_display_name: null,
      }
      state.loading = loading
      const { rerender } = render(<SettingsIntegrations setSnackbar={setSnackbar} />)
      const connect = screen.getByRole("button", { name: "settings:integrations.spotify.connect" })
      expect(connect).toBeDisabled()
      await user.click(connect)
      expect(state.get).not.toHaveBeenCalled()

      state.user = { ...state.user, spotify_connected: true }
      rerender(<SettingsIntegrations setSnackbar={setSnackbar} />)
      const disconnect = screen.getByRole("button", {
        name: "settings:integrations.spotify.disconnect",
      })
      expect(disconnect).toBeDisabled()
      await user.click(disconnect)
      expect(state.post).not.toHaveBeenCalled()

      state.user = { ...state.user, id: "user-1" }
      state.loading = false
      state.post.mockRejectedValueOnce(new Error("disconnect failed"))
      rerender(<SettingsIntegrations setSnackbar={setSnackbar} />)
      expect(disconnect).toBeEnabled()
      await user.click(disconnect)
      await waitFor(() => expect(state.post).toHaveBeenCalledWith("/spotify/disconnect"))
      await waitFor(() => expect(setSnackbar).toHaveBeenCalled())

      state.user = { ...state.user, spotify_connected: false }
      state.get.mockRejectedValueOnce(new Error("authorization failed"))
      rerender(<SettingsIntegrations setSnackbar={setSnackbar} />)
      const enabledConnect = screen.getByRole("button", {
        name: "settings:integrations.spotify.connect",
      })
      expect(enabledConnect).toBeEnabled()
      await user.click(enabledConnect)
      await waitFor(() => expect(state.get).toHaveBeenCalledWith("/spotify/auth-url"))
      await act(async () => undefined)
    }
  )
})
