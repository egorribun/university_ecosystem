#!/usr/bin/env node

/**
 * Merge V8/Istanbul coverage-final.json files emitted by Vitest shards.
 *
 * The script deliberately discovers reports recursively because
 * download-artifact keeps each shard in its own directory.  It never turns a
 * missing shard into an empty report: no input, malformed JSON, or a report
 * without files is a hard failure.
 */

import { readdir, readFile, mkdir } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import coverageLib from "istanbul-lib-coverage"
import { createContext } from "istanbul-lib-report"
import reportsLib from "istanbul-reports"

const { createCoverageMap } = coverageLib
const { create: createReport } = reportsLib

/**
 * V8's experimental AST remapper can emit a negative branch hit count for a
 * no-else conditional when a shard only observes the enclosing range.  A
 * negative counter is not valid Istanbul/LCOV data and makes the aggregate
 * artifact impossible to parse.  Clamp only that impossible value to zero;
 * all positive counters are left untouched, so the 100% gate remains
 * fail-closed for any genuinely uncovered branch.
 *
 * @param {Record<string, unknown>} report
 * @returns {number} number of corrected counters
 */
function normaliseNegativeHitCounts(report) {
  let corrected = 0
  for (const fileCoverage of Object.values(report)) {
    if (!fileCoverage || typeof fileCoverage !== "object" || Array.isArray(fileCoverage)) {
      continue
    }
    for (const property of ["s", "f"]) {
      const counters = fileCoverage[property]
      if (!counters || typeof counters !== "object" || Array.isArray(counters)) continue
      for (const [key, value] of Object.entries(counters)) {
        if (typeof value === "number" && value < 0) {
          throw new Error(`Negative ${property} coverage counter at ${key}`)
        }
      }
    }
    const branchCounters = fileCoverage.b
    if (branchCounters && typeof branchCounters === "object" && !Array.isArray(branchCounters)) {
      for (const values of Object.values(branchCounters)) {
        if (!Array.isArray(values)) continue
        for (let index = 0; index < values.length; index += 1) {
          if (typeof values[index] === "number" && values[index] < 0) {
            values[index] = 0
            corrected += 1
          }
        }
      }
    }
  }
  return corrected
}

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
    } else if (entry.isFile() && entry.name === "coverage-final.json") {
      files.push(entryPath)
    }
  }
  return files
}

async function main() {
  const input = option("input")
  const output = option("output")
  const expectedShards = option("expected-shards")
  if (!input || !output) {
    throw new Error(
      "Usage: merge-vitest-coverage.mjs --input=<dir> --output=<dir> [--expected-shards=<count>]"
    )
  }

  const inputDir = path.resolve(input)
  const outputDir = path.resolve(output)
  const files = (await findCoverageFiles(inputDir)).sort()
  if (files.length === 0) {
    throw new Error(`No coverage-final.json files found under ${inputDir}`)
  }
  if (expectedShards !== undefined) {
    const expectedCount = Number.parseInt(expectedShards, 10)
    if (!Number.isInteger(expectedCount) || expectedCount < 1) {
      throw new Error(`--expected-shards must be a positive integer, got ${expectedShards}`)
    }
    if (files.length !== expectedCount) {
      throw new Error(
        `Expected ${expectedCount} coverage shards, found ${files.length} under ${inputDir}`
      )
    }
  }

  const coverageMap = createCoverageMap({})
  let correctedHitCounts = 0
  for (const file of files) {
    let report
    try {
      report = JSON.parse(await readFile(file, "utf8"))
    } catch (error) {
      throw new Error(`Cannot parse coverage report ${file}`, { cause: error })
    }
    if (!report || typeof report !== "object" || Array.isArray(report)) {
      throw new Error(`Coverage report ${file} must be a JSON object`)
    }
    correctedHitCounts += normaliseNegativeHitCounts(report)
    coverageMap.merge(report)
  }

  if (coverageMap.files().length === 0) {
    throw new Error("Merged coverage contains no instrumented files")
  }

  await mkdir(outputDir, { recursive: true })
  const context = createContext({ dir: outputDir, coverageMap })
  createReport("json").execute(context)
  createReport("lcovonly").execute(context)
  if (correctedHitCounts > 0) {
    console.warn(`Normalised ${correctedHitCounts} negative coverage hit count(s) to zero`)
  }
  console.log(`Merged ${files.length} Vitest coverage shards into ${outputDir}`)
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
})
