import api from "@/api/client"

const DUMMY_ORIGIN = "http://__avatar__"
// eslint-disable-next-line security/detect-unsafe-regex -- linear pattern, no backtracking risk
const ABSOLUTE_URL_PATTERN = /^(?:https?:)?\/\//i

const getLocationOrigin = (): string | undefined => {
  if (typeof window === "undefined") return undefined
  try {
    return window.location?.origin
  } catch {
    return undefined
  }
}

type ResolveOptions = {
  baseURL?: string
  locationOrigin?: string
}

export function resolveBackendOrigin({
  baseURL = api.defaults.baseURL,
  locationOrigin = getLocationOrigin(),
}: ResolveOptions = {}): string | undefined {
  const fallback = locationOrigin
  if (!baseURL) {
    return fallback
  }

  try {
    const resolved = new URL(baseURL, fallback ?? DUMMY_ORIGIN)
    return resolved.origin
  } catch {
    return fallback
  }
}

const appendUid = (relativeUrl: string, uid: string | number) => {
  try {
    const parsed = new URL(relativeUrl, DUMMY_ORIGIN)
    parsed.searchParams.set("uid", String(uid))
    return parsed.toString().replace(DUMMY_ORIGIN, "")
  } catch {
    const separator = relativeUrl.includes("?") ? "&" : "?"
    return `${relativeUrl}${separator}uid=${encodeURIComponent(String(uid))}`
  }
}

type AvatarUrlOptions = ResolveOptions

export function buildAvatarUrl(
  rawUrl: string | null | undefined,
  uid: string | number,
  options: AvatarUrlOptions = {}
): string {
  if (!rawUrl) return ""
  const trimmed = String(rawUrl).trim()
  if (!trimmed) return ""

  if (ABSOLUTE_URL_PATTERN.test(trimmed)) {
    return trimmed
  }

  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`
  const relativeWithUid = appendUid(withLeadingSlash, uid)
  const origin = resolveBackendOrigin(options)
  return origin ? `${origin}${relativeWithUid}` : relativeWithUid
}
