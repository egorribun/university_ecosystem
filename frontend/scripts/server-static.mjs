import path from "node:path"

/**
 * Resolve a request path beneath the built client directory.
 *
 * Static assets are served before the SSR handler, so this boundary must be
 * fail-closed for both malformed URL encoding and paths that resolve outside
 * the client root.  Returning null lets the caller continue with its normal
 * route handling without ever touching an unsafe filesystem path.
 */
export function resolveStaticFile(staticRoot, urlPath) {
  let decodedPath
  try {
    decodedPath = decodeURIComponent(urlPath)
  } catch {
    // Malformed percent-encoding must not escape the request handler as an
    // uncaught URIError.  The SSR layer will produce its regular safe error.
    return null
  }

  const requested = path.normalize(decodedPath).replace(/^[/\\]+/, "")
  const filePath = path.resolve(staticRoot, requested)
  const relative = path.relative(staticRoot, filePath)

  // A sibling such as `dist/client_secrets` must not pass a string-prefix
  // check against `dist/client`.  `path.relative` handles platform separators
  // and drive roots, while the absolute check rejects a different volume.
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null

  return filePath
}
