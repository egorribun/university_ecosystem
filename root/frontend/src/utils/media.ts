const ABSOLUTE_PATTERN = /^(data:|blob:|https?:\/\/)/i

const ensureOrigin = (origin?: string) => origin?.replace(/\/+$/, "") ?? ""

const encodePath = (value: string) => {
  return value
    .split("/")
    .map((segment) => {
      if (!segment) return segment
      try {
        return encodeURIComponent(decodeURIComponent(segment))
      } catch {
        return encodeURIComponent(segment)
      }
    })
    .join("/")
    .replace(/\/{2,}/g, "/")
}

const readEnvOrigin = () => {
  if (typeof import.meta !== "undefined" && import.meta.env?.VITE_BACKEND_ORIGIN) {
    return import.meta.env.VITE_BACKEND_ORIGIN
  }
  return ""
}

const DEFAULT_BACKEND_ORIGIN = ensureOrigin(readEnvOrigin())

const sanitizePath = (raw: string) => raw.replace(/^\/?static\//i, "/media/")

type ResolveMediaOptions = {
  fallback?: string
}

export function resolveMediaUrl(
  input?: string | null,
  origin = DEFAULT_BACKEND_ORIGIN,
  options?: ResolveMediaOptions
): string {
  const fallback = options?.fallback ?? ""
  if (input == null) return fallback
  const raw = String(input).trim()
  if (!raw) return fallback
  if (ABSOLUTE_PATTERN.test(raw)) return raw

  const normalizedRaw = sanitizePath(raw)

  const resolvedOrigin = ensureOrigin(
    origin || (typeof window !== "undefined" ? window.location.origin : "")
  )

  if (!resolvedOrigin) {
    const normalized = normalizedRaw.startsWith("/") ? normalizedRaw : `/${normalizedRaw}`
    return encodePath(normalized) || fallback
  }

  try {
    const resolved = new URL(normalizedRaw, `${resolvedOrigin}/`)
    resolved.pathname = encodePath(resolved.pathname)
    return resolved.toString()
  } catch {
    const normalized = normalizedRaw.replace(/^\/+/, "")
    return `${resolvedOrigin}/${encodePath(normalized)}` || fallback
  }
}

export function appendCacheBust(
  url: string | undefined,
  version: number | string = Date.now()
): string | undefined {
  if (!url) return undefined
  const value = String(version)
  if (!value) return url
  try {
    const parsed = new URL(url)
    parsed.searchParams.set("v", value)
    return parsed.toString()
  } catch {
    const sep = url.includes("?") ? "&" : "?"
    return `${url}${sep}v=${encodeURIComponent(value)}`
  }
}

export type { ResolveMediaOptions }