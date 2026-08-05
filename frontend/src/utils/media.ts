const DUMMY_BASE = "http://internal.placeholder"

// eslint-disable-next-line security/detect-unsafe-regex -- linear pattern, no backtracking risk
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

  // Check for dangerous protocols
  const dangerous = /^\s*(javascript:|vbscript:|data:text\/)/i.test(trimmed)
  if (dangerous) return ""

  if (hasProtocol(trimmed)) {
    return trimmed
  }

  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`
  const needsPrefix =
    withLeadingSlash.startsWith("/static/") || withLeadingSlash.startsWith("/media/")

  if (!needsPrefix) {
    return trimmed
  }

  const cleanOrigin = origin?.trim() ?? ""

  // Empty origin means use relative paths (nginx proxy)
  if (!cleanOrigin) {
    return withLeadingSlash
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
    const cleanOrigin = origin?.trim() ?? ""

    // Empty origin means use relative paths (nginx proxy)
    const base = cleanOrigin ? cleanOrigin.replace(/\/+$/, "") : ""

    // Capture the path relative to static/media or use it as is if already proxy path
    let proxyPath = withLeadingSlash
    if (withLeadingSlash.startsWith("/api/v1/img/")) {
      proxyPath = withLeadingSlash.replace("/api/v1/img/", "/")
    }

    const url = new URL(`${base}${apiBase}${proxyPath}`, DUMMY_BASE)
    if (width) {
      url.searchParams.set("w", String(width))
    }

    // Return absolute URL or path-relative depending on origin presence
    const result = url.toString().replace(DUMMY_BASE, "")
    return result
  }

  return resolveMediaUrl(raw, origin)
}

export function addVersionParam(url?: string, version?: string | number | null): string {
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

/**
 * Sanitize a URL to prevent XSS attacks (javascript:, vbscript:, data:html).
 * Allows http, https, blob, mailto, tel, data:image.
 */
export function sanitizeUrl(url: string): string | null {
  if (!url) return null
  try {
    // If it's a relative URL, we need a base to parse it
    const base = typeof window !== "undefined" ? window.location.origin : DUMMY_BASE
    const parsed = new URL(url, base)
    const protocol = parsed.protocol.toLowerCase()

    // Block dangerous protocols outright
    if (protocol === "javascript:" || protocol === "vbscript:") {
      return null
    }

    // Only allow safe protocols: http, https, blob, mailto, tel, and data:image/*
    if (protocol === "data:") {
      const pathname = parsed.pathname.toLowerCase()
      // Allow images, block everything else (e.g. text/html, application/xml)
      if (!pathname.startsWith("image/")) {
        return null
      }
    } else {
      const allowedProtocols = new Set(["http:", "https:", "blob:", "mailto:", "tel:"])
      if (!allowedProtocols.has(protocol)) {
        return null
      }
    }

    // Return a normalized, sanitized URL string. For relative URLs we strip the dummy base.
    const sanitized = parsed.toString()
    if (base === DUMMY_BASE) {
      return sanitized.replace(base, "")
    }
    return sanitized
  } catch {
    // If parsing fails, treat URL as unsafe
    return null
  }
}
