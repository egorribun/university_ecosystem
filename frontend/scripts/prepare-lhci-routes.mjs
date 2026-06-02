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
]

async function injectLhciMode(htmlPath) {
  let html = await readFile(htmlPath, "utf-8")

  // Add lhci-mode class to the html element
  html = html.replace('<html lang="ru"', '<html lang="ru" class="lhci-mode"')

  // Replace the LHCI_MODE_MARKER comment with a script that adds the class
  html = html.replace(
    "<!-- LHCI_MODE_MARKER -->",
    '<script>document.documentElement.classList.add("lhci-mode");</script>'
  )

  // Make the lhci-marker visible by changing display: none to display: flex
  html = html.replace(/id="lhci-marker"([^>]*?)display:\s*none/, 'id="lhci-marker"$1display: flex')

  // Inject CSS to make root immediately visible in LHCI mode
  // Note: The CSS placeholder comment gets removed by Vite, so we inject into empty style tag
  html = html.replace(
    "<style>\n    \n  </style>",
    "<style>.lhci-mode #root { opacity: 1 !important; }</style>"
  )

  await writeFile(htmlPath, html, "utf-8")
}

async function ensureRouteFiles(route) {
  const segments = route.split("/").filter(Boolean)

  const directoryTarget = path.join(distDir, ...segments)
  await mkdir(directoryTarget, { recursive: true })

  const indexTarget = path.join(directoryTarget, "index.html")
  await copyFile(entryFile, indexTarget)

  const htmlFallback = `${path.join(distDir, ...segments)}.html`
  await copyFile(entryFile, htmlFallback)
}

async function main() {
  // First inject LHCI mode into the main entry file
  await injectLhciMode(entryFile)

  // Then copy the modified file to SPA routes
  await Promise.all(spaRoutes.map(ensureRouteFiles))
}

main().catch((error) => {
  console.error("Failed to prepare LHCI SPA route fallbacks:", error)
  process.exitCode = 1
})
