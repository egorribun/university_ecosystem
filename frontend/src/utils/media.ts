const DUMMY_BASE = "http://internal.placeholder"

// eslint-disable-next-line security/detect-unsafe-regex -- linear pattern, no backtracking risk
const hasProtocol = (value: string) => /^(?:https?:)?\/\//i.test(value)

export function resolveMediaUrl(
  raw?: string,
  origin = import.meta.env.VITE_BACKEND_ORIGIN
): string {
  if (!raw) return ""
  const trimmed = String(raw).trim()

  // Check for dangerous protocols
  if (/^(?:javascript:|vbscript:|data:text\/)/i.test(trimmed)) return ""

  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`
  const needsPrefix =
    withLeadingSlash.startsWith("/static/") ||
    withLeadingSlash.startsWith("/media/") ||
    withLeadingSlash.startsWith("/api/v1/chats/") ||
    withLeadingSlash.startsWith("/api/v1/events/")

  // Absolute, protocol-relative and blob: URLs (and "") never carry one of
  // these backend prefixes, so they are returned unchanged here too.
  if (!needsPrefix) {
    return trimmed
  }

  // An empty origin keeps the path relative (nginx proxy).
  const normalizedOrigin = (origin?.trim() ?? "").replace(/\/+$/, "")
  return `${normalizedOrigin}${withLeadingSlash}`
}

/** The image-proxy path of a local static/media or already proxied image, else null. */
function toImageProxyPath(raw: string): string | null {
  const trimmed = raw.trim()
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`
  if (withLeadingSlash.startsWith("/api/v1/img/")) {
    return withLeadingSlash.replace("/api/v1/img/", "/")
  }
  if (withLeadingSlash.startsWith("/static/") || withLeadingSlash.startsWith("/media/")) {
    return withLeadingSlash
  }
  return null
}

export function resolveProxyImageUrl(
  raw?: string,
  width?: number,
  origin = import.meta.env.VITE_BACKEND_ORIGIN
): string {
  // Empty input, blob: and absolute URLs never map to a proxy path.
  const proxyPath = raw ? toImageProxyPath(raw) : null
  if (proxyPath === null) {
    return resolveMediaUrl(raw, origin)
  }

  // Empty origin means use relative paths (nginx proxy)
  const base = (origin?.trim() ?? "").replace(/\/+$/, "")
  const url = new URL(`${base}/api/v1/img${proxyPath}`, DUMMY_BASE)
  if (width) {
    url.searchParams.set("w", String(width))
  }

  // Return absolute URL or path-relative depending on origin presence
  return url.toString().replace(DUMMY_BASE, "")
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

    // Only allow safe protocols: http, https, blob, mailto, tel, and data:image/*.
    // Everything else, including javascript: and vbscript:, is rejected.
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
