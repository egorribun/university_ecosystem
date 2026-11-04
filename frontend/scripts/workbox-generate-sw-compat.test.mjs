import assert from "node:assert/strict"
import { realpathSync } from "node:fs"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import { basename, dirname, join } from "node:path"
import { Script } from "node:vm"
import test from "node:test"
import { generateSW } from "workbox-build"

const require = createRequire(import.meta.url)

async function withGeneratedWorker(content, maximumFileSizeToCacheInBytes, run) {
  const root = await mkdtemp(join(tmpdir(), "workbox-generate-sw-compat-"))
  try {
    const assets = join(root, "assets")
    const output = join(root, "output")
    await mkdir(assets)
    await mkdir(output)
    await writeFile(join(assets, "index.html"), content)
    const result = await generateSW({
      globDirectory: assets,
      globPatterns: ["index.html"],
      swDest: join(output, "sw.js"),
      // Exercise Workbox's real OMT factory call and AMD code-splitting branch.
      inlineWorkboxRuntime: false,
      // Keep this synthetic contract focused on bundling, without minifier workers.
      mode: "development",
      sourcemap: true,
      maximumFileSizeToCacheInBytes,
    })
    await run(result, output)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

test(
  "Workbox resolves the same OMT 4 factory exercised by the isolated worker tests",
  { timeout: 10000 },
  async () => {
    const direct = require.resolve("@trickfilm400/rollup-plugin-off-main-thread")
    const workboxRequire = createRequire(require.resolve("workbox-build"))
    const consumed = workboxRequire.resolve("@trickfilm400/rollup-plugin-off-main-thread")
    assert.equal(realpathSync(consumed), realpathSync(direct))
    const manifest = JSON.parse(await readFile(join(dirname(consumed), "package.json"), "utf8"))
    assert.equal(manifest.name, "@trickfilm400/rollup-plugin-off-main-thread")
    assert.equal(manifest.version, "4.0.0")
  }
)

test(
  "generateSW emits a split AMD runtime and source maps without precache warnings",
  { timeout: 30000 },
  async () => {
    const content = "<!doctype html><title>Fixture</title>"
    await withGeneratedWorker(content, 128, async (result, output) => {
      assert.deepEqual(result.warnings, [])
      assert.equal(result.count, 1)
      assert.equal(result.size, Buffer.byteLength(content))
      const names = result.filePaths.map((path) => basename(path)).sort()
      const runtime = names.find((name) => /^workbox-[0-9a-f]+\.js$/.test(name))
      assert.ok(runtime, "Workbox must emit its external runtime chunk")
      assert.deepEqual(names, ["sw.js", "sw.js.map", runtime, runtime + ".map"].sort())
      for (const name of ["sw.js", runtime]) {
        const code = await readFile(join(output, name), "utf8")
        assert.doesNotThrow(() => new Script(code, { filename: name }))
        const map = JSON.parse(await readFile(join(output, name + ".map"), "utf8"))
        assert.equal(map.version, 3)
        assert.ok(Array.isArray(map.sources) && map.sources.length > 0)
      }
      const worker = await readFile(join(output, "sw.js"), "utf8")
      assert.ok(
        worker.includes(runtime.replace(/\.js$/, "")),
        "worker must reference the emitted runtime"
      )
      assert.ok(worker.includes("index.html"), "the requested synthetic asset must be precached")
      assert.equal(worker.includes("<%"), false, "EJS tags must not escape into generated output")
    })
  }
)

test(
  "generateSW preserves the precache size warning instead of accepting an oversized asset",
  { timeout: 30000 },
  async () => {
    await withGeneratedWorker("x".repeat(256), 128, async (result) => {
      assert.equal(result.count, 0)
      assert.equal(result.size, 0)
      assert.equal(result.warnings.length, 1)
      assert.match(result.warnings[0], /index\.html/)
      assert.match(result.warnings[0], /won't be precached|will not be precached/)
    })
  }
)
