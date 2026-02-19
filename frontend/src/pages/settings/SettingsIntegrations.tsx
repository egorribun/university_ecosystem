import api from "@/api/client"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import { nowPlayingQueryKey } from "@/hooks/useNowPlaying"
import { sanitizeSpotifyAuthorizeUrl } from "@/utils/spotify"

import { SpotifySection } from "./sections"
import type { SetSnackbar } from "./types"

interface SettingsIntegrationsProps {
  setSnackbar: SetSnackbar
}

export function SettingsIntegrations({ setSnackbar }: SettingsIntegrationsProps) {
  const { t } = useTranslation(["settings"])
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()

  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const spotifyName = user?.spotify_display_name ?? ""

  const connectSpotify = async () => {
    try {
      const { data } = await api.get<{ url?: string }>("/spotify/auth-url")
      const safeUrl = sanitizeSpotifyAuthorizeUrl(data?.url)
      if (!safeUrl) throw new Error("Received unsafe Spotify authorization URL")
      window.location.assign(safeUrl)
    } catch (_error) {
      setSnackbar({
        text: t("settings:integrations.spotify.snackbar.openFailed"),
        severity: "error",
      })
    }
  }

  const disconnectSpotify = async () => {
    try {
      await api.post("/spotify/disconnect")
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: currentUserQueryKey }),
        queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey }),
      ])
      try {
        const profile = await fetchCurrentUser()
        setUser(profile)
      } catch {
        setUser((prev) =>
          prev
            ? {
                ...prev,
                spotify_connected: false,
                spotify_is_connected: false,
                spotify_display_name: null,
              }
            : prev
        )
      }
      setSnackbar({
        text: t("settings:integrations.spotify.snackbar.disconnected"),
        severity: "success",
      })
    } catch {
      setSnackbar({
        text: t("settings:integrations.spotify.snackbar.disconnectFailed"),
        severity: "error",
      })
    }
  }

  return (
    <div className="flex w-full flex-col gap-5 sm:gap-6 xl:max-w-(--layout-max-page) 2xl:max-w-(--layout-max-wide) animate-fade-in delay-200">
      <SpotifySection
        setSnackbar={setSnackbar}
        connected={spotifyConnected}
        displayName={spotifyName}
        onConnect={connectSpotify}
        onDisconnect={disconnectSpotify}
      />
    </div>
  )
}
