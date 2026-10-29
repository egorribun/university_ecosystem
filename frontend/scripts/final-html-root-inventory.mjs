/**
 * Diagnostic final-HTML root inventory, not budget or artifact admission.
 *
 * This reads two owned build documents and their direct script roots. It never
 * executes scripts or recursively follows imports. "complete" covers only this
 * root grammar, not handlers, service workers or arbitrary JavaScript execution.
 * The caller owns checkout/run provenance and a quiescent output directory.
 * Optional trusted synchronous onRejected gets one closed reason on failure,
 * never on success. Its return value is not awaited; rejected promises are handled.
 *
 * Static path checks and O_NOFOLLOW do not eliminate intermediate-directory
 * rename races. AST limits apply after parsing, not before parser allocation;
 * the caller still needs an external time/memory bound. This is not a sandbox.
 */
import { createHash } from "node:crypto"
import { constants } from "node:fs"
import { lstat, open, realpath } from "node:fs/promises"
import path from "node:path"
import { parse } from "@babel/parser"
import { JSDOM, VirtualConsole } from "jsdom"

const MIB = 1024 * 1024
const HTML_LIMIT = MIB
const ASSET_LIMIT = 4 * MIB
const TOTAL_ASSET_LIMIT = 16 * MIB
const ROOT_LIMIT = 128
const NODE_LIMIT = 100_000
const IMPORT_LIMIT = 256
const OUTPUT_LIMIT = 32_767
const ASSET_PATH =
  /^(?:assets\/[A-Za-z0-9_-][A-Za-z0-9._-]*\.(?:js|mjs)|(?:theme-init|static-shell-i18n|not-found-i18n|sw)\.js)$/u
const CLASSIC_TYPES = new Set(["", "text/javascript", "application/javascript"])
const IGNORED_AST_KEYS = new Set([
  "loc",
  "comments",
  "leadingComments",
  "innerComments",
  "trailingComments",
  "tokens",
  "extra",
])

const REJECTION_REASONS = new Set([
  "input-read",
  "input-path",
  "platform",
  "path",
  "file-kind",
  "file-change",
  "file-bytes",
  "utf8",
  "empty-html",
  "namespace",
  "inline-location",
  "root-count",
  "ast-nodes",
  "import-edges",
  "total-asset-bytes",
  "output-bytes",
])

class InventoryRejection extends Error {
  constructor(reason) {
    super("FINAL_HTML_INPUT_REJECTED")
    this.reason = reason
  }
}

function requireInput(condition, reason) {
  if (!condition) throw new InventoryRejection(reason)
}

function digest(bytes) {
  return createHash("sha256").update(bytes).digest("hex")
}

function decode(bytes) {
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes)
  } catch {
    throw new InventoryRejection("utf8")
  }
}

function sameFile(left, right) {
  return ["dev", "ino", "size", "mtimeNs", "ctimeNs"].every((key) => left[key] === right[key])
}

async function readOwnedFile(root, name, limit) {
  const parts = name.split("/")
  let parent = root
  for (const part of parts.slice(0, -1)) {
    parent = path.join(parent, part)
    const directory = await lstat(parent)
    requireInput(directory.isDirectory() && !directory.isSymbolicLink(), "path")
  }
  const file = path.join(root, ...parts)
  requireInput((await realpath(parent)) === parent, "path")
  const before = await lstat(file, { bigint: true })
  requireInput(before.isFile() && !before.isSymbolicLink(), "file-kind")
  requireInput(before.size <= BigInt(limit), "file-bytes")
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK)
  try {
    const opened = await handle.stat({ bigint: true })
    requireInput(opened.isFile() && sameFile(before, opened), "file-change")
    const chunks = []
    let size = 0
    while (true) {
      const chunk = Buffer.alloc(Math.min(65_536, limit - size + 1))
      const { bytesRead } = await handle.read(chunk, 0, chunk.length, null)
      if (bytesRead === 0) break
      size += bytesRead
      requireInput(size <= limit, "file-bytes")
      chunks.push(chunk.subarray(0, bytesRead))
    }
    const after = await handle.stat({ bigint: true })
    const linked = await lstat(file, { bigint: true })
    requireInput(
      after.isFile() &&
        linked.isFile() &&
        !linked.isSymbolicLink() &&
        sameFile(opened, after) &&
        sameFile(after, linked) &&
        BigInt(size) === after.size &&
        (await realpath(parent)) === parent,
      "file-change"
    )
    return Buffer.concat(chunks, size)
  } finally {
    await handle.close()
  }
}

