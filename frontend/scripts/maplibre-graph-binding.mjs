/**
 * Final HTML/compiler consistency and a separately source-bound MapLibre budget verifier.
 *
 * inspectMapLibreGraphBinding remains an untrusted-input diagnostic, not admission.
 * verifyMapLibreBudgetAllowance binds owned source and artifact bytes for one static
 * noninitial allowance. Neither API proves runtime, handler, service-worker or
 * network closure. The caller owns resource limits and a quiescent directory;
 * parent-directory rename races are not excluded by these bounded no-follow reads.
 */
import { execFileSync } from "node:child_process"
import { createHash } from "node:crypto"
import { constants } from "node:fs"
import { lstat, open, realpath } from "node:fs/promises"
import { createRequire } from "node:module"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { gzipSync } from "node:zlib"

import { parse } from "@babel/parser"

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

async function readFingerprint(root, name, includeBytes = false, maximum = FILE_LIMIT) {
  requireInput(safeFileName(name) && count(maximum, FILE_LIMIT) && maximum > 0)
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
  requireInput(before.isFile() && !before.isSymbolicLink() && before.size <= BigInt(maximum))
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK)
  try {
    const opened = await handle.stat({ bigint: true })
    requireInput(opened.isFile() && sameFile(before, opened))
    const digest = createHash("sha256")
    const parts = []
    let size = 0
    while (true) {
      const buffer = Buffer.alloc(Math.min(65_536, maximum - size + 1))
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, null)
      if (bytesRead === 0) break
      size += bytesRead
      requireInput(size <= maximum)
      digest.update(buffer.subarray(0, bytesRead))
      if (includeBytes) parts.push(buffer.subarray(0, bytesRead))
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
    return {
      rawBytes: size,
      sha256: digest.digest("hex"),
      ...(includeBytes ? { bytes: Buffer.concat(parts, size) } : {}),
    }
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

const CAPTURE_SOURCE_PATHS = [
  ".github/workflows/reusable-frontend-tests.yml",
  "frontend/package.json",
  "frontend/package-lock.json",
  "frontend/vite.config.mts",
  "frontend/scripts/final-html-root-inventory.mjs",
  "frontend/scripts/build-orchestrated.mjs",
  "frontend/scripts/post-build-shell.mjs",
]
const POLICY_SOURCE_PATHS = [
  ...CAPTURE_SOURCE_PATHS,
  "frontend/scripts/maplibre-build-metadata.mjs",
  "frontend/scripts/maplibre-graph-binding.mjs",
  "frontend/scripts/check-bundle-budget.mjs",
  "frontend/public/theme-init.js",
  "frontend/public/static-shell-i18n.js",
]
const AUXILIARY_PATHS = ["theme-init.js", "static-shell-i18n.js"]
const MAP_MODULE_PATHS = [
  "dist/maplibre-gl.css",
  "dist/maplibre-gl.mjs",
  "dist/maplibre-gl-worker.mjs",
]
const BUILD_PROFILE = {
  command: "build",
  mode: "production",
  isProduction: true,
  lhci: false,
  lhciEnv: false,
  reactDevMode: false,
  unminified: false,
  consumer: "client",
  isWorker: false,
  minify: "oxc",
  sourcemap: "hidden",
  target: ["chrome111", "edge111", "firefox114", "safari16.4", "ios16.4"],
  format: "es",
}
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex")
const commitId = (value) => typeof value === "string" && /^[a-f0-9]{40}$/u.test(value)
const hashId = (value) => typeof value === "string" && HASH.test(value)
const equalJson = (left, right) => JSON.stringify(left) === JSON.stringify(right)

function sourceGit(workspace) {
  const env = {
    PATH: process.env.PATH || "",
    HOME: workspace,
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: "/dev/null",
    GIT_TERMINAL_PROMPT: "0",
    GIT_OPTIONAL_LOCKS: "0",
    GIT_NO_LAZY_FETCH: "1",
    GIT_NO_REPLACE_OBJECTS: "1",
    LC_ALL: "C",
  }
  return (args, maxBuffer = 4096) =>
    execFileSync("git", ["--no-pager", "-c", "core.fsmonitor=false", ...args], {
      cwd: workspace,
      env,
      timeout: 5000,
      maxBuffer,
      stdio: ["ignore", "pipe", "pipe"],
    })
}

async function ownedDirectory(value) {
  requireInput(typeof value === "string" && path.isAbsolute(value))
  requireInput(path.resolve(value) === value && (await realpath(value)) === value)
  const info = await lstat(value)
  requireInput(info.isDirectory() && !info.isSymbolicLink())
  return value
}

async function evidenceFile(file, maximum) {
  requireInput(typeof file === "string" && path.isAbsolute(file) && path.resolve(file) === file)
  const directory = await ownedDirectory(path.dirname(file))
  return readFingerprint(directory, path.basename(file), true, maximum)
}

function parseJson(bytes) {
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes))
}

