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

export function resolveMediaUrl(input?: string, backendOrigin = ""): string {
  if (!input) return ""
  const raw = String(input).trim()
  if (!raw) return ""
  if (ABSOLUTE_PATTERN.test(raw)) return raw

  const origin = ensureOrigin(
    backendOrigin || (typeof window !== "undefined" ? window.location.origin : "")
  )

  if (!origin) {
    const normalized = raw.startsWith("/") ? raw : `/${raw}`
    return encodePath(normalized)
  }

  try {
    const resolved = new URL(raw, `${origin}/`)
    resolved.pathname = encodePath(resolved.pathname)
    return resolved.toString()
  } catch {
    const normalized = raw.replace(/^\/+/, "")
    return `${origin}/${encodePath(normalized)}`
  }
}

export function addVersionParam(
  url: string | undefined,
  version: number | string
): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    parsed.searchParams.set("v", String(version))
    return parsed.toString()
  } catch {
    const sep = url.includes("?") ? "&" : "?"
    return `${url}${sep}v=${encodeURIComponent(String(version))}`
  }
}