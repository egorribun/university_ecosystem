import assert from "node:assert/strict"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import { test } from "node:test"
import { build, loadConfigFromFile } from "vite"

const configPath = fileURLToPath(new URL("../vite.config.mts", import.meta.url))
const loaded = await loadConfigFromFile(
  { command: "build", mode: "production" },
  configPath,
  undefined,
  "silent"
)

async function flattenPlugins(options) {
  const resolved = await Promise.all(options)
  return resolved.flatMap((option) => (Array.isArray(option) ? option : [option]))
}

const telemetry = (await flattenPlugins(loaded.config.plugins)).find(
  (plugin) => plugin?.name === "build-memory-telemetry"
)
const linePattern =
  /^\[build-memory\] environment=(client|ssr|worker|other) phase=([a-z-]+) rss_mib=\d+\.\d heap_used_mib=\d+\.\d heap_total_mib=\d+\.\d external_mib=\d+\.\d array_buffers_mib=\d+\.\d\n$/u

function captureTelemetry(t) {
  const lines = []
  const originalWrite = process.stderr.write.bind(process.stderr)
  t.mock.method(process.stderr, "write", (chunk, ...args) => {
    const line = String(chunk)
    if (line.startsWith("[build-memory]")) {
      lines.push(line)
      return true
    }
    return originalWrite(chunk, ...args)
  })
  return lines
}

async function fixture(t) {
  const root = await mkdtemp(path.join(tmpdir(), "vite-build-memory-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  await writeFile(
    path.join(root, "answer.js"),
    "export function answer(value) { return value + 1 }\n"
  )
  await writeFile(
    path.join(root, "entry.js"),
    'import { answer } from "./answer.js"\nexport const total = answer(41)\n'
  )
  return root
}

for (const environment of ["client", "ssr"]) {
  test(`canonical build reports ${environment} memory phases without changing output or maps`, async (t) => {
    assert.ok(telemetry, "canonical Vite config must register build memory telemetry")
    const lines = captureTelemetry(t)
    const root = await fixture(t)
    const result = await build({
      configFile: false,
      root,
      logLevel: "silent",
      plugins: [telemetry],
      build: {
        minify: false,
        sourcemap: true,
        reportCompressedSize: false,
        ...(environment === "ssr"
          ? { ssr: path.join(root, "entry.js") }
          : { lib: { entry: path.join(root, "entry.js"), formats: ["es"] } }),
      },
    })
    for (const line of lines) assert.match(line, linePattern)
    assert.deepEqual(
      lines.map((line) => line.match(linePattern).slice(1)),
      [
        "build-start",
        "transform-complete",
        "render-start",
        "render-complete",
        "write-complete",
        "build-closed",
      ].map((phase) => [environment, phase])
    )
    const bundle = Array.isArray(result) ? result[0] : result
    const entry = bundle.output.find((output) => output.type === "chunk" && output.isEntry)
    const outputPath = path.join(root, "dist", entry.fileName)
    assert.equal((await import(pathToFileURL(outputPath).href)).total, 42)
    const map = JSON.parse(await readFile(`${outputPath}.map`, "utf8"))
    assert.ok(map.mappings.length > 0)
    assert.ok(map.sources.some((source) => source.endsWith("answer.js")))
    assert.ok(map.sources.some((source) => source.endsWith("entry.js")))
  })
}

test("failed transforms report failure and closure without error payloads", async (t) => {
  assert.ok(telemetry, "canonical Vite config must register build memory telemetry")
  const lines = captureTelemetry(t)
  const root = await fixture(t)
  await writeFile(path.join(root, "entry.js"), 'import "./unavailable.js"\n')
  await assert.rejects(
    build({
      configFile: false,
      root,
      logLevel: "silent",
      plugins: [telemetry],
      build: { lib: { entry: path.join(root, "entry.js"), formats: ["es"] } },
    }),
    /Could not resolve/u
  )
  const phases = lines.map((line) => line.match(linePattern)?.[2])
  assert.deepEqual(phases.slice(0, 2), ["build-start", "transform-failed"])
  // Rolldown and Vite can each close the failed bundle. Both calls must remain
  // harmless, without reporting successful render/write phases.
  assert.ok(phases.length >= 3)
  assert.ok(phases.slice(2).every((phase) => phase === "build-closed"))
  assert.ok(lines.every((line) => !line.includes(root) && !line.includes("unavailable")))
})

test("telemetry uses static labels for unfamiliar environments and never logs error content", (t) => {
  assert.ok(telemetry, "canonical Vite config must register build memory telemetry")
  const lines = captureTelemetry(t)
  const context = { environment: { name: "private-environment-detail", config: {} } }
  telemetry.buildEnd.call(context, new Error("private-error-detail"))
  assert.equal(lines.length, 1)
  assert.match(lines[0], linePattern)
  assert.match(lines[0], /environment=other phase=transform-failed/u)
  assert.doesNotMatch(lines[0], /private/u)
  assert.equal(telemetry.apply, "build")
})

test("worker and absent contexts use bounded labels", (t) => {
  assert.ok(telemetry, "canonical Vite config must register build memory telemetry")
  const lines = captureTelemetry(t)
  telemetry.buildStart.call({ environment: { config: { isWorker: true } } })
  telemetry.buildStart.call({})
  assert.deepEqual(
    lines.map((line) => line.match(linePattern)?.slice(1)),
    [
      ["worker", "build-start"],
      ["other", "build-start"],
    ]
  )
})
