import { copyFile, mkdir } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, '..')
const distDir = path.join(frontendRoot, 'dist')
const entryFile = path.join(distDir, 'index.html')

const spaRoutes = ['login']

async function ensureRouteFile(route) {
  const targetDir = path.join(distDir, route)
  await mkdir(targetDir, { recursive: true })
  const targetFile = path.join(targetDir, 'index.html')
  await copyFile(entryFile, targetFile)
}

async function main() {
  await Promise.all(spaRoutes.map(ensureRouteFile))
}

main().catch((error) => {
  console.error('Failed to prepare LHCI SPA route fallbacks:', error)
  process.exitCode = 1
})
