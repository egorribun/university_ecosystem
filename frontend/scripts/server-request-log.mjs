const RESET_PASSWORD_TOKEN = /^(\/reset-password\/)[^/]+/iu

/**
 * Return a safe request path for access logs.
 *
 * Query strings and fragments can contain OAuth codes or other credentials,
 * while reset-password uses a bearer token in the path itself. Access logs
 * must retain route-level diagnostics without persisting either value.
 */
export function sanitizeRequestTarget(requestTarget) {
  let pathname = "/"
  try {
    pathname = new URL(requestTarget ?? "/", "http://request.local").pathname
  } catch {
    pathname = String(requestTarget ?? "/").split(/[?#]/u, 1)[0] || "/"
  }
  return pathname.replace(RESET_PASSWORD_TOKEN, "$1[REDACTED]")
}
