import { promises as fs } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { brotliCompressSync, gzipSync } from "node:zlib"

const DEFAULT_DIST_DIR = path.resolve(process.cwd(), "dist")
const DEFAULT_REPORT_PATH = path.resolve(process.cwd(), "bundle-report.json")
const ASSET_EXTENSIONS = new Set([".js", ".css"])

// Transfer budgets are baseline ratchets, not substitutes for route-level LHCI.
// Password dictionaries are isolated, user-intent-loaded chunks and therefore
// have their own bounded ceiling instead of weakening the general lazy limit.
export const BUNDLE_BUDGETS = Object.freeze({
  mainJsRawKb: 500,
  initialJsGzipKb: 420,
  generalLazyJsGzipKb: 280,
  // The language dictionaries are fetched only after explicit password-field
  // interaction. Keep their raw ceiling bounded too, while allowing Vite's
  // global warning threshold to reflect the largest intentional lazy asset.
  passwordDictionaryRawKb: 1250,
  passwordDictionaryGzipKb: 600,
})

const formatKiB = (bytes) => Math.round((bytes / 1024) * 100) / 100

export function normalizeAssetPath(filePath) {
  return filePath.replaceAll("\\", "/")
}

async function readFiles(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true })
  const files = await Promise.all(
    entries.map(async (entry) => {
      const resolved = path.join(dir, entry.name)
      return entry.isDirectory() ? readFiles(resolved) : [resolved]
    })
  )
  return files.flat()
}

function getAttribute(tag, attribute) {
  for (const match of tag.matchAll(/\b([a-z][\w:-]*)=["']([^"']+)["']/gi)) {
    if (match[1]?.toLowerCase() === attribute.toLowerCase()) return match[2]
  }
  return undefined
}

