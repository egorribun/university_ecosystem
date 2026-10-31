import assert from "node:assert/strict"
import { execFileSync, spawnSync } from "node:child_process"
import { createHash, randomUUID } from "node:crypto"
import { existsSync, writeFileSync } from "node:fs"
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { gzipSync } from "node:zlib"

import { analyzeBundle, assertBundleBudgets } from "./check-bundle-budget.mjs"
import { inspectFinalHtml } from "./final-html-root-inventory.mjs"

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

    assert.equal(report.schemaVersion, 3)
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
      "graph-missing-raw-bytes",
      changed((value) => {
        delete value.graph.chunks[0].rawBytes
      }),
    ],
    [
      "graph-wrong-raw-bytes",
      changed((value) => {
        value.graph.chunks[0].rawBytes += 1
      }),
    ],
    [
      "graph-invalid-raw-bytes",
      changed((value) => {
        value.graph.chunks[0].rawBytes = privateCanary
      }),
    ],
    [
      "graph-missing-sha256",
      changed((value) => {
        delete value.graph.chunks[0].sha256
      }),
    ],
    [
      "graph-invalid-sha256",
      changed((value) => {
        value.graph.chunks[0].sha256 = privateCanary
      }),
    ],
    [
      "graph-wrong-sha256",
      changed((value) => {
        value.graph.chunks[0].sha256 = "0".repeat(64)
      }),
    ],
    [
      "changed-non-map-bytes",
      (fixture) => writeFile(path.join(fixture.outputDir, "assets/index-A.js"), privateCanary),
    ],
    ["missing-non-map-bytes", (fixture) => rm(path.join(fixture.outputDir, "assets/index-A.js"))],
    [
      "schema-without-chunk-proof",
      changed((value) => {
        value.schemaVersion = 2
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
              rawBytes: candidate.rawBytes,
              sha256: candidate.sha256,
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
    assert.equal(report.schemaVersion, 3)
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
    assert.deepEqual(
      report.graph.chunks.map((chunk) => chunk.fileName),
      expectedNames
    )
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

test("compiler graph keeps unresolved static and dynamic edges distinct", async (t) => {
  for (const field of ["imports", "dynamicImports"]) {
    await t.test(field, async () => {
      const fixture = await makeAllChunkFixture()
      try {
        const external = "private-external-compiler-edge"
        fixture.bundle["assets/index-A.js"][field].push(external)
        await writeAllChunkFixture(fixture)
        const raw = await readFile(fixture.reportPath, "utf8")
        const report = JSON.parse(raw)
        const staticUnknown = field === "imports"
        assert.equal(report.graph.unresolvedStaticImportCount, Number(staticUnknown))
        assert.equal(report.graph.unresolvedDynamicImportCount, Number(!staticUnknown))
        // `complete` covers only compiler entry-point static reachability.
        assert.equal(report.graph.complete, !staticUnknown)
        assert.equal(report.mapLibreChunks[0].staticEntryReachable, staticUnknown ? null : false)
        assert.equal(raw.includes(external), false)
      } finally {
        await rm(fixture.root, { recursive: true, force: true })
      }
    })
  }
})

test("compiler graph rejects malformed edge and entry metadata before writing", async (t) => {
  const cases = [
    ["missing imports", "imports", undefined],
    ["null imports", "imports", null],
    ["string imports", "imports", "assets/Map-A.js"],
    ["non-string static edge", "imports", [null]],
    ["empty static edge", "imports", [""]],
    ["sparse static edges", "imports", Array(1)],
    ["duplicate static edge", "imports", ["assets/vendor-map-A.js", "assets/vendor-map-A.js"]],
    ["missing dynamic imports", "dynamicImports", undefined],
    ["object dynamic imports", "dynamicImports", {}],
    ["non-string dynamic edge", "dynamicImports", [42]],
    ["empty dynamic edge", "dynamicImports", [""]],
    ["sparse dynamic edges", "dynamicImports", Array(1)],
    ["duplicate dynamic edge", "dynamicImports", ["assets/Map-A.js", "assets/Map-A.js"]],
    ["non-boolean entry", "isEntry", "true"],
    ["missing entry", "isEntry", undefined],
    ["non-boolean dynamic entry", "isDynamicEntry", 1],
    ["missing dynamic entry", "isDynamicEntry", undefined],
  ]
  for (const [name, field, value] of cases) {
    await t.test(name, async () => {
      const fixture = await makeAllChunkFixture()
      try {
        fixture.bundle["assets/index-A.js"][field] = value
        await assert.rejects(
          writeAllChunkFixture(fixture),
          /invalid client (?:import|entry) metadata/u
        )
        assert.equal(existsSync(fixture.reportPath), false)
      } finally {
        await rm(fixture.root, { recursive: true, force: true })
      }
    })
  }
})

test("compiler graph rejects a chunk changed while metadata is being captured", async () => {
  const fixture = await makeAllChunkFixture()
  try {
    const build = fixture.environment.config.build
    const target = build.target
    Object.defineProperty(build, "target", {
      get() {
        writeFileSync(
          path.join(fixture.outputDir, "assets/detached-A.js"),
          "changed-during-capture"
        )
        return target
      },
    })
    await assert.rejects(writeAllChunkFixture(fixture), /emitted bytes differ/u)
    assert.equal(existsSync(fixture.reportPath), false)
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})

test("compiler graph snapshots chunk and module metadata before asynchronous reads", async () => {
  const fixture = await makeAllChunkFixture()
  try {
    const entry = fixture.bundle["assets/index-A.js"]
    const map = fixture.bundle["assets/vendor-map-A.js"]
    const code = entry.code
    let scheduled = false
    Object.defineProperty(entry, "code", {
      get() {
        if (!scheduled) {
          scheduled = true
          queueMicrotask(() => {
            map.imports.push("external-mutated-after-snapshot")
            map.isEntry = true
            map.isDynamicEntry = true
            Object.values(map.modules)[0].renderedLength = 999
          })
        }
        return code
      },
    })
    await writeAllChunkFixture(fixture)
    const report = JSON.parse(await readFile(fixture.reportPath, "utf8"))
    const graphMap = report.graph.chunks.find((chunk) => chunk.fileName === map.fileName)
    assert.deepEqual(report.graph.entryFiles, ["assets/index-A.js"])
    assert.equal(report.graph.unresolvedStaticImportCount, 0)
    assert.equal(graphMap.isEntry, false)
    assert.equal(graphMap.isDynamicEntry, false)
    assert.deepEqual(graphMap.imports, [])
    assert.equal(report.mapLibreChunks[0].modules[0].renderedCodeUnits, 13)
  } finally {
    await rm(fixture.root, { recursive: true, force: true })
  }
})

test("compiler graph bounds external edges before writing evidence", async (t) => {
  const externalEdges = () => Array.from({ length: 5_000 }, (_, index) => `external-${index}`)
  await t.test("per-array limit", async () => {
    const fixture = await makeAllChunkFixture()
    try {
      const edges = externalEdges()
      fixture.bundle["assets/index-A.js"].dynamicImports = edges
      await writeAllChunkFixture(fixture)
      const control = JSON.parse(await readFile(fixture.reportPath, "utf8"))
      assert.equal(control.graph.unresolvedDynamicImportCount, 5_000)
      await rm(fixture.reportPath)
      edges.push("external-extra")
      await assert.rejects(writeAllChunkFixture(fixture), /oversized client import metadata/u)
      assert.equal(existsSync(fixture.reportPath), false)
    } finally {
      await rm(fixture.root, { recursive: true, force: true })
    }
  })

  await t.test("aggregate limit", async () => {
    const fixture = await makeAllChunkFixture()
    try {
      for (let index = 0; index < 7; index += 1) {
        const fileName = `assets/extra-${index}.js`
        const code = `export const value = ${index}`
        fixture.bundle[fileName] = {
          type: "chunk",
          fileName,
          code,
          imports: [],
          dynamicImports: [],
          isEntry: false,
          isDynamicEntry: false,
          modules: {},
        }
        await writeFile(path.join(fixture.outputDir, fileName), code)
      }
      const chunks = Object.values(fixture.bundle)
      for (const chunk of chunks.slice(0, 10)) chunk.dynamicImports = externalEdges()
      // The fixture already has one resolved static edge.
      chunks[9].dynamicImports.pop()
      await writeAllChunkFixture(fixture)
      const control = JSON.parse(await readFile(fixture.reportPath, "utf8"))
      assert.equal(control.graph.unresolvedDynamicImportCount, 49_999)
      await rm(fixture.reportPath)
      chunks[10].dynamicImports = externalEdges()
      await assert.rejects(writeAllChunkFixture(fixture), /oversized client import metadata/u)
      assert.equal(existsSync(fixture.reportPath), false)
    } finally {
      await rm(fixture.root, { recursive: true, force: true })
    }
  })
})

const policySourcePaths = [
  ".github/workflows/reusable-frontend-tests.yml",
  "frontend/package.json",
  "frontend/package-lock.json",
  "frontend/vite.config.mts",
  "frontend/scripts/final-html-root-inventory.mjs",
  "frontend/scripts/build-orchestrated.mjs",
  "frontend/scripts/post-build-shell.mjs",
  "frontend/scripts/maplibre-build-metadata.mjs",
  "frontend/scripts/maplibre-graph-binding.mjs",
  "frontend/scripts/check-bundle-budget.mjs",
  "frontend/public/theme-init.js",
  "frontend/public/static-shell-i18n.js",
]

function policyPayload(blocks) {
  const bytes = Buffer.concat(
    Array.from({ length: blocks }, (_, index) =>
      createHash("sha256")
        .update("owned MapLibre budget fixture " + index)
        .digest()
    )
  )
  return 'export const ownedPayload = "' + bytes.toString("base64") + '";\n'
}

async function makePolicyFixture(change = () => {}) {
  const directory = fileURLToPath(new URL("..", import.meta.url))
  const workspace = await mkdtemp(path.join(directory, "node_modules", ".maplibre-budget-"))
  const frontend = path.join(workspace, "frontend")
  const outputDir = path.join(frontend, "dist", "client")
  const temporary = path.join(workspace, "runner-temp")
  try {
    await mkdir(path.join(outputDir, "assets"), { recursive: true })
    await mkdir(temporary)
    for (const relative of policySourcePaths) {
      const destination = path.join(workspace, relative)
      await mkdir(path.dirname(destination), { recursive: true })
      await writeFile(destination, await readFile(new URL("../../" + relative, import.meta.url)))
    }
    const installedDir = path.join(frontend, "node_modules", "maplibre-gl")
    await mkdir(installedDir, { recursive: true })
    await writeFile(
      path.join(installedDir, "package.json"),
      await readFile(new URL("../node_modules/maplibre-gl/package.json", import.meta.url))
    )
    const contents = {
      "assets/index-A.js": 'export const loadMap = () => import("./Map-A.js")\n',
      "assets/Map-A.js": 'import "./vendor-map-A.js"\nexport const route = true\n',
      "assets/vendor-map-A.js": policyPayload(9000),
      "assets/Detached-A.js": "export const detached = true\n",
    }
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
        modules: Object.fromEntries(
          ["maplibre-gl.css", "maplibre-gl.mjs", "maplibre-gl-worker.mjs?url"].map((name) => [
            path.join(installedDir, "dist", name),
            { renderedLength: name.endsWith(".css") ? 0 : 1 },
          ])
        ),
      }),
      "assets/Detached-A.js": chunk("assets/Detached-A.js"),
    }
    const fixture = {
      workspace,
      frontend,
      outputDir,
      temporary,
      contents,
      bundle,
      html:
        '<!doctype html><html><head><script src="/theme-init.js"></script></head><body>' +
        '<script type="module" src="/assets/index-A.js"></script></body></html>',
    }
    await change(fixture)
    for (const item of Object.values(bundle)) {
      await writeFile(path.join(outputDir, item.fileName), item.code)
    }
    for (const name of ["theme-init.js", "static-shell-i18n.js"]) {
      await writeFile(
        path.join(outputDir, name),
        await readFile(path.join(frontend, "public", name))
      )
    }
    for (const name of ["_shell.html", "index.html"]) {
      await writeFile(path.join(outputDir, name), fixture.html)
    }
    const gitEnvironment = {
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
    const git = (...args) =>
      execFileSync("git", ["--no-pager", "-c", "core.fsmonitor=false", ...args], {
        cwd: workspace,
        env: gitEnvironment,
        encoding: "utf8",
        timeout: 5000,
        maxBuffer: 4096,
        stdio: ["ignore", "pipe", "pipe"],
      }).trim()
    git("init", "--quiet", "--initial-branch=egorribun")
    git("add", "--", ...policySourcePaths)
    git(
      "-c",
      "user.name=Owned Budget Fixture",
      "-c",
      "user.email=budget@example.invalid",
      "-c",
      "commit.gpgsign=false",
      "commit",
      "--quiet",
      "-m",
      "owned budget fixture"
    )
    const checkoutSha = git("rev-parse", "--verify", "HEAD")
    const treeSha = git("rev-parse", "HEAD^{tree}")
    const metadataPath = path.join(temporary, "maplibre-inventory-1234-1-" + checkoutSha + ".json")
    const producer = (await loadProducer())({ outputPath: metadataPath, isLhci: false })
    producer.configResolved({
      root: frontend,
      command: "build",
      mode: "production",
      isProduction: true,
      env: { VITE_LHCI: "false" },
    })
    await producer.writeBundle.call(
      {
        environment: {
          name: "client",
          config: {
            consumer: "client",
            isWorker: false,
            build: {
              minify: "oxc",
              sourcemap: "hidden",
              target: ["chrome111", "edge111", "firefox114", "safari16.4", "ios16.4"],
            },
          },
        },
      },
      { dir: outputDir, format: "es" },
      bundle
    )
    const workflow = await readFile(inventoryWorkflowUrl, "utf8")
    const opening = "          node --input-type=module <<'FINAL_HTML_INVENTORY'\n"
    const closing = "          FINAL_HTML_INVENTORY"
    assert.equal(workflow.split(opening).length, 2)
    const start = workflow.indexOf(opening) + opening.length
    const end = workflow.indexOf(closing, start)
    assert.ok(end > start)
    const program = workflow
      .slice(start, end)
      .split("\n")
      .filter((line) => line !== "")
      .map((line) => {
        assert.ok(line.startsWith("          "))
        return line.slice(10)
      })
      .join("\n")
    const result = spawnSync(process.execPath, ["--input-type=module"], {
      cwd: frontend,
      input: program,
      env: {
        PATH: process.env.PATH || "",
        HOME: workspace,
        NODE_OPTIONS: "--max-old-space-size=512 --max-semi-space-size=16",
        GITHUB_WORKSPACE: workspace,
        GITHUB_SHA: checkoutSha,
        GITHUB_RUN_ID: "1234",
        GITHUB_RUN_ATTEMPT: "1",
        GITHUB_EVENT_NAME: "push",
        RUNNER_TEMP: temporary,
      },
      encoding: "utf8",
      timeout: 30_000,
      maxBuffer: 65_536,
    })
    assert.equal(result.error, undefined)
    assert.equal(result.status, 0, "owned final HTML capture must succeed")
    assert.equal(result.stderr, "")
    assert.equal(result.stdout.includes(workspace), false)
    const htmlReportPath = path.join(
      temporary,
      "final-html-inventory-1234-1-" + checkoutSha + ".json"
    )
    const evidence = {
      workspace,
      metadataPath,
      htmlReportPath,
      metadataSha256: sha256(await readFile(metadataPath)),
      htmlReportSha256: sha256(await readFile(htmlReportPath)),
      checkoutSha,
      treeSha,
      runId: "1234",
      runAttempt: "1",
    }
    return { ...fixture, evidence }
  } catch (error) {
    await rm(workspace, { recursive: true, force: true })
    throw error
  }
}

async function policyReport(fixture) {
  return analyzeBundle(path.join(fixture.frontend, "dist"), {
    mapLibreEvidence: fixture.evidence,
  })
}

async function changePolicyMetadata(fixture, change) {
  const metadata = JSON.parse(await readFile(fixture.evidence.metadataPath, "utf8"))
  change(metadata)
  const bytes = Buffer.from(JSON.stringify(metadata))
  await writeFile(fixture.evidence.metadataPath, bytes)
  fixture.evidence.metadataSha256 = sha256(bytes)
}

async function refreshPolicyHtml(fixture) {
  const report = JSON.parse(await readFile(fixture.evidence.htmlReportPath, "utf8"))
  report.inventory = await inspectFinalHtml(fixture.outputDir)
  assert.ok(report.inventory, "mutated owned HTML must still produce a valid diagnostic")
  const bytes = Buffer.from(JSON.stringify(report))
  await writeFile(fixture.evidence.htmlReportPath, bytes)
  fixture.evidence.htmlReportSha256 = sha256(bytes)
}

test("admits only a proven MapLibre 6.15 chunk within the separate lazy ceiling", async () => {
  const fixture = await makePolicyFixture()
  try {
    const bytes = Buffer.from(fixture.bundle["assets/vendor-map-A.js"].code)
    const compressed = gzipSync(bytes, { level: 9 }).byteLength
    assert.ok(compressed > 280 * 1024 && compressed <= 286 * 1024)
    const metadata = JSON.parse(await readFile(fixture.evidence.metadataPath, "utf8"))
    const worker = metadata.mapLibreChunks[0].modules.find(
      (module) => module.path === "dist/maplibre-gl-worker.mjs"
    )
    assert.ok(worker)
    assert.equal(
      worker.idSha256,
      sha256("node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs?url")
    )

    const ordinary = await analyzeBundle(path.join(fixture.frontend, "dist"))
    assert.throws(() => assertBundleBudgets(ordinary), /vendor-map-A\.js.*280 KiB/u)

    const report = await policyReport(fixture)
    assert.doesNotThrow(
      () => assertBundleBudgets(report),
      "valid build-bound MapLibre evidence must admit only the separate 286 KiB ceiling"
    )
    assert.equal(report.budgets.generalLazyJsGzipKb, 280)
    const candidate = report.assets.find((asset) => asset.path === "client/assets/vendor-map-A.js")
    assert.equal(candidate.isInitial, false)
    assert.equal(candidate.rawBytes, bytes.byteLength)
    assert.equal(candidate.gzipBytes, compressed)
  } finally {
    await rm(fixture.workspace, { recursive: true, force: true })
  }
})

test("invalid MapLibre evidence cannot grant a lazy budget allowance", async () => {
  const opaqueCanary = "owned-" + randomUUID()
  const knownStages = new Set([
    "input-shape",
    "input-identities",
    "workspace-directory",
    "client-directory",
    "no-follow-capabilities",
    "evidence-outside-client",
    "git-client",
    "checkout-git-identity",
    "commit-read",
    "commit-header",
    "parent-identities",
    "parent-uniqueness",
    "source-read",
    "source-git-blob",
    "source-byte-match",
    "executing-source-read",
    "executing-source-match",
    "metadata-read",
    "html-report-read",
    "evidence-hashes",
    "metadata-json",
    "html-report-json",
    "metadata-source-binding",
    "report-provenance",
    "event-context-shape",
    "event-checkout",
    "merge-parent-binding",
    "push-context-binding",
    "capture-source-shape",
    "capture-source-hash",
    "toolchain-claim",
    "toolchain-resolver",
    "lock-json",
    "toolchain-manifest-read",
    "toolchain-manifest-json",
    "toolchain-installed-version",
    "installed-package-read",
    "package-validation",
    "graph-validation",
    "graph-static-complete",
    "candidate-validation",
    "candidate-read",
    "candidate-gzip",
    "candidate-byte-match",
    "auxiliary-disjointness",
    "auxiliary-read",
    "auxiliary-source-match",
    "auxiliary-parse",
    "inventory-recompute",
    "inventory-match",
    "binding-recompute",
    "binding-present",
    "html-root-membership",
    "literal-edge-membership",
    "closure-node",
    "candidate-noninitial",
    "checkout-recheck",
    "source-reread",
    "source-recheck",
    "evidence-recheck",
  ])
  const expectedStages = {
    "metadata-content-hash": "evidence-hashes",
    "wrong-run": "report-provenance",
    "wrong-attempt": "report-provenance",
    "wrong-checkout": "checkout-git-identity",
    "wrong-tree": "checkout-git-identity",
    "wrong-version": "package-validation",
    "LHCI-profile": "package-validation",
    "unresolved-static-import": "graph-static-complete",
    "wrong-integrity": "package-validation",
    "wrong-producer": "metadata-source-binding",
    "wrong-vite-source": "metadata-source-binding",
    "missing-module": "candidate-validation",
    "duplicate-module": "candidate-validation",
    "foreign-module": "candidate-validation",
    "forged-module-id": "candidate-validation",
    "worker-missing-query": "candidate-validation",
    "worker-wrong-query": "candidate-validation",
    "worker-extra-query": "candidate-validation",
    "css-query": "candidate-validation",
    "main-query": "candidate-validation",
    "candidate-count-0": "candidate-validation",
    "candidate-count-2": "graph-validation",
    "candidate-count-3": "graph-validation",
    "changed-detached-chunk": "binding-present",
    "missing-detached-chunk": "binding-present",
    "changed-final-document": "inventory-match",
    "changed-auxiliary-asset": "auxiliary-source-match",
    "changed-tracked-auxiliary-source": "source-byte-match",
    "unknown-static-target": "graph-validation",
    "initial-static-closure": "candidate-noninitial",
    "non-entry-HTML-static-closure": "candidate-noninitial",
    "renamed-non-vendor-candidate": "candidate-validation",
    "direct-HTML-candidate": "candidate-noninitial",
    "unknown-HTML-root": "html-root-membership",
  }
  const rejectedAt = (stage, fixture) => (error) => {
    assert.ok(knownStages.has(stage))
    assert.ok(error instanceof Error)
    assert.equal(
      error.message === "MapLibre budget evidence rejected: " + stage,
      true,
      "MapLibre rejection must match its fixed stage"
    )
    assert.equal(error.stack === error.message, true, "MapLibre rejection stack must be opaque")
    assert.equal(error.message.includes(fixture.workspace), false)
    assert.equal(error.message.includes(opaqueCanary), false)
    return true
  }
  const changedMetadata = (change) => (fixture) => changePolicyMetadata(fixture, change)
  const cases = [
    ["metadata-content-hash", (fixture) => writeFile(fixture.evidence.metadataPath, "{}")],
    [
      "wrong-run",
      (fixture) => {
        fixture.evidence.runId = "1235"
      },
    ],
    [
      "wrong-attempt",
      (fixture) => {
        fixture.evidence.runAttempt = "2"
      },
    ],
    [
      "wrong-checkout",
      (fixture) => {
        fixture.evidence.checkoutSha = "0".repeat(40)
      },
    ],
    [
      "wrong-tree",
      (fixture) => {
        fixture.evidence.treeSha = "0".repeat(40)
      },
    ],
    [
      "wrong-version",
      changedMetadata((metadata) => {
        metadata.package.installedVersion = "6.16.0"
      }),
    ],
    [
      "LHCI-profile",
      changedMetadata((metadata) => {
        metadata.profile.lhci = true
      }),
    ],
    [
      "unresolved-static-import",
      changedMetadata((metadata) => {
        metadata.graph.unresolvedStaticImportCount = 1
        metadata.graph.complete = false
      }),
    ],
    [
      "wrong-integrity",
      changedMetadata((metadata) => {
        metadata.package.lockIntegrity += "x"
      }),
    ],
    [
      "wrong-producer",
      changedMetadata((metadata) => {
        metadata.producerSha256 = "0".repeat(64)
      }),
    ],
    [
      "wrong-vite-source",
      changedMetadata((metadata) => {
        metadata.viteConfigSha256 = "0".repeat(64)
      }),
    ],
    [
      "missing-module",
      changedMetadata((metadata) => {
        metadata.mapLibreChunks[0].modules.pop()
      }),
    ],
    [
      "duplicate-module",
      changedMetadata((metadata) => {
        metadata.mapLibreChunks[0].modules.push(metadata.mapLibreChunks[0].modules[0])
      }),
    ],
    [
      "foreign-module",
      changedMetadata((metadata) => {
        metadata.mapLibreChunks[0].modules[0].package = "other"
      }),
    ],
    [
      "forged-module-id",
      changedMetadata((metadata) => {
        metadata.mapLibreChunks[0].modules[0].idSha256 = "0".repeat(64)
      }),
    ],
    ...[
      ["worker-missing-query", "dist/maplibre-gl-worker.mjs", ""],
      ["worker-wrong-query", "dist/maplibre-gl-worker.mjs", "?worker"],
      ["worker-extra-query", "dist/maplibre-gl-worker.mjs", "?url&inline"],
      ["css-query", "dist/maplibre-gl.css", "?url"],
      ["main-query", "dist/maplibre-gl.mjs", "?url"],
    ].map(([name, modulePath, suffix]) => [
      name,
      changedMetadata((metadata) => {
        const module = metadata.mapLibreChunks[0].modules.find((item) => item.path === modulePath)
        module.idSha256 = sha256("node_modules/maplibre-gl/" + modulePath + suffix)
      }),
    ]),
    ...[0, 2, 3].map((count) => [
      "candidate-count-" + count,
      changedMetadata((metadata) => {
        metadata.mapLibreChunks = Array(count).fill(metadata.mapLibreChunks[0])
      }),
    ]),
    [
      "changed-detached-chunk",
      (fixture) => writeFile(path.join(fixture.outputDir, "assets/Detached-A.js"), "changed"),
    ],
    [
      "missing-detached-chunk",
      (fixture) => rm(path.join(fixture.outputDir, "assets/Detached-A.js")),
    ],
    [
      "changed-final-document",
      (fixture) => writeFile(path.join(fixture.outputDir, "index.html"), fixture.html + "\n"),
    ],
    [
      "changed-auxiliary-asset",
      (fixture) => writeFile(path.join(fixture.outputDir, "theme-init.js"), "void 0;\n"),
    ],
    [
      "changed-tracked-auxiliary-source",
      (fixture) => writeFile(path.join(fixture.frontend, "public", "theme-init.js"), "void 0;\n"),
    ],
    [
      "unknown-static-target",
      changedMetadata((metadata) => {
        metadata.graph.chunks.find((chunk) => chunk.isEntry).imports.push("assets/unknown.js")
      }),
    ],
    [
      "initial-static-closure",
      async (fixture) => {
        const code = 'import "./vendor-map-A.js"\n' + fixture.contents["assets/index-A.js"]
        await writeFile(path.join(fixture.outputDir, "assets/index-A.js"), code)
        await changePolicyMetadata(fixture, (metadata) => {
          const entry = metadata.graph.chunks.find((chunk) => chunk.isEntry)
          entry.imports.push("assets/vendor-map-A.js")
          entry.rawBytes = Buffer.byteLength(code)
          entry.sha256 = sha256(code)
          metadata.mapLibreChunks[0].staticEntryReachable = false
        })
        await refreshPolicyHtml(fixture)
      },
    ],
    [
      "non-entry-HTML-static-closure",
      async (fixture) => {
        const html = fixture.html.replace(
          "</body>",
          '<script type="module" src="/assets/Map-A.js"></script></body>'
        )
        for (const name of ["_shell.html", "index.html"]) {
          await writeFile(path.join(fixture.outputDir, name), html)
        }
        await refreshPolicyHtml(fixture)
      },
    ],
    [
      "renamed-non-vendor-candidate",
      async (fixture) => {
        const oldName = "assets/vendor-map-A.js"
        const newName = "assets/renamed-map-A.js"
        const code = 'import "./renamed-map-A.js"\nexport const route = true\n'
        await writeFile(
          path.join(fixture.outputDir, newName),
          await readFile(path.join(fixture.outputDir, oldName))
        )
        await rm(path.join(fixture.outputDir, oldName))
        await writeFile(path.join(fixture.outputDir, "assets/Map-A.js"), code)
        await changePolicyMetadata(fixture, (metadata) => {
          metadata.mapLibreChunks[0].fileName = newName
          metadata.graph.chunks.find((chunk) => chunk.fileName === oldName).fileName = newName
          const route = metadata.graph.chunks.find((chunk) => chunk.fileName === "assets/Map-A.js")
          route.imports = [newName]
          route.rawBytes = Buffer.byteLength(code)
          route.sha256 = sha256(code)
          metadata.graph.chunks.sort((left, right) => left.fileName.localeCompare(right.fileName))
        })
      },
    ],
    [
      "direct-HTML-candidate",
      async (fixture) => {
        const html = fixture.html.replace(
          "</body>",
          '<script type="module" src="/assets/vendor-map-A.js"></script></body>'
        )
        for (const name of ["_shell.html", "index.html"]) {
          await writeFile(path.join(fixture.outputDir, name), html)
        }
        await refreshPolicyHtml(fixture)
      },
    ],
    [
      "unknown-HTML-root",
      async (fixture) => {
        await writeFile(path.join(fixture.outputDir, "assets/Unknown-A.js"), "export const x = 1\n")
        const html = fixture.html.replace(
          "</body>",
          '<script type="module" src="/assets/Unknown-A.js"></script></body>'
        )
        for (const name of ["_shell.html", "index.html"]) {
          await writeFile(path.join(fixture.outputDir, name), html)
        }
        await refreshPolicyHtml(fixture)
      },
    ],
  ]
  for (const [name, mutate] of cases) {
    const fixture = await makePolicyFixture()
    try {
      const control = await policyReport(fixture)
      assert.doesNotThrow(() => assertBundleBudgets(control), name + ": accepting control")
      await mutate(fixture)
      await assert.rejects(policyReport(fixture), rejectedAt(expectedStages[name], fixture), name)
      if (name === "metadata-content-hash") {
        const malformed = Buffer.from('{"private":' + opaqueCanary)
        await writeFile(fixture.evidence.metadataPath, malformed)
        fixture.evidence.metadataSha256 = sha256(malformed)
        await assert.rejects(policyReport(fixture), rejectedAt("metadata-json", fixture))
      }
    } finally {
      await rm(fixture.workspace, { recursive: true, force: true })
    }
  }
})

test("keeps every other lazy asset at 280 KiB and the MapLibre ceiling at 286", async (t) => {
  const cases = [
    [
      "other-lazy-over-280",
      (fixture) => {
        fixture.bundle["assets/Detached-A.js"].code = policyPayload(8960)
      },
      /Detached-A\.js.*280 KiB/u,
    ],
    [
      "MapLibre-over-286",
      (fixture) => {
        fixture.bundle["assets/vendor-map-A.js"].code = policyPayload(9300)
      },
      /vendor-map-A\.js.*286 KiB/u,
    ],
  ]
  for (const [name, change, expected] of cases) {
    const control = await makePolicyFixture()
    try {
      const accepted = await policyReport(control)
      assert.doesNotThrow(() => assertBundleBudgets(accepted), name + ": accepting control")
    } finally {
      await rm(control.workspace, { recursive: true, force: true })
    }
    const fixture = await makePolicyFixture(change)
    try {
      const mapSize = gzipSync(Buffer.from(fixture.bundle["assets/vendor-map-A.js"].code), {
        level: 9,
      }).byteLength
      if (name === "other-lazy-over-280") {
        const otherSize = gzipSync(Buffer.from(fixture.bundle["assets/Detached-A.js"].code), {
          level: 9,
        }).byteLength
        assert.ok(otherSize > 280 * 1024 && otherSize < mapSize)
        assert.ok(mapSize <= 286 * 1024)
        t.diagnostic(`MapLibre gzip bytes=${mapSize}; other lazy gzip bytes=${otherSize}`)
      } else {
        assert.ok(mapSize > 286 * 1024)
        t.diagnostic(`Oversized MapLibre gzip bytes=${mapSize}`)
      }
      const report = await policyReport(fixture)
      assert.equal(report.budgets.generalLazyJsGzipKb, 280)
      assert.throws(() => assertBundleBudgets(report), expected)
    } finally {
      await rm(fixture.workspace, { recursive: true, force: true })
    }
  }
})
