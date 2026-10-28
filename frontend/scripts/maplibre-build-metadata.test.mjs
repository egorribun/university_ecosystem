import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { existsSync } from "node:fs"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"
import { gzipSync } from "node:zlib"

const helperUrl = new URL("./maplibre-build-metadata.mjs", import.meta.url)
const sha256 = (value) => createHash("sha256").update(value).digest("hex")

async function loadProducer() {
  assert.ok(existsSync(helperUrl), "the client build metadata producer must exist")
  return (await import(helperUrl.href)).mapLibreBuildMetadata
}

async function makeFixture() {
  const root = await mkdtemp(path.join(tmpdir(), "maplibre-metadata-"))
  const outputDir = path.join(root, "dist", "client")
  const reportPath = path.join(root, "evidence.json")
  const packageDir = path.join(root, "node_modules", "maplibre-gl")
  await mkdir(path.join(outputDir, "assets"), { recursive: true })
  await mkdir(packageDir, { recursive: true })
  const packageJson = JSON.stringify({ dependencies: { "maplibre-gl": "^6.15.0" } })
  const lockJson = JSON.stringify({
    lockfileVersion: 3,
    packages: {
      "node_modules/maplibre-gl": { version: "6.15.0", integrity: "sha512-ZXhhbXBsZQ==" },
    },
  })
  const installedJson = JSON.stringify({ name: "maplibre-gl", version: "6.15.0" })
  await writeFile(path.join(root, "package.json"), packageJson)
  await writeFile(path.join(root, "package-lock.json"), lockJson)
  await writeFile(path.join(packageDir, "package.json"), installedJson)
  await writeFile(path.join(root, "vite.config.mts"), "fixture-vite-config")
  const contents = {
    "assets/index-A.js": "entry-code-private",
    "assets/Map-A.js": "route-code-private",
    "assets/vendor-map-A.js": "map-code-private",
  }
  for (const [fileName, code] of Object.entries(contents)) {
    await writeFile(path.join(outputDir, fileName), code)
  }
  const moduleId = path.join(packageDir, "dist", "maplibre-gl.js")
  const chunk = (fileName, options = {}) => ({
    type: "chunk",
    fileName,
    code: contents[fileName],
    imports: options.imports ?? [],
    dynamicImports: options.dynamicImports ?? [],
    isEntry: options.isEntry ?? false,
    isDynamicEntry: options.isDynamicEntry ?? false,
    modules: options.modules ?? {},
  })
  const bundle = {
    "assets/index-A.js": chunk("assets/index-A.js", {
      isEntry: true,
      dynamicImports: ["assets/Map-A.js"],
    }),
    "assets/Map-A.js": chunk("assets/Map-A.js", {
      isDynamicEntry: true,
      imports: ["assets/vendor-map-A.js"],
    }),
    "assets/vendor-map-A.js": chunk("assets/vendor-map-A.js", {
      modules: { [moduleId]: { renderedLength: 13, originalLength: 21 } },
    }),
  }
  const environment = {
    name: "client",
    config: {
      consumer: "client",
      isWorker: false,
      build: { minify: "oxc", sourcemap: "hidden", target: ["chrome107"] },
    },
  }
  const config = {
    root,
    command: "build",
    mode: "production",
    isProduction: true,
    env: { VITE_LHCI: "false" },
  }
  return {
    root,
    outputDir,
    reportPath,
    contents,
    packageJson,
    lockJson,
    installedJson,
    bundle,
    environment,
    config,
  }
}

