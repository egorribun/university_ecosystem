const BACKEND_ORIGIN =
  import.meta.env.VITE_BACKEND_ORIGIN ||
  (typeof window !== "undefined" ? window.location.origin : "")

const safeEncode = (seg: string) => {
  try {
    return encodeURIComponent(decodeURIComponent(seg))
  } catch {
    return encodeURIComponent(seg)
  }
}

export function resolveMediaUrl(raw?: string): string {
  if (!raw) return ""
  const cleaned = String(raw).trim()
  if (!cleaned) return ""
  if (/^https?:\/\//i.test(cleaned)) return cleaned
  const base = BACKEND_ORIGIN.replace(/\/+$/, "")
  const path = cleaned.replace(/^\/+/, "/")
  const encoded = path
    .split("/")
    .map(safeEncode)
    .join("/")
    .replace(/\/{2,}/g, "/")
  try {
    const u = new URL(encoded, base + "/")
    return u.toString()
  } catch {
    return base + encoded
  }
}

export function withCacheBust(url: string, v?: number): string {
  if (!url) return url
  const vv = v ?? Date.now()
  try {
    const u = new URL(url)
    u.searchParams.set("v", String(vv))
    return u.toString()
  } catch {
    return url + (url.includes("?") ? "&" : "?") + "v=" + vv
  }
}
