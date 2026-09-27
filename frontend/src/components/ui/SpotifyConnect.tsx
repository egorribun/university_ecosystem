import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import api from "@/api/client"
import { useAuth, currentUserQueryKey } from "@/contexts/AuthContext"
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying"
import { sanitizeSpotifyAuthorizeUrl } from "@/utils/spotify"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { Alert, Button } from "@/components/settings/SettingsUI"
import { RefreshCw, LogOut, Music, ExternalLink } from "lucide-react"

export default function SpotifyConnect() {
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()
  const [actionLoading, setActionLoading] = useState(false)
  const [feedback, setFeedback] = useState<{
    key: string
    disconnected?: boolean
  } | null>(null)
  const { t } = useTranslation(["settings", "common"])

  const spotifyEnabled = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const { data: now, isFetching: refreshing, refetch } = useNowPlaying(spotifyEnabled)

  const connect = async () => {
    setFeedback(null)
    setActionLoading(true)
    try {
      const r = await api.get<{ url?: string }>("/spotify/auth-url")
      const safeUrl = sanitizeSpotifyAuthorizeUrl(r.data?.url)
      if (!safeUrl) {
        setFeedback({ key: "settings:integrations.spotify.snackbar.openFailed" })
        return
      }
      window.location.href = safeUrl
    } catch {
      setFeedback({ key: "settings:integrations.spotify.snackbar.connectFailed" })
    } finally {
      setActionLoading(false)
    }
  }

  const disconnect = async () => {
    setFeedback(null)
    setActionLoading(true)
    let disconnected = false
    try {
      await api.post("/spotify/disconnect")
      disconnected = true
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
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: currentUserQueryKey }, { throwOnError: true }),
        queryClient.invalidateQueries({ queryKey: nowPlayingQueryKey }, { throwOnError: true }),
      ])
    } catch {
      setFeedback(
        disconnected
          ? { key: "common:errors.generic", disconnected: true }
          : { key: "settings:integrations.spotify.snackbar.disconnectFailed" }
      )
    } finally {
      setActionLoading(false)
    }
  }

  const refresh = async () => {
    setFeedback(null)
    try {
      await refetch({ throwOnError: true })
    } catch {
      setFeedback({ key: "common:errors.generic" })
    }
  }

  useEffect(() => {
    const qp = new URLSearchParams(window.location.search)
    if (!qp.get("spotify")) return
    let active = true
    setFeedback(null)
    const refreshAfterCallback = async () => {
      try {
        await refetch({ throwOnError: true })
      } catch {
        if (active) setFeedback({ key: "common:errors.generic" })
      }
    }
    void refreshAfterCallback()
    return () => {
      active = false
    }
  }, [refetch])

  if (!user) return null

  return (
    <div className="mt-4 overflow-hidden rounded-3xl border border-glass-border bg-(--bg-surface)/(--opacity-soft) backdrop-blur-xl transition-all duration-slow shadow-glass">
      <div className="px-6 py-4 border-b border-glass-border/(--opacity-subtle) bg-(--bg-surface)/(--opacity-subtle)">
        <h3 className="text-lg font-black tracking-tight text-text-primary flex items-center gap-2">
          <Music className="h-5 w-5 text-(--color-spotify)" />
          {t("settings:integrations.spotify.title")}
        </h3>
      </div>
      <div className="p-6">
        {feedback && (
          <Alert severity="error" className="mb-4">
            {feedback.disconnected && (
              <>{t("settings:integrations.spotify.snackbar.disconnected")} </>
            )}
            {t(feedback.key)}
          </Alert>
        )}
        {!spotifyEnabled ? (
          <Button
            onClick={connect}
            variant="solid"
            disabled={actionLoading}
            className="w-full h-12 rounded-2xl bg-(--color-spotify) hover:bg-(--color-spotify-hover) text-white font-black shadow-lg shadow-(--color-spotify)/(--opacity-dim)"
            loading={actionLoading}
          >
            {t("settings:integrations.spotify.connect")}
          </Button>
        ) : (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex items-center rounded-full bg-(--color-spotify)/(--opacity-dim) border border-(--color-spotify)/(--opacity-dim) px-4 py-1.5 text-xs font-black text-(--color-spotify) tracking-tight">
                {user.spotify_display_name ||
                  t("settings:integrations.spotify.status.connectedFallback")}
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={refresh}
                  variant="outline"
                  size="sm"
                  disabled={actionLoading || refreshing}
                  className="rounded-xl h-9 px-4 font-black"
                  startIcon={<RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />}
                >
                  {t("common:buttons.refresh")}
                </Button>
                <Button
                  onClick={disconnect}
                  variant="outline"
                  size="sm"
                  disabled={actionLoading}
                  className="rounded-xl h-9 px-4 font-black border-error/(--opacity-dim) text-error hover:bg-error/(--opacity-subtle)"
                  startIcon={<LogOut className="h-4 w-4" />}
                >
                  {t("settings:integrations.spotify.disconnect")}
                </Button>
              </div>
            </div>

            {now && (
              <div className="rounded-2xl bg-(--bg-surface-raised)/(--opacity-soft) border border-glass-border/(--opacity-subtle) p-4 space-y-1 transition-all hover:bg-(--bg-surface-raised)/(--opacity-medium)">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-base font-black tracking-tight text-text-primary truncate">
                      {now.track_name || "—"}
                    </p>
                    <p className="text-sm font-bold text-(--text-secondary) truncate">
                      {(now.artists || []).join(", ")}
                    </p>
                    {!!now.album_name && (
                      <p className="text-xs font-medium text-(--text-tertiary) truncate opacity-strong">
                        {now.album_name}
                      </p>
                    )}
                  </div>
                  {now.track_url && (
                    <a
                      href={now.track_url}
                      target="_blank"
                      rel="noreferrer"
                      className="p-2 rounded-xl bg-(--color-spotify)/(--opacity-dim) text-(--color-spotify) hover:bg-(--color-spotify-hover)/(--opacity-dim) transition-colors"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
