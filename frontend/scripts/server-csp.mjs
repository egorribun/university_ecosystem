import { Transform } from "node:stream"

export const CSP_NONCE_PLACEHOLDER = "__CSP_NONCE__"

// Mirrors the backend production defaults in app/core/config/mixins/csp_settings.py
// and app/core/policies/csp.py. Node SSR currently has no bridge for backend
// custom SECURITY_CSP/connect-source settings, so this deliberately implements
// the approved production-default boundary rather than claiming those overrides.
const DEFAULT_CONNECT_SOURCES = Object.freeze([
  "'self'",
  "https://*.push.apple.com",
  "https://*.push.services.mozilla.com",
  "https://api.spotify.com",
  "https://fcm.googleapis.com",
  "https://fcmregistrations.googleapis.com",
  "https://updates.push.services.mozilla.com",
])

function assertNonce(nonce) {
  if (
    typeof nonce !== "string" ||
    nonce.length === 0 ||
    nonce.length > 128 ||
    !/^[A-Za-z0-9+/_-]+={0,2}$/u.test(nonce)
  ) {
    throw new TypeError("CSP nonce must be a bounded base64 token")
  }
}

export function buildNodeCspHeaders(nonce) {
  assertNonce(nonce)
  const connectSources = [...new Set(DEFAULT_CONNECT_SOURCES)].sort().join(" ")
  const policyDirectives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ` +
      "https://accounts.google.com 'report-sample'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: https: blob:",
    `connect-src ${connectSources}`,
    "font-src 'self' data: https://fonts.gstatic.com",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
    "frame-ancestors 'self'",
    "trusted-types app dompurify-news goog#html 'allow-duplicates'",
    "require-trusted-types-for 'script'",
  ]
  const enforcingPolicy = policyDirectives.join("; ")
  const reportOnlyPolicy = policyDirectives
    .filter((directive) => directive !== "upgrade-insecure-requests")
    .join("; ")

  return Object.freeze({
    "content-security-policy": enforcingPolicy,
    "content-security-policy-report-only": `${reportOnlyPolicy}; report-uri /api/v1/csp-report`,
  })
}

export function applyNodeCspToHtmlResponse(response, nonce) {
  assertNonce(nonce)
  const contentType = response.headers.get("content-type") ?? ""
  if (!contentType.toLowerCase().includes("text/html")) return response

  const headers = new Headers(response.headers)
  for (const [name, value] of Object.entries(buildNodeCspHeaders(nonce))) {
    headers.set(name, value)
  }
  headers.set("cache-control", "no-store, private, max-age=0")
  headers.delete("etag")
  headers.delete("last-modified")

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  })
}

export function replaceCspNoncePlaceholder(html, nonce) {
  assertNonce(nonce)
  if (typeof html !== "string") {
    throw new TypeError("Static CSP placeholder replacement requires HTML text")
  }
  return html.replaceAll(CSP_NONCE_PLACEHOLDER, nonce)
}

/** Replace only the explicit build-time marker while preserving arbitrary HTML bytes. */
export function createCspNoncePlaceholderTransform(nonce) {
  assertNonce(nonce)
  const marker = Buffer.from(CSP_NONCE_PLACEHOLDER, "ascii")
  const markerText = CSP_NONCE_PLACEHOLDER
  let carry = Buffer.alloc(0)

  return new Transform({
    transform(chunk, _encoding, callback) {
      const input = Buffer.concat([carry, Buffer.from(chunk)])
      let safeEnd = Math.max(0, input.length - marker.length + 1)
      let scanFrom = 0
      while (scanFrom < safeEnd) {
        const markerAt = input.indexOf(marker, scanFrom)
        if (markerAt < 0 || markerAt >= safeEnd) break
        if (markerAt + marker.length > safeEnd) {
          safeEnd = markerAt + marker.length
          break
        }
        scanFrom = markerAt + marker.length
      }

      const safeBytes = input.subarray(0, safeEnd)
      carry = input.subarray(safeEnd)
      const safeText = safeBytes.toString("latin1")
      callback(null, Buffer.from(safeText.replaceAll(markerText, nonce), "latin1"))
    },
    flush(callback) {
      const tail = carry.toString("latin1").replaceAll(markerText, nonce)
      carry = Buffer.alloc(0)
      callback(null, Buffer.from(tail, "latin1"))
    },
  })
}
