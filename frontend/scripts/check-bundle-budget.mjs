import { promises as fs } from "node:fs"
import path from "node:path"
import { brotliCompressSync, gzipSync } from "node:zlib"

const DIST_DIR = path.resolve(process.cwd(), "dist")
const ASSET_EXTENSIONS = [".js", ".css"]

const LIMITS = {
  maxCompressedTotalKb: 1200,
  maxIndividualCompressedKb: 420,
  maxInitialJsKb: 620,
}

const formatKb = (bytes) => Math.round((bytes / 1024) * 100) / 100

async function readFiles(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true })
  const files = await Promise.all(
    entries.map(async (entry) => {
      const resolved = path.join(dir, entry.name)
      if (entry.isDirectory()) return readFiles(resolved)
      return [resolved]
    })
  )
  return files.flat()
}

function isAsset(filePath) {
  return ASSET_EXTENSIONS.some((ext) => filePath.endsWith(ext))
}

async function collectAssetStats() {
  const files = await readFiles(DIST_DIR)
  const assetFiles = files.filter(isAsset)

  const stats = await Promise.all(
    assetFiles.map(async (filePath) => {
      const content = await fs.readFile(filePath)
      const gzipSize = gzipSync(content).byteLength
      const brotliSize = brotliCompressSync(content).byteLength
      return {
        path: path.relative(DIST_DIR, filePath),
        raw: content.byteLength,
        gzip: gzipSize,
        brotli: brotliSize,
        isInitial: /\/assets\/index-[\w]+\.js$/.test(filePath),
      }
    })
  )

  return stats
}

function assertBudgets(stats) {
  const totalCompressed = stats.reduce((acc, item) => acc + Math.min(item.gzip, item.brotli), 0)
  const heaviest = stats.reduce((prev, curr) => (curr.gzip > prev.gzip ? curr : prev), stats[0])
  const initialJsTotal = stats
    .filter((item) => item.isInitial && item.path.endsWith(".js"))
    .reduce((acc, item) => acc + Math.min(item.gzip, item.brotli), 0)

  const violations = []

  if (formatKb(totalCompressed) > LIMITS.maxCompressedTotalKb) {
    violations.push(
      `Total compressed assets exceed budget: ${formatKb(totalCompressed)}kb > ${LIMITS.maxCompressedTotalKb}kb`
    )
  }

  if (formatKb(heaviest.gzip) > LIMITS.maxIndividualCompressedKb) {
    violations.push(
      `Largest asset '${heaviest.path}' exceeds budget: ${formatKb(heaviest.gzip)}kb > ${LIMITS.maxIndividualCompressedKb}kb`
    )
  }

  if (formatKb(initialJsTotal) > LIMITS.maxInitialJsKb) {
    violations.push(
      `Initial JS entry exceeds budget: ${formatKb(initialJsTotal)}kb > ${LIMITS.maxInitialJsKb}kb`
    )
  }

  if (violations.length) {
    for (const violation of violations) {
      console.error(violation)
    }
    throw new Error(
      `Bundle budgets violated (${violations.length} issue${violations.length === 1 ? "" : "s"})`
    )
  }

  return {
    totalCompressedKb: formatKb(totalCompressed),
    largestAssetKb: formatKb(heaviest.gzip),
    initialJsKb: formatKb(initialJsTotal),
  }
}

async function main() {
  const stats = await collectAssetStats()
  if (!stats.length) {
    throw new Error(`No build assets found in ${DIST_DIR}. Did you run the build?`)
  }

  const summary = assertBudgets(stats)
  console.log("Bundle budgets within limits:", summary)
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
