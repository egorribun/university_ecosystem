import assert from "node:assert/strict"
import { execFileSync, spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { existsSync } from "node:fs"
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises"
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

    assert.equal(report.schemaVersion, 2)
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
        renderedCodeUnits: 13,
        originalCodeUnits: 21,
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

const inventoryWorkflowUrl = new URL(
  "../../.github/workflows/reusable-frontend-tests.yml",
  import.meta.url
)
const inventoryStepName = "      - name: Report bounded MapLibre build inventory\n"
const inventoryPrefix = "MAPLIBRE_BUILD_INVENTORY "
const privateCanary = "PRIVATE_MAP_INVENTORY_CANARY"

async function diagnosticProgram() {
  const workflow = await readFile(inventoryWorkflowUrl, "utf8")
  assert.equal(workflow.split(inventoryStepName).length, 2)
  const start = workflow.indexOf(inventoryStepName)
  const end = workflow.indexOf("\n      - name:", start + inventoryStepName.length)
  assert.ok(end > start)
  const step = workflow.slice(start, end)
  assert.match(step, /timeout-minutes: 1/u)
  assert.doesNotMatch(step, /continue-on-error|permissions:/u)
  const opening = "          node --input-type=module <<'MAPLIBRE_INVENTORY'\n"
  const closing = "          MAPLIBRE_INVENTORY"
  const bodyStart = step.indexOf(opening)
  const bodyEnd = step.indexOf(closing, bodyStart + opening.length)
  assert.ok(bodyStart >= 0 && bodyEnd > bodyStart)
  return step
    .slice(bodyStart + opening.length, bodyEnd)
    .split("\n")
    .filter((line) => line !== "")
    .map((line) => {
      assert.ok(line.startsWith("          "))
      return line.slice(10)
    })
    .join("\n")
}

async function makeDiagnosticFixture() {
  const fixture = await makeFixture()
  try {
    const scriptsDir = path.join(fixture.root, "scripts")
    const runnerTemp = path.join(fixture.root, "runner-temp")
    await mkdir(scriptsDir)
    await mkdir(runnerTemp)
    await writeFile(path.join(scriptsDir, "maplibre-build-metadata.mjs"), await readFile(helperUrl))
    const git = (...args) =>
      execFileSync("git", args, {
        cwd: fixture.root,
        encoding: "utf8",
        timeout: 5_000,
        maxBuffer: 4096,
        stdio: ["ignore", "pipe", "pipe"],
      }).trim()
    git("init", "--quiet")
    git("add", "package.json", "package-lock.json", "vite.config.mts", "scripts")
    git(
      "-c",
      "user.name=Inventory Fixture",
      "-c",
      "user.email=inventory@example.invalid",
      "-c",
      "commit.gpgsign=false",
      "commit",
      "--quiet",
      "-m",
      "owned fixture"
    )
    const checkoutSha = git("rev-parse", "HEAD")
    const reportPath = path.join(runnerTemp, "maplibre-inventory-1234-1-" + checkoutSha + ".json")
    const producer = (await loadProducer())({ outputPath: reportPath, isLhci: false })
    producer.configResolved(fixture.config)
    await producer.writeBundle.call(
      { environment: fixture.environment },
      { dir: fixture.outputDir, format: "es" },
      fixture.bundle
    )
    return {
      ...fixture,
      reportPath,
      runnerTemp,
      checkoutSha,
      env: {
        ...process.env,
        GITHUB_SHA: checkoutSha,
        GITHUB_RUN_ID: "1234",
        GITHUB_RUN_ATTEMPT: "1",
        RUNNER_TEMP: runnerTemp,
        MAPLIBRE_PRIVATE_CANARY: privateCanary,
      },
    }
  } catch (error) {
    await rm(fixture.root, { recursive: true, force: true })
    throw error
  }
}

function runDiagnostic(program, fixture) {
  return spawnSync(process.execPath, ["--input-type=module"], {
    cwd: fixture.root,
    input: program,
    env: fixture.env,
    encoding: "utf8",
    timeout: 10_000,
    maxBuffer: 65_536,
  })
}

async function mutateDiagnostic(fixture, mutate) {
  const value = JSON.parse(await readFile(fixture.reportPath, "utf8"))
  mutate(value)
  await writeFile(fixture.reportPath, JSON.stringify(value))
}

test("inventory capture is production-only and preserves general budgets", async () => {
  const workflow = await readFile(inventoryWorkflowUrl, "utf8")
  const buildStart = workflow.indexOf("      - name: Build app\n")
  const uploadStart = workflow.indexOf("      - name: Upload production bundle\n", buildStart)
  const lighthouseStart = workflow.indexOf("      - name: Build Lighthouse bundle\n", uploadStart)
  const build = workflow.slice(buildStart, uploadStart)
  assert.ok(buildStart >= 0 && uploadStart > buildStart && lighthouseStart > uploadStart)
  const buildEnd = workflow.indexOf("\n      - name:", buildStart + 1)
  const buildStep = workflow.slice(buildStart, buildEnd)
  assert.ok(buildEnd > buildStart && buildEnd < uploadStart)
  assert.ok(
    buildStep.includes(
      "\n          MAPLIBRE_BUILD_METADATA_OUTPUT: ${{ runner.temp }}/maplibre-inventory-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}.json\n"
    )
  )
  assert.equal((workflow.match(/^\s+MAPLIBRE_BUILD_METADATA_OUTPUT:/gmu) ?? []).length, 1)
  assert.ok(build.includes(inventoryStepName))
  const lighthouseEnd = workflow.indexOf("\n      - name:", lighthouseStart + 1)
  assert.doesNotMatch(
    workflow.slice(lighthouseStart, lighthouseEnd),
    /MAPLIBRE_BUILD_METADATA_OUTPUT/u
  )
  assert.match(
    workflow,
    /node --test scripts\/check-bundle-budget\.test\.mjs scripts\/maplibre-build-metadata\.test\.mjs/u
  )
  const { BUNDLE_BUDGETS } = await import("./check-bundle-budget.mjs")
  assert.equal(BUNDLE_BUDGETS.generalLazyJsGzipKb, 280)
})

test("inventory diagnostic validates real receipts and rejects unsafe data", async (t) => {
  const program = await diagnosticProgram()
  await t.test("prints only a bounded diagnostic inventory, not a budget proof", async () => {
    const fixture = await makeDiagnosticFixture()
    try {
      const result = runDiagnostic(program, fixture)
      assert.equal(result.error, undefined)
      assert.equal(result.status, 0, result.stderr)
      assert.equal(result.stderr, "")
      assert.ok(result.stdout.startsWith(inventoryPrefix))
      assert.ok(Buffer.byteLength(result.stdout) <= 32_768)
      assert.equal(result.stdout.trimEnd().split("\n").length, 1)
      const receipt = JSON.parse(result.stdout.slice(inventoryPrefix.length))
      assert.equal(receipt.kind, "maplibre-build-inventory-not-budget-proof")
      assert.equal(receipt.checkoutSha, fixture.checkoutSha)
      assert.equal(receipt.runId, "1234")
      assert.equal(receipt.runAttempt, "1")
      assert.equal(receipt.package.installedVersion, "6.15.0")
      assert.equal(receipt.mapLibreChunks.length, 1)
      assert.equal(receipt.mapLibreChunks[0].fileName, "assets/vendor-map-A.js")
      assert.equal(
        receipt.mapLibreChunks[0].sha256,
        sha256(fixture.contents["assets/vendor-map-A.js"])
      )
      assert.equal(receipt.mapLibreChunks[0].staticEntryReachable, false)
      assert.equal(receipt.mapLibreChunks[0].modules[0].package, "maplibre-gl")
      assert.equal(receipt.mapLibreChunks[0].modules[0].path, "dist/maplibre-gl.js")
      assert.equal(receipt.mapLibreChunks[0].modules[0].packageRoot, undefined)
      assert.equal(result.stdout.includes(fixture.root), false)
      assert.equal(result.stdout.includes(privateCanary), false)
      assert.doesNotMatch(result.stdout, /code-private/u)
    } finally {
      await rm(fixture.root, { recursive: true, force: true })
    }
  })

  const changed = (mutate) => (fixture) => mutateDiagnostic(fixture, mutate)
  const cases = [
    ["missing", (fixture) => rm(fixture.reportPath)],
    ["malformed", (fixture) => writeFile(fixture.reportPath, privateCanary)],
    [
      "oversized",
      (fixture) => writeFile(fixture.reportPath, Buffer.alloc(4 * 1024 * 1024 + 1, 32)),
    ],
    [
      "symlink",
      async (fixture) => {
        const target = path.join(fixture.runnerTemp, "private-input-" + privateCanary)
        await writeFile(target, await readFile(fixture.reportPath))
        await rm(fixture.reportPath)
        await symlink(target, fixture.reportPath)
      },
    ],
    [
      "wrong-checkout",
      async (fixture) => {
        fixture.env.GITHUB_SHA = "0".repeat(40)
        const wrongPath = path.join(
          fixture.runnerTemp,
          "maplibre-inventory-1234-1-" + fixture.env.GITHUB_SHA + ".json"
        )
        await writeFile(wrongPath, await readFile(fixture.reportPath))
      },
    ],
    [
      "missing-attempt-receipt",
      async (fixture) => {
        fixture.env.GITHUB_RUN_ATTEMPT = "2"
      },
    ],
    [
      "changed-source",
      (fixture) => writeFile(path.join(fixture.root, "vite.config.mts"), privateCanary),
    ],
    [
      "changed-map-bytes",
      (fixture) => writeFile(path.join(fixture.outputDir, "assets/vendor-map-A.js"), privateCanary),
    ],
    [
      "wrong-package-hash",
      changed((value) => {
        value.package.packageJsonSha256 = "0".repeat(64)
      }),
    ],
    [
      "wrong-version",
      changed((value) => {
        value.package.installedVersion = privateCanary
      }),
    ],
    [
      "bad-module-path",
      changed((value) => {
        value.mapLibreChunks[0].modules[0].path = "../" + privateCanary
      }),
    ],
    [
      "bad-module-kind",
      changed((value) => {
        value.mapLibreChunks[0].modules[0].kind = privateCanary
      }),
    ],
    [
      "bad-chunk-path",
      async (fixture) => {
        const fileName = "private-" + privateCanary + ".js"
        await writeFile(
          path.join(fixture.root, "dist", fileName),
          fixture.contents["assets/vendor-map-A.js"]
        )
        await mutateDiagnostic(fixture, (value) => {
          value.mapLibreChunks[0].fileName = "../" + fileName
        })
      },
    ],
    [
      "wrong-map-hash",
      changed((value) => {
        value.mapLibreChunks[0].sha256 = "0".repeat(64)
      }),
    ],
    [
      "too-many-chunks",
      async (fixture) => {
        const value = JSON.parse(await readFile(fixture.reportPath, "utf8"))
        const candidate = value.mapLibreChunks[0]
        value.mapLibreChunks = []
        for (let index = 0; index < 9; index += 1) {
          const fileName =
            index === 0 ? candidate.fileName : "assets/vendor-map-probe-" + index + ".js"
          await writeFile(
            path.join(fixture.outputDir, fileName),
            fixture.contents["assets/vendor-map-A.js"]
          )
          value.mapLibreChunks.push({ ...candidate, fileName })
          if (index > 0) {
            value.graph.chunks.push({
              fileName,
              isEntry: false,
              isDynamicEntry: true,
              imports: [],
              dynamicImports: [],
            })
          }
        }
        value.mapLibreChunks.sort((left, right) => left.fileName.localeCompare(right.fileName))
        value.graph.chunks.sort((left, right) => left.fileName.localeCompare(right.fileName))
        await writeFile(fixture.reportPath, JSON.stringify(value))
      },
    ],
    [
      "oversized-module-population",
      changed((value) => {
        const module = value.mapLibreChunks[0].modules[0]
        value.mapLibreChunks[0].modules = Array.from({ length: 257 }, (_, index) => {
          if (index === 0) return module
          const modulePath = "dist/module-" + index + ".js"
          return {
            ...module,
            path: modulePath,
            idSha256: sha256("node_modules/maplibre-gl/" + modulePath),
            renderedCodeUnits: 0,
            originalCodeUnits: 0,
          }
        })
        value.mapLibreChunks[0].modules.sort((left, right) =>
          left.idSha256.localeCompare(right.idSha256)
        )
      }),
    ],
  ]

  const invalidLengths = [
    ["negative", -1],
    ["fractional", 0.5],
    ["over-limit", 1_000_000_001],
    ["string", privateCanary],
    ["boolean", true],
  ]
  for (const field of ["renderedCodeUnits", "originalCodeUnits"]) {
    cases.push([
      "missing-" + field,
      changed((value) => {
        delete value.mapLibreChunks[0].modules[0][field]
      }),
    ])
    for (const [label, invalid] of invalidLengths) {
      cases.push([
        field + "-" + label,
        changed((value) => {
          value.mapLibreChunks[0].modules[0][field] = invalid
        }),
      ])
    }
  }
  cases.push(
    [
      "null-rendered-code-units",
      changed((value) => {
        value.mapLibreChunks[0].modules[0].renderedCodeUnits = null
      }),
    ],
    [
      "legacy-schema",
      changed((value) => {
        value.schemaVersion = 1
      }),
    ],
    [
      "legacy-module-length-fields",
      changed((value) => {
        const module = value.mapLibreChunks[0].modules[0]
        module.renderedBytes = module.renderedCodeUnits
        module.originalBytes = module.originalCodeUnits
        delete module.renderedCodeUnits
        delete module.originalCodeUnits
      }),
    ]
  )
  for (const [name, mutate] of cases) {
    await t.test(name, async () => {
      const fixture = await makeDiagnosticFixture()
      try {
        await mutate(fixture)
        const result = runDiagnostic(program, fixture)
        assert.equal(result.error, undefined)
        assert.equal(result.status, 1)
        assert.equal(result.stdout, "")
        assert.equal(result.stderr.trim(), "MAPLIBRE_BUILD_INVENTORY_REJECTED")
        assert.equal(result.stderr.includes(privateCanary), false)
        assert.equal(result.stderr.includes(fixture.root), false)
      } finally {
        await rm(fixture.root, { recursive: true, force: true })
      }
    })
  }
})

test("Rolldown lengths use code units and unavailable original stays null", async () => {
  const fixture = await makeDiagnosticFixture()
  try {
    // Rolldown 1.2.12 transformToRenderedModule exposes these three getters,
    // not Rollup's originalLength. renderedLength counts UTF-16 code units.
    const privateSource = 'export const label = "PRIVATE_MAP_INVENTORY_CANARY_é😀"\n'
    assert.notEqual(privateSource.length, Buffer.byteLength(privateSource))
    let sourceReads = 0
    const module = {
      get code() {
        sourceReads += 1
        return privateSource
      },
      get renderedLength() {
        return privateSource.length
      },
      get renderedExports() {
        return ["label"]
      },
    }
    assert.equal(Object.hasOwn(module, "originalLength"), false)
    const chunk = fixture.bundle["assets/vendor-map-A.js"]
    const [moduleId] = Object.keys(chunk.modules)
    chunk.modules = { [moduleId]: module }
    await rm(fixture.reportPath)
    const producer = (await loadProducer())({ outputPath: fixture.reportPath, isLhci: false })
    producer.configResolved(fixture.config)
    await producer.writeBundle.call(
      { environment: fixture.environment },
      { dir: fixture.outputDir, format: "es" },
      fixture.bundle
    )

    const raw = await readFile(fixture.reportPath, "utf8")
    const report = JSON.parse(raw)
    const candidate = report.mapLibreChunks[0]
    const record = candidate.modules[0]
    // Missing metadata is not zero and must survive JSON serialization.
    assert.equal(record.originalCodeUnits, null)
    assert.equal(record.renderedCodeUnits, privateSource.length)
    assert.equal(Object.hasOwn(record, "renderedBytes"), false)
    assert.equal(Object.hasOwn(record, "originalBytes"), false)
    assert.equal(report.schemaVersion, 2)
    assert.equal(sourceReads, 0)
    assert.equal(raw.includes(privateCanary), false)
    const bytes = Buffer.from(fixture.contents["assets/vendor-map-A.js"])
    const compressed = gzipSync(bytes, { level: 9 })
    assert.equal(candidate.rawBytes, bytes.length)
    assert.equal(candidate.gzipBytes, compressed.length)
    assert.equal(candidate.sha256, sha256(bytes))
    assert.equal(candidate.gzipSha256, sha256(compressed))

    const result = runDiagnostic(await diagnosticProgram(), fixture)
    assert.equal(result.error, undefined)
    assert.equal(result.status, 0, result.stderr)
    assert.equal(result.stderr, "")
    assert.ok(result.stdout.startsWith(inventoryPrefix))
    assert.ok(Buffer.byteLength(result.stdout) <= 32_768)
    assert.equal(result.stdout.trimEnd().split("\n").length, 1)
    const diagnostic = JSON.parse(result.stdout.slice(inventoryPrefix.length))
    assert.equal(diagnostic.kind, "maplibre-build-inventory-not-budget-proof")
    const sanitized = diagnostic.mapLibreChunks[0].modules[0]
    assert.equal(sanitized.originalCodeUnits, null)
    assert.equal(sanitized.renderedCodeUnits, privateSource.length)
    assert.equal(Object.hasOwn(sanitized, "renderedBytes"), false)
    assert.equal(Object.hasOwn(sanitized, "originalBytes"), false)
    assert.equal(sanitized.packageRoot, undefined)
    assert.equal(result.stdout.includes(fixture.root), false)
    assert.equal(result.stdout.includes(privateCanary), false)
    assert.doesNotMatch(result.stdout, /code-private/u)
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})

test("metadata rejects malformed module lengths before writing any receipt", async (t) => {
  const createProducer = await loadProducer()
  const capture = async (fixture) => {
    const plugin = createProducer({ outputPath: fixture.reportPath })
    plugin.configResolved(fixture.config)
    await plugin.writeBundle.call(
      { environment: fixture.environment },
      { dir: fixture.outputDir, format: "es" },
      fixture.bundle
    )
  }
  await t.test("zero is a known code-unit length, not missing metadata", async () => {
    const fixture = await makeFixture()
    try {
      const [module] = Object.values(fixture.bundle["assets/vendor-map-A.js"].modules)
      module.renderedLength = 0
      module.originalLength = 0
      await capture(fixture)
      const report = JSON.parse(await readFile(fixture.reportPath, "utf8"))
      const record = report.mapLibreChunks[0].modules[0]
      assert.equal(record.renderedCodeUnits, 0)
      assert.equal(record.originalCodeUnits, 0)
    } finally {
      await rm(fixture.root, { recursive: true, force: true })
    }
  })

  const invalidLengths = [
    ["undefined", undefined],
    ["null", null],
    ["nan", Number.NaN],
    ["infinity", Number.POSITIVE_INFINITY],
    ["negative-infinity", Number.NEGATIVE_INFINITY],
    ["negative", -1],
    ["fractional", 0.5],
    ["unsafe", Number.MAX_SAFE_INTEGER + 1],
    ["over-limit", 1_000_000_001],
    ["string", "13"],
    ["boolean", true],
  ]
  const cases = [["renderedLength", "missing", undefined, true]]
  for (const field of ["renderedLength", "originalLength"]) {
    for (const [label, invalid] of invalidLengths) {
      cases.push([field, label, invalid, false])
    }
  }
  for (const [field, label, invalid, missing] of cases) {
    await t.test(field + "-" + label, async () => {
      const fixture = await makeFixture()
      try {
        const [module] = Object.values(fixture.bundle["assets/vendor-map-A.js"].modules)
        if (missing) delete module[field]
        else module[field] = invalid
        await assert.rejects(capture(fixture), {
          name: "Error",
          message: "invalid module length metadata",
        })
        assert.equal(existsSync(fixture.reportPath), false)
      } finally {
        await rm(fixture.root, { recursive: true, force: true })
      }
    })
  }
})

async function makeAllChunkFixture() {
  const fixture = await makeFixture()
  try {
    const entry = "assets/index-A.js"
    fixture.contents[entry] = 'export const label = "map-proof-private-π🙂"'
    fixture.bundle[entry].code = fixture.contents[entry]
    await writeFile(path.join(fixture.outputDir, entry), fixture.contents[entry])

    const detached = "assets/detached-A.js"
    fixture.contents[detached] = 'export const unused = "detached-proof-private-🙂"'
    fixture.bundle[detached] = {
      type: "chunk",
      fileName: detached,
      code: fixture.contents[detached],
      imports: [],
      dynamicImports: [],
      isEntry: false,
      isDynamicEntry: false,
      modules: {},
    }
    await writeFile(path.join(fixture.outputDir, detached), fixture.contents[detached])
    return fixture
  } catch (error) {
    await rm(fixture.root, { recursive: true, force: true })
    throw error
  }
}

async function writeAllChunkFixture(fixture) {
  const plugin = (await loadProducer())({ outputPath: fixture.reportPath })
  plugin.configResolved(fixture.config)
  await plugin.writeBundle.call(
    { environment: fixture.environment },
    { dir: fixture.outputDir, format: "es" },
    fixture.bundle
  )
}

test("metadata fingerprints every emitted client chunk without exposing source", async () => {
  const fixture = await makeAllChunkFixture()
  try {
    await writeAllChunkFixture(fixture)
    const raw = await readFile(fixture.reportPath, "utf8")
    const report = JSON.parse(raw)
    const expectedNames = Object.keys(fixture.bundle).sort((left, right) =>
      left.localeCompare(right)
    )
    assert.deepEqual(report.graph.chunks.map((chunk) => chunk.fileName), expectedNames)
    for (const chunk of report.graph.chunks) {
      const bytes = await readFile(path.join(fixture.outputDir, chunk.fileName))
      assert.deepEqual(bytes, Buffer.from(fixture.bundle[chunk.fileName].code))
      assert.equal(chunk.rawBytes, bytes.byteLength)
      assert.equal(chunk.sha256, sha256(bytes))
    }
    assert.ok(
      Buffer.byteLength(fixture.contents["assets/index-A.js"]) >
        fixture.contents["assets/index-A.js"].length
    )
    const map = report.mapLibreChunks[0]
    const graphMap = report.graph.chunks.find((chunk) => chunk.fileName === map.fileName)
    const mapBytes = Buffer.from(fixture.contents[map.fileName])
    assert.equal(graphMap.rawBytes, map.rawBytes)
    assert.equal(graphMap.sha256, map.sha256)
    assert.equal(map.gzipBytes, gzipSync(mapBytes, { level: 9 }).byteLength)
    assert.equal(map.gzipSha256, sha256(gzipSync(mapBytes, { level: 9 })))
    assert.equal(map.staticEntryReachable, false)
    assert.equal(report.schemaVersion, 3)
    assert.doesNotMatch(raw, /map-proof-private|detached-proof-private|code-private/u)
    assert.equal(raw.includes(fixture.root.replaceAll("\\", "/")), false)
    assert.equal(raw.includes(fixture.root.replaceAll("\\", "\\\\")), false)
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})

test("metadata rejects changed or missing non-Map chunks before writing evidence", async (t) => {
  for (const fileName of ["assets/index-A.js", "assets/Map-A.js", "assets/detached-A.js"]) {
    for (const defect of ["changed", "missing"]) {
      await t.test(fileName + "-" + defect, async () => {
        const fixture = await makeAllChunkFixture()
        try {
          // A successful real capture is the control for each rejection case.
          await writeAllChunkFixture(fixture)
          const control = JSON.parse(await readFile(fixture.reportPath, "utf8"))
          assert.equal(
            control.mapLibreChunks[0].sha256,
            sha256(fixture.contents["assets/vendor-map-A.js"])
          )
          await rm(fixture.reportPath)
          const target = path.join(fixture.outputDir, fileName)
          if (defect === "changed") await writeFile(target, "changed-chunk-private")
          else await rm(target)
          await assert.rejects(
            writeAllChunkFixture(fixture),
            defect === "changed" ? /emitted bytes differ/u : { code: "ENOENT" }
          )
          assert.equal(existsSync(fixture.reportPath), false)
        } finally {
          await rm(fixture.root, { recursive: true, force: true })
        }
      })
    }
  }
})
