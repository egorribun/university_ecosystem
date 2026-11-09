import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { existsSync } from "node:fs"
import { mkdir, mkdtemp, readFile, rename, rm, symlink, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"

import { mapLibreBuildMetadata } from "./maplibre-build-metadata.mjs"

const subject = new URL("./maplibre-graph-binding.mjs", import.meta.url)
const privateCanary = "PRIVATE_GRAPH_BINDING_CANARY"
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex")

async function bind(clientDir, metadata) {
  assert.ok(existsSync(subject), "the inactive graph binding diagnostic must exist")
  return (await import(subject.href)).inspectMapLibreGraphBinding(clientDir, metadata)
}

async function fixture() {
  const root = await mkdtemp(path.join(tmpdir(), "maplibre-binding-"))
  const clientDir = path.join(root, "client")
  const packageDir = path.join(root, "node_modules", "maplibre-gl")
  await mkdir(path.join(clientDir, "assets"), { recursive: true })
  await mkdir(packageDir, { recursive: true })
  await writeFile(
    path.join(root, "package.json"),
    JSON.stringify({ dependencies: { "maplibre-gl": "^6.15.0" } })
  )
  await writeFile(
    path.join(root, "package-lock.json"),
    JSON.stringify({ packages: { "node_modules/maplibre-gl": { version: "6.15.0" } } })
  )
  await writeFile(
    path.join(packageDir, "package.json"),
    JSON.stringify({ name: "maplibre-gl", version: "6.15.0" })
  )
  await writeFile(path.join(root, "vite.config.mts"), "fixture-config")
  const files = {
    "assets/entry-A.js":
      'import "./shared-A.js"; import("./lazy-A.js"); const load = (name) => import(name);',
    "assets/shared-A.js": "export const shared = 1;",
    "assets/lazy-A.js": 'import "./vendor-map-A.js"; export const lazy = true;',
    "assets/vendor-map-A.js": `export const map = ${JSON.stringify(privateCanary)};`,
    "assets/detached-A.js": "export const detached = true;",
  }
  for (const [name, contents] of Object.entries(files)) {
    await writeFile(path.join(clientDir, name), contents)
  }
  const html =
    '<script type="module" src="/assets/entry-A.js"></script>' +
    '<link rel="modulepreload" href="/assets/shared-A.js">'
  await writeFile(path.join(clientDir, "_shell.html"), html)
  await writeFile(path.join(clientDir, "index.html"), html)

  const chunk = (fileName, options = {}) => ({
    type: "chunk",
    fileName,
    code: files[fileName],
    isEntry: options.isEntry ?? false,
    isDynamicEntry: options.isDynamicEntry ?? false,
    imports: options.imports ?? [],
    dynamicImports: options.dynamicImports ?? [],
    modules: options.modules ?? {},
  })
  const mapId = path.join(packageDir, "dist", "maplibre-gl.js")
  const bundle = {
    "assets/entry-A.js": chunk("assets/entry-A.js", {
      isEntry: true,
      imports: ["assets/shared-A.js"],
      dynamicImports: ["assets/lazy-A.js"],
    }),
    "assets/shared-A.js": chunk("assets/shared-A.js"),
    "assets/lazy-A.js": chunk("assets/lazy-A.js", {
      isDynamicEntry: true,
      imports: ["assets/vendor-map-A.js"],
    }),
    "assets/vendor-map-A.js": chunk("assets/vendor-map-A.js", {
      modules: { [mapId]: { renderedLength: 1, originalLength: 1 } },
    }),
    "assets/detached-A.js": chunk("assets/detached-A.js"),
  }
  const environment = {
    name: "client",
    config: {
      consumer: "client",
      isWorker: false,
      build: { minify: "oxc", sourcemap: false, target: ["chrome107"] },
    },
  }
  const output = path.join(root, "metadata.json")
  const plugin = mapLibreBuildMetadata({ outputPath: output })
  plugin.configResolved({ root, command: "build", mode: "production", isProduction: true, env: {} })
  await plugin.writeBundle.call({ environment }, { dir: clientDir, format: "es" }, bundle)
  return { root, clientDir, files, html, metadata: JSON.parse(await readFile(output, "utf8")) }
}

async function withFixture(run) {
  const item = await fixture()
  try {
    await run(item)
  } finally {
    await rm(item.root, { recursive: true, force: true })
  }
}

test("binds final document roots and every emitted graph artifact without an admission verdict", async () => {
  await withFixture(async ({ clientDir, metadata, files, html }) => {
    const result = await bind(clientDir, metadata)
    assert.notEqual(result, null)
    assert.equal(result.kind, "maplibre-graph-binding-diagnostic-not-budget-proof")
    assert.equal(result.provenance, "unverified")
    assert.equal(result.transitiveRuntimeImports, "uninspected")
    assert.equal(result.otherExecutionSurfaces, "uninspected")
    assert.equal(result.graph.chunkCount, 5)
    assert.equal(result.graph.candidateCount, 1)
    assert.deepEqual(result.graph.candidates, [
      {
        fileName: "assets/vendor-map-A.js",
        rawBytes: Buffer.byteLength(files["assets/vendor-map-A.js"]),
        sha256: digest(files["assets/vendor-map-A.js"]),
      },
    ])
    assert.equal(result.graph.unresolvedStaticImportCount, 0)
    assert.equal(result.graph.unresolvedDynamicImportCount, 0)
    assert.deepEqual(
      result.documents.map((document) => document.fileName),
      ["_shell.html", "index.html"]
    )
    for (const document of result.documents) {
      assert.equal(document.sha256, digest(html))
      assert.equal(document.rawBytes, Buffer.byteLength(html))
      assert.equal(document.unresolvedComputedImports, 1)
      assert.deepEqual(
        document.roots.map((root) => root.kind),
        ["external-module", "modulepreload"]
      )
      assert.equal(document.roots[0].assetPath, "assets/entry-A.js")
      assert.equal(document.roots[0].sha256, digest(files["assets/entry-A.js"]))
      assert.equal(document.roots[0].graphRelation, "byte-matched")
      assert.equal(document.roots[1].graphRelation, "byte-matched")
      assert.deepEqual(document.roots[0].literalImports, [
        { kind: "static", assetPath: "assets/shared-A.js", graphRelation: "reported-edge" },
        { kind: "dynamic", assetPath: "assets/lazy-A.js", graphRelation: "reported-edge" },
      ])
    }
    assert.doesNotMatch(JSON.stringify(result), /complete|reachable|admitted/u)
    assert.equal(JSON.stringify(result).includes(privateCanary), false)
    assert.equal(JSON.stringify(result).includes(clientDir), false)
  })
})

test("computed imports remain unresolved even when compiler dynamic edges are reported", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    const result = await bind(clientDir, metadata)
    assert.notEqual(result, null)
    assert.equal(metadata.graph.unresolvedDynamicImportCount, 0)
    assert.equal(result.documents[0].unresolvedComputedImports, 1)
    assert.equal(result.documents[1].unresolvedComputedImports, 1)
    assert.equal(result.transitiveRuntimeImports, "uninspected")
  })
})

