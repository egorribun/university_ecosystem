import { createHash } from "node:crypto"
import { readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { gzipSync } from "node:zlib"

const MAX_CHUNKS = 5000
const MAX_MODULES = 10000
const MAX_EDGES_PER_KIND = 5000
const MAX_EDGES = 50000
const MAX_REPORT_BYTES = 4 * 1024 * 1024
const hash = (value) => createHash("sha256").update(value).digest("hex")
const normalize = (value) => value.replaceAll("\\", "/")

function isClient(environment) {
  return (
    environment?.name === "client" &&
    environment.config?.consumer === "client" &&
    !environment.config?.isWorker
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

function moduleMetadata(id, info, root) {
  const renderedCodeUnits = info.renderedLength
  const hasOriginalLength = "originalLength" in info
  const originalLength = hasOriginalLength ? info.originalLength : undefined
  const validLength = (value) => Number.isSafeInteger(value) && value >= 0 && value <= 1_000_000_000
  if (!validLength(renderedCodeUnits) || (hasOriginalLength && !validLength(originalLength)))
    throw new Error("invalid module length metadata")
  const originalCodeUnits = hasOriginalLength ? originalLength : null
  const separator = id.search(/[?#]/u)
  const file = separator < 0 ? id : id.slice(0, separator)
  const suffix = separator < 0 ? "" : id.slice(separator)
  const relative = normalize(path.relative(root, path.resolve(root, file)))
  const local = relative !== ".." && !relative.startsWith("../") && !path.isAbsolute(relative)
  const stableId = local ? relative + suffix : id
  const result = {
    kind: local ? "project" : "other",
    idSha256: hash(stableId),
    renderedCodeUnits,
    originalCodeUnits,
  }
  const marker = local ? relative.lastIndexOf("node_modules/") : -1
  if (marker < 0 || (marker > 0 && relative[marker - 1] !== "/")) return result
  const pieces = relative.slice(marker + "node_modules/".length).split("/")
  const packageParts = pieces[0]?.startsWith("@") ? pieces.splice(0, 2) : pieces.splice(0, 1)
  const packageName = packageParts.join("/")
  const modulePath = pieces.join("/")
  const packageRoot = `${relative.slice(0, marker)}node_modules/${packageName}`
  if (!safeFileName(packageName) || !safeFileName(packageRoot) || !safeFileName(modulePath))
    return result
  return {
    kind: "package",
    package: packageName,
    packageRoot,
    path: modulePath,
    idSha256: hash(stableId),
    renderedCodeUnits,
    originalCodeUnits,
  }
}

function boundedValue(value) {
  if (
    typeof value !== "string" ||
    value.length > 128 ||
    !/^[A-Za-z0-9.*+^~<>=| _/-]+$/u.test(value)
  ) {
    return null
  }
  return value
}

async function packageMetadata(root) {
  const [packageBytes, lockBytes, installedBytes] = await Promise.all([
    readFile(path.join(root, "package.json")),
    readFile(path.join(root, "package-lock.json")),
    readFile(path.join(root, "node_modules", "maplibre-gl", "package.json")),
  ])
  const manifest = JSON.parse(packageBytes)
  const lock = JSON.parse(lockBytes)
  const installed = JSON.parse(installedBytes)
  const entry = lock.packages?.["node_modules/maplibre-gl"]
  const integrity = entry?.integrity
  return {
    declared: boundedValue(manifest.dependencies?.["maplibre-gl"]),
    installedName: installed.name === "maplibre-gl" ? installed.name : null,
    installedVersion: boundedValue(installed.version),
    lockVersion: boundedValue(entry?.version),
    lockIntegrity:
      typeof integrity === "string" && /^sha(?:256|384|512)-[A-Za-z0-9+/=]+$/u.test(integrity)
        ? integrity
        : null,
    packageJsonSha256: hash(packageBytes),
    lockSha256: hash(lockBytes),
    installedManifestSha256: hash(installedBytes),
  }
}

function profile(config, environment, output, options) {
  const build = environment.config.build
  const target = Array.isArray(build.target) ? build.target : [build.target]
  return {
    command: config.command === "build" ? "build" : "other",
    mode: ["production", "development", "test", "analyze"].includes(config.mode)
      ? config.mode
      : "other",
    isProduction: config.isProduction === true,
    lhci: options.isLhci === true,
    lhciEnv: config.env?.VITE_LHCI === "true",
    reactDevMode: options.isReactDevMode === true,
    unminified: options.isUnminified === true,
    consumer: environment.config.consumer,
    isWorker: environment.config.isWorker === true,
    minify: [false, "oxc", "esbuild", "terser"].includes(build.minify) ? build.minify : "other",
    sourcemap: [false, true, "inline", "hidden"].includes(build.sourcemap)
      ? build.sourcemap
      : "other",
    target: target.map(boundedValue),
    format: ["es", "cjs", "iife", "umd", "system", "amd"].includes(output.format)
      ? output.format
      : "other",
  }
}

async function buildMetadata(config, environment, output, bundle, options) {
  const inputChunks = Object.values(bundle).filter((item) => item.type === "chunk")
  if (inputChunks.length > MAX_CHUNKS || !output.dir)
    throw new Error("invalid or oversized client bundle")
  const root = config.root
  const chunks = []
  const names = new Set()
  let edgeCount = 0
  // Capture compiler metadata synchronously before any file reads can yield.
  for (const chunk of inputChunks) {
    const fileName = chunk.fileName
    const isEntry = chunk.isEntry
    const isDynamicEntry = chunk.isDynamicEntry
    if (!safeFileName(fileName) || names.has(fileName)) {
      throw new Error("invalid client chunk filename")
    }
    if (typeof isEntry !== "boolean" || typeof isDynamicEntry !== "boolean") {
      throw new Error("invalid client entry metadata")
    }
    const edgeLists = []
    for (const edges of [chunk.imports, chunk.dynamicImports]) {
      if (!Array.isArray(edges)) throw new Error("invalid client import metadata")
      edgeCount += edges.length
      if (edges.length > MAX_EDGES_PER_KIND || edgeCount > MAX_EDGES) {
        throw new Error("oversized client import metadata")
      }
      const captured = []
      for (let index = 0; index < edges.length; index += 1) {
        if (!Object.hasOwn(edges, index)) throw new Error("invalid client import metadata")
        const name = edges[index]
        if (typeof name !== "string" || name.length === 0) {
          throw new Error("invalid client import metadata")
        }
        captured.push(name)
      }
      edgeLists.push(captured)
    }
    const code = chunk.code
    chunks.push({
      fileName,
      isEntry,
      isDynamicEntry,
      imports: edgeLists[0],
      dynamicImports: edgeLists[1],
      code: typeof code === "string" ? code : Buffer.from(code),
      modules: Object.entries(chunk.modules).map(([id, info]) => moduleMetadata(id, info, root)),
    })
    names.add(fileName)
  }
  let unresolvedStaticImportCount = 0
  let unresolvedDynamicImportCount = 0
  const graphChunks = []
  for (const chunk of chunks) {
    const imports = chunk.imports.filter((name) => names.has(name)).sort()
    const dynamicImports = chunk.dynamicImports.filter((name) => names.has(name)).sort()
    if (
      new Set(imports).size !== imports.length ||
      new Set(dynamicImports).size !== dynamicImports.length
    ) {
      throw new Error("invalid client import metadata")
    }
    unresolvedStaticImportCount += chunk.imports.length - imports.length
    unresolvedDynamicImportCount += chunk.dynamicImports.length - dynamicImports.length
    const bytes = await readFile(path.resolve(output.dir, chunk.fileName))
    if (!bytes.equals(Buffer.from(chunk.code))) throw new Error("emitted bytes differ from bundle")
    graphChunks.push({
      fileName: chunk.fileName,
      rawBytes: bytes.byteLength,
      sha256: hash(bytes),
      isEntry: chunk.isEntry,
      isDynamicEntry: chunk.isDynamicEntry,
      imports,
      dynamicImports,
    })
  }
  graphChunks.sort((left, right) => left.fileName.localeCompare(right.fileName))
  const entryFiles = graphChunks.filter((chunk) => chunk.isEntry).map((chunk) => chunk.fileName)
  const complete = entryFiles.length > 0 && unresolvedStaticImportCount === 0
  const byName = new Map(graphChunks.map((chunk) => [chunk.fileName, chunk]))
  const reachable = new Set()
  const pending = [...entryFiles]
  while (pending.length > 0) {
    const name = pending.pop()
    if (reachable.has(name)) continue
    reachable.add(name)
    pending.push(...byName.get(name).imports)
  }

  const mapLibreChunks = []
  let moduleCount = 0
  for (const chunk of chunks) {
    const modules = chunk.modules
    if (
      !modules.some((module) => module.kind === "package" && module.package === "maplibre-gl") &&
      !/(?:^|\/)vendor-map(?:-|\.)/u.test(chunk.fileName)
    )
      continue
    moduleCount += modules.length
    if (moduleCount > MAX_MODULES) throw new Error("oversized MapLibre module inventory")
    modules.sort((left, right) => left.idSha256.localeCompare(right.idSha256))
    const bytes = await readFile(path.resolve(output.dir, chunk.fileName))
    if (!bytes.equals(Buffer.from(chunk.code))) throw new Error("emitted bytes differ from bundle")
    const gzip = gzipSync(bytes, { level: 9 })
    mapLibreChunks.push({
      fileName: chunk.fileName,
      staticEntryReachable: complete ? reachable.has(chunk.fileName) : null,
      rawBytes: bytes.byteLength,
      gzipBytes: gzip.byteLength,
      sha256: hash(bytes),
      gzipSha256: hash(gzip),
      modules,
    })
  }
  mapLibreChunks.sort((left, right) => left.fileName.localeCompare(right.fileName))
  return {
    schemaVersion: 3,
    profile: profile(config, environment, output, options),
    package: await packageMetadata(root),
    producerSha256: hash(await readFile(fileURLToPath(import.meta.url))),
    viteConfigSha256: hash(await readFile(path.join(root, "vite.config.mts"))),
    graph: {
      complete,
      entryFiles,
      unresolvedStaticImportCount,
      unresolvedDynamicImportCount,
      chunks: graphChunks,
    },
    mapLibreChunks,
  }
}

// Opt-in evidence is written outside the bundle, after the client bytes exist.
// It contains identifiers, graph edges, lengths and hashes, never source code.
export function mapLibreBuildMetadata(options = {}) {
  let config
  return {
    name: "maplibre-build-metadata",
    apply: "build",
    enforce: "post",
    applyToEnvironment: isClient,
    configResolved(resolved) {
      config = resolved
    },
    async writeBundle(output, bundle) {
      if (!options.outputPath || !isClient(this.environment)) return
      if (!path.isAbsolute(options.outputPath))
        throw new Error("metadata output path must be absolute")
      const outputSnapshot = { dir: output.dir, format: output.format }
      const report = await buildMetadata(config, this.environment, outputSnapshot, bundle, options)
      const data = `${JSON.stringify(report, null, 2)}\n`
      if (Buffer.byteLength(data) > MAX_REPORT_BYTES) throw new Error("oversized metadata report")
      // This is still a writeBundle snapshot; final post-build consumers must rehash.
      for (const chunk of report.graph.chunks) {
        const bytes = await readFile(path.resolve(outputSnapshot.dir, chunk.fileName))
        if (bytes.byteLength !== chunk.rawBytes || hash(bytes) !== chunk.sha256) {
          throw new Error("emitted bytes differ from bundle")
        }
      }
      await writeFile(options.outputPath, data, { flag: "wx" })
    },
  }
}
