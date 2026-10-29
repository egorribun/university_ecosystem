/**
 * Inactive consistency diagnostic for final HTML roots and schema-3 Vite metadata.
 *
 * This does not authenticate the supplied metadata, its source or its build run.
 * Computed imports remain unresolved, and scripts outside the direct HTML-root
 * inventory are not analyzed. There is no reachability or budget verdict here.
 * The caller must provide a quiescent output directory and its own resource limits.
 * As with the underlying inventory, parent-directory rename races are not excluded.
 */
import { createHash } from "node:crypto"
import { constants } from "node:fs"
import { lstat, open, realpath } from "node:fs/promises"
import path from "node:path"

import { inspectFinalHtml } from "./final-html-root-inventory.mjs"

const FILE_LIMIT = 4 * 1024 * 1024
const TOTAL_GRAPH_LIMIT = 256 * 1024 * 1024
const GRAPH_CHUNK_LIMIT = 5000
const GRAPH_EDGE_LIMIT = 50_000
const OUTPUT_LIMIT = 128 * 1024
const HASH = /^[0-9a-f]{64}$/u
const GRAPH_KEYS = [
  "chunks",
  "complete",
  "entryFiles",
  "unresolvedDynamicImportCount",
  "unresolvedStaticImportCount",
]
const CHUNK_KEYS = [
  "dynamicImports",
  "fileName",
  "imports",
  "isDynamicEntry",
  "isEntry",
  "rawBytes",
  "sha256",
]
const ISSUE_KEYS = [
  "baseElements",
  "computedImports",
  "foreignReferences",
  "importMaps",
  "parseErrors",
  "unknownScriptTypes",
  "unsafeReferences",
]

function requireInput(condition) {
  if (!condition) throw new Error("GRAPH_BINDING_REJECTED")
}

function exactKeys(value, expected) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).sort().join("\0") === expected.join("\0")
  )
}

function safeFileName(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 1024 &&
    /^[A-Za-z0-9_@./-]+$/u.test(value) &&
    !value.startsWith("/") &&
    value.split("/").every((part) => part !== "" && part !== "." && part !== "..")
  )
}

function count(value, maximum) {
  return Number.isSafeInteger(value) && value >= 0 && value <= maximum
}

