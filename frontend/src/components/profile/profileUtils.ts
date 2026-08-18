/**
 * Profile Types and Utilities
 *
 * Shared types and helper functions for the Profile page components.
 */

export type SnackbarKey =
  "spotifyConnected" | "spotifyError" | "copied" | "profileUpdated" | "error"

export type SnackbarState = {
  key?: SnackbarKey
  message?: string
  severity?: "success" | "info" | "warning" | "error"
}

/**
 * Parse achievements string into structured list
 */
export type AchievementItem = {
  key: string
  name: string
  issuer?: string
  date?: string
  url?: string
}

export function parseAchievements(achievementsStr: string | null | undefined): AchievementItem[] {
  return String(achievementsStr || "")
    .split(/[,;\n]/)
    .map((str) => String(str || "").trim())
    .filter(Boolean)
    .map((raw, index) => {
      const [name, issuer, date, url] = raw.split("|").map((s) => s.trim())
      return { key: `${raw}-${index}`, name: name || raw, issuer, date, url }
    })
}

/**
 * Build vCard string for QR codes
 */
export function buildVCardString(user: {
  full_name?: string | null
  email?: string | null
  institute?: string | null
  department?: string | null
  position?: string | null
  status?: string | null
}): string {
  const lines = [
    "BEGIN:VCARD",
    "VERSION:4.0",
    `FN:${user.full_name || ""}`,
    user.email ? `EMAIL:${user.email}` : "",
    user.institute || user.department ? `ORG:${user.institute || user.department}` : "",
    user.position || user.status ? `TITLE:${user.position || user.status}` : "",
    typeof window !== "undefined" ? `URL:${window.location.href}` : "",
  ].filter(Boolean)
  lines.push("END:VCARD")
  return lines.join("\r\n")
}

/**
 * Format milliseconds to mm:ss string
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "0:00"
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(seconds / 60)
  const rest = String(seconds % 60).padStart(2, "0")
  return `${minutes}:${rest}`
}

/**
 * Calculate avatar and layout dimensions
 */
export function calculateAvatarSize(isMobile: boolean, isWideScreen: boolean): number {
  if (isMobile) return 120
  if (isWideScreen) return 188
  return 168
}

/**
 * Calculate hero layout values based on avatar size
 */
export function calculateHeroLayout(
  avatarPx: number,
  isMobile: boolean
): {
  avatarFloat: number
  heroPaddingBottom: string
  heroTextPaddingTop: string
} {
  const avatarFloat = Math.round(avatarPx * 0.55)
  const heroPaddingBottom = `${Math.max(avatarFloat - 12, 28)}px`
  const heroTextPaddingTop = isMobile
    ? `${Math.round(40 + avatarPx + 12)}px`
    : `${Math.round(48 + avatarPx + 16)}px`

  return { avatarFloat, heroPaddingBottom, heroTextPaddingTop }
}

/**
 * Calculate online status indicator dimensions
 */
export function calculateStatusIndicator(avatarPx: number): {
  size: number
  offset: number
} {
  return {
    size: Math.max(12, Math.round(avatarPx * 0.16)),
    offset: Math.max(6, Math.round(avatarPx * 0.08)),
  }
}