function normalizeHtmlAssetReference(reference, htmlRelativeDirectory) {
  const withoutSuffix = reference.split(/[?#]/, 1)[0]
  if (!withoutSuffix || /^(?:https?:)?\/\//i.test(withoutSuffix)) return null
  const relativeReference = withoutSuffix.replace(/^\//, "")
  return normalizeAssetPath(
    path.posix.normalize(path.posix.join(htmlRelativeDirectory, relativeReference))
  )
}

function extractInitialAssetPaths(html, htmlRelativeDirectory) {
  const initialPaths = new Set()
  for (const tag of html.match(/<(?:link|script)\b[^>]*>/gi) ?? []) {
    const isModulePreload =
      tag.startsWith("<link") && getAttribute(tag, "rel")?.toLowerCase() === "modulepreload"
    const isModuleScript =
      tag.startsWith("<script") && getAttribute(tag, "type")?.toLowerCase() === "module"
    if (!isModulePreload && !isModuleScript) continue

    const reference = getAttribute(tag, isModulePreload ? "href" : "src")
    if (!reference) continue
    const normalized = normalizeHtmlAssetReference(reference, htmlRelativeDirectory)
    if (normalized?.endsWith(".js")) initialPaths.add(normalized)
  }
  return initialPaths
}

async function findEntryHtml(distDir) {
  for (const candidate of [
    path.join(distDir, "client", "index.html"),
    path.join(distDir, "index.html"),
  ]) {
    try {
      await fs.access(candidate)
      return candidate
    } catch (error) {
      if (error?.code !== "ENOENT") throw error
    }
  }
  throw new Error(
    `No client index.html found in ${distDir}; initial bundle graph cannot be verified`
  )
}

function largestBy(items, field) {
  return items.reduce(
    (largest, current) => (!largest || current[field] > largest[field] ? current : largest),
    null
  )
}

export async function analyzeBundle(distDir = DEFAULT_DIST_DIR, options = {}) {
  const entryHtmlPath = await findEntryHtml(distDir)
  const html = await fs.readFile(entryHtmlPath, "utf8")
  const htmlRelativeDirectory = normalizeAssetPath(
    path.relative(distDir, path.dirname(entryHtmlPath))
  )
  const initialPaths = extractInitialAssetPaths(html, htmlRelativeDirectory)
  const assetFiles = (await readFiles(path.dirname(entryHtmlPath))).filter((filePath) =>
    ASSET_EXTENSIONS.has(path.extname(filePath))
  )
  if (assetFiles.length === 0) {
    throw new Error(`No build assets found in ${distDir}. Did you run the build?`)
  }

  const assets = await Promise.all(
    assetFiles.map(async (filePath) => {
      const content = await fs.readFile(filePath)
      const assetPath = normalizeAssetPath(path.relative(distDir, filePath))
      const isJavaScript = assetPath.endsWith(".js")
      return {
        path: assetPath,
        type: isJavaScript ? "javascript" : "stylesheet",
        rawBytes: content.byteLength,
        gzipBytes: gzipSync(content, { level: 9 }).byteLength,
        brotliBytes: brotliCompressSync(content).byteLength,
        isMain: isJavaScript && /(?:^|\/)(?:index|main)-[^/]+\.js$/.test(assetPath),
        isInitial: isJavaScript && initialPaths.has(assetPath),
        isPasswordDictionary:
          isJavaScript && /(?:^|\/)vendor-password-strength-(?:en|ru)-[^/]+\.js$/.test(assetPath),
      }
    })
  )
  assets.sort((left, right) => left.path.localeCompare(right.path))

  const javascriptAssets = assets.filter((asset) => asset.type === "javascript")
  const mainAssets = javascriptAssets.filter((asset) => asset.isMain)
  if (mainAssets.length === 0) {
    throw new Error(`No main/index JavaScript chunk found in ${distDir}`)
  }
  const initialAssets = javascriptAssets.filter((asset) => asset.isInitial)
  if (initialAssets.length === 0) {
    throw new Error(`No initial JavaScript assets referenced by ${entryHtmlPath}`)
  }
  const generalLazyAssets = javascriptAssets.filter(
    (asset) => !asset.isInitial && !asset.isPasswordDictionary
  )
  const passwordDictionaryAssets = javascriptAssets.filter(
    (asset) => !asset.isInitial && asset.isPasswordDictionary
  )
  const main = largestBy(mainAssets, "rawBytes")
  const largestGeneralLazy = largestBy(generalLazyAssets, "gzipBytes")
  const largestPasswordDictionary = largestBy(passwordDictionaryAssets, "gzipBytes")
  const sum = (items, field) => items.reduce((total, asset) => total + asset[field], 0)

  return {
    schemaVersion: 1,
    generatedAt: options.generatedAt ?? new Date().toISOString(),
    commitSha: options.commitSha ?? process.env.GITHUB_SHA ?? null,
    sourceRoot: normalizeAssetPath(path.relative(process.cwd(), distDir)) || ".",
    budgets: BUNDLE_BUDGETS,
    summary: {
      assetCount: assets.length,
      javascriptAssetCount: javascriptAssets.length,
      initialJsAssetCount: initialAssets.length,
      lazyJsAssetCount: javascriptAssets.length - initialAssets.length,
      totalRawBytes: sum(assets, "rawBytes"),
      totalGzipBytes: sum(assets, "gzipBytes"),
      totalBrotliBytes: sum(assets, "brotliBytes"),
      mainJsPath: main?.path ?? null,
      mainJsRawBytes: main?.rawBytes ?? 0,
      initialJsGzipBytes: sum(initialAssets, "gzipBytes"),
      initialJsBrotliBytes: sum(initialAssets, "brotliBytes"),
      largestGeneralLazyJsPath: largestGeneralLazy?.path ?? null,
      largestGeneralLazyJsGzipBytes: largestGeneralLazy?.gzipBytes ?? 0,
      largestPasswordDictionaryPath: largestPasswordDictionary?.path ?? null,
      largestPasswordDictionaryRawBytes: largestPasswordDictionary?.rawBytes ?? 0,
      largestPasswordDictionaryGzipBytes: largestPasswordDictionary?.gzipBytes ?? 0,
    },
    assets,
  }
}

export function getBundleBudgetViolations(report) {
  const { summary } = report
  const violations = []
  const checks = [
    {
      actualBytes: summary.mainJsRawBytes,
      limitKb: BUNDLE_BUDGETS.mainJsRawKb,
      message: `Main JS chunk '${summary.mainJsPath}' exceeds raw budget`,
    },
    {
      actualBytes: summary.initialJsGzipBytes,
      limitKb: BUNDLE_BUDGETS.initialJsGzipKb,
      message: "Initial JS preload graph exceeds gzip budget",
    },
    {
      actualBytes: summary.largestGeneralLazyJsGzipBytes,
      limitKb: BUNDLE_BUDGETS.generalLazyJsGzipKb,
      message: `Lazy JS chunk '${summary.largestGeneralLazyJsPath}' exceeds gzip budget`,
    },
    {
      actualBytes: summary.largestPasswordDictionaryRawBytes ?? 0,
      limitKb: BUNDLE_BUDGETS.passwordDictionaryRawKb,
      message: `Password dictionary '${summary.largestPasswordDictionaryPath}' exceeds raw budget`,
    },
    {
      actualBytes: summary.largestPasswordDictionaryGzipBytes,
      limitKb: BUNDLE_BUDGETS.passwordDictionaryGzipKb,
      message: `Password dictionary '${summary.largestPasswordDictionaryPath}' exceeds gzip budget`,
    },
  ]

  for (const { actualBytes, limitKb, message } of checks) {
    if (actualBytes > limitKb * 1024) {
      violations.push(`${message}: ${formatKiB(actualBytes).toFixed(2)} KiB > ${limitKb} KiB`)
    }
  }
  return violations
}

export function assertBundleBudgets(report) {
  const violations = getBundleBudgetViolations(report)
  if (violations.length > 0) {
    throw new Error(
      `${violations.join("\n")}\nBundle budgets violated (${violations.length} issue${violations.length === 1 ? "" : "s"})`
    )
  }
  return report.summary
}

async function main() {
  const report = await analyzeBundle()
  const violations = getBundleBudgetViolations(report)
  report.validation = { valid: violations.length === 0, violations }
  await fs.writeFile(DEFAULT_REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`, "utf8")
  console.log(`Bundle report written to ${DEFAULT_REPORT_PATH}`)
  assertBundleBudgets(report)
  console.log("Bundle budgets within limits:", {
    mainJsRawKiB: formatKiB(report.summary.mainJsRawBytes),
    initialJsGzipKiB: formatKiB(report.summary.initialJsGzipBytes),
    largestGeneralLazyJsGzipKiB: formatKiB(report.summary.largestGeneralLazyJsGzipBytes),
    largestPasswordDictionaryRawKiB: formatKiB(report.summary.largestPasswordDictionaryRawBytes),
    largestPasswordDictionaryGzipKiB: formatKiB(report.summary.largestPasswordDictionaryGzipBytes),
  })
}

const isDirectExecution =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))
if (isDirectExecution) {
  main().catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
}
