const getDefaultOrigin = () => {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin
  }
  return ""
}

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
  origin = import.meta.env.VITE_BACKEND_ORIGIN,
): string {
  if (!raw) return ""
  const cleaned = String(raw).trim()
  if (!cleaned) return ""
  if (/^(?:https?:)?\/\//i.test(cleaned)) {
    try {
      return new URL(cleaned, "http://dummy").toString().replace("http://dummy", "")
    } catch {
      return cleaned
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
    return resolved.toString()
  } catch {
    const fallback = `${base}/${relative}`
    return fallback.replace(/(?<!:)\/{2,}/g, "/")
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
