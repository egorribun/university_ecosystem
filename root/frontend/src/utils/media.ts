const DUMMY_BASE = "http://__dummy__"

const hasProtocol = (value: string) => /^(?:https?:)?\/\//i.test(value)

export function resolveMediaUrl(
  raw?: string,
  origin = import.meta.env.VITE_BACKEND_ORIGIN
): string {
  if (!raw) return ""
  const trimmed = String(raw).trim()
  if (!trimmed) return ""

  if (hasProtocol(trimmed)) {
    return trimmed
  }

  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`
  const needsPrefix =
    withLeadingSlash.startsWith("/static/") || withLeadingSlash.startsWith("/media/")

  if (!needsPrefix) {
    return trimmed
  }

  const dev = import.meta.env.DEV === true
  const cleanOrigin = origin?.trim()

  if (!cleanOrigin) {
    if (dev) {
      return withLeadingSlash
    }
    throw new Error("VITE_BACKEND_ORIGIN is not set for production build")
  }

  const normalizedOrigin = cleanOrigin.replace(/\/+$/, "")
  return `${normalizedOrigin}${withLeadingSlash}`
}

export function addVersionParam(url?: string, version?: string | number): string {
  if (!url) return ""
  if (version === undefined || version === null || version === "") return url
  const value = String(version)

  try {
    const parsed = new URL(url, DUMMY_BASE)
    parsed.searchParams.set("_v", value)
    if (hasProtocol(url)) {
      return parsed.toString()
    }
    const relative = parsed.toString().replace(DUMMY_BASE, "")
    return relative
  } catch {
    const separator = url.includes("?") ? "&" : "?"
    return `${url}${separator}_v=${encodeURIComponent(value)}`
  }
}
