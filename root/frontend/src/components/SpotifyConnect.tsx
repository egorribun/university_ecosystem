import { useEffect, useMemo, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material"
import { nowPlayingQueryKey, useNowPlaying } from "@/hooks/useNowPlaying"

export default function SpotifyConnect() {
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()
  const [actionLoading, setActionLoading] = useState(false)

  const spotifyEnabled = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const nowPlayingQuery = useNowPlaying(spotifyEnabled)
  const now = nowPlayingQuery.data
  const refreshing = nowPlayingQuery.isFetching

  const connect = async () => {
    setActionLoading(true)
    try {
      const r = await api.get("/spotify/auth-url")
      window.location.href = r.data.url
    } finally {
      setActionLoading(false)
    }
  }

  const disconnect = async () => {
    setActionLoading(true)
    try {
      await api.post("/spotify/disconnect")
      setUser({ ...user, spotify_connected: false, spotify_display_name: null })
      queryClient.setQueryData(nowPlayingQueryKey, null)
    } finally {
      setActionLoading(false)
    }
  }

  const refresh = async () => {
    await nowPlayingQuery.refetch()
  }

  useEffect(() => {
    const qp = new URLSearchParams(window.location.search)
    if (qp.get("spotify")) void nowPlayingQuery.refetch()
  }, [])

  if (!user) return null

  const loadingIndicator = useMemo(
    () => (actionLoading ? <CircularProgress size={22} color="inherit" /> : "Подключить Spotify"),
    [actionLoading]
  )

  return (
    <Card sx={{ mt: 2 }}>
      <CardHeader title="Spotify" />
      <CardContent>
        {!user.spotify_connected ? (
          <Button onClick={connect} variant="contained" disabled={actionLoading}>
            {loadingIndicator}
          </Button>
        ) : (
          <Stack spacing={1.2}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip size="small" label={user.spotify_display_name || "Аккаунт подключен"} />
              <Button onClick={refresh} size="small" variant="outlined" disabled={actionLoading || refreshing}>
                {actionLoading || refreshing ? "..." : "Обновить"}
              </Button>
              <Button onClick={disconnect} size="small" variant="outlined" color="error" disabled={actionLoading}>
                Отключить
              </Button>
            </Stack>
            {now && (
              <Box>
                <Typography fontWeight={700}>{now.track_name || "—"}</Typography>
                <Typography>{(now.artists || []).join(", ")}</Typography>
                {!!now.album_name && <Typography color="text.secondary">{now.album_name}</Typography>}
                {!!now.track_url && (
                  <a href={now.track_url} target="_blank" rel="noreferrer">
                    {now.track_url}
                  </a>
                )}
              </Box>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}
