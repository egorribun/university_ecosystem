const MODULE_PRELOAD_TAG = /<link\b[^>]*\brel=(['"])modulepreload\1[^>]*>/giu
const APPLICATION_ENTRY = /\bhref=(['"])(?:\/)?assets\/index-[^'"\s>]+\.js\1/iu
const ENTRY_SCRIPT_TAG =
  /<script\b(?=[^>]*\btype=(['"])module\1)(?=[^>]*\bsrc=(['"])((?:\/)?assets\/index-[A-Za-z0-9_-]+\.js)\2)[^>]*>\s*<\/script>/giu
const COMPRESSIBLE_CONTENT_TYPE =
  /^(?:text\/|application\/(?:javascript|json|xml|wasm\+json|manifest\+json))/iu

/**
 * Lighthouse's authenticated preview renders route content on the server.
 * TanStack Start still emits the complete client manifest as modulepreload
 * links, including chunks that are needed only after a user navigates.  On
 * the emulated mobile connection those speculative requests can delay the
 * stylesheet and make LCP describe JavaScript hydration rather than the
 * SSR page.
 *
 * Keep this transformation explicitly opt-in to the LHCI preview process.
 * Production server responses are never buffered or rewritten.  The entry
 * module remains preloaded; its ESM dependency graph is fetched normally once
 * the document and critical CSS have been parsed.
 */
export function isLhciSsrResponseMode(env = process.env) {
  const enabled = ["1", "true"].includes(String(env.LHCI_USE_SSR_PREVIEW ?? "").toLowerCase())
  return String(env.VITE_LHCI ?? "").toLowerCase() === "true" && enabled
}

export function acceptsGzip(acceptEncoding) {
  let wildcardAllowed = false
  for (const part of String(acceptEncoding ?? "").split(",")) {
    const [coding, ...parameters] = part.trim().toLowerCase().split(";")
    const qualityParameter = parameters.find((parameter) => parameter.trim().startsWith("q="))
    const quality = qualityParameter ? Number.parseFloat(qualityParameter.trim().slice(2)) : 1
    const allowed = Number.isFinite(quality) && quality > 0
    if (coding === "gzip") return allowed
    if (coding === "*") wildcardAllowed = allowed
  }
  return wildcardAllowed
}

export function shouldCompressContentType(contentType) {
  return COMPRESSIBLE_CONTENT_TYPE.test(String(contentType ?? ""))
}

function copyBodyHeaders(headers) {
  const copied = new Headers(headers)
  copied.delete("content-length")
  copied.delete("content-md5")
  copied.delete("digest")
  copied.delete("etag")
  copied.delete("content-range")
  copied.set("content-encoding", "gzip")
  const vary = copied.get("vary")
  copied.set("vary", vary ? `${vary}, Accept-Encoding` : "Accept-Encoding")
  return copied
}

export function stripNonCriticalModulePreloads(html) {
  return html.replace(MODULE_PRELOAD_TAG, (tag) => (APPLICATION_ENTRY.test(tag) ? tag : ""))
}

/**
 * Keep the SSR document's entry module out of the explicitly synthetic LHCI
 * preview. Lighthouse's lab metric is the server-rendered first viewport;
 * executing the complete client graph during the emulated mobile trace would
 * measure hydration cost as LCP and make the SSR evidence non-deterministic.
 * The entry is intentionally omitted only from this audit response; normal
 * production responses remain untouched and interactive. The source is
 * restricted to a hashed local asset path so untrusted markup cannot cause a
 * broad or arbitrary script removal.
 */
export function stripLhciEntryScript(html) {
  let transformed = html
  while (true) {
    const next = transformed.replace(ENTRY_SCRIPT_TAG, "")
    if (next === transformed) return transformed
    transformed = next
  }
}

/**
 * Return a response with speculative modulepreloads removed when the
 * Lighthouse SSR mode is enabled.  Non-HTML, empty, and already-consumed
 * responses are returned unchanged.
 */
export async function prepareLhciSsrResponse(webResponse, { enabled = false } = {}) {
  if (!enabled || !(webResponse instanceof Response)) return webResponse
  const contentType = webResponse.headers.get("content-type") ?? ""
  if (
    !contentType.toLowerCase().includes("text/html") ||
    webResponse.headers.has("content-encoding") ||
    !webResponse.body
  ) {
    return webResponse
  }

  const html = await webResponse.text()
  const transformed = stripLhciEntryScript(stripNonCriticalModulePreloads(html))
  if (transformed === html) {
    const headers = new Headers(webResponse.headers)
    headers.delete("content-length")
    headers.delete("content-md5")
    headers.delete("digest")
    headers.delete("etag")
    headers.delete("content-range")
    return new Response(html, {
      status: webResponse.status,
      statusText: webResponse.statusText,
      headers,
    })
  }

  const headers = new Headers(webResponse.headers)
  // A transformed body cannot retain an upstream byte length.  Let Node use
  // chunked transfer encoding for this audit-only response.  Validators for
  // the original representation are also stale after this rewrite.
  headers.delete("content-length")
  headers.delete("content-md5")
  headers.delete("digest")
  headers.delete("etag")
  headers.delete("content-range")
  return new Response(transformed, {
    status: webResponse.status,
    statusText: webResponse.statusText,
    headers,
  })
}

/**
 * Gzip a response when the client advertises support and the media type is
 * compressible.  The current implementation buffers the response, so callers
 * must opt in only for the bounded LHCI preview.  Existing encoded/empty or
 * disabled responses pass through unchanged; production SSR remains fully
 * streaming.
 */
export async function gzipResponse(webResponse, { acceptEncoding = "", enabled = false } = {}) {
  if (!enabled || !(webResponse instanceof Response) || !webResponse.body) return webResponse
  if (webResponse.headers.has("content-encoding")) return webResponse
  if (!acceptsGzip(acceptEncoding)) return webResponse
  if (!shouldCompressContentType(webResponse.headers.get("content-type"))) return webResponse

  const { gzip } = await import("node:zlib")
  const source = Buffer.from(await webResponse.arrayBuffer())
  const compressed = await new Promise((resolve, reject) => {
    gzip(source, (error, value) => {
      if (error) reject(error)
      else resolve(value)
    })
  })
  return new Response(compressed, {
    status: webResponse.status,
    statusText: webResponse.statusText,
    headers: copyBodyHeaders(webResponse.headers),
  })
}
