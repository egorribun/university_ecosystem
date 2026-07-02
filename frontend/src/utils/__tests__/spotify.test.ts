import { describe, expect, it } from "vitest"
import { sanitizeSpotifyAuthorizeUrl } from "../spotify"

describe("sanitizeSpotifyAuthorizeUrl", () => {
  it("returns null for null, undefined, or empty inputs", () => {
    expect(sanitizeSpotifyAuthorizeUrl(null)).toBeNull()
    expect(sanitizeSpotifyAuthorizeUrl(undefined)).toBeNull()
    expect(sanitizeSpotifyAuthorizeUrl("")).toBeNull()
  })

  it("returns null for invalid URLs that throw URL parse error", () => {
    expect(sanitizeSpotifyAuthorizeUrl("not-a-url")).toBeNull()
    expect(sanitizeSpotifyAuthorizeUrl("http::/invalid")).toBeNull()
  })

  it("returns null for non-https protocol urls", () => {
    expect(
      sanitizeSpotifyAuthorizeUrl("http://accounts.spotify.com/authorize?client_id=123")
    ).toBeNull()
    expect(
      sanitizeSpotifyAuthorizeUrl("ftp://accounts.spotify.com/authorize?client_id=123")
    ).toBeNull()
  })

  it("returns null for disallowed hostname URLs", () => {
    expect(sanitizeSpotifyAuthorizeUrl("https://spotify.com/authorize?client_id=123")).toBeNull()
    expect(
      sanitizeSpotifyAuthorizeUrl("https://accounts.evil-spotify.com/authorize?client_id=123")
    ).toBeNull()
  })

  it("returns null if credentials (username or password) are embedded in URL", () => {
    expect(
      sanitizeSpotifyAuthorizeUrl("https://user:pass@accounts.spotify.com/authorize?client_id=123") // pragma: allowlist secret
    ).toBeNull()
    expect(
      sanitizeSpotifyAuthorizeUrl("https://user@accounts.spotify.com/authorize?client_id=123")
    ).toBeNull()
  })

  it("returns null if port is present and is not 443", () => {
    expect(
      sanitizeSpotifyAuthorizeUrl("https://accounts.spotify.com:8443/authorize?client_id=123")
    ).toBeNull()
  })

  it("returns null if pathname does not start with /authorize prefix", () => {
    expect(
      sanitizeSpotifyAuthorizeUrl("https://accounts.spotify.com/api/token?client_id=123")
    ).toBeNull()
  })

  it("returns sanitized URL string for valid https Spotify accounts authorize URLs", () => {
    const validUrl1 = "https://accounts.spotify.com/authorize?client_id=123&response_type=code"
    const validUrl2 = "https://accounts.spotify.com:443/authorize/extra?client_id=456"

    expect(sanitizeSpotifyAuthorizeUrl(validUrl1)).toBe(validUrl1)
    // The JS URL constructor strips the default :443 port for https
    expect(sanitizeSpotifyAuthorizeUrl(validUrl2)).toBe(
      "https://accounts.spotify.com/authorize/extra?client_id=456"
    )
  })
})
