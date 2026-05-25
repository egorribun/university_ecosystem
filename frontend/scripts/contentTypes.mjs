/**
 * Static-file MIME-type map for the production Node SSR runtime.
 *
 * Extracted from `frontend/scripts/server-prod.mjs` in Wave 175 SW8 so that
 * regression tests (`frontend/src/__tests__/serverProd.test.ts`) can import
 * the map without triggering the script's top-level `http.createServer` +
 * `server.listen()` side effects.
 *
 * Critical invariants enforced by the test suite:
 * - `.wasm` resolves to "application/wasm" exactly (Wave 173 SW1 Fix B,
 *   prevents WebAssembly.instantiateStreaming "Incorrect response MIME
 *   type" → forces regex fallback in sanitize.ts + breaks crypto.worker).
 *   This regression lay dormant ≥17 waves between W131 SW7 introduction
 *   and W173 SW1 discovery because /messenger (the only feature
 *   exercising crypto.worker) was Phase 5 punted.
 * - Other static extensions resolve to UTF-8-charset MIME types where
 *   applicable (.js, .css, .html, .json, .webmanifest, .txt) and binary
 *   types without charset suffix (.png, .woff2, .wasm).
 * - Missing extension entries fall through to `application/octet-stream`
 *   in the caller (server-prod.mjs serveStatic line 123).
 */
export const CONTENT_TYPES = Object.freeze({
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".wasm": "application/wasm",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".ttf": "font/ttf",
  ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
})

/**
 * Resolve a file path to its Content-Type header value. Returns
 * "application/octet-stream" for any unknown extension.
 *
 * @param {string} filePath - File path or just a filename with extension.
 * @returns {string} Content-Type header value.
 */
export function getContentType(filePath) {
  const lastDot = filePath.lastIndexOf(".")
  if (lastDot === -1) return "application/octet-stream"
  const ext = filePath.slice(lastDot).toLowerCase()
  return CONTENT_TYPES[ext] ?? "application/octet-stream"
}
