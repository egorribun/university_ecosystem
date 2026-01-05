import { copyFile, mkdir } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, "..")
const distDir = path.join(frontendRoot, "dist")
const entryFile = path.join(distDir, "index.html")

const spaRoutes = ["login"]

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
  await Promise.all(spaRoutes.map(ensureRouteFiles))
}

main().catch((error) => {
  console.error("Failed to prepare LHCI SPA route fallbacks:", error)
  process.exitCode = 1
})
