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
            renderedBytes: 0,
            originalBytes: 0,
          }
        })
        value.mapLibreChunks[0].modules.sort((left, right) =>
          left.idSha256.localeCompare(right.idSha256)
        )
      }),
    ],
  ]
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
