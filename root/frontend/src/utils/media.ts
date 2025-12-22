const DUMMY_BASE = "http://__dummy__"

const hasProtocol = (value: string) => /^(?:https?:)?\/\//i.test(value)
const isBlobUrl = (value: string) => /^blob:/i.test(value)

export function resolveMediaUrl(
  raw?: string,
  origin = import.meta.env.VITE_BACKEND_ORIGIN
): string {
  if (!raw) return ""
  const trimmed = String(raw).trim()
  if (!trimmed) return ""

  // Return blob: URLs unchanged — they're local preview URLs
  if (isBlobUrl(trimmed)) {
    return trimmed
  }

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

export function resolveProxyImageUrl(
  raw?: string,
  width?: number,
  origin = import.meta.env.VITE_BACKEND_ORIGIN
): string {
  if (!raw) return ""
  const trimmed = String(raw).trim()
  if (!trimmed || isBlobUrl(trimmed) || hasProtocol(trimmed)) {
    return resolveMediaUrl(raw, origin)
  }

  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`

  if (
    withLeadingSlash.startsWith("/static/") ||
    withLeadingSlash.startsWith("/media/") ||
    withLeadingSlash.startsWith("/api/v1/img/")
  ) {
    const apiBase = "/api/v1/img"
    const dev = import.meta.env.DEV === true
    const cleanOrigin = origin?.trim()

    let base = ""
    if (cleanOrigin) {
      base = cleanOrigin.replace(/\/+$/, "")
    } else if (!dev) {
      throw new Error("VITE_BACKEND_ORIGIN is not set for production build")
    }

    // Capture the path relative to static/media or use it as is if already proxy path
    let proxyPath = withLeadingSlash
    if (withLeadingSlash.startsWith("/api/v1/img/")) {
      proxyPath = withLeadingSlash.replace("/api/v1/img/", "/")
    }

    const url = new URL(`${base}${apiBase}${proxyPath}`, "http://dummy.com")
    if (width) {
      url.searchParams.set("w", String(width))
    }

    // Return absolute URL or path-relative depending on origin presence
    const result = url.toString().replace("http://dummy.com", "")
    return result
  }

  return resolveMediaUrl(raw, origin)
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
