const ALLOWED_SPOTIFY_HOSTS = new Set(["accounts.spotify.com"])
const AUTH_PATH_PREFIX = "/authorize"

export const sanitizeSpotifyAuthorizeUrl = (
  raw: string | null | undefined,
): string | null => {
  if (!raw) return null
  try {
    const url = new URL(raw)
    if (url.protocol !== "https:") return null
    const hostname = url.hostname.toLowerCase()
    if (!ALLOWED_SPOTIFY_HOSTS.has(hostname)) return null
    if (url.username || url.password) return null
    if (url.port && url.port !== "443") return null
    if (!url.pathname.startsWith(AUTH_PATH_PREFIX)) return null
    return url.toString()
  } catch {
    return null
  }
}
