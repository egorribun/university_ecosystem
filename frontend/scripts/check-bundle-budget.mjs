import { promises as fs } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { brotliCompressSync, gzipSync } from "node:zlib"

import { parse } from "parse5"

const DEFAULT_DIST_DIR = path.resolve(process.cwd(), "dist")
const DEFAULT_REPORT_PATH = path.resolve(process.cwd(), "bundle-report.json")
const ASSET_EXTENSIONS = new Set([".js", ".mjs", ".css"])
const HTML_LIMIT = 1024 * 1024
const HTML_NAMESPACE = "http://www.w3.org/1999/xhtml"

// parse5 preserves browser tree recovery without reporting every mismatched end
// tag. Require a real closing token where HTML does not permit its omission.
// Void names follow parse5's HTML serializer, including its legacy void tags.
const HTML_VOID_ELEMENTS = new Set([
  "area",
  "base",
  "basefont",
  "bgsound",
  "br",
  "col",
  "embed",
  "frame",
  "hr",
  "img",
  "input",
  "keygen",
  "link",
  "meta",
  "param",
  "source",
  "track",
  "wbr",
])
const HTML_OPTIONAL_END_TAGS = new Set([
  "html",
  "head",
  "body",
  "li",
  "dt",
  "dd",
  "p",
  "rb",
  "rt",
  "rtc",
  "rp",
  "optgroup",
  "option",
  "colgroup",
  "thead",
  "tbody",
  "tfoot",
  "tr",
  "td",
  "th",
])

