import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import omt from "@trickfilm400/rollup-plugin-off-main-thread"
import { rollup } from "rollup"

// Execute only the emitted synthetic worker fixtures. A child process owns its
// rejection handler so a missing AMD dependency can be asserted without leaking
// an unhandled rejection into node:test or loading any application code.
const WORKER_RUNNER = String.raw`
import { readFileSync } from "node:fs"
import { createContext, runInContext } from "node:vm"
const input = JSON.parse(readFileSync(0, "utf8"))
const files = new Map(input.chunks.map((chunk) => [chunk.fileName, chunk.code]))
const removed = new Set(input.missingFiles)
const imports = []
const workers = []
let rejection
process.on("unhandledRejection", (error) => {
  rejection = error instanceof Error ? error.message : String(error)
})
const origin = "https://omt-fixture.invalid/"
const scope = {
  URL,
  location: { href: new URL(input.entry, origin).href },
  Worker: class {
    constructor(url, options) {
      this.url = String(url)
      this.options = options
      workers.push({ url: this.url, options: this.options })
    }
  },
}
scope.self = scope
const context = createContext(scope)
scope.importScripts = (url) => {
  const parsed = new URL(url)
  if (parsed.origin !== new URL(origin).origin) throw new Error("unexpected-fixture-origin")
  const name = parsed.pathname.slice(1)
  imports.push(name)
  if (removed.has(name) || !files.has(name)) throw new Error("missing-fixture:" + name)
  runInContext(files.get(name), context, { timeout: 1000, filename: name })
}
try {
  for (let count = 0; count < input.entryRuns; count += 1) {
    runInContext(files.get(input.entry), context, { timeout: 1000, filename: input.entry })
  }
  for (let turn = 0; turn < 20 && rejection === undefined && !Object.hasOwn(scope, "__result"); turn += 1) {
    await new Promise((resolve) => setImmediate(resolve))
  }
  // Allow a rejection in another emitted dependency chain to surface too.
  await new Promise((resolve) => setImmediate(resolve))
  console.log(JSON.stringify({
    status: rejection === undefined && Object.hasOwn(scope, "__result") ? "resolved" : "rejected",
    value: scope.__result,
    rejection,
    imports,
    workers,
  }))
} catch (error) {
  console.log(JSON.stringify({ status: "rejected", rejection: error.message, imports, workers }))
}
`

async function bundleFixture(files, run, { output = {}, pluginOptions, warnings } = {}) {
  const root = await mkdtemp(join(tmpdir(), "workbox-omt-compat-"))
  let bundle
  try {
    for (const [name, code] of Object.entries(files)) await writeFile(join(root, name), code)
    bundle = await rollup({
      input: join(root, "entry.js"),
      plugins: [omt(pluginOptions)],
      onwarn(warning) {
        if (warnings) warnings.push(warning)
        else throw new Error(warning.message)
      },
    })
    const generated = await bundle.generate({
      format: "amd",
      sourcemap: true,
      hashCharacters: "hex",
      manualChunks: (id) =>
        id.replaceAll("\\", "/").endsWith("/workbox-runtime.js") ? "workbox" : undefined,
      ...output,
    })
    const chunks = generated.output.filter((item) => item.type === "chunk")
    await run(chunks, generated.output)
  } finally {
    try {
      await bundle?.close()
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  }
}

function executeWorker(chunks, entry, { missingFiles = [], entryRuns = 1 } = {}) {
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", WORKER_RUNNER], {
    input: JSON.stringify({ chunks, entry, missingFiles, entryRuns }),
    encoding: "utf8",
    env: {},
    timeout: 5000,
    maxBuffer: 1024 * 1024,
    shell: false,
  })
  assert.ifError(result.error)
  assert.equal(result.signal, null)
  assert.equal(result.status, 0, result.stderr)
  assert.equal(result.stderr, "")
  return JSON.parse(result.stdout)
}

const SPLIT_FILES = {
  "entry.js": 'import { answer } from "./workbox-runtime.js"; globalThis.__result = answer;',
  "workbox-runtime.js": "export const answer = 42;",
}

