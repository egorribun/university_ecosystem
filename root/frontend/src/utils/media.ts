const ABSOLUTE_URL_PATTERN = /^(?:[a-z][a-z\d+\-.]*:|\/\/)/i

const ensureOrigin = (origin?: string) => origin?.replace(/\/+$/, "") ?? ""

const readEnvOrigin = () => {
  if (typeof import.meta !== "undefined" && import.meta.env?.VITE_BACKEND_ORIGIN) {
    return import.meta.env.VITE_BACKEND_ORIGIN
  }
  return ""
}

const DEFAULT_BACKEND_ORIGIN = ensureOrigin(readEnvOrigin())

const sanitizeStaticPrefix = (value: string) => value.replace(/^\/?static\//i, "/media/")

const encodeSegment = (segment: string) => {
  if (!segment) return segment
  if (segment === "." || segment === "..") return segment
  try {
    return encodeURIComponent(decodeURIComponent(segment))
  } catch {
    return encodeURIComponent(segment)
  }
}

const encodePathname = (pathname: string) => {
  const normalized = pathname.replace(/\\+/g, "/")
  const hasLeadingSlash = normalized.startsWith("/")
  const hasTrailingSlash = normalized.endsWith("/")
  const rawSegments = normalized.split("/")
  const filtered = rawSegments.filter((segment, index) => {
    if (segment) return true
    if (index === 0 && hasLeadingSlash) return false
    if (index === rawSegments.length - 1 && hasTrailingSlash) return false
    return false
  })
  const encodedSegments = filtered.map(encodeSegment).filter((segment) => segment !== undefined && segment !== "")
  let result = encodedSegments.join("/")
  if (hasLeadingSlash) result = `/${result}`
  if (!result && hasLeadingSlash) result = "/"
  if (hasTrailingSlash && result !== "/") result = `${result}/`
  return result
}

const normalizeRelativePath = (rawPath: string) => {
  const trimmed = sanitizeStaticPrefix(rawPath.trim())
  if (!trimmed) return ""
  const replacedBackslashes = trimmed.replace(/\\/g, "/")
  const [pathAndQuery, hash = ""] = replacedBackslashes.split("#", 2)
  const [pathPart, query = ""] = pathAndQuery.split("?", 2)

  const encodedPath = encodePathname(pathPart || "/") || "/"

  const normalizedQuery = query
    ? (() => {
        const params = new URLSearchParams(query)
        return params.toString()
      })()
    : ""

  const normalizedHash = hash ? `#${encodeURIComponent(hash)}` : ""

  const queryPart = normalizedQuery ? `?${normalizedQuery}` : ""

  return `${encodedPath}${queryPart}${normalizedHash}`
}

type ResolveMediaOptions = {
  fallback?: string
}

export function resolveMediaUrl(
  input?: string | null,
  backendOrigin = DEFAULT_BACKEND_ORIGIN || (typeof window !== "undefined" ? window.location.origin : ""),
  options?: ResolveMediaOptions
): string | undefined {
  const fallback = options?.fallback
  if (input == null) return fallback
  const raw = String(input).trim()
  if (!raw) return fallback
  if (ABSOLUTE_URL_PATTERN.test(raw)) return raw

  const origin = ensureOrigin(backendOrigin)
  const normalizedRelative = normalizeRelativePath(raw)

  if (!origin) {
    return normalizedRelative || fallback
  }

  try {
    const url = new URL(normalizedRelative || "/", `${origin}/`)
    url.pathname = encodePathname(url.pathname)
    return url.toString()
  } catch {
    const basePath = normalizedRelative.replace(/^\/+/, "")
    const finalPath = basePath ? `/${basePath}` : ""
    return `${origin}${finalPath}` || fallback
  }
}

export function addCacheBuster(url: string | undefined, version: number | string): string | undefined {
  if (!url) return undefined
  const value = String(version)
  if (!value) return url
  try {
    const parsed = new URL(url)
    parsed.searchParams.set("v", value)
    return parsed.toString()
  } catch {
    const separator = url.includes("?") ? "&" : "?"
    return `${url}${separator}v=${encodeURIComponent(value)}`
  }
}

export type { ResolveMediaOptions }