test("pins validated graph fields against concurrent caller mutation", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    const graph = metadata.graph
    const entry = graph.chunks.find((chunk) => chunk.isEntry)
    Object.defineProperty(metadata, "graph", {
      get() {
        queueMicrotask(() => {
          entry.dynamicImports = []
        })
        return graph
      },
    })
    const result = await bind(clientDir, metadata)
    assert.equal(entry.dynamicImports.length, 0)
    assert.notEqual(result, null)
    assert.equal(result.documents[0].roots[0].literalImports[1].graphRelation, "reported-edge")
  })
})

test("does not substitute a different candidate when its filename getter changes", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    const candidate = metadata.mapLibreChunks[0]
    let reads = 0
    Object.defineProperty(candidate, "fileName", {
      get() {
        reads += 1
        return reads === 1 ? "assets/vendor-map-A.js" : "assets/shared-A.js"
      },
    })
    const result = await bind(clientDir, metadata)
    assert.notEqual(result, null)
    assert.equal(result.graph.candidates[0].fileName, "assets/vendor-map-A.js")
  })
})

test("snapshots graph collections before validating and iterating them", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    const graph = metadata.graph
    for (const [owner, field] of [
      [graph, "chunks"],
      [graph, "entryFiles"],
      [metadata, "mapLibreChunks"],
    ]) {
      const original = owner[field]
      let reads = 0
      Object.defineProperty(owner, field, {
        get() {
          reads += 1
          return reads === 1 ? original : []
        },
      })
    }
    const result = await bind(clientDir, metadata)
    assert.notEqual(result, null)
    assert.equal(result.graph.chunkCount, 5)
    assert.equal(result.graph.candidateCount, 1)
  })
})

