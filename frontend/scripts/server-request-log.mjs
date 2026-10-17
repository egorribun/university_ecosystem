/**
 * Return a safe request path for access logs.
 *
 * Query strings and fragments can contain OAuth codes or other credentials,
 * while reset-password uses a bearer token in the path itself. Access logs
 * must retain route-level diagnostics without persisting either value.
 */
export function sanitizeRequestTarget(requestTarget) {
  let pathname
  try {
    pathname = new URL(requestTarget ?? "/", "http://request.local").pathname
  } catch {
    return "[REDACTED]"
  }

  let decodedPath
  try {
    decodedPath = decodeURIComponent(pathname).replaceAll("\\", "/")
  } catch {
    return "[REDACTED]"
  }

  const segments = decodedPath.split("/").filter(Boolean)
  const resetPasswordIndex = segments.findIndex(
    (segment) => segment.toLowerCase() === "reset-password"
  )
  if (resetPasswordIndex < 0) return pathname

  const safeSegments = segments.slice(0, resetPasswordIndex + 1)
  if (resetPasswordIndex + 1 < segments.length) safeSegments.push("[REDACTED]")
  return `/${safeSegments.join("/")}`
}