function validateAuxiliary(bytes, name) {
  const source = new TextDecoder("utf-8", { fatal: true }).decode(bytes)
  const tree = parse(source, {
    sourceType: name === "theme-init.js" ? "script" : "module",
    createImportExpressions: true,
    errorRecovery: false,
    attachComment: false,
    tokens: false,
    plugins: [],
  })
  const pending = [tree]
  let nodes = 0
  let dynamicEdges = 0
  while (pending.length > 0) {
    const node = pending.pop()
    if (!node || typeof node !== "object") continue
    if (typeof node.type === "string") {
      nodes += 1
      requireInput(nodes <= 100_000)
      requireInput(
        node.type !== "ImportDeclaration" &&
          !(
            (node.type === "ExportNamedDeclaration" || node.type === "ExportAllDeclaration") &&
            node.source
          )
      )
      if (node.type === "ImportExpression") {
        requireInput(
          name === "theme-init.js" &&
            node.source?.type === "StringLiteral" &&
            node.source.value === "./static-shell-i18n.js" &&
            node.options == null
        )
        dynamicEdges += 1
        requireInput(dynamicEdges <= 1)
      }
    }
    for (const [key, value] of Object.entries(node)) {
      if (["loc", "start", "end", "extra", "comments", "tokens"].includes(key)) continue
      if (Array.isArray(value)) pending.push(...value)
      else if (value && typeof value === "object") pending.push(value)
    }
  }
  requireInput(dynamicEdges === (name === "theme-init.js" ? 1 : 0))
}

function validatePackage(metadata, sources, installedBytes) {
  const manifestBytes = sources.get("frontend/package.json")
  const lockBytes = sources.get("frontend/package-lock.json")
  const manifest = parseJson(manifestBytes)
  const lock = parseJson(lockBytes)
  const installed = parseJson(installedBytes)
  const entry = lock.packages?.["node_modules/maplibre-gl"]
  requireInput(
    installed.name === "maplibre-gl" &&
      installed.version === "6.15.0" &&
      entry?.version === "6.15.0" &&
      typeof entry.integrity === "string" &&
      /^sha512-[A-Za-z0-9+/=]+$/u.test(entry.integrity)
  )
  const expected = {
    declared: manifest.dependencies?.["maplibre-gl"],
    installedName: installed.name,
    installedVersion: installed.version,
    lockVersion: entry.version,
    lockIntegrity: entry.integrity,
    packageJsonSha256: sha256(manifestBytes),
    lockSha256: sha256(lockBytes),
    installedManifestSha256: sha256(installedBytes),
  }
  requireInput(exactKeys(metadata.package, Object.keys(expected).sort()))
  for (const [name, value] of Object.entries(expected)) {
    requireInput(typeof value === "string" && metadata.package[name] === value)
  }
  requireInput(exactKeys(metadata.profile, Object.keys(BUILD_PROFILE).sort()))
  for (const [name, value] of Object.entries(BUILD_PROFILE)) {
    requireInput(equalJson(metadata.profile[name], value))
  }
}