test("preserves unreported external roots and compiler unresolved counts as unknown", async () => {
  await withFixture(async ({ clientDir, metadata, html }) => {
    await writeFile(path.join(clientDir, "theme-init.js"), "void 0;")
    const extra = html + '<script src="/theme-init.js"></script>'
    await writeFile(path.join(clientDir, "_shell.html"), extra)
    await writeFile(path.join(clientDir, "index.html"), extra)
    metadata.graph.unresolvedDynamicImportCount = 1
    const result = await bind(clientDir, metadata)
    assert.notEqual(result, null)
    assert.equal(result.graph.unresolvedDynamicImportCount, 1)
    assert.equal(result.documents[0].roots[2].graphRelation, "not-in-graph")
  })
})

test("rejects changed or missing bytes even for a detached graph chunk", async () => {
  await withFixture(async ({ clientDir, metadata, files }) => {
    await writeFile(
      path.join(clientDir, "assets/detached-A.js"),
      files["assets/detached-A.js"] + " "
    )
    assert.equal(await bind(clientDir, metadata), null)
    await rm(path.join(clientDir, "assets/detached-A.js"))
    assert.equal(await bind(clientDir, metadata), null)
  })
})

test("rejects a changed actual HTML root or mismatched candidate artifact identity", async () => {
  await withFixture(async ({ clientDir, metadata, files }) => {
    await writeFile(path.join(clientDir, "assets/entry-A.js"), files["assets/entry-A.js"] + " ")
    assert.equal(await bind(clientDir, metadata), null)
    await writeFile(path.join(clientDir, "assets/entry-A.js"), files["assets/entry-A.js"])
    metadata.mapLibreChunks[0].sha256 = digest("different")
    assert.equal(await bind(clientDir, metadata), null)
  })
})

test("rejects duplicate chunks, unknown graph targets and duplicate edges", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    const duplicate = structuredClone(metadata)
    duplicate.graph.chunks.push(structuredClone(duplicate.graph.chunks[0]))
    assert.equal(await bind(clientDir, duplicate), null)
    const missing = structuredClone(metadata)
    missing.graph.chunks[0].imports.push("assets/missing-A.js")
    assert.equal(await bind(clientDir, missing), null)
    const repeated = structuredClone(metadata)
    const entry = repeated.graph.chunks.find((chunk) => chunk.isEntry)
    entry.imports.push(entry.imports[0])
    assert.equal(await bind(clientDir, repeated), null)
  })
})

test("rejects graph metadata that omits a direct literal edge observed in actual bytes", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    metadata.graph.chunks.find((chunk) => chunk.isEntry).dynamicImports = []
    assert.equal(await bind(clientDir, metadata), null)
  })
})

