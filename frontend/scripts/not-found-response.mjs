import path from "node:path"

const DOCUMENT_METHODS = new Set(["GET", "HEAD"])

function acceptsHtml(accept) {
  if (!accept) return true
  const normalized = String(accept).toLowerCase()
  return (
    normalized.includes("text/html") ||
    normalized.includes("application/xhtml+xml") ||
    normalized.includes("*/*")
  )
}

/**
 * Keep API, WebSocket and asset errors intact while giving browser document
 * navigations a useful product fallback after the SSR router returns 404.
 */
export function shouldServeNotFoundDocument({ method, urlPath, accept } = {}) {
  const normalizedMethod = String(method ?? "GET").toUpperCase()
  if (!DOCUMENT_METHODS.has(normalizedMethod) || !acceptsHtml(accept)) return false

  const normalizedPath = typeof urlPath === "string" ? urlPath.split("?", 1)[0] : "/"
  if (/^\/(?:api|ws|graphql)(?:\/|$)/iu.test(normalizedPath)) return false
  if (normalizedPath === "/healthz") return false

  const extension = path.extname(normalizedPath)
  return extension === "" || extension.toLowerCase() === ".html"
}

export function createNotFoundResponse(html, { method = "GET", contentLanguage = "ru" } = {}) {
  const normalizedMethod = String(method).toUpperCase()
  const body = String(html)
  const headers = new Headers({
    "cache-control": "no-store, max-age=0",
    "content-language": String(contentLanguage),
    "content-type": "text/html; charset=utf-8",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, nofollow",
  })
  headers.set("content-length", String(Buffer.byteLength(body, "utf8")))

  return new Response(
    DOCUMENT_METHODS.has(normalizedMethod) && normalizedMethod === "HEAD" ? null : body,
    {
      status: 404,
      statusText: "Not Found",
      headers,
    }
  )
}

export { DOCUMENT_METHODS }
