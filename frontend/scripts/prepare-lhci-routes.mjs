import { existsSync } from "node:fs"
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, "..")
// W139 SW5 fix — post-W125 SSR migration, the SPA index.html mirror lives
// at dist/client/index.html (per post-build-shell.mjs candidates). Pre-W125
// it was at dist/index.html. Defensive detection handles both layouts so
// LHCI route preparation works regardless of build pipeline variant.
const distClientDir = path.join(frontendRoot, "dist", "client")
const distLegacyDir = path.join(frontendRoot, "dist")
const distDir = existsSync(path.join(distClientDir, "index.html")) ? distClientDir : distLegacyDir
const entryFile = path.join(distDir, "index.html")
const notFoundFile = path.join(distDir, "not-found.html")

// Wave 112 — LHCI covers all 6 target pages for baseline measurement.
// Auth-gated routes redirect to /login when no session — the redirect
// itself is a valid CWV baseline (TTFB/FCP/LCP of the final page).
const spaRoutes = [
  "login",
  "dashboard",
  "news",
  "schedule",
  "events",
  "activity",
  "map",
  "messenger",
  // Keep the unknown-document audit on a dedicated lightweight page instead
  // of falling back to the full React shell.
  "404",
]

/**
 * Lighthouse does not emulate `prefers-reduced-motion` by default. Keep the
 * audit shell deterministic by disabling only decorative, continuously
 * running effects. One-shot content entrance animations are intentionally
 * left untouched so the captured DOM still follows the production geometry.
 */
export const LHCI_STATIC_EFFECTS_CSS = `/* data-lhci-static-effects */
.lhci-mode .aurora-mesh::after,
.lhci-mode .sched-aurora-hero {
  animation: none !important;
  filter: none !important;
  transform: none !important;
}

.lhci-mode .weather-ambient,
.lhci-mode .sched-current-glow,
.lhci-mode .sched-progress-fill::after,
.lhci-mode .sched-today-badge,
.lhci-mode .sched-empty-icon,
.lhci-mode .sched-empty-ring,
.lhci-mode .sched-empty-orbit,
.lhci-mode .sched-flip-colon,
.lhci-mode .sched-drop-target,
.lhci-mode .sched-skeleton-shimmer,
.lhci-mode .messenger-typing-pulse,
.lhci-mode .messenger-online-pulse::after,
.lhci-mode .messenger-skeleton-shimmer,
.lhci-mode .profile-skeleton-shimmer,
.lhci-mode .settings-skeleton-shimmer,
.lhci-mode .auth-skeleton-shimmer,
.lhci-mode .events-register-pulse,
.lhci-mode .refetch-shimmer::after,
.lhci-mode .border-glow-pulse {
  animation: none !important;
}

.lhci-mode .weather-ambient {
  display: none !important;
}`

const HTML_OPEN_TAG_PATTERN = /<html\b[^>]*>/iu
const CLASS_ATTRIBUTE_PATTERN = /(\bclass\s*=\s*)(["'])([^"']*)\2/iu

/** Add the marker class without assuming attribute order or language. */
export function addLhciModeClass(html) {
  return html.replace(HTML_OPEN_TAG_PATTERN, (openingTag) => {
    if (/\bclass\s*=\s*["'][^"']*\blhci-mode\b[^"']*["']/iu.test(openingTag)) {
      return openingTag
    }

    const classAttribute = openingTag.match(CLASS_ATTRIBUTE_PATTERN)
    if (classAttribute) {
      const [, prefix, quote, value] = classAttribute
      const classes = value.trim()
      const nextValue = classes ? `${classes} lhci-mode` : "lhci-mode"
      return openingTag.replace(
        CLASS_ATTRIBUTE_PATTERN,
        () => `${prefix}${quote}${nextValue}${quote}`
      )
    }

    return openingTag.replace(/>$/u, ' class="lhci-mode">')
  })
}

/** Inject the static-effect rules once, even when route preparation is retried. */
export function addLhciStaticEffectsCss(html) {
  if (html.includes("data-lhci-static-effects")) return html

  const styleBlock = `<style data-lhci-static-effects>${LHCI_STATIC_EFFECTS_CSS}</style>`
  if (/<\/head>/iu.test(html)) {
    return html.replace(/<\/head>/iu, `${styleBlock}</head>`)
  }
  return `${styleBlock}${html}`
}

/** Prepare a shell string; kept pure so the contract is unit-testable. */
export function prepareLhciHtml(html) {
  let prepared = addLhciModeClass(html)
  // The class is present on the opening tag before any script can run. Drop
  // the legacy marker rather than interpolating a script into externally
  // supplied HTML (which would trigger an XSS-prone sink in static analysis).
  prepared = prepared.replace(/<!--\s*LHCI_MODE_MARKER\s*-->/iu, "")
  return addLhciStaticEffectsCss(prepared)
}

/** Resolve the source document for a prepared audit route. */
export function routeSourcePath(route, entryPath = entryFile, notFoundPath = notFoundFile) {
  return route === "404" ? notFoundPath : entryPath
}

async function injectLhciMode(htmlPath) {
  let html = await readFile(htmlPath, "utf-8")

  html = prepareLhciHtml(html)

  // Make the lhci-marker visible by changing display: none to display: flex
  html = html.replace(/id="lhci-marker"([^>]*?)display:\s*none/, 'id="lhci-marker"$1display: flex')

  await writeFile(htmlPath, html, "utf-8")
}

async function ensureRouteFiles(route) {
  const segments = route.split("/").filter(Boolean)

  const directoryTarget = path.join(distDir, ...segments)
  await mkdir(directoryTarget, { recursive: true })

  const indexTarget = path.join(directoryTarget, "index.html")
  const sourcePath = routeSourcePath(route)
  await copyFile(sourcePath, indexTarget)

  const htmlFallback = `${path.join(distDir, ...segments)}.html`
  await copyFile(sourcePath, htmlFallback)
}

async function main() {
  // First inject LHCI mode into the main entry file
  await injectLhciMode(entryFile)

  // Then copy the modified file to SPA routes
  await Promise.all(spaRoutes.map(ensureRouteFiles))
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error("Failed to prepare LHCI SPA route fallbacks:", error)
    process.exitCode = 1
  })
}