function validateCandidate(metadata, byName) {
  requireInput(metadata.mapLibreChunks.length === 1)
  const candidate = metadata.mapLibreChunks[0]
  requireInput(
    exactKeys(candidate, [
      "fileName",
      "gzipBytes",
      "gzipSha256",
      "modules",
      "rawBytes",
      "sha256",
      "staticEntryReachable",
    ]) &&
      /^assets\/vendor-map-[A-Za-z0-9_-]+\.js$/u.test(candidate.fileName) &&
      candidate.staticEntryReachable === false &&
      count(candidate.gzipBytes, FILE_LIMIT) &&
      hashId(candidate.gzipSha256) &&
      Array.isArray(candidate.modules) &&
      candidate.modules.length === MAP_MODULE_PATHS.length
  )
  const seen = new Set()
  for (const module of candidate.modules) {
    requireInput(
      exactKeys(module, [
        "idSha256",
        "kind",
        "originalCodeUnits",
        "package",
        "packageRoot",
        "path",
        "renderedCodeUnits",
      ])
    )
    requireInput(
      module.kind === "package" &&
        module.package === "maplibre-gl" &&
        module.packageRoot === "node_modules/maplibre-gl" &&
        MAP_MODULE_PATHS.includes(module.path) &&
        !seen.has(module.path) &&
        module.idSha256 === sha256("node_modules/maplibre-gl/" + module.path) &&
        count(module.renderedCodeUnits, 1_000_000_000) &&
        (module.originalCodeUnits === null || count(module.originalCodeUnits, 1_000_000_000)) &&
        (module.path !== "dist/maplibre-gl.css" || module.renderedCodeUnits === 0)
    )
    seen.add(module.path)
  }
  requireInput(byName.has(candidate.fileName))
  return candidate
}

/**
 * Verify the one version-bound static-noninitial allowance on owned source/artifact bytes.
 * Artifact IDs and archive digests are checked by the existing Actions download boundary.
 * This API does not authenticate arbitrary caller-supplied context or prove runtime closure.
 */