test("rejects invalid paths, unknown graph schema and inconsistent compiler entry metadata", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    const unsafe = structuredClone(metadata)
    unsafe.graph.chunks[0].fileName = "../outside.js"
    assert.equal(await bind(clientDir, unsafe), null)
    const schema = structuredClone(metadata)
    schema.schemaVersion = 4
    assert.equal(await bind(clientDir, schema), null)
    const entry = structuredClone(metadata)
    entry.graph.entryFiles = []
    assert.equal(await bind(clientDir, entry), null)
    const completeness = structuredClone(metadata)
    completeness.graph.complete = false
    assert.equal(await bind(clientDir, completeness), null)
  })
})

test("rejects unsupported foreign references and malformed scripts rather than claiming closure", async () => {
  await withFixture(async ({ clientDir, metadata, html }) => {
    for (const addition of [
      '<script src="https://example.invalid/unknown.js"></script>',
      "<script>import(</script>",
      '<base href="/other/">',
      '<script type="importmap">{}</script>',
    ]) {
      await writeFile(path.join(clientDir, "index.html"), html + addition)
      assert.equal(await bind(clientDir, metadata), null)
    }
  })
})

test("keeps a literal import with an unknown target unresolved", async () => {
  await withFixture(async ({ clientDir, metadata, html }) => {
    const extra = html + '<script type="module">import("/assets/unknown-A.js")</script>'
    await writeFile(path.join(clientDir, "_shell.html"), extra)
    await writeFile(path.join(clientDir, "index.html"), extra)
    const result = await bind(clientDir, metadata)
    assert.notEqual(result, null)
    assert.equal(result.documents[0].roots[2].graphRelation, "inline")
    assert.equal(result.documents[0].roots[2].literalImports[0].graphRelation, "not-in-graph")
  })
})

test("reports a real external module absent from the graph as unknown", async () => {
  await withFixture(async ({ clientDir, metadata, html }) => {
    await writeFile(path.join(clientDir, "assets/unreported-A.js"), "export const value = 1;")
    const extra = html + '<script type="module" src="/assets/unreported-A.js"></script>'
    await writeFile(path.join(clientDir, "_shell.html"), extra)
    await writeFile(path.join(clientDir, "index.html"), extra)
    const result = await bind(clientDir, metadata)
    assert.notEqual(result, null)
    assert.equal(result.documents[0].roots[2].graphRelation, "not-in-graph")
  })
})

test("rejects symlinked roots, graph artifacts and intermediate directories", async () => {
  await withFixture(async ({ root, clientDir, metadata, files }) => {
    const linkedRoot = path.join(root, "linked-client")
    await symlink(clientDir, linkedRoot, "dir")
    assert.equal(await bind(linkedRoot, metadata), null)
    const detached = path.join(clientDir, "assets/detached-A.js")
    const outside = path.join(root, "detached-copy.js")
    await writeFile(outside, files["assets/detached-A.js"])
    await rm(detached)
    await symlink(outside, detached, "file")
    assert.equal(await bind(clientDir, metadata), null)
    await rm(detached)
    await writeFile(detached, files["assets/detached-A.js"])
    await rename(path.join(clientDir, "assets"), path.join(clientDir, "actual-assets"))
    await symlink(path.join(clientDir, "actual-assets"), path.join(clientDir, "assets"), "dir")
    assert.equal(await bind(clientDir, metadata), null)
  })
})

test("rejects an oversized graph artifact even when its supplied hash and size match", async () => {
  await withFixture(async ({ clientDir, metadata }) => {
    const oversized = Buffer.alloc(4 * 1024 * 1024 + 1, 120)
    await writeFile(path.join(clientDir, "assets/detached-A.js"), oversized)
    const detached = metadata.graph.chunks.find(
      (chunk) => chunk.fileName === "assets/detached-A.js"
    )
    detached.rawBytes = oversized.length
    detached.sha256 = digest(oversized)
    assert.equal(await bind(clientDir, metadata), null)
  })
})