function validateGraph(metadata) {
  requireInput(metadata !== null && typeof metadata === "object" && metadata.schemaVersion === 3)
  const graph = metadata.graph
  requireInput(exactKeys(graph, GRAPH_KEYS))
  const unresolvedStaticImportCount = graph.unresolvedStaticImportCount
  const unresolvedDynamicImportCount = graph.unresolvedDynamicImportCount
  const complete = graph.complete
  const chunks = graph.chunks
  const entryFileNames = graph.entryFiles
  const mapLibreChunks = metadata.mapLibreChunks
  requireInput(
    Array.isArray(chunks) &&
      chunks.length <= GRAPH_CHUNK_LIMIT &&
      Array.isArray(entryFileNames) &&
      entryFileNames.length <= GRAPH_CHUNK_LIMIT &&
      Array.isArray(mapLibreChunks) &&
      mapLibreChunks.length <= GRAPH_CHUNK_LIMIT &&
      typeof complete === "boolean" &&
      count(unresolvedStaticImportCount, GRAPH_EDGE_LIMIT) &&
      count(unresolvedDynamicImportCount, GRAPH_EDGE_LIMIT)
  )
  const byName = new Map()
  let graphBytes = 0
  let graphEdges = 0
  for (const chunk of chunks) {
    requireInput(exactKeys(chunk, CHUNK_KEYS))
    const imports = chunk.imports
    const dynamicImports = chunk.dynamicImports
    requireInput(
      Array.isArray(imports) &&
        Array.isArray(dynamicImports) &&
        imports.length <= GRAPH_EDGE_LIMIT &&
        dynamicImports.length <= GRAPH_EDGE_LIMIT
    )
    const snapshot = {
      fileName: chunk.fileName,
      rawBytes: chunk.rawBytes,
      sha256: chunk.sha256,
      isEntry: chunk.isEntry,
      isDynamicEntry: chunk.isDynamicEntry,
      imports: [...imports],
      dynamicImports: [...dynamicImports],
    }
    requireInput(
      safeFileName(snapshot.fileName) &&
        !byName.has(snapshot.fileName) &&
        count(snapshot.rawBytes, FILE_LIMIT) &&
        typeof snapshot.sha256 === "string" &&
        HASH.test(snapshot.sha256) &&
        typeof snapshot.isEntry === "boolean" &&
        typeof snapshot.isDynamicEntry === "boolean"
    )
    graphBytes += snapshot.rawBytes
    graphEdges += snapshot.imports.length + snapshot.dynamicImports.length
    requireInput(graphBytes <= TOTAL_GRAPH_LIMIT && graphEdges <= GRAPH_EDGE_LIMIT)
    for (const edges of [snapshot.imports, snapshot.dynamicImports]) {
      requireInput(edges.every(safeFileName) && new Set(edges).size === edges.length)
    }
    byName.set(snapshot.fileName, snapshot)
  }
  for (const chunk of byName.values()) {
    requireInput([...chunk.imports, ...chunk.dynamicImports].every((name) => byName.has(name)))
  }
  const entries = [...byName.values()]
    .filter((chunk) => chunk.isEntry)
    .map((chunk) => chunk.fileName)
  const entryFiles = new Set(entryFileNames)
  requireInput(
    entryFileNames.every(safeFileName) &&
      entryFiles.size === entryFileNames.length &&
      entries.length === entryFileNames.length &&
      entries.every((name) => entryFiles.has(name)) &&
      complete === (entries.length > 0 && unresolvedStaticImportCount === 0)
  )
  const candidates = new Set()
  for (const candidate of mapLibreChunks) {
    requireInput(candidate !== null && typeof candidate === "object" && !Array.isArray(candidate))
    const fileName = candidate.fileName
    const rawBytes = candidate.rawBytes
    const sha256 = candidate.sha256
    const chunk = byName.get(fileName)
    requireInput(
      chunk !== undefined &&
        !candidates.has(fileName) &&
        rawBytes === chunk.rawBytes &&
        sha256 === chunk.sha256
    )
    candidates.add(fileName)
  }
  return {
    graph: { unresolvedStaticImportCount, unresolvedDynamicImportCount },
    byName,
    candidates,
  }
}

function sameFile(left, right) {
  return ["dev", "ino", "size", "mtimeNs", "ctimeNs"].every((key) => left[key] === right[key])
}

async function readFingerprint(root, name) {
  requireInput(safeFileName(name))
  const parts = name.split("/")
  let parent = root
  for (const part of parts.slice(0, -1)) {
    parent = path.join(parent, part)
    const directory = await lstat(parent)
    requireInput(directory.isDirectory() && !directory.isSymbolicLink())
  }
  requireInput((await realpath(parent)) === parent)
  const file = path.join(root, ...parts)
  const before = await lstat(file, { bigint: true })
  requireInput(before.isFile() && !before.isSymbolicLink() && before.size <= BigInt(FILE_LIMIT))
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK)
  try {
    const opened = await handle.stat({ bigint: true })
    requireInput(opened.isFile() && sameFile(before, opened))
    const digest = createHash("sha256")
    let size = 0
    while (true) {
      const buffer = Buffer.alloc(Math.min(65_536, FILE_LIMIT - size + 1))
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, null)
      if (bytesRead === 0) break
      size += bytesRead
      requireInput(size <= FILE_LIMIT)
      digest.update(buffer.subarray(0, bytesRead))
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
        (await realpath(parent)) === parent
    )
    return { rawBytes: size, sha256: digest.digest("hex") }
  } finally {
    await handle.close()
  }
}

function matchesFingerprint(actual, expected) {
  return actual.rawBytes === expected.rawBytes && actual.sha256 === expected.sha256
}

async function verifyGraphFiles(root, byName) {
  for (const chunk of byName.values()) {
    requireInput(matchesFingerprint(await readFingerprint(root, chunk.fileName), chunk))
  }
}