export async function verifyMapLibreBudgetAllowance(clientDir, evidence) {
  let stage = "input-shape"
  try {
    requireInput(
      exactKeys(evidence, [
        "checkoutSha",
        "htmlReportPath",
        "htmlReportSha256",
        "metadataPath",
        "metadataSha256",
        "runAttempt",
        "runId",
        "treeSha",
        "workspace",
      ])
    )
    stage = "input-identities"
    requireInput(
      commitId(evidence.checkoutSha) &&
        commitId(evidence.treeSha) &&
        hashId(evidence.metadataSha256) &&
        hashId(evidence.htmlReportSha256) &&
        typeof evidence.runId === "string" &&
        /^[1-9][0-9]{0,19}$/u.test(evidence.runId) &&
        typeof evidence.runAttempt === "string" &&
        /^[1-9][0-9]{0,9}$/u.test(evidence.runAttempt)
    )
    stage = "workspace-directory"
    const workspace = await ownedDirectory(evidence.workspace)
    stage = "client-directory"
    const client = await ownedDirectory(path.resolve(clientDir))
    stage = "no-follow-capabilities"
    requireInput(
      [constants.O_NOFOLLOW, constants.O_NONBLOCK].every(
        (flag) => Number.isSafeInteger(flag) && flag > 0
      )
    )
    for (const file of [evidence.metadataPath, evidence.htmlReportPath]) {
      stage = "evidence-outside-client"
      requireInput(typeof file === "string" && !file.startsWith(client + path.sep))
    }
    stage = "git-client"
    const git = sourceGit(workspace)
    const text = (args) => git(args).toString("utf8").trim()
    stage = "checkout-git-identity"
    requireInput(
      text(["rev-parse", "--show-toplevel"]) === workspace &&
        text(["rev-parse", "--verify", "HEAD"]) === evidence.checkoutSha &&
        text(["rev-parse", "HEAD^{tree}"]) === evidence.treeSha
    )
    stage = "commit-read"
    const rawCommit = git(["cat-file", "commit", evidence.checkoutSha], 65_536)
    const headerEnd = rawCommit.indexOf("\n\n")
    stage = "commit-header"
    requireInput(headerEnd > 0)
    const headers = rawCommit.subarray(0, headerEnd).toString("utf8").split("\n")
    const parents = headers
      .filter((line) => line.startsWith("parent "))
      .map((line) => line.slice(7))
    stage = "parent-identities"
    requireInput(parents.length <= 16 && parents.every(commitId))
    stage = "parent-uniqueness"
    requireInput(new Set(parents).size === parents.length)
    const sources = new Map()
    for (const relative of POLICY_SOURCE_PATHS) {
      stage = "source-read"
      const actual = await readFingerprint(workspace, relative, true, 2 * 1024 * 1024)
      stage = "source-git-blob"
      const committed = git(
        ["cat-file", "blob", evidence.checkoutSha + ":" + relative],
        2 * 1024 * 1024
      )
      stage = "source-byte-match"
      requireInput(actual.bytes.equals(committed))
      sources.set(relative, actual.bytes)
    }
    for (const name of ["maplibre-graph-binding.mjs", "check-bundle-budget.mjs"]) {
      stage = "executing-source-read"
      const executing = await evidenceFile(
        fileURLToPath(new URL("./" + name, import.meta.url)),
        2 * 1024 * 1024
      )
      stage = "executing-source-match"
      requireInput(executing.bytes.equals(sources.get("frontend/scripts/" + name)))
    }
    stage = "metadata-read"
    const metadataFile = await evidenceFile(evidence.metadataPath, FILE_LIMIT)
    stage = "html-report-read"
    const htmlFile = await evidenceFile(evidence.htmlReportPath, 65_536)
    stage = "evidence-hashes"
    requireInput(
      metadataFile.sha256 === evidence.metadataSha256 &&
        htmlFile.sha256 === evidence.htmlReportSha256
    )
    stage = "metadata-json"
    const metadata = parseJson(metadataFile.bytes)
    stage = "html-report-json"
    const report = parseJson(htmlFile.bytes)
    stage = "metadata-source-binding"
    requireInput(
      exactKeys(metadata, [
        "graph",
        "mapLibreChunks",
        "package",
        "producerSha256",
        "profile",
        "schemaVersion",
        "viteConfigSha256",
      ]) &&
        metadata.producerSha256 ===
          sha256(sources.get("frontend/scripts/maplibre-build-metadata.mjs")) &&
        metadata.viteConfigSha256 === sha256(sources.get("frontend/vite.config.mts"))
    )
    stage = "report-provenance"
    requireInput(
      exactKeys(report, [
        "checkedSourceFiles",
        "checkout",
        "eventContext",
        "inventory",
        "kind",
        "profile",
        "relationship",
        "runContext",
        "schemaVersion",
        "toolchain",
      ]) &&
        report.schemaVersion === 1 &&
        report.kind === "final-html-capture-diagnostic-not-admission" &&
        report.profile === "production-final-client" &&
        exactKeys(report.checkout, ["commitSha", "parentShas", "treeSha"]) &&
        report.checkout.commitSha === evidence.checkoutSha &&
        report.checkout.treeSha === evidence.treeSha &&
        equalJson(report.checkout.parentShas, parents) &&
        exactKeys(report.runContext, ["runAttempt", "runId"]) &&
        report.runContext.runId === evidence.runId &&
        report.runContext.runAttempt === evidence.runAttempt
    )
    const context = report.eventContext
    stage = "event-context-shape"
    requireInput(exactKeys(context, ["eventName", "githubSha", "prBaseSha", "prHeadSha"]))
    stage = "event-checkout"
    requireInput(context.githubSha === evidence.checkoutSha)
    if (context.eventName === "pull_request") {
      stage = "merge-parent-binding"
      requireInput(
        parents.length === 2 &&
          parents[0] === context.prBaseSha &&
          parents[1] === context.prHeadSha &&
          report.relationship === "merge-parents-match-event-context"
      )
    } else {
      stage = "push-context-binding"
      requireInput(
        context.eventName === "push" &&
          context.prBaseSha === null &&
          context.prHeadSha === null &&
          report.relationship === "checkout-only"
      )
    }
    stage = "capture-source-shape"
    requireInput(exactKeys(report.checkedSourceFiles, [...CAPTURE_SOURCE_PATHS].sort()))
    for (const relative of CAPTURE_SOURCE_PATHS) {
      stage = "capture-source-hash"
      requireInput(report.checkedSourceFiles[relative] === sha256(sources.get(relative)))
    }
    stage = "toolchain-claim"
    requireInput(
      exactKeys(report.toolchain, ["babelParser", "jsdom"]) &&
        report.toolchain.babelParser === "8.0.7" &&
        report.toolchain.jsdom === "30.1.3"
    )
    stage = "toolchain-resolver"
    const require = createRequire(path.join(workspace, "frontend/package.json"))
    stage = "lock-json"
    const lock = parseJson(sources.get("frontend/package-lock.json"))
    for (const [name, version] of [
      ["jsdom", "30.1.3"],
      ["@babel/parser", "8.0.7"],
    ]) {
      stage = "toolchain-manifest-read"
      const toolFile = await evidenceFile(require.resolve(name + "/package.json"), 2 * 1024 * 1024)
      stage = "toolchain-manifest-json"
      const tool = parseJson(toolFile.bytes)
      stage = "toolchain-installed-version"
      requireInput(
        tool.name === name &&
          tool.version === version &&
          lock.packages?.["node_modules/" + name]?.version === version
      )
    }
    stage = "installed-package-read"
    const installed = await readFingerprint(
      workspace,
      "frontend/node_modules/maplibre-gl/package.json",
      true,
      2 * 1024 * 1024
    )
    stage = "package-validation"
    validatePackage(metadata, sources, installed.bytes)
    stage = "graph-validation"
    const { byName } = validateGraph(metadata)
    stage = "graph-static-complete"
    requireInput(metadata.graph.complete && metadata.graph.unresolvedStaticImportCount === 0)
    stage = "candidate-validation"
    const candidate = validateCandidate(metadata, byName)
    stage = "candidate-read"
    const bytes = await readFingerprint(client, candidate.fileName, true)
    stage = "candidate-gzip"
    const gzip = gzipSync(bytes.bytes, { level: 9 })
    stage = "candidate-byte-match"
    requireInput(
      matchesFingerprint(bytes, candidate) &&
        gzip.byteLength === candidate.gzipBytes &&
        sha256(gzip) === candidate.gzipSha256
    )
    for (const name of AUXILIARY_PATHS) {
      stage = "auxiliary-disjointness"
      requireInput(!byName.has(name))
      stage = "auxiliary-read"
      const auxiliary = await readFingerprint(client, name, true)
      stage = "auxiliary-source-match"
      requireInput(auxiliary.bytes.equals(sources.get("frontend/public/" + name)))
      stage = "auxiliary-parse"
      validateAuxiliary(auxiliary.bytes, name)
    }
    stage = "inventory-recompute"
    const inventory = await inspectFinalHtml(client)
    stage = "inventory-match"
    requireInput(inventory !== null && equalJson(inventory, report.inventory))
    stage = "binding-recompute"
    const binding = await inspectMapLibreGraphBinding(client, metadata)
    stage = "binding-present"
    requireInput(binding !== null)
    const pending = [...metadata.graph.entryFiles]
    for (const document of binding.documents) {
      for (const root of document.roots) {
        if (root.assetPath !== null) {
          stage = "html-root-membership"
          requireInput(byName.has(root.assetPath) || AUXILIARY_PATHS.includes(root.assetPath))
          if (byName.has(root.assetPath)) pending.push(root.assetPath)
        }
        for (const edge of root.literalImports) {
          const auxiliaryEdge =
            root.assetPath === "theme-init.js" &&
            edge.kind === "dynamic" &&
            edge.assetPath === "static-shell-i18n.js"
          stage = "literal-edge-membership"
          requireInput(byName.has(edge.assetPath) || auxiliaryEdge)
          if (edge.kind === "static") pending.push(edge.assetPath)
        }
      }
    }
    const reachable = new Set()
    while (pending.length > 0) {
      const name = pending.pop()
      stage = "closure-node"
      requireInput(byName.has(name))
      if (reachable.has(name)) continue
      reachable.add(name)
      pending.push(...byName.get(name).imports)
    }
    stage = "candidate-noninitial"
    requireInput(!reachable.has(candidate.fileName))
    stage = "checkout-recheck"
    requireInput(text(["rev-parse", "--verify", "HEAD"]) === evidence.checkoutSha)
    for (const [relative, original] of sources) {
      stage = "source-reread"
      const current = await readFingerprint(workspace, relative, true, 2 * 1024 * 1024)
      stage = "source-recheck"
      requireInput(current.bytes.equals(original))
    }
    stage = "evidence-recheck"
    requireInput(
      (await evidenceFile(evidence.metadataPath, FILE_LIMIT)).sha256 === evidence.metadataSha256 &&
        (await evidenceFile(evidence.htmlReportPath, 65_536)).sha256 === evidence.htmlReportSha256
    )
    return {
      fileName: candidate.fileName,
      rawBytes: candidate.rawBytes,
      gzipBytes: candidate.gzipBytes,
      sha256: candidate.sha256,
      packageVersion: "6.15.0",
      staticInitialReachable: false,
      runtimeClosure: "unproved",
    }
  } catch {
    const error = new Error("MapLibre budget evidence rejected: " + stage)
    error.stack = error.message
    throw error
  }
}
