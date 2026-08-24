import { spawn } from "node:child_process"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { after, before, describe, it } from "node:test"
import assert from "node:assert/strict"

const scriptPath = fileURLToPath(new URL("./merge-vitest-coverage.mjs", import.meta.url))
let fixtureRoot

function reportFor(filePath, hits) {
  return {
    [filePath]: {
      path: filePath,
      statementMap: {
        0: {
          start: { line: 1, column: 0 },
          end: { line: 1, column: 10 },
        },
      },
      fnMap: {
        0: {
          name: "sample",
          decl: { start: { line: 1, column: 0 }, end: { line: 1, column: 10 } },
          loc: { start: { line: 1, column: 0 }, end: { line: 1, column: 10 } },
        },
      },
      branchMap: {},
      s: { 0: hits },
      f: { 0: hits },
      b: {},
    },
  }
}

function reportWithNegativeBranch(filePath) {
  return {
    [filePath]: {
      path: filePath,
      statementMap: {
        0: {
          start: { line: 1, column: 0 },
          end: { line: 1, column: 10 },
        },
      },
      fnMap: {},
      branchMap: {
        0: {
          type: "if",
          line: 1,
          loc: { start: { line: 1, column: 0 }, end: { line: 1, column: 10 } },
          locations: [
            { start: { line: 1, column: 0 }, end: { line: 1, column: 5 } },
            { start: { line: 1, column: 5 }, end: { line: 1, column: 10 } },
          ],
        },
      },
      s: { 0: 1 },
      f: {},
      b: { 0: [4, -3] },
    },
  }
}

function runMerger(input, output, expectedShards) {
  const argumentsList = [scriptPath, `--input=${input}`, `--output=${output}`]
  if (expectedShards !== undefined) {
    argumentsList.push(`--expected-shards=${expectedShards}`)
  }
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, argumentsList, {
      stdio: ["ignore", "pipe", "pipe"],
    })
    let stdout = ""
    let stderr = ""
    child.stdout.setEncoding("utf8")
    child.stderr.setEncoding("utf8")
    child.stdout.on("data", (chunk) => {
      stdout += chunk
    })
    child.stderr.on("data", (chunk) => {
      stderr += chunk
    })
    child.once("error", reject)
    child.once("close", (code) => resolve({ code, stdout, stderr }))
  })
}

describe("merge-vitest-coverage", () => {
  before(async () => {
    fixtureRoot = await mkdtemp(path.join(os.tmpdir(), "university-ecosystem-vitest-merge-"))
    await mkdir(path.join(fixtureRoot, "input", "shard-1"), { recursive: true })
    await mkdir(path.join(fixtureRoot, "input", "shard-2", "nested"), { recursive: true })
    await writeFile(
      path.join(fixtureRoot, "input", "shard-1", "coverage-final.json"),
      JSON.stringify(reportFor("src/first.ts", 1))
    )
    await writeFile(
      path.join(fixtureRoot, "input", "shard-2", "nested", "coverage-final.json"),
      JSON.stringify(reportFor("src/second.ts", 1))
    )
  })

  after(async () => {
    await rm(fixtureRoot, { recursive: true, force: true })
  })

  it("recursively merges every shard and emits JSON plus LCOV", async () => {
    const output = path.join(fixtureRoot, "merged")
    const result = await runMerger(path.join(fixtureRoot, "input"), output, "2")

    assert.equal(result.code, 0, result.stderr)
    assert.match(result.stdout, /Merged 2 Vitest coverage shards/)

    const merged = JSON.parse(await readFile(path.join(output, "coverage-final.json"), "utf8"))
    assert.deepEqual(Object.keys(merged).sort(), ["src/first.ts", "src/second.ts"])
    assert.equal(merged["src/first.ts"].s["0"], 1)
    assert.equal(merged["src/second.ts"].f["0"], 1)
    assert.match(await readFile(path.join(output, "lcov.info"), "utf8"), /SF:.*first\.ts/)
  })

  it("fails closed when no shard report exists", async () => {
    const emptyInput = path.join(fixtureRoot, "empty-input")
    const output = path.join(fixtureRoot, "empty-output")
    await mkdir(emptyInput, { recursive: true })

    const result = await runMerger(emptyInput, output)

    assert.notEqual(result.code, 0)
    assert.match(result.stderr, /No coverage-final\.json files found/)
  })

  it("fails closed when the expected shard count is incomplete", async () => {
    const output = path.join(fixtureRoot, "incomplete-output")
    const result = await runMerger(path.join(fixtureRoot, "input"), output, "3")

    assert.notEqual(result.code, 0)
    assert.match(result.stderr, /Expected 3 coverage shards, found 2/)
  })

  it("normalises negative V8 branch counters before emitting LCOV", async () => {
    const input = path.join(fixtureRoot, "negative-input")
    const output = path.join(fixtureRoot, "negative-output")
    await mkdir(input, { recursive: true })
    await writeFile(
      path.join(input, "coverage-final.json"),
      JSON.stringify(reportWithNegativeBranch("src/negative.ts"))
    )

    const result = await runMerger(input, output, "1")

    assert.equal(result.code, 0, result.stderr)
    assert.match(result.stderr, /Normalised 1 negative coverage hit count\(s\) to zero/)
    const merged = JSON.parse(await readFile(path.join(output, "coverage-final.json"), "utf8"))
    assert.deepEqual(merged["src/negative.ts"].b["0"], [4, 0])
    assert.doesNotMatch(
      await readFile(path.join(output, "lcov.info"), "utf8"),
      /,-[0-9]+(?:\r?\n|$)/
    )
  })
})
