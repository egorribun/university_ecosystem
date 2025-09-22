export function resolveMediaUrl(input?: string, backendOrigin = ""): string {
  if (!input) return ""
  const raw = String(input).trim()
  if (/^(data:|blob:|https?:\/\/)/i.test(raw)) return raw
  const base = backendOrigin || (typeof window !== "undefined" ? window.location.origin : "")
  if (!base) return raw
  if (/^\/(static|media)\//i.test(raw)) return base.replace(/\/+$/, "") + raw
  try {
    const u = new URL(raw, base)
    if (u.pathname.startsWith("/static/") || u.pathname.startsWith("/media/")) {
      return u.origin + u.pathname + u.search
    }
    return u.toString()
  } catch {
    return raw
  }
}