function emptyIssues() {
  return {
    baseElements: 0,
    computedImports: 0,
    foreignReferences: 0,
    importMaps: 0,
    parseErrors: 0,
    unknownScriptTypes: 0,
    unsafeReferences: 0,
  }
}

function reference(value, importer, isImport, issues) {
  if (typeof value !== "string") {
    issues.unsafeReferences += 1
    return null
  }
  if (/^(?:https?:)?\/\//iu.test(value)) {
    issues.foreignReferences += 1
    return null
  }
  if (
    !value ||
    /[\s\\%?#:]/u.test(value) ||
    Array.from(value).some((character) => {
      const code = character.charCodeAt(0)
      return code < 32 || code === 127
    }) ||
    value.includes("..") ||
    (isImport && !value.startsWith("/") && !value.startsWith("./"))
  ) {
    issues.unsafeReferences += 1
    return null
  }
  const absolute = value.startsWith("/")
  const relative = value.startsWith("./") ? value.slice(2) : value
  const local = absolute ? value.slice(1) : relative
  if (local.split("/").some((part) => part === "" || part === "." || part === "..")) {
    issues.unsafeReferences += 1
    return null
  }
  const resolved = absolute
    ? local
    : path.posix.join(isImport ? path.posix.dirname(importer) : ".", local)
  if (!ASSET_PATH.test(resolved) || resolved.includes("..")) {
    issues.unsafeReferences += 1
    return null
  }
  return resolved
}

function analyzeScript(source, mode, importer) {
  const issues = emptyIssues()
  const result = { imports: [], computedImports: 0, parseErrors: 0, issues }
  let tree
  try {
    tree = parse(source, {
      sourceType: mode,
      createImportExpressions: true,
      errorRecovery: false,
      attachComment: false,
      locations: false,
      tokens: false,
      plugins: [],
    })
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error
    result.parseErrors = 1
    issues.parseErrors = 1
    return result
  }
  const pending = [tree]
  const occurrences = []
  let nodes = 0
  while (pending.length) {
    const node = pending.pop()
    if (!node || typeof node !== "object") continue
    if (Array.isArray(node)) {
      for (let index = node.length - 1; index >= 0; index -= 1) pending.push(node[index])
      continue
    }
    if (typeof node.type !== "string") continue
    nodes += 1
    requireInput(nodes <= NODE_LIMIT, "ast-nodes")
    if (
      node.type === "ImportExpression" ||
      node.type === "ImportDeclaration" ||
      ((node.type === "ExportNamedDeclaration" || node.type === "ExportAllDeclaration") &&
        node.source !== null)
    ) {
      const sourceNode = node.source
      if (sourceNode !== undefined && sourceNode !== null) {
        occurrences.push({
          start: node.start,
          kind: node.type === "ImportExpression" ? "dynamic" : "static",
          literal: sourceNode.type === "StringLiteral",
          value: sourceNode.value,
        })
        requireInput(occurrences.length <= IMPORT_LIMIT, "import-edges")
      }
    }
    for (const key of Object.keys(node)) {
      if (!IGNORED_AST_KEYS.has(key) && node[key] && typeof node[key] === "object") {
        pending.push(node[key])
      }
    }
  }
  occurrences.sort((left, right) => left.start - right.start)
  for (const occurrence of occurrences) {
    if (!occurrence.literal) {
      result.computedImports += 1
      issues.computedImports += 1
      continue
    }
    const assetPath = reference(occurrence.value, importer, true, issues)
    if (assetPath !== null) result.imports.push({ kind: occurrence.kind, assetPath })
  }
  return result
}

function scriptKind(element, issues) {
  const type = (element.getAttribute("type") ?? "").trim().toLowerCase()
  const external = element.hasAttribute("src")
  if (CLASSIC_TYPES.has(type)) return external ? "external-classic" : "inline-classic"
  if (type === "module") return external ? "external-module" : "inline-module"
  if (type === "application/json" && !external) return "inline-data"
  if (type === "importmap" && !external) {
    issues.importMaps += 1
    return "inline-importmap"
  }
  issues.unknownScriptTypes += 1
  return null
}

async function inspectDocument(fileName, bytes, assets) {
  requireInput(bytes.length > 0, "empty-html")
  const source = decode(bytes)
  // Omit both resources and runScripts. Even resources: {} enables subresource
  // loading in jsdom 30. A fresh unforwarded console cannot print input details.
  const dom = new JSDOM(source, {
    virtualConsole: new VirtualConsole(),
    includeNodeLocations: true,
  })
  try {
    const issues = emptyIssues()
    const roots = []
    let rootCount = 0
    for (const element of dom.window.document.querySelectorAll("base, script, link")) {
      requireInput(element.namespaceURI === "http://www.w3.org/1999/xhtml", "namespace")
      if (element.localName === "base") {
        issues.baseElements += 1
        continue
      }
      let kind
      let attribute
      if (element.localName === "script") {
        rootCount += 1
        kind = scriptKind(element, issues)
        attribute = element.hasAttribute("src") ? "src" : null
      } else {
        const relations = (element.getAttribute("rel") ?? "").toLowerCase().split(/\s+/u)
        if (relations.includes("modulepreload")) {
          kind = "modulepreload"
        } else if (
          relations.includes("preload") &&
          (element.getAttribute("as") ?? "").toLowerCase() === "script"
        ) {
          kind = "script-preload"
        } else {
          continue
        }
        rootCount += 1
        attribute = "href"
      }
      requireInput(rootCount <= ROOT_LIMIT, "root-count")
      if (kind === null) continue
      let assetPath = null
      let content
      let text
      let asset
      if (attribute !== null) {
        assetPath = reference(element.getAttribute(attribute), fileName, false, issues)
        if (assetPath === null) continue
        asset = await assets(assetPath)
        content = asset.bytes
        text = asset.text
      } else {
        const location = dom.nodeLocation(element)
        requireInput(
          location?.startTag &&
            location.endTag &&
            Number.isSafeInteger(location.startTag.endOffset) &&
            Number.isSafeInteger(location.endTag.startOffset) &&
            location.startTag.endOffset <= location.endTag.startOffset,
          "inline-location"
        )
        text = source.slice(location.startTag.endOffset, location.endTag.startOffset)
        content = Buffer.from(text, "utf8")
      }
      let analysis = { imports: [], computedImports: 0, parseErrors: 0, issues: emptyIssues() }
      if (kind !== "inline-data" && kind !== "inline-importmap") {
        const mode = kind.endsWith("module") || kind === "modulepreload" ? "module" : "script"
        analysis = asset?.analysis.get(mode)
        if (!analysis) {
          analysis = analyzeScript(text, mode, assetPath ?? fileName)
          asset?.analysis.set(mode, analysis)
        }
      }
      for (const key of Object.keys(issues)) issues[key] += analysis.issues[key]
      roots.push({
        kind,
        assetPath,
        rawBytes: content.length,
        sha256: digest(content),
        imports: analysis.imports,
        computedImports: analysis.computedImports,
        parseErrors: analysis.parseErrors,
      })
    }
    return {
      fileName,
      rawBytes: bytes.length,
      sha256: digest(bytes),
      complete: Object.values(issues).every((count) => count === 0),
      roots,
      issues,
    }
  } finally {
    dom.window.close()
  }
}

export async function inspectFinalHtml(clientDir, onRejected) {
  try {
    requireInput(typeof clientDir === "string" && clientDir.length > 0, "input-path")
    requireInput(
      [constants.O_NOFOLLOW, constants.O_NONBLOCK].every(
        (flag) => Number.isSafeInteger(flag) && flag > 0
      ),
      "platform"
    )
    const root = path.resolve(clientDir)
    const directory = await lstat(root)
    requireInput(directory.isDirectory() && !directory.isSymbolicLink(), "path")
    requireInput((await realpath(root)) === root, "path")
    const cache = new Map()
    let assetBytes = 0
    async function assets(name) {
      if (!cache.has(name)) {
        const bytes = await readOwnedFile(root, name, ASSET_LIMIT)
        assetBytes += bytes.length
        requireInput(assetBytes <= TOTAL_ASSET_LIMIT, "total-asset-bytes")
        cache.set(name, { bytes, text: decode(bytes), analysis: new Map() })
      }
      return cache.get(name)
    }
    const shell = await readOwnedFile(root, "_shell.html", HTML_LIMIT)
    const index = await readOwnedFile(root, "index.html", HTML_LIMIT)
    const documents = [
      await inspectDocument("_shell.html", shell, assets),
      await inspectDocument("index.html", index, assets),
    ]
    const result = {
      schemaVersion: 1,
      kind: "final-html-root-inventory-not-budget-proof",
      documentsMatch: shell.equals(index),
      documents,
    }
    requireInput(Buffer.byteLength(JSON.stringify(result)) <= OUTPUT_LIMIT, "output-bytes")
    return result
  } catch (error) {
    const reason =
      error instanceof InventoryRejection && REJECTION_REASONS.has(error.reason)
        ? error.reason
        : "input-read"
    if (typeof onRejected === "function") {
      try {
        // Trusted synchronous diagnostics cannot change null or leak rejected promises.
        void Promise.resolve(onRejected(reason)).catch(() => undefined)
      } catch {
        // A throwing diagnostic callback must not replace the closed result.
      }
    }
    return null
  }
}
