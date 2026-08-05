import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import assert from "node:assert/strict"
import { mergePlaywrightCoverage } from "./merge-playwright-coverage.mjs"

test("merges a Chromium V8 report into Istanbul JSON and LCOV", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "university-ecosystem-e2e-coverage-"))
  try {
    const input = path.join(root, "test-results", "test-1")
    const output = path.join(root, "coverage")
    const source =
      "function greet(name) { return name ? `Hello ${name}` : `Hello`; }\ngreet('world')\n"
    await mkdir(input, { recursive: true })
    await writeFile(
      path.join(input, "playwright-coverage.json"),
      JSON.stringify([
        {
          url: "http://127.0.0.1/assets/fixture.js",
          source,
          functions: [
            {
              functionName: "greet",
              ranges: [{ startOffset: 0, endOffset: source.length, count: 1 }],
              isBlockCoverage: true,
            },
          ],
        },
      ]),
      "utf8"
    )

    await mergePlaywrightCoverage(root, output)

    const report = JSON.parse(await readFile(path.join(output, "coverage-final.json"), "utf8"))
    assert.ok(Object.keys(report).length > 0)
    assert.ok((await readFile(path.join(output, "lcov.info"), "utf8")).includes("SF:"))
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("merges coverage when the captured bundle has an external source map", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "university-ecosystem-e2e-external-map-"))
  try {
    const input = path.join(root, "test-results", "test-1")
    const output = path.join(root, "coverage")
    const source =
      "function greet(name) { return name ? `Hello ${name}` : `Hello`; }\ngreet('world')\n//# sourceMappingURL=fixture.js.map\n"
    await mkdir(input, { recursive: true })
    await writeFile(
      path.join(input, "playwright-coverage.json"),
      JSON.stringify([
        {
          url: "http://127.0.0.1/assets/fixture.js",
          source,
          functions: [
            {
              functionName: "greet",
              ranges: [{ startOffset: 0, endOffset: source.length, count: 1 }],
              isBlockCoverage: true,
            },
          ],
        },
      ]),
      "utf8"
    )

    await mergePlaywrightCoverage(root, output)

    const report = JSON.parse(await readFile(path.join(output, "coverage-final.json"), "utf8"))
    assert.ok(Object.keys(report).length > 0)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("rejects an empty Playwright coverage input", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "university-ecosystem-e2e-empty-"))
  try {
    await assert.rejects(
      mergePlaywrightCoverage(root, path.join(root, "coverage")),
      /No playwright-coverage\.json files found/
    )
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