test(
  "Workbox-style AMD output renders the EJS loader and executes the external runtime once",
  { timeout: 10000 },
  async () => {
    await bundleFixture(SPLIT_FILES, (chunks, output) => {
      assert.equal(chunks.length, 2)
      const entry = chunks.find((chunk) => chunk.isEntry)
      const runtime = chunks.find((chunk) => !chunk.isEntry)
      assert.match(runtime.fileName, /^workbox-[0-9a-f]+\.js$/)
      assert.deepEqual(entry.imports, [runtime.fileName])
      assert.equal(entry.code.includes("<%"), false)
      assert.match(entry.code, /self\.define/)
      assert.equal(
        output.filter((item) => item.type === "asset" && item.fileName.endsWith(".map")).length,
        2
      )
      const result = executeWorker(chunks, entry.fileName, { entryRuns: 2 })
      assert.equal(result.status, "resolved")
      assert.equal(result.value, 42)
      assert.deepEqual(result.imports, [runtime.fileName])
      assert.deepEqual(result.workers, [])
    })
  }
)

test(
  "AMD loader rejects an absent emitted dependency instead of running the entry factory",
  { timeout: 10000 },
  async () => {
    await bundleFixture(SPLIT_FILES, (chunks) => {
      const entry = chunks.find((chunk) => chunk.isEntry)
      const runtime = chunks.find((chunk) => !chunk.isEntry)
      const result = executeWorker(chunks, entry.fileName, {
        missingFiles: [runtime.fileName],
      })
      assert.equal(result.status, "rejected")
      assert.equal(result.rejection, "missing-fixture:" + runtime.fileName)
      assert.equal(Object.hasOwn(result, "value"), false)
      assert.deepEqual(result.imports, [runtime.fileName])
    })
  }
)

test(
  "native matching rewrites both worker constructors and strips module type from AMD workers",
  { timeout: 10000 },
  async () => {
    await bundleFixture(
      {
        "entry.js": `
        const first = new Worker(new URL("./worker-a.js", import.meta.url), { type: "module", name: "first" });
        const second = new Worker(new URL("./worker-b.js", import.meta.url), { type: "module", name: "second" });
        globalThis.__result = [first.url, second.url];
      `,
        "worker-a.js":
          'import { answer } from "./workbox-runtime.js"; globalThis.__result = answer + 1;',
        "worker-b.js":
          'import { answer } from "./workbox-runtime.js"; globalThis.__result = answer + 2;',
        "workbox-runtime.js": "export const answer = 42;",
      },
      (chunks) => {
        assert.equal(chunks.length, 4)
        const entry = chunks.find((chunk) =>
          chunk.facadeModuleId?.replaceAll("\\", "/").endsWith("/entry.js")
        )
        const runtime = chunks.find((chunk) => chunk.name === "workbox")
        const result = executeWorker(chunks, entry.fileName)
        assert.equal(result.status, "resolved")
        assert.equal(result.workers.length, 2)
        assert.deepEqual(
          result.workers.map((worker) => worker.options),
          [{ name: "first" }, { name: "second" }]
        )
        for (const [index, worker] of result.workers.entries()) {
          const name = new URL(worker.url).pathname.slice(1)
          const chunk = chunks.find((item) => item.fileName === name)
          assert.ok(chunk, "rewritten URL must reference an emitted worker chunk")
          assert.match(chunk.code, /self\.define/)
          const actual = executeWorker(chunks, name)
          assert.equal(actual.status, "resolved")
          assert.equal(actual.value, 43 + index)
          assert.deepEqual(actual.imports, [runtime.fileName])
        }
      }
    )
  }
)

test(
  "worker resolution failure rejects the bundle rather than emitting a broken URL",
  { timeout: 10000 },
  async () => {
    await assert.rejects(
      bundleFixture(
        {
          "entry.js":
            'new Worker(new URL("./missing-worker.js", import.meta.url), { type: "module" });',
        },
        () => {}
      ),
      { code: "PLUGIN_ERROR", plugin: "off-main-thread", hook: "transform" }
    )
  }
)

test("AMD plugin rejects unsupported output formats", { timeout: 10000 }, async () => {
  await assert.rejects(
    bundleFixture({ "entry.js": "globalThis.__result = 1;" }, () => {}, {
      output: { format: "iife" },
    }),
    /must either be "amd" or "esm"/
  )
})

test("ES module output stays free of the AMD loader", { timeout: 10000 }, async () => {
  await bundleFixture(
    { "entry.js": "export const answer = 42;" },
    (chunks) => {
      assert.equal(chunks.length, 1)
      assert.equal(chunks[0].code.includes("self.define"), false)
      assert.match(chunks[0].code, /export/)
    },
    {
      output: { format: "es" },
      pluginOptions: { silenceESMWorkerWarning: true },
    }
  )
})