// Transfer budgets are baseline ratchets, not substitutes for route-level LHCI.
// Password dictionaries are isolated, user-intent-loaded chunks and therefore
// have their own bounded ceiling instead of weakening the general lazy limit.
export const BUNDLE_BUDGETS = Object.freeze({
  mainJsRawKb: 500,
  initialJsGzipKb: 420,
  // Route-scoped token layers must not be folded back into the application
  // shell. Keep the CSS that blocks first paint below the measured core-shell
  // ceiling; route CSS is delivered with its lazy page chunk instead.
  initialCssGzipKb: 40,
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

const invalidHtml = () => new Error("Unsupported or malformed bundle HTML")
const trimHtmlSpace = (value) => value.replace(/^[\t\n\f\r ]+|[\t\n\f\r ]+$/gu, "")

function htmlAttribute(node, name) {
  return node.attrs?.find((attribute) => attribute.name === name && !attribute.namespace)?.value
}

function normalizeHtmlAssetReference(reference, htmlRelativeDirectory, extension) {
  const segments = reference.split("/")
  const hasExtension =
    extension === ".js"
      ? reference.endsWith(".js") || reference.endsWith(".mjs")
      : reference.endsWith(extension)
  if (
    !/^\/[A-Za-z0-9_@.-]+(?:\/[A-Za-z0-9_@.-]+)*$/u.test(reference) ||
    segments.some((segment) => segment === "." || segment === "..") ||
    !hasExtension
  ) {
    throw invalidHtml()
  }
  return path.posix.join(htmlRelativeDirectory, reference.slice(1))
}

// These are unique direct HTML asset bytes, not a browser network total.
// Inline script behavior and transitive imports are outside this report.
function extractInitialAssetPaths(html, htmlRelativeDirectory) {
  let parseError = false
  const document = parse(html, {
    scriptingEnabled: true,
    sourceCodeLocationInfo: true,
    onParseError(error) {
      if (error.code !== "missing-doctype") parseError = true
    },
  })
  if (parseError) throw invalidHtml()

  const initialPaths = new Set()
  const moduleRoots = new Map()
  const addInitial = (node, reference, extension, isModule) => {
    const assetPath = normalizeHtmlAssetReference(reference, htmlRelativeDirectory, extension)
    const unqualifiedModule =
      isModule &&
      ["crossorigin", "integrity", "referrerpolicy", "fetchpriority"].every(
        (attribute) => htmlAttribute(node, attribute) === undefined
      )
    const plainModuleScript = unqualifiedModule && node.tagName === "script"
    const lowPriorityPreload =
      isModule &&
      node.tagName === "link" &&
      htmlAttribute(node, "rel") === "modulepreload" &&
      htmlAttribute(node, "fetchpriority") === "low" &&
      ["crossorigin", "integrity", "referrerpolicy"].every(
        (attribute) => htmlAttribute(node, attribute) === undefined
      )
    const previous = moduleRoots.get(assetPath)
    const ordinaryDuplicate = previous?.unqualifiedModule && unqualifiedModule
    // The pinned producer pairs one low-priority preload with one plain module.
    // Keep other qualified duplicates closed; this is unique-asset accounting.
    const producerDuplicate =
      (previous?.plainModuleScript && lowPriorityPreload) ||
      (previous?.lowPriorityPreload && plainModuleScript)
    if (previous && !ordinaryDuplicate && !producerDuplicate) throw invalidHtml()
    moduleRoots.set(
      assetPath,
      previous
        ? { unqualifiedModule: ordinaryDuplicate }
        : { unqualifiedModule, plainModuleScript, lowPriorityPreload }
    )
    initialPaths.add(assetPath)
  }
  const pending = [{ node: document, foreign: false }]
  while (pending.length > 0) {
    const { node, foreign } = pending.pop()
    const inForeign = foreign || (node.namespaceURI && node.namespaceURI !== HTML_NAMESPACE)
    const name = node.tagName?.toLowerCase()
    if (inForeign && (name === "script" || name === "link")) throw invalidHtml()

    if (node.namespaceURI === HTML_NAMESPACE) {
      const location = node.sourceCodeLocation
      if (
        location &&
        !location.endTag &&
        !HTML_VOID_ELEMENTS.has(name) &&
        !HTML_OPTIONAL_END_TAGS.has(name)
      ) {
        throw invalidHtml()
      }
      if (name === "template") continue
      if (name === "base" && htmlAttribute(node, "href") !== undefined) throw invalidHtml()

      if (name === "script") {
        const src = htmlAttribute(node, "src")
        if (src !== undefined) {
          const type = trimHtmlSpace(htmlAttribute(node, "type") ?? "").toLowerCase()
          if (!["application/json", "application/ld+json"].includes(type)) {
            if (
              !["", "module", "text/javascript", "application/javascript"].includes(type) ||
              htmlAttribute(node, "nomodule") !== undefined ||
              htmlAttribute(node, "language") !== undefined
            ) {
              throw invalidHtml()
            }
            addInitial(node, src, ".js", type === "module")
          }
        }
      }

      if (name === "link") {
        const rel = (htmlAttribute(node, "rel") ?? "").toLowerCase().split(/[\t\n\f\r ]+/u)
        const asAttribute = htmlAttribute(node, "as")
        const as = (asAttribute ?? "").toLowerCase()
        const href = htmlAttribute(node, "href")
        const modulePreload = rel.includes("modulepreload")
        const stylesheet = rel.includes("stylesheet")
        const scriptPreload = rel.includes("preload") && as === "script"
        const stylePreload = rel.includes("preload") && as === "style"
        if (
          rel.includes("preload") &&
          !modulePreload &&
          !stylesheet &&
          !scriptPreload &&
          !stylePreload &&
          href !== undefined &&
          (/\.(?:m?js|css)(?:[?#]|$)/iu.test(href) || /[%\\]/u.test(href.split(/[?#]/u, 1)[0]))
        ) {
          throw invalidHtml()
        }
        if (modulePreload || stylesheet || scriptPreload || stylePreload) {
          if (
            rel.some(
              (token) => token && !["modulepreload", "stylesheet", "preload"].includes(token)
            ) ||
            htmlAttribute(node, "media") !== undefined ||
            htmlAttribute(node, "disabled") !== undefined ||
            htmlAttribute(node, "type") !== undefined ||
            (modulePreload && asAttribute !== undefined && as !== "script") ||
            ((modulePreload || scriptPreload) && (stylesheet || stylePreload))
          ) {
            throw invalidHtml()
          }
          if (href === undefined) throw invalidHtml()
          const extension = stylesheet || stylePreload ? ".css" : ".js"
          addInitial(node, href, extension, modulePreload)
        }
      }
    }

    for (let index = (node.childNodes?.length ?? 0) - 1; index >= 0; index -= 1) {
      pending.push({ node: node.childNodes[index], foreign: inForeign })
    }
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
  const htmlBytes = await fs.readFile(entryHtmlPath)
  if (htmlBytes.byteLength > HTML_LIMIT) throw invalidHtml()
  let html
  try {
    html = new TextDecoder("utf-8", { fatal: true }).decode(htmlBytes)
  } catch {
    throw invalidHtml()
  }
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
  const availablePaths = new Set(
    assetFiles.map((filePath) => normalizeAssetPath(path.relative(distDir, filePath)))
  )
  for (const assetPath of initialPaths) {
    if (!availablePaths.has(assetPath)) {
      throw new Error(`HTML asset reference not found: ${assetPath}`)
    }
    if (/(?:^|\/)vendor-password-strength-(?:en|ru)-[^/]+\.m?js$/u.test(assetPath)) {
      throw new Error(`Password dictionary cannot be an initial HTML asset: ${assetPath}`)
    }
  }

  const assets = await Promise.all(
    assetFiles.map(async (filePath) => {
      const content = await fs.readFile(filePath)
      const assetPath = normalizeAssetPath(path.relative(distDir, filePath))
      const isJavaScript = assetPath.endsWith(".js") || assetPath.endsWith(".mjs")
      return {
        path: assetPath,
        type: isJavaScript ? "javascript" : "stylesheet",
        rawBytes: content.byteLength,
        gzipBytes: gzipSync(content, { level: 9 }).byteLength,
        brotliBytes: brotliCompressSync(content).byteLength,
        isMain: isJavaScript && /(?:^|\/)(?:index|main)-[^/]+\.m?js$/.test(assetPath),
        isInitial: initialPaths.has(assetPath),
        isPasswordDictionary:
          isJavaScript && /(?:^|\/)vendor-password-strength-(?:en|ru)-[^/]+\.js$/.test(assetPath),
      }
    })
  )
  assets.sort((left, right) => left.path.localeCompare(right.path))

  const javascriptAssets = assets.filter((asset) => asset.type === "javascript")
  const stylesheetAssets = assets.filter((asset) => asset.type === "stylesheet")
  const mainAssets = javascriptAssets.filter((asset) => asset.isMain)
  if (mainAssets.length === 0) {
    throw new Error(`No main/index JavaScript chunk found in ${distDir}`)
  }
  const initialJavaScriptAssets = javascriptAssets.filter((asset) => asset.isInitial)
  if (initialJavaScriptAssets.length === 0) {
    throw new Error(`No initial JavaScript assets referenced by ${entryHtmlPath}`)
  }
  const initialStylesheetAssets = stylesheetAssets.filter((asset) => asset.isInitial)
  const generalLazyAssets = javascriptAssets.filter(
    (asset) => !asset.isInitial && !asset.isPasswordDictionary
  )
  const passwordDictionaryAssets = javascriptAssets.filter(
    (asset) => !asset.isInitial && asset.isPasswordDictionary
  )
  const passwordDictionaryRawAssets = javascriptAssets.filter(
    (asset) =>
      !asset.isInitial &&
      /(?:^|\/)vendor-password-strength-(?:en|ru)-[^/]+\.m?js$/u.test(asset.path)
  )
  const main = largestBy(mainAssets, "rawBytes")
  const largestGeneralLazy = largestBy(generalLazyAssets, "gzipBytes")
  const largestPasswordDictionary = largestBy(passwordDictionaryAssets, "gzipBytes")
  const largestPasswordDictionaryRaw = largestBy(passwordDictionaryRawAssets, "rawBytes")
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
      stylesheetAssetCount: stylesheetAssets.length,
      initialJsAssetCount: initialJavaScriptAssets.length,
      lazyJsAssetCount: javascriptAssets.length - initialJavaScriptAssets.length,
      initialCssAssetCount: initialStylesheetAssets.length,
      lazyCssAssetCount: stylesheetAssets.length - initialStylesheetAssets.length,
      totalRawBytes: sum(assets, "rawBytes"),
      totalGzipBytes: sum(assets, "gzipBytes"),
      totalBrotliBytes: sum(assets, "brotliBytes"),
      mainJsPath: main?.path ?? null,
      mainJsRawBytes: main?.rawBytes ?? 0,
      initialJsGzipBytes: sum(initialJavaScriptAssets, "gzipBytes"),
      initialJsBrotliBytes: sum(initialJavaScriptAssets, "brotliBytes"),
      initialCssGzipBytes: sum(initialStylesheetAssets, "gzipBytes"),
      initialCssBrotliBytes: sum(initialStylesheetAssets, "brotliBytes"),
      largestGeneralLazyJsPath: largestGeneralLazy?.path ?? null,
      largestGeneralLazyJsGzipBytes: largestGeneralLazy?.gzipBytes ?? 0,
      largestPasswordDictionaryPath: largestPasswordDictionary?.path ?? null,
      largestPasswordDictionaryRawPath: largestPasswordDictionaryRaw?.path ?? null,
      largestPasswordDictionaryRawBytes: largestPasswordDictionaryRaw?.rawBytes ?? 0,
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
      actualBytes: summary.initialCssGzipBytes,
      limitKb: BUNDLE_BUDGETS.initialCssGzipKb,
      message: "Initial CSS delivery graph exceeds gzip budget",
    },
    {
      actualBytes: summary.largestGeneralLazyJsGzipBytes,
      limitKb: BUNDLE_BUDGETS.generalLazyJsGzipKb,
      message: `Lazy JS chunk '${summary.largestGeneralLazyJsPath}' exceeds gzip budget`,
    },
    {
      actualBytes: summary.largestPasswordDictionaryRawBytes ?? 0,
      limitKb: BUNDLE_BUDGETS.passwordDictionaryRawKb,
      message: `Password dictionary '${summary.largestPasswordDictionaryRawPath ?? summary.largestPasswordDictionaryPath}' exceeds raw budget`,
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
    initialCssGzipKiB: formatKiB(report.summary.initialCssGzipBytes),
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
