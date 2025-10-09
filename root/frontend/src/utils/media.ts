const getDefaultOrigin = () => {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin
  }
  return ""
}

const isSecureContext = () => {
  if (typeof window === "undefined") return false
  const { protocol, origin } = window.location || {}
  if (typeof origin === "string" && /^https:\/\//i.test(origin)) return true
  if (protocol) return protocol === "https:"
  return false
}

const shouldUpgradeToHttps = (url: string) => {
  if (!isSecureContext()) return false
  return /^http:\/\//i.test(url)
}

const upgradeToHttps = (url: string) => url.replace(/^http:\/\//i, "https://")

const safeEncode = (segment: string) => {
  const trimmed = segment.trim()
  if (!trimmed) return ""
  try {
    return encodeURIComponent(decodeURIComponent(trimmed))
  } catch {
    return encodeURIComponent(trimmed)
  }
}

const normaliseOrigin = (origin?: string) => {
  const fallback = getDefaultOrigin()
  const raw = origin?.trim() || fallback
  if (!raw) return ""
  try {
    const parsed = new URL(raw)
    parsed.hash = ""
    parsed.search = ""
    return parsed.origin
  } catch {
    return fallback
  }
}

export function resolveMediaUrl(
  raw?: string,
  origin = import.meta.env.VITE_ASSETS_BASE || import.meta.env.VITE_BACKEND_ORIGIN,
): string {
  if (!raw) return ""
  const cleaned = String(raw).trim()
  if (!cleaned) return ""
  if (/^(?:https?:)?\/\//i.test(cleaned)) {
    try {
      const resolved = new URL(cleaned, "http://dummy").toString().replace("http://dummy", "")
      return shouldUpgradeToHttps(resolved) ? upgradeToHttps(resolved) : resolved
    } catch {
      return shouldUpgradeToHttps(cleaned) ? upgradeToHttps(cleaned) : cleaned
    }
  }

  const base = normaliseOrigin(origin)
  if (!base) return cleaned

  const stripped = cleaned.replace(/^\/+/, "")
  const match = /^([^?#]*)(\?[^#]*)?(#.*)?$/.exec(stripped)
  const pathPart = match?.[1] ?? ""
  const queryPart = match?.[2] ?? ""
  const hashPart = match?.[3] ?? ""

  const normalisedPath = pathPart.replace(/\/{2,}/g, "/")
  const encodedPath = normalisedPath
    .split("/")
    .map((segment) => safeEncode(segment))
    .join("/")

  const relative = `${encodedPath}${queryPart}${hashPart}`

  try {
    const resolved = new URL(relative, base + "/")
    const finalUrl = resolved.toString()
    return shouldUpgradeToHttps(finalUrl) ? upgradeToHttps(finalUrl) : finalUrl
  } catch {
    const fallback = `${base}/${relative}`.replace(/(?<!:)\/{2,}/g, "/")
    return shouldUpgradeToHttps(fallback) ? upgradeToHttps(fallback) : fallback
  }
}

export function addVersionParam(url: string, version?: number): string {
  if (!url) return ""
  if (version == null) return url
  try {
    const parsed = new URL(url)
    parsed.searchParams.set("v", String(version))
    return parsed.toString()
  } catch {
    const separator = url.includes("?") ? "&" : "?"
    return `${url}${separator}v=${encodeURIComponent(String(version))}`
  }
}