async function bindDocuments(root, inventory, byName) {
  requireInput(
    inventory?.schemaVersion === 2 &&
      inventory.kind === "final-html-root-inventory-not-budget-proof" &&
      Array.isArray(inventory.documents) &&
      inventory.documents.length === 2 &&
      Array.isArray(inventory.scripts)
  )
  const assetFingerprints = new Map()
  const documents = []
  for (const document of inventory.documents) {
    requireInput(exactKeys(document.issues, ISSUE_KEYS))
    for (const [name, value] of Object.entries(document.issues)) {
      requireInput(count(value, GRAPH_EDGE_LIMIT) && (name === "computedImports" || value === 0))
    }
    const roots = []
    for (const rootRecord of document.roots) {
      requireInput(
        count(rootRecord.scriptIndex, inventory.scripts.length - 1) &&
          typeof rootRecord.kind === "string"
      )
      const script = inventory.scripts[rootRecord.scriptIndex]
      const chunk = script.assetPath === null ? undefined : byName.get(script.assetPath)
      if (script.assetPath !== null) {
        if (!assetFingerprints.has(script.assetPath)) {
          assetFingerprints.set(script.assetPath, await readFingerprint(root, script.assetPath))
        }
        requireInput(matchesFingerprint(assetFingerprints.get(script.assetPath), script))
        if (chunk !== undefined) requireInput(matchesFingerprint(chunk, script))
      }
      const literalImports = script.imports.map((edge) => {
        const target = byName.get(edge.assetPath)
        if (chunk !== undefined && target !== undefined) {
          const reported = edge.kind === "static" ? chunk.imports : chunk.dynamicImports
          requireInput(reported.includes(edge.assetPath))
          return { kind: edge.kind, assetPath: edge.assetPath, graphRelation: "reported-edge" }
        }
        return {
          kind: edge.kind,
          assetPath: edge.assetPath,
          graphRelation: target === undefined ? "not-in-graph" : "target-in-graph",
        }
      })
      roots.push({
        kind: rootRecord.kind,
        assetPath: script.assetPath,
        rawBytes: script.rawBytes,
        sha256: script.sha256,
        graphRelation:
          script.assetPath === null ? "inline" : chunk ? "byte-matched" : "not-in-graph",
        literalImports,
      })
    }
    documents.push({
      fileName: document.fileName,
      rawBytes: document.rawBytes,
      sha256: document.sha256,
      unresolvedComputedImports: document.issues.computedImports,
      roots,
    })
  }
  return documents
}

/** Returns a bounded diagnostic or null; it never authorizes a bundle exception. */
export async function inspectMapLibreGraphBinding(clientDir, metadata) {
  try {
    requireInput(typeof clientDir === "string" && clientDir.length > 0)
    requireInput(
      [constants.O_NOFOLLOW, constants.O_NONBLOCK].every(
        (flag) => Number.isSafeInteger(flag) && flag > 0
      )
    )
    const root = path.resolve(clientDir)
    const before = await lstat(root, { bigint: true })
    requireInput(
      before.isDirectory() && !before.isSymbolicLink() && (await realpath(root)) === root
    )
    const { graph, byName, candidates } = validateGraph(metadata)
    const firstInventory = await inspectFinalHtml(root)
    requireInput(firstInventory !== null)
    await verifyGraphFiles(root, byName)
    const documents = await bindDocuments(root, firstInventory, byName)
    const lastInventory = await inspectFinalHtml(root)
    requireInput(
      lastInventory !== null && JSON.stringify(lastInventory) === JSON.stringify(firstInventory)
    )
    await verifyGraphFiles(root, byName)
    const after = await lstat(root, { bigint: true })
    requireInput(after.isDirectory() && !after.isSymbolicLink() && sameFile(before, after))
    requireInput((await realpath(root)) === root)
    const result = {
      schemaVersion: 1,
      kind: "maplibre-graph-binding-diagnostic-not-budget-proof",
      provenance: "unverified",
      transitiveRuntimeImports: "uninspected",
      otherExecutionSurfaces: "uninspected",
      graph: {
        chunkCount: byName.size,
        candidateCount: candidates.size,
        candidates: [...candidates].map((name) => {
          const chunk = byName.get(name)
          return { fileName: name, rawBytes: chunk.rawBytes, sha256: chunk.sha256 }
        }),
        unresolvedStaticImportCount: graph.unresolvedStaticImportCount,
        unresolvedDynamicImportCount: graph.unresolvedDynamicImportCount,
      },
      documents,
    }
    requireInput(Buffer.byteLength(JSON.stringify(result)) <= OUTPUT_LIMIT)
    return result
  } catch {
    return null
  }
}
