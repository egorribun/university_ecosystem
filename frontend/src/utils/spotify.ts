const ALLOWED_SPOTIFY_HOSTS = new Set(["accounts.spotify.com"])
const AUTH_PATH_PREFIX = "/authorize"

export const sanitizeSpotifyAuthorizeUrl = (raw: string | null | undefined): string | null => {
  try {
    // null, undefined and "" stringify to non-URLs, so the parser rejects them too.
    const url = new URL(String(raw))
    if (url.protocol !== "https:") return null
    const hostname = url.hostname.toLowerCase()
    if (!ALLOWED_SPOTIFY_HOSTS.has(hostname)) return null
    if (url.username || url.password) return null
    // The parser drops the default :443 of an https URL, so any port left is custom.
    if (url.port) return null
    if (!url.pathname.startsWith(AUTH_PATH_PREFIX)) return null
    return url.toString()
  } catch {
    return null
  }
}
