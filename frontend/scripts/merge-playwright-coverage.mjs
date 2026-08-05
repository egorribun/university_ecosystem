#!/usr/bin/env node

/**
 * Convert Chromium Playwright V8 coverage files into an Istanbul/LCOV report.
 *
 * The E2E fixture writes one `playwright-coverage.json` per test under
 * Playwright's output directory. Missing input is a hard error: Codecov must
 * never receive a silently empty E2E report.
 */

import { readdir, readFile, mkdir } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import v8ToIstanbul from "v8-to-istanbul"
import coverageLib from "istanbul-lib-coverage"
import { createContext } from "istanbul-lib-report"
import reportsLib from "istanbul-reports"

const { createCoverageMap } = coverageLib
const { create: createReport } = reportsLib

function option(name) {
  const prefix = `--${name}=`
  const value = process.argv.find((argument) => argument.startsWith(prefix))
  return value ? value.slice(prefix.length) : undefined
}

async function findCoverageFiles(root) {
  const entries = await readdir(root, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const entryPath = path.join(root, entry.name)
    if (entry.isDirectory()) {
      files.push(...(await findCoverageFiles(entryPath)))
    } else if (entry.isFile() && entry.name === "playwright-coverage.json") {
      files.push(entryPath)
    }
  }
  return files
}

async function convertReport(file, coverageMap) {
  let report
  try {
    report = JSON.parse(await readFile(file, "utf8"))
  } catch (error) {
    throw new Error(`Cannot parse Playwright coverage report ${file}`, { cause: error })
  }
  if (!Array.isArray(report)) {
    throw new Error(`Playwright coverage report ${file} must be an array`)
  }

  for (const [index, entry] of report.entries()) {
    if (
      !entry ||
      typeof entry !== "object" ||
      typeof entry.url !== "string" ||
      typeof entry.source !== "string" ||
      !Array.isArray(entry.functions)
    ) {
      throw new Error(`Invalid V8 coverage entry ${index} in ${file}`)
    }

    const converter = v8ToIstanbul(entry.url, 0, { source: entry.source })
    try {
      await converter.load()
      converter.applyCoverage(entry.functions)
      coverageMap.merge(converter.toIstanbul())
    } catch (error) {
      throw new Error(`Cannot convert V8 entry ${entry.url} from ${file}`, { cause: error })
    }
  }
}

export async function mergePlaywrightCoverage(input, output) {
  const inputDir = path.resolve(input)
  const outputDir = path.resolve(output)
  const files = (await findCoverageFiles(inputDir)).sort()
  if (files.length === 0) {
    throw new Error(`No playwright-coverage.json files found under ${inputDir}`)
  }

  const coverageMap = createCoverageMap({})
  for (const file of files) {
    await convertReport(file, coverageMap)
  }
  if (coverageMap.files().length === 0) {
    throw new Error("Merged Playwright coverage contains no instrumented files")
  }

  await mkdir(outputDir, { recursive: true })
  const context = createContext({ dir: outputDir, coverageMap })
  createReport("json").execute(context)
  createReport("lcovonly").execute(context)
  process.stdout.write(`Merged ${files.length} Playwright coverage files into ${outputDir}\n`)
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))
) {
  const input = option("input")
  const output = option("output")
  if (!input || !output) {
    throw new Error("Usage: merge-playwright-coverage.mjs --input=<dir> --output=<dir>")
  }
  mergePlaywrightCoverage(input, output).catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`)
    process.exitCode = 1
  })
}