test("metadata records real emitted bytes, module identities and entry reachability", async () => {
  const createProducer = await loadProducer()
  const fixture = await makeFixture()
  try {
    const plugin = createProducer({ outputPath: fixture.reportPath, isLhci: false })
    plugin.configResolved(fixture.config)
    await plugin.writeBundle.call(
      { environment: fixture.environment },
      { dir: fixture.outputDir, format: "es" },
      fixture.bundle
    )
    const raw = await readFile(fixture.reportPath, "utf8")
    const report = JSON.parse(raw)
    const candidate = report.mapLibreChunks[0]
    const mapBytes = Buffer.from(fixture.contents["assets/vendor-map-A.js"])

    assert.equal(report.schemaVersion, 1)
    assert.deepEqual(report.profile, {
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
      target: ["chrome107"],
      format: "es",
    })
    assert.equal(report.package.declared, "^6.15.0")
    assert.equal(report.package.installedVersion, "6.15.0")
    assert.equal(report.package.lockVersion, "6.15.0")
    assert.equal(report.package.lockIntegrity, "sha512-ZXhhbXBsZQ==")
    assert.equal(report.package.packageJsonSha256, sha256(fixture.packageJson))
    assert.equal(report.package.lockSha256, sha256(fixture.lockJson))
    assert.equal(report.package.installedManifestSha256, sha256(fixture.installedJson))
    assert.equal(report.viteConfigSha256, sha256("fixture-vite-config"))
    assert.equal(report.graph.complete, true)
    assert.deepEqual(report.graph.entryFiles, ["assets/index-A.js"])
    assert.equal(candidate.fileName, "assets/vendor-map-A.js")
    assert.equal(candidate.staticEntryReachable, false)
    assert.equal(candidate.rawBytes, mapBytes.length)
    assert.equal(candidate.gzipBytes, gzipSync(mapBytes, { level: 9 }).length)
    assert.equal(candidate.sha256, sha256(mapBytes))
    assert.deepEqual(candidate.modules, [
      {
        kind: "package",
        package: "maplibre-gl",
        packageRoot: "node_modules/maplibre-gl",
        path: "dist/maplibre-gl.js",
        idSha256: sha256("node_modules/maplibre-gl/dist/maplibre-gl.js"),
        renderedBytes: 13,
        originalBytes: 21,
      },
    ])
    assert.deepEqual(
      report.graph.chunks.find((item) => item.fileName === "assets/index-A.js").dynamicImports,
      ["assets/Map-A.js"]
    )
    assert.doesNotMatch(raw, /code-private/u)
    assert.equal(raw.includes(fixture.root.replaceAll("\\", "/")), false)
    assert.equal(raw.includes(fixture.root.replaceAll("\\", "\\\\")), false)
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})

test("an entry import is reported as reachable and an incomplete graph stays unknown", async () => {
  const createProducer = await loadProducer()
  const fixture = await makeFixture()
  try {
    fixture.bundle["assets/index-A.js"].imports = ["assets/vendor-map-A.js"]
    const first = createProducer({ outputPath: fixture.reportPath })
    first.configResolved(fixture.config)
    await first.writeBundle.call(
      { environment: fixture.environment },
      { dir: fixture.outputDir, format: "es" },
      fixture.bundle
    )
    let report = JSON.parse(await readFile(fixture.reportPath, "utf8"))
    assert.equal(report.mapLibreChunks[0].staticEntryReachable, true)

    await rm(fixture.reportPath)
    fixture.bundle["assets/index-A.js"].imports = ["missing-external-module"]
    const second = createProducer({ outputPath: fixture.reportPath })
    second.configResolved(fixture.config)
    await second.writeBundle.call(
      { environment: fixture.environment },
      { dir: fixture.outputDir, format: "es" },
      fixture.bundle
    )
    report = JSON.parse(await readFile(fixture.reportPath, "utf8"))
    assert.equal(report.graph.complete, false)
    assert.equal(report.mapLibreChunks[0].staticEntryReachable, null)
    assert.equal(report.graph.unresolvedStaticImportCount, 1)
    assert.equal(JSON.stringify(report).includes("missing-external-module"), false)
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})

test("metadata is opt-in, client-only, and never overwrites existing evidence", async () => {
  const createProducer = await loadProducer()
  const fixture = await makeFixture()
  try {
    const disabled = createProducer({})
    disabled.configResolved(fixture.config)
    await disabled.writeBundle.call(
      { environment: fixture.environment },
      { dir: fixture.outputDir },
      fixture.bundle
    )
    assert.equal(existsSync(fixture.reportPath), false)
    const plugin = createProducer({ outputPath: fixture.reportPath })
    plugin.configResolved(fixture.config)
    assert.equal(plugin.applyToEnvironment(fixture.environment), true)
    assert.equal(
      plugin.applyToEnvironment({ name: "ssr", config: { consumer: "server", isWorker: false } }),
      false
    )
    assert.equal(
      plugin.applyToEnvironment({ name: "client", config: { consumer: "client", isWorker: true } }),
      false
    )
    await plugin.writeBundle.call(
      { environment: { name: "ssr", config: { consumer: "server", isWorker: false } } },
      { dir: fixture.outputDir },
      fixture.bundle
    )
    assert.equal(existsSync(fixture.reportPath), false)
    await writeFile(fixture.reportPath, "existing evidence")
    await assert.rejects(
      plugin.writeBundle.call(
        { environment: fixture.environment },
        { dir: fixture.outputDir },
        fixture.bundle
      ),
      { code: "EEXIST" }
    )
    assert.equal(await readFile(fixture.reportPath, "utf8"), "existing evidence")
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})

test("metadata rejects an emitted file whose bytes differ from the bundle", async () => {
  const createProducer = await loadProducer()
  const fixture = await makeFixture()
  try {
    await writeFile(path.join(fixture.outputDir, "assets/vendor-map-A.js"), "changed-after-render")
    const plugin = createProducer({ outputPath: fixture.reportPath })
    plugin.configResolved(fixture.config)
    await assert.rejects(
      plugin.writeBundle.call(
        { environment: fixture.environment },
        { dir: fixture.outputDir },
        fixture.bundle
      ),
      /emitted bytes differ/u
    )
    assert.equal(existsSync(fixture.reportPath), false)
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})
