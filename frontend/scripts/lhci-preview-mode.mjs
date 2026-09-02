/**
 * Resolve how Lighthouse serves an already-built frontend.
 *
 * Static SPA fallbacks are useful for a local smoke check, but they are not a
 * faithful performance target for the SSR application: every deep link starts
 * from a route-agnostic document and then clears it through createRoot(). CI
 * can opt into the production SSR wrapper so each URL receives the same
 * route-specific HTML that a deployment serves. Keep this decision pure so
 * workflow contracts can test it without starting a server or Lighthouse.
 */

const DEFAULT_SSR_PREVIEW_PORT = 4175

function resolvePort(rawValue) {
  const port = Number.parseInt(String(rawValue ?? ""), 10)
  return Number.isInteger(port) && port >= 1024 && port <= 65_535 ? port : DEFAULT_SSR_PREVIEW_PORT
}

export function resolveLhciPreviewMode(env = process.env) {
  const remotePreview = env.PREVIEW_URL ?? env.LHCI_URL ?? ""
  const useSsrPreview = ["1", "true"].includes(String(env.LHCI_USE_SSR_PREVIEW ?? "").toLowerCase())

  if (remotePreview) {
    return { kind: "remote", base: remotePreview }
  }

  if (useSsrPreview) {
    const port = resolvePort(env.LHCI_SSR_PREVIEW_PORT)
    return { kind: "ssr", base: `http://127.0.0.1:${port}`, port }
  }

  return { kind: "static", base: "" }
}

export function previewServerCommand(mode) {
  if (mode.kind === "ssr") return "node scripts/server-prod.mjs"
  if (mode.kind === "remote") return "node scripts/lhci-preview.mjs"
  return null
}

export function previewReadyPattern(mode) {
  if (mode.kind === "ssr") return "server-prod: listening"
  if (mode.kind === "remote") return "LHCI_READY"
  return null
}

/**
 * TanStack Start's Node SSR handler canonicalizes non-root trailing slashes
 * with a 307 redirect. Keep directory-form paths for static and remote
 * previews, but address the SSR handler at its canonical pathname so
 * Lighthouse starts its trace on the actual document.
 */
export function pathForLhciPreview(pathname, mode) {
  if (mode?.kind !== "ssr" || pathname === "/") return pathname
  return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname
}
