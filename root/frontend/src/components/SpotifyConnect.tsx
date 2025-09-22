import { useEffect, useMemo, useState } from "react"
import api from "@/api/axios"
import { useAuth } from "@/contexts/AuthContext"
import { Box, Button, Card, CardContent, CardHeader, Chip, CircularProgress, Stack, Typography } from "@mui/material"

export default function SpotifyConnect() {
  const { user, setUser } = useAuth()
  const [loading, setLoading] = useState(false)
  const [now, setNow] = useState<any | null>(null)

  const connect = async () => {
    setLoading(true)
    try {
      const r = await api.get("/spotify/auth-url")
      window.location.href = r.data.url
    } finally {
      setLoading(false)
    }
  }

  const disconnect = async () => {
    setLoading(true)
    try {
      await api.post("/spotify/disconnect")
      setUser({ ...user, spotify_connected: false, spotify_display_name: null })
      setNow(null)
    } finally {
      setLoading(false)
    }
  }

  const refresh = async () => {
    setLoading(true)
    try {
      const r = await api.get("/spotify/now-playing")
      setNow(r.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const qp = new URLSearchParams(window.location.search)
    if (qp.get("spotify")) refresh()
  }, [])

  if (!user) return null

  return (
    <Card sx={{ mt: 2 }}>
      <CardHeader title="Spotify" />
      <CardContent>
        {!user.spotify_connected ? (
          <Button onClick={connect} variant="contained" disabled={loading}>{loading ? <CircularProgress size={22} color="inherit" /> : "Подключить Spotify"}</Button>
        ) : (
          <Stack spacing={1.2}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip size="small" label={user.spotify_display_name || "Аккаунт подключен"} />
              <Button onClick={refresh} size="small" variant="outlined" disabled={loading}>{loading ? "..." : "Обновить"}</Button>
              <Button onClick={disconnect} size="small" variant="outlined" color="error" disabled={loading}>Отключить</Button>
            </Stack>
            {now && (
              <Box>
                <Typography fontWeight={700}>{now.track_name || "—"}</Typography>
                <Typography>{(now.artists || []).join(", ")}</Typography>
                {!!now.album_name && <Typography color="text.secondary">{now.album_name}</Typography>}
                {!!now.track_url && <a href={now.track_url} target="_blank" rel="noreferrer">{now.track_url}</a>}
              </Box>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}