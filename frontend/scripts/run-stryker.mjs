#!/usr/bin/env node

import { spawn } from "node:child_process"
import { createHash, randomUUID } from "node:crypto"
import { execFile } from "node:child_process"
import {
  glob,
  lstat,
  mkdir,
  open,
  readdir,
  readFile,
  rename,
  rm,
  writeFile,
} from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import process from "node:process"
import { promisify } from "node:util"
import { fileURLToPath } from "node:url"

import {
  buildMutationInventory,
  generateInstrumenterPreflight,
  listPolicyFiles,
  mutantSignature,
  mutationPatternsFromPolicy,
} from "./validate-stryker-inventory.mjs"

const execFileAsync = promisify(execFile)
const frontendRoot = fileURLToPath(new URL("..", import.meta.url))
const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url))
const outputRoot = path.join(frontendRoot, "reports", "mutation")
const preflightArtifactOutputPath = path.join(
  outputRoot,
  "preflight-artifact",
  "PREFLIGHT_ARTIFACT.json"
)
const preflightCandidateRoot = path.join(outputRoot, "preflight-candidates")
const historicalCostCandidateRoot = path.join(outputRoot, "cost-candidates")
const historicalCostArtifactOutputPath = path.join(
  outputRoot,
  "historical-costs",
  "HISTORICAL_COSTS.json"
)
const sourcePolicyPath = path.join(repositoryRoot, "quality", "coverage-source-policy.json")
const strykerEntry = path.join(
  frontendRoot,
  "node_modules",
  "@stryker-mutator",
  "core",
  "bin",
  "stryker.js"
)
const instrumenterOptions = { plugins: null, excludedMutations: [], ignorers: [] }
const preflightArtifactSchemaVersion = "1.0"
const historicalCostArtifactSchemaVersion = "1.0"
const maximumHistoricalCostMs = 14_400_000
const windowsDeviceNamePattern = /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9]|clock\$)(?:\..*)?$/iu

function sha256(value) {
  return createHash("sha256").update(value).digest("hex")
}

function normalizePath(value) {
  return value.replaceAll("\\", "/").replace(/^\.\//u, "")
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function assertExactObjectKeys(value, expectedKeys, description) {
  if (!isRecord(value)) throw new Error(`${description} must be an object`)
  const actualKeys = Object.keys(value).sort()
  const sortedExpectedKeys = [...expectedKeys].sort()
  if (JSON.stringify(actualKeys) !== JSON.stringify(sortedExpectedKeys)) {
    throw new Error(`${description} has an unexpected shape`)
  }
}

function assertSha256(value, description) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/u.test(value)) {
    throw new Error(`${description} must be a SHA-256 digest`)
  }
}

function canonicalMutationSourcePath(value) {
  if (typeof value !== "string" || value.includes("\0")) {
    throw new Error("Preflight artifact source denominator contains an invalid path")
  }
  const normalized = normalizePath(value)
  if (
    normalized === "" ||
    normalized.startsWith("/") ||
    /^[A-Za-z]:/u.test(normalized) ||
    normalized.split("/").some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new Error("Preflight artifact source denominator contains an invalid path")
  }
  return normalized
}

function assertPortableArtifactRelativePath(value) {
  for (const component of value.split("/")) {
    if (
      !/^[\x21-\x7e]+$/u.test(component) ||
      /[:<>"|?*]/u.test(component) ||
      /[. ]$/u.test(component) ||
      windowsDeviceNamePattern.test(component)
    ) {
      throw new Error("Artifact path is not portable")
    }
  }
}

function canonicalSourceFiles(sourceFiles) {
  if (!Array.isArray(sourceFiles) || sourceFiles.length === 0) {
    throw new Error("Preflight artifact source denominator is missing")
  }
  const normalized = sourceFiles.map(canonicalMutationSourcePath).sort()
  const aliases = new Set(normalized.map((file) => file.toLocaleLowerCase("en-US")))
  if (new Set(normalized).size !== normalized.length || aliases.size !== normalized.length) {
    throw new Error("Preflight artifact source denominator contains duplicate paths")
  }
  return normalized
}

function assertCanonicalStringArray(value, description) {
  if (
    !Array.isArray(value) ||
    value.some((entry) => typeof entry !== "string" || entry === "") ||
    JSON.stringify(value) !== JSON.stringify([...value].sort()) ||
    new Set(value).size !== value.length
  ) {
    throw new Error(`${description} must be a sorted unique string array`)
  }
}

export async function stageStrykerSandboxInputs(tempDir, policyPath = sourcePolicyPath) {
  const policyBytes = await readFile(policyPath)
  const policyDirectory = path.join(tempDir, "quality")
  const stagedPolicyPath = path.join(policyDirectory, "coverage-source-policy.json")
  await mkdir(policyDirectory, { recursive: false })
  await writeFile(stagedPolicyPath, policyBytes, { flag: "wx" })
  const stagedPolicyBytes = await readFile(stagedPolicyPath)
  if (sha256(stagedPolicyBytes) !== sha256(policyBytes)) {
    throw new Error("Staged Stryker coverage policy differs from the canonical policy")
  }
  return stagedPolicyPath
}

function sortedObject(value) {
  return Object.fromEntries(
    Object.entries(value).sort(([left], [right]) => left.localeCompare(right))
  )
}

export function assertRunnerArguments(args) {
  if (!Array.isArray(args) || args.length !== 0) {
    throw new Error("Canonical mutation runner does not accept Stryker CLI overrides")
  }
}

function validatedHistoricalCosts(preflightByFile, historicalCosts) {
  if (historicalCosts === undefined) return undefined
  if (!(historicalCosts instanceof Map)) {
    throw new Error("Historical Stryker costs must be provided as a Map")
  }
  const activeFiles = [...preflightByFile.entries()]
    .filter(([, entry]) => entry?.mutants?.length > 0)
    .map(([file]) => file)
    .sort()
  const activeFileSet = new Set(activeFiles)
  if (historicalCosts.size !== activeFiles.length) {
    throw new Error("Historical Stryker costs do not cover the complete viable source inventory")
  }
  for (const file of activeFiles) {
    const cost = historicalCosts.get(file)
    if (!Number.isFinite(cost) || cost <= 0) {
      throw new Error(`Historical Stryker cost is invalid for ${file}`)
    }
  }
  for (const [file, cost] of historicalCosts) {
    if (!activeFileSet.has(file) || !Number.isFinite(cost) || cost <= 0) {
      throw new Error("Historical Stryker costs do not match the viable source inventory")
    }
  }
  return historicalCosts
}

const mutationRangePattern = /^(.*?):(\d+)(?::(\d+))?-(\d+)(?::(\d+))?$/u

export function parseMutationPattern(pattern) {
  if (typeof pattern !== "string" || pattern === "" || pattern.startsWith("!")) {
    throw new Error("Stryker mutation pattern is invalid")
  }
  const match = mutationRangePattern.exec(pattern)
  if (!match) {
    return { pattern, sourcePath: canonicalMutationSourcePath(pattern), range: undefined }
  }
  const [, rawSourcePath, rawStartLine, rawStartColumn, rawEndLine, rawEndColumn] = match
  const sourcePath = canonicalMutationSourcePath(rawSourcePath)
  const start = {
    line: Number(rawStartLine) - 1,
    column: rawStartColumn === undefined ? 0 : Number(rawStartColumn),
  }
  const end = {
    line: Number(rawEndLine) - 1,
    column: rawEndColumn === undefined ? Number.MAX_SAFE_INTEGER : Number(rawEndColumn),
  }
  if (
    !Number.isSafeInteger(start.line) ||
    !Number.isSafeInteger(end.line) ||
    !Number.isSafeInteger(start.column) ||
    !Number.isSafeInteger(end.column) ||
    start.line < 0 ||
    end.line < start.line ||
    start.column < 0 ||
    end.column < 0 ||
    (start.line === end.line && end.column < start.column)
  ) {
    throw new Error("Stryker mutation pattern range is invalid")
  }
  const canonical = `${sourcePath}:${start.line + 1}${
    rawStartColumn === undefined ? "" : `:${start.column}`
  }-${end.line + 1}${rawEndColumn === undefined ? "" : `:${end.column}`}`
  if (pattern !== canonical) {
    throw new Error("Stryker mutation pattern is not canonical")
  }
  return { pattern, sourcePath, range: { start, end } }
}

function parseMutantMetadata(mutant, sourcePath) {
  let metadata = mutant
  if (typeof mutant === "string") {
    try {
      metadata = JSON.parse(mutant)
    } catch {
      return undefined
    }
  }
  if (!isRecord(metadata)) return undefined
  // Stryker's runtime report uses `location`, while serialized preflight
  // signatures store the same points as top-level `start`/`end` fields.
  const location = isRecord(metadata.location)
    ? metadata.location
    : { start: metadata.start, end: metadata.end }
  if (!isRecord(location)) return undefined
  // Runtime mutant records omit fileName; the caller's source path is the
  // authoritative key in that case. Serialized signatures must still match it.
  const rawSourcePath = metadata.fileName ?? metadata.sourcePath ?? sourcePath
  let normalizedSourcePath
  try {
    normalizedSourcePath = canonicalMutationSourcePath(rawSourcePath)
  } catch {
    return undefined
  }
  if (normalizedSourcePath !== sourcePath) return undefined
  const { start, end } = location
  if (
    !isRecord(start) ||
    !isRecord(end) ||
    !Number.isInteger(start.line) ||
    !Number.isInteger(start.column) ||
    !Number.isInteger(end.line) ||
    !Number.isInteger(end.column) ||
    start.line < 0 ||
    start.column < 0 ||
    end.line < start.line ||
    (end.line === start.line && end.column < start.column)
  ) {
    return undefined
  }
  return {
    sourcePath: normalizedSourcePath,
    mutatorName: metadata.mutatorName,
    replacement: metadata.replacement,
    start: { line: start.line, column: start.column },
    end: { line: end.line, column: end.column },
  }
}

function mutantLocation(mutant, sourcePath) {
  const metadata = parseMutantMetadata(mutant, sourcePath)
  if (metadata === undefined) return undefined
  return { start: metadata.start, end: metadata.end }
}

export function mutationSignature(mutant, sourcePath) {
  if (typeof mutant !== "string") return mutantSignature(mutant, sourcePath)
  const metadata = parseMutantMetadata(mutant, sourcePath)
  if (
    metadata === undefined ||
    typeof metadata.mutatorName !== "string" ||
    typeof metadata.replacement !== "string"
  ) {
    throw new Error("Stryker mutant signature metadata is invalid")
  }
  return JSON.stringify({
    sourcePath: metadata.sourcePath,
    mutatorName: metadata.mutatorName,
    replacement: metadata.replacement,
    start: metadata.start,
    end: metadata.end,
  })
}

function compareLocation(left, right) {
  return left.line - right.line || left.column - right.column
}

export function mutationPatternCoversMutant(pattern, mutant, sourcePath) {
  const parsed = parseMutationPattern(pattern)
  if (parsed.sourcePath !== sourcePath) return false
  if (parsed.range === undefined) return true
  const location = mutantLocation(mutant, sourcePath)
  return (
    location !== undefined &&
    compareLocation(location.start, parsed.range.start) >= 0 &&
    compareLocation(location.start, parsed.range.end) <= 0
  )
}

function splitMutationUnits({ file, mutants, budget, estimatedCost }) {
  if (mutants.length <= budget) {
    return [{ pattern: file, mutantCount: mutants.length, estimatedCost }]
  }
  const located = mutants
    .map((mutant, index) => ({ mutant, index, location: mutantLocation(mutant, file) }))
    .sort(
      (left, right) =>
        (left.location && right.location
          ? compareLocation(left.location.start, right.location.start) ||
            compareLocation(left.location.end, right.location.end)
          : 0) || left.index - right.index
    )
  if (located.some(({ location }) => location === undefined)) {
    // Artifact consumers from older runs may carry only signatures that do
    // not include locations. Keeping that source whole is safer than guessing
    // a range and silently dropping a mutation from the canonical denominator.
    return [{ pattern: file, mutantCount: mutants.length, estimatedCost }]
  }

  const groups = []
  let current = []
  let currentEnd
  const emit = () => {
    if (current.length === 0) return
    const first = current[0].location
    // Stryker's mutation-range matcher requires the complete AST node to be
    // contained in the range (not merely its start position).  A mutation can
    // therefore extend past the start of a later mutation, for example an
    // enclosing JSX block.  Keep the range endpoint at the furthest mutation
    // end so those spans are not silently omitted by the runner.
    const end = currentEnd
    if (!end) throw new Error(`Stryker mutation range has no endpoint for ${file}`)
    groups.push({
      // Include columns as well as lines.  This makes adjacent ranges
      // disjoint even when a source file contains several mutations on one
      // line, while preserving Stryker's zero-based column semantics.
      pattern: `${file}:${first.start.line + 1}:${first.start.column}-${end.line + 1}:${end.column}`,
      mutantCount: current.length,
      estimatedCost: estimatedCost * (current.length / mutants.length),
    })
    current = []
    currentEnd = undefined
  }
  for (const entry of located) {
    const startsAfterCurrent =
      current.length > 0 &&
      currentEnd !== undefined &&
      compareLocation(entry.location.start, currentEnd) > 0
    if (current.length >= budget && startsAfterCurrent) emit()
    current.push(entry)
    if (currentEnd === undefined || compareLocation(entry.location.end, currentEnd) > 0) {
      currentEnd = entry.location.end
    }
  }
  emit()
  return groups
}

export function normalizeStrykerRuntimeReport(report) {
  if (!isRecord(report) || !isRecord(report.files)) {
    throw new Error("Stryker runtime report is malformed")
  }
  const files = Object.fromEntries(
    Object.entries(report.files).map(([file, fileReport]) => {
      if (!isRecord(fileReport) || !Array.isArray(fileReport.mutants)) {
        throw new Error(`Stryker runtime mutant list is malformed for ${file}`)
      }
      const mutants = fileReport.mutants.map((mutant) => {
        if (!isRecord(mutant) || !isRecord(mutant.location)) {
          throw new Error(`Stryker runtime mutant location is malformed for ${file}`)
        }
        const normalizePoint = (point) => {
          if (
            !isRecord(point) ||
            !Number.isInteger(point.line) ||
            !Number.isInteger(point.column) ||
            point.line < 1 ||
            point.column < 1
          ) {
            throw new Error(`Stryker runtime mutant location is malformed for ${file}`)
          }
          return { line: point.line - 1, column: point.column - 1 }
        }
        const start = normalizePoint(mutant.location.start)
        const end = normalizePoint(mutant.location.end)
        if (compareLocation(end, start) < 0) {
          throw new Error(`Stryker runtime mutant location is malformed for ${file}`)
        }
        return { ...mutant, location: { ...mutant.location, start, end } }
      })
      return [file, { ...fileReport, mutants }]
    })
  )
  return { ...report, files }
}

// A first Stryker attempt has no historical cost model.  A one-file assignment
// can therefore hide a disproportionate number of static mutants (which must
// execute the complete test suite) behind an otherwise balanced mutant count.
// Keep the public logical shard count stable, but create fine-grained source
// ranges before packing those shards so expensive regions are spread across
// multiple runners.  The threshold avoids changing the compact deterministic
// plans used by small local/test inventories; every consumer reconstructs the
// same plan from the exact preflight universe.
const largeMutationUniverseThreshold = 10_000
const firstAttemptUnitSplitFactor = 16
// These weights are the distinct test counts observed in the latest
// provenance-bound Stryker mutation graph for the source ranges that completed
// (run 33618615853).  They are intentionally checked in: a fresh run has no
// historical timing model, but these API modules still fan out to materially
// different related-test graphs.  A weight of one means that the regular
// locality-aware count model remains in effect.
const firstAttemptSourceCostWeights = new Map([
  ["src/api/interceptors/etagCache.ts", 267], // 137 mutants / 267 tests
  ["src/api/hooks/users.ts", 229], // 8 mutants / 229 tests
  ["src/api/hooks/events.ts", 52], // 253 mutants / 52 tests
  ["src/api/hooks/news.ts", 38], // 170 mutants / 38 tests
  ["src/api/hooks/messenger.ts", 131], // 35 mutants / 131 tests
  ["src/api/validation.ts", 46], // 20 mutants / 46 tests
  ["src/api/weather.ts", 41], // 163 mutants / 41 tests
  ["src/api/hooks/schedule.ts", 33], // 23 mutants / 33 tests
])
const firstAttemptCostAwareShardCount = 8

function firstAttemptSourceCostWeight(file) {
  return firstAttemptSourceCostWeights.get(file) ?? 1
}

function assignWeightedMutationUnits(weightedUnits, shards) {
  const orderedUnits = [...weightedUnits].sort(
    (left, right) =>
      right.estimatedCost - left.estimatedCost ||
      right.mutantCount - left.mutantCount ||
      left.pattern.localeCompare(right.pattern)
  )
  let cursor = 0

  // Seed each shard before choosing the lightest target.  This preserves the
  // planner's invariant that every requested logical shard has an assignment
  // whenever there are at least as many units as shards.
  for (const target of shards) {
    const entry = orderedUnits[cursor]
    target.files.push(entry.pattern)
    target.mutantCount += entry.mutantCount
    target.estimatedCost += entry.estimatedCost
    cursor += 1
  }

  for (; cursor < orderedUnits.length; cursor += 1) {
    const entry = orderedUnits[cursor]
    const target = shards.reduce((lightest, shard) => {
      return shard.estimatedCost < lightest.estimatedCost ||
        (shard.estimatedCost === lightest.estimatedCost && shard.id < lightest.id)
        ? shard
        : lightest
    })
    target.files.push(entry.pattern)
    target.mutantCount += entry.mutantCount
    target.estimatedCost += entry.estimatedCost
  }
}

function assignFirstAttemptMutationUnits(weightedUnits, shards) {
  const expensiveUnits = weightedUnits.filter((entry) => entry.costWeight > 1)
  if (expensiveUnits.length === 0) {
    assignLocalityAwareMutationUnits(weightedUnits, shards)
    return
  }

  const regularUnits = weightedUnits.filter((entry) => entry.costWeight === 1)
  if (shards.length === 1) {
    // A single requested shard has no isolation boundary.  Put both classes
    // on that shard rather than dropping the regular units while reserving a
    // nonexistent companion shard.
    assignWeightedMutationUnits(weightedUnits, shards)
    return
  }
  // Keep the expensive API graph in a bounded group of dedicated shards.  The
  // lower bound guarantees that the regular units can still seed every
  // remaining shard when the inventory is small or unusually fragmented.
  const minimumExpensiveShards = Math.max(1, shards.length - regularUnits.length)
  const maximumExpensiveShards = regularUnits.length > 0 ? shards.length - 1 : shards.length
  const expensiveShardCount = Math.min(
    expensiveUnits.length,
    maximumExpensiveShards,
    Math.max(minimumExpensiveShards, Math.min(firstAttemptCostAwareShardCount, shards.length))
  )
  const expensiveShards = shards.slice(0, expensiveShardCount)
  const regularShards = shards.slice(expensiveShardCount)

  assignWeightedMutationUnits(expensiveUnits, expensiveShards)
  assignLocalityAwareMutationUnits(regularUnits, regularShards)
}

function assignLocalityAwareMutationUnits(weightedUnits, shards) {
  const orderedUnits = [...weightedUnits].sort((left, right) =>
    left.pattern.localeCompare(right.pattern)
  )
  let cursor = 0
  let remainingMutants = orderedUnits.reduce((sum, entry) => sum + entry.mutantCount, 0)

  for (let shardIndex = 0; shardIndex < shards.length; shardIndex += 1) {
    const target = shards[shardIndex]
    const remainingShards = shards.length - shardIndex
    const targetMutants = remainingMutants / remainingShards
    const lastAssignableCursor = orderedUnits.length - (remainingShards - 1)

    while (cursor < lastAssignableCursor) {
      const entry = orderedUnits[cursor]
      if (target.files.length > 0) {
        const currentDistance = Math.abs(targetMutants - target.mutantCount)
        const nextDistance = Math.abs(targetMutants - target.mutantCount - entry.mutantCount)
        if (nextDistance > currentDistance) break
      }
      target.files.push(entry.pattern)
      target.mutantCount += entry.mutantCount
      target.estimatedCost += entry.mutantCount
      cursor += 1
    }
    remainingMutants -= target.mutantCount
  }
}

function canonicalizeShardAssignments(shards) {
  return shards.map(({ id, files, mutantCount }) => ({
    id,
    files: [...files].sort(),
    mutantCount,
  }))
}

export function planMutationShards(
  preflightByFile,
  targetMutants = 750,
  requestedShardCount,
  historicalCosts
) {
  if (!(preflightByFile instanceof Map) || !Number.isInteger(targetMutants) || targetMutants < 1) {
    throw new Error("Mutation shard planning inputs are invalid")
  }
  const validatedCosts = validatedHistoricalCosts(preflightByFile, historicalCosts)
  const sourceEntries = [...preflightByFile.entries()]
    .map(([file, entry]) => ({
      file,
      mutantCount: entry?.mutants?.length,
      estimatedCost: validatedCosts?.get(file),
    }))
    .filter(({ mutantCount }) => mutantCount > 0)
    .sort(
      (left, right) =>
        (validatedCosts
          ? right.estimatedCost - left.estimatedCost
          : right.mutantCount - left.mutantCount) ||
        right.mutantCount - left.mutantCount ||
        left.file.localeCompare(right.file)
    )
  if (sourceEntries.length === 0) return []
  const totalMutants = sourceEntries.reduce((sum, entry) => sum + entry.mutantCount, 0)
  if (
    requestedShardCount !== undefined &&
    (!Number.isInteger(requestedShardCount) || requestedShardCount < 1)
  ) {
    throw new Error("Requested mutation shard count is invalid")
  }
  const requestedOrTargetShardCount = requestedShardCount ?? Math.ceil(totalMutants / targetMutants)
  const requestedUnitBudget = requestedShardCount
    ? Math.max(1, Math.ceil(totalMutants / requestedShardCount))
    : targetMutants
  const firstAttempt =
    validatedCosts === undefined && totalMutants >= largeMutationUniverseThreshold
  const unitBudget =
    requestedShardCount !== undefined && totalMutants >= largeMutationUniverseThreshold
      ? Math.max(1, Math.ceil(requestedUnitBudget / firstAttemptUnitSplitFactor))
      : requestedUnitBudget
  const weightedUnits = sourceEntries.flatMap(({ file, mutantCount, estimatedCost }) => {
    const mutants = preflightByFile.get(file)?.mutants ?? []
    const costWeight = firstAttempt ? firstAttemptSourceCostWeight(file) : 1
    const units = splitMutationUnits({
      file,
      mutants,
      budget: unitBudget,
      estimatedCost: estimatedCost ?? mutantCount * costWeight,
    })
    return units.map((unit) => ({ ...unit, costWeight }))
  })
  const shardCount = Math.min(weightedUnits.length, requestedOrTargetShardCount)
  const shards = Array.from({ length: shardCount }, (_, index) => ({
    id: `shard-${String(index).padStart(3, "0")}`,
    files: [],
    mutantCount: 0,
    estimatedCost: 0,
  }))
  if (firstAttempt) {
    // Related-mode test discovery is the dominant first-attempt cost for
    // static mutants. Keeping adjacent source ranges together avoids turning
    // every regular logical shard into a union of unrelated feature test
    // graphs.  Checked-in API graph weights are isolated first so the most
    // expensive related-test regions cannot monopolize a count-balanced shard.
    assignFirstAttemptMutationUnits(weightedUnits, shards)
    return canonicalizeShardAssignments(shards)
  }
  weightedUnits.sort(
    (left, right) =>
      (validatedCosts
        ? right.estimatedCost - left.estimatedCost
        : right.mutantCount - left.mutantCount) ||
      right.mutantCount - left.mutantCount ||
      left.pattern.localeCompare(right.pattern)
  )
  for (const entry of weightedUnits) {
    const target = shards.reduce((lightest, shard) => {
      const useCost = validatedCosts !== undefined
      const candidateWeight = useCost ? shard.estimatedCost : shard.mutantCount
      const lightestWeight = useCost ? lightest.estimatedCost : lightest.mutantCount
      return candidateWeight < lightestWeight ||
        (candidateWeight === lightestWeight && shard.id < lightest.id)
        ? shard
        : lightest
    })
    target.files.push(entry.pattern)
    target.mutantCount += entry.mutantCount
    target.estimatedCost += validatedCosts ? entry.estimatedCost : entry.mutantCount
  }
  return canonicalizeShardAssignments(shards)
}

function assertShardReportConfig(report, files, id) {
  if (report?.schemaVersion !== "1.0" || !report.files || typeof report.files !== "object") {
    throw new Error(`Stryker ${id} report is missing or malformed`)
  }
  if (
    JSON.stringify(report.config?.mutate) !== JSON.stringify(files) ||
    report.config?.coverageAnalysis !== "perTest" ||
    report.config?.incremental !== false ||
    JSON.stringify(report.config?.mutator) !==
      JSON.stringify({ plugins: null, excludedMutations: [] }) ||
    JSON.stringify(report.config?.ignorers) !== JSON.stringify([])
  ) {
    throw new Error(`Stryker ${id} effective configuration differs from its assignment`)
  }
}

function expectedMutantsForPattern(pattern, preflightByFile) {
  const parsed = parseMutationPattern(pattern)
  const entry = preflightByFile?.get(parsed.sourcePath)
  if (!entry || !Array.isArray(entry.mutants)) {
    throw new Error(`Stryker preflight is missing an assignment for ${parsed.sourcePath}`)
  }
  return entry.mutants.filter((mutant) =>
    mutationPatternCoversMutant(pattern, mutant, parsed.sourcePath)
  )
}

export function mergeShardReports({ shards, expectedPatterns, preflightByFile, sourceByFile }) {
  if (!Array.isArray(shards) || shards.length === 0 || !Array.isArray(expectedPatterns)) {
    throw new Error("Stryker shard aggregation inputs are invalid")
  }
  const mergedFiles = {}
  const assignedMutantSignatures = new Set()
  for (const { id, files, report } of shards) {
    assertShardReportConfig(report, files, id)
    if (!Array.isArray(files) || files.length === 0) {
      throw new Error(`Stryker ${id} has no mutation assignment`)
    }
    const parsedAssignments = files.map((pattern) => parseMutationPattern(pattern))
    const assignedPatterns = new Set()
    const expectedByPattern = new Map()
    for (const assignment of parsedAssignments) {
      if (assignedPatterns.has(assignment.pattern)) {
        throw new Error(`Stryker ${id} contains a duplicate mutation assignment`)
      }
      assignedPatterns.add(assignment.pattern)
      if (preflightByFile) {
        const expected = expectedMutantsForPattern(assignment.pattern, preflightByFile)
        if (expected.length === 0) {
          throw new Error(`Stryker ${id} assigned an empty mutation range`)
        }
        const expectedSignatures = new Set(
          expected.map((mutant) => mutationSignature(mutant, assignment.sourcePath))
        )
        for (const signature of expectedSignatures) {
          if (assignedMutantSignatures.has(signature)) {
            throw new Error(`Stryker mutation assigned to multiple shards: ${signature}`)
          }
        }
        expectedByPattern.set(assignment.pattern, expectedSignatures)
      }
    }
    for (const [file, fileReport] of Object.entries(report.files)) {
      const normalizedFile = normalizePath(file)
      const matchingAssignments = parsedAssignments.filter(
        (assignment) =>
          assignment.sourcePath === normalizedFile &&
          (preflightByFile
            ? expectedByPattern.get(assignment.pattern)?.size > 0
            : mutationPatternCoversMutant(
                assignment.pattern,
                fileReport?.mutants?.[0],
                normalizedFile
              ))
      )
      if (matchingAssignments.length === 0) {
        throw new Error(`Stryker ${id} reported an unassigned source file: ${file}`)
      }
      if (!Array.isArray(fileReport?.mutants)) {
        throw new Error(`Stryker ${id} mutant list is malformed for ${file}`)
      }
      if (sourceByFile) {
        const source = sourceByFile.get(normalizedFile)
        if (typeof source !== "string" || fileReport.source !== source) {
          throw new Error(`Stryker ${id} source snapshot is stale for ${normalizedFile}`)
        }
      }
      const normalizedReport = mergedFiles[normalizedFile] ?? {
        ...fileReport,
        mutants: [],
      }
      if (normalizedReport.source !== fileReport.source) {
        throw new Error(`Stryker shard reports disagree on source snapshot at ${normalizedFile}`)
      }
      for (const mutant of fileReport.mutants) {
        const matchingMutantAssignments = parsedAssignments.filter((assignment) =>
          mutationPatternCoversMutant(assignment.pattern, mutant, normalizedFile)
        )
        if (matchingMutantAssignments.length !== 1) {
          throw new Error(
            `Stryker ${id} mutant does not belong to its assigned mutation range: ${normalizedFile}`
          )
        }
        const signature = mutationSignature(mutant, normalizedFile)
        if (assignedMutantSignatures.has(signature)) {
          throw new Error(`Stryker shard reports duplicate mutant ${signature}`)
        }
        const expected = expectedByPattern.get(matchingMutantAssignments[0].pattern)
        if (expected && !expected.has(signature)) {
          throw new Error(`Stryker ${id} reported a mutant outside the preflight assignment`)
        }
        assignedMutantSignatures.add(signature)
        normalizedReport.mutants.push({ ...mutant, id: `${id}:${mutant.id}` })
      }
      mergedFiles[normalizedFile] = normalizedReport
    }
    if (preflightByFile) {
      for (const [pattern, expected] of expectedByPattern) {
        const actual = []
        const parsed = parseMutationPattern(pattern)
        for (const [rawFile, fileReport] of Object.entries(report.files)) {
          if (normalizePath(rawFile) !== parsed.sourcePath) continue
          for (const mutant of fileReport.mutants ?? []) {
            if (mutationPatternCoversMutant(pattern, mutant, parsed.sourcePath)) {
              actual.push(mutantSignature(mutant, parsed.sourcePath))
            }
          }
        }
        if (actual.length !== expected.size || new Set(actual).size !== expected.size) {
          throw new Error(`Stryker ${id} report is incomplete for ${pattern}`)
        }
      }
    }
  }
  return {
    schemaVersion: "1.0",
    config: {
      mutate: expectedPatterns,
      coverageAnalysis: "perTest",
      incremental: false,
      mutator: { plugins: null, excludedMutations: [] },
      ignorers: [],
    },
    files: mergedFiles,
  }
}

function normalizeEvidenceCommitSha(value, fallback, description) {
  const resolved = value ?? fallback
  if (typeof resolved !== "string" || !/^[a-f0-9]{40,64}$/u.test(resolved)) {
    throw new Error(`${description} must be a full Git SHA`)
  }
  return resolved
}

function normalizeEvidenceBaseRef(value) {
  if (value === undefined || value === null) return null
  if (typeof value !== "string" || value === "" || /[\0\r\n]/u.test(value)) {
    throw new Error("Evidence base ref must be a non-empty branch or tag name")
  }
  return value
}

export function buildWorkflowEvidenceIdentity(testedCommitSha, env = process.env) {
  const testedSha = normalizeEvidenceCommitSha(testedCommitSha, undefined, "Evidence tested commit")
  return {
    sourceHeadSha: normalizeEvidenceCommitSha(
      env.STRYKER_SOURCE_HEAD_SHA,
      testedSha,
      "Evidence source head"
    ),
    baseSha: normalizeEvidenceCommitSha(env.STRYKER_BASE_SHA, testedSha, "Evidence base commit"),
    baseRef: normalizeEvidenceBaseRef(
      env.STRYKER_BASE_REF || env.GITHUB_BASE_REF || env.GITHUB_REF_NAME
    ),
  }
}

export function buildEvidenceIdentity({
  headSha,
  sourceHeadSha,
  baseSha,
  baseRef,
  dirtyPaths,
  inputHashes,
}) {
  const testedCommitSha = normalizeEvidenceCommitSha(headSha, undefined, "Evidence tested commit")
  const sourceCommitSha = normalizeEvidenceCommitSha(
    sourceHeadSha,
    testedCommitSha,
    "Evidence source head"
  )
  const baseCommitSha = normalizeEvidenceCommitSha(baseSha, testedCommitSha, "Evidence base commit")
  const normalizedBaseRef = normalizeEvidenceBaseRef(baseRef)
  if (!Array.isArray(dirtyPaths) || dirtyPaths.some((entry) => typeof entry !== "string")) {
    throw new Error("Evidence dirty paths must be an array of strings")
  }
  if (!inputHashes || typeof inputHashes !== "object" || Array.isArray(inputHashes)) {
    throw new Error("Evidence input hashes must be an object")
  }
  const normalizedHashes = sortedObject(inputHashes)
  const evidenceDigest = sha256(
    JSON.stringify({
      baseRef: normalizedBaseRef,
      baseSha: baseCommitSha,
      headSha: testedCommitSha,
      inputHashes: normalizedHashes,
      sourceHeadSha: sourceCommitSha,
    })
  )
  const repositoryDirty = dirtyPaths.length > 0
  return {
    headSha: testedCommitSha,
    sourceHeadSha: sourceCommitSha,
    baseSha: baseCommitSha,
    baseRef: normalizedBaseRef,
    evidenceDigest,
    repositoryDirty,
    dirtyPaths: [...dirtyPaths].sort(),
    inputHashes: normalizedHashes,
    revision: repositoryDirty
      ? `${testedCommitSha}-dirty.${evidenceDigest.slice(0, 12)}`
      : testedCommitSha,
  }
}

export function assertEvidenceUnchanged(expected, actual) {
  if (
    expected.headSha !== actual.headSha ||
    expected.sourceHeadSha !== actual.sourceHeadSha ||
    expected.baseSha !== actual.baseSha ||
    expected.baseRef !== actual.baseRef ||
    expected.evidenceDigest !== actual.evidenceDigest ||
    expected.repositoryDirty !== actual.repositoryDirty ||
    JSON.stringify(expected.dirtyPaths) !== JSON.stringify(actual.dirtyPaths)
  ) {
    throw new Error("Frontend mutation evidence changed while Stryker was running")
  }
}

export function isReleaseEligible(identity, env = process.env) {
  return (
    identity?.repositoryDirty === false &&
    typeof env.GITHUB_RUN_ID === "string" &&
    env.GITHUB_RUN_ID !== "" &&
    typeof env.GITHUB_RUN_ATTEMPT === "string" &&
    env.GITHUB_RUN_ATTEMPT !== "" &&
    env.GITHUB_SHA === identity.headSha
  )
}

export async function cleanupCanonicalArtifacts(root = outputRoot) {
  await Promise.all(
    [
      "mutation.json",
      "mutation.html",
      "inventory.json",
      "preflight.json",
      "VALIDATED.json",
      "LOCAL_VALIDATION.json",
    ].map((name) => rm(path.join(root, name), { force: true }))
  )
  await rm(path.join(root, "runs"), { recursive: true, force: true })
  await rm(path.join(root, "shards"), { recursive: true, force: true })
  await rm(path.join(root, "historical-costs"), { recursive: true, force: true })
}

export async function acquireRunLock(lockPath, runId) {
  await mkdir(path.dirname(lockPath), { recursive: true })
  let handle
  try {
    handle = await open(lockPath, "wx")
  } catch (error) {
    if (error && typeof error === "object" && error.code === "EEXIST") {
      throw new Error(`Another Stryker evidence run is already active (${lockPath})`)
    }
    throw error
  }
  const payload = `${JSON.stringify({ runId, pid: process.pid, startedAt: new Date().toISOString() })}\n`
  await handle.writeFile(payload, "utf8")
  await handle.close()
  let released = false
  return {
    async release() {
      if (released) return
      const current = JSON.parse(await readFile(lockPath, "utf8"))
      if (current.runId !== runId) {
        throw new Error("Refusing to release a Stryker lock owned by another run")
      }
      await rm(lockPath)
      released = true
    },
  }
}

async function atomicJson(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true })
  const temporary = `${filePath}.${randomUUID()}.tmp`
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8")
  await rename(temporary, filePath)
}

async function atomicText(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true })
  const temporary = `${filePath}.${randomUUID()}.tmp`
  await writeFile(temporary, value, "utf8")
  await rename(temporary, filePath)
}

export async function writeValidatedEvidence({
  outputRoot: targetRoot = outputRoot,
  inventory,
  preflight,
}) {
  if (inventory?.summary?.viableMutantScore !== 100) {
    throw new Error("Validated evidence requires a 100% viable mutation score")
  }
  if (preflight?.runId !== inventory?.runId) {
    throw new Error("Preflight and inventory must belong to the same Stryker run")
  }
  const inventoryPath = path.join(targetRoot, "inventory.json")
  const preflightPath = path.join(targetRoot, "preflight.json")
  const inventoryText = `${JSON.stringify(inventory, null, 2)}\n`
  const preflightText = `${JSON.stringify(preflight, null, 2)}\n`
  await mkdir(targetRoot, { recursive: true })
  const temporaryInventory = `${inventoryPath}.${randomUUID()}.tmp`
  const temporaryPreflight = `${preflightPath}.${randomUUID()}.tmp`
  await Promise.all([
    writeFile(temporaryInventory, inventoryText, "utf8"),
    writeFile(temporaryPreflight, preflightText, "utf8"),
  ])
  await Promise.all([
    rename(temporaryInventory, inventoryPath),
    rename(temporaryPreflight, preflightPath),
  ])
  const releaseEligible = inventory.releaseEligible === true
  const marker = {
    schemaVersion: "1.0",
    runId: inventory.runId,
    revision: inventory.revision,
    inventory: normalizePath(path.relative(repositoryRoot, inventoryPath)),
    inventorySha256: sha256(inventoryText),
    preflight: normalizePath(path.relative(repositoryRoot, preflightPath)),
    preflightSha256: sha256(preflightText),
    releaseEligible,
    validatedAt: new Date().toISOString(),
  }
  // The marker is intentionally last: its existence means the inventory was
  // atomically persisted after every report and TOCTOU check succeeded.
  const markerName = releaseEligible ? "VALIDATED.json" : "LOCAL_VALIDATION.json"
  await rm(path.join(targetRoot, releaseEligible ? "LOCAL_VALIDATION.json" : "VALIDATED.json"), {
    force: true,
  })
  await atomicJson(path.join(targetRoot, markerName), marker)
  return marker
}

export function indexShardProducerEvidence(shardResults, root = repositoryRoot) {
  if (!Array.isArray(shardResults) || shardResults.length === 0) {
    throw new Error("Mutation shard producer evidence is missing")
  }
  return shardResults.map((shard) => {
    if (
      typeof shard?.id !== "string" ||
      typeof shard.shardEvidencePath !== "string" ||
      typeof shard.shardEvidenceText !== "string" ||
      !shard.shardEvidence ||
      shard.shardEvidence.shardId !== shard.id ||
      shard.shardEvidence.schemaVersion !== "1.0" ||
      typeof shard.shardEvidence.revision !== "string" ||
      typeof shard.shardEvidence.sourceHeadSha !== "string" ||
      typeof shard.shardEvidence.baseSha !== "string" ||
      (shard.shardEvidence.baseRef !== null && typeof shard.shardEvidence.baseRef !== "string") ||
      !/^[a-f0-9]{64}$/u.test(shard.shardEvidence.evidenceDigest) ||
      typeof shard.shardEvidence.workflowRunId !== "string" ||
      shard.shardEvidence.workflowRunId === "" ||
      parseWorkflowRunAttempt(shard.shardEvidence.workflowRunAttempt) === undefined ||
      !/^[a-f0-9]{64}$/u.test(shard.shardEvidence.reportSha256) ||
      JSON.stringify(JSON.parse(shard.shardEvidenceText)) !== JSON.stringify(shard.shardEvidence)
    ) {
      throw new Error(`Mutation shard producer evidence is malformed: ${shard?.id ?? "unknown"}`)
    }
    const relativePath = normalizePath(path.relative(root, shard.shardEvidencePath))
    if (relativePath.startsWith("../") || path.isAbsolute(relativePath)) {
      throw new Error(`Mutation shard producer evidence escapes the repository: ${relativePath}`)
    }
    return {
      shardId: shard.id,
      path: relativePath,
      sha256: sha256(shard.shardEvidenceText),
      schemaVersion: shard.shardEvidence.schemaVersion,
      revision: shard.shardEvidence.revision,
      sourceHeadSha: shard.shardEvidence.sourceHeadSha,
      baseSha: shard.shardEvidence.baseSha,
      baseRef: shard.shardEvidence.baseRef,
      evidenceDigest: shard.shardEvidence.evidenceDigest,
      workflowRunId: shard.shardEvidence.workflowRunId,
      workflowRunAttempt: shard.shardEvidence.workflowRunAttempt,
      reportSha256: shard.shardEvidence.reportSha256,
    }
  })
}

function parseWorkflowRunAttempt(value) {
  if (typeof value !== "string" || !/^[1-9]\d*$/u.test(value)) return undefined
  const attempt = Number(value)
  return Number.isSafeInteger(attempt) ? attempt : undefined
}

function boundedEnvironmentInteger(name, fallback, minimum, maximum) {
  const raw = process.env[name]
  const value = raw === undefined ? fallback : Number(raw)
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`)
  }
  return value
}

async function terminateChildTree(child) {
  if (child.exitCode !== null || child.signalCode !== null) return
  if (process.platform === "win32") {
    try {
      await execFileAsync("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        windowsHide: true,
      })
      return
    } catch {
      // Fall through to the direct child kill if taskkill is unavailable.
    }
  }
  child.kill("SIGKILL")
}

async function runNode(args, description, env, timeoutMs) {
  await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, {
      cwd: frontendRoot,
      env,
      stdio: "inherit",
      shell: false,
    })
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      void terminateChildTree(child)
    }, timeoutMs)
    child.on("error", (error) => {
      clearTimeout(timer)
      reject(error)
    })
    child.on("exit", (code, signal) => {
      clearTimeout(timer)
      if (timedOut) reject(new Error(`${description} exceeded ${timeoutMs}ms`))
      else if (signal) reject(new Error(`${description} exited due to signal ${signal}`))
      else if (code === 0) resolve()
      else reject(new Error(`${description} exited with code ${code}`))
    })
  })
}

async function git(args) {
  const { stdout } = await execFileAsync("git", args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  })
  return stdout.trim()
}

async function captureEvidence(sourceFiles) {
  const [headSha, status, listedFiles] = await Promise.all([
    git(["rev-parse", "HEAD"]),
    git(["status", "--porcelain=v1", "--untracked-files=all"]),
    git([
      "ls-files",
      "-co",
      "--exclude-standard",
      "--",
      "frontend",
      "quality/coverage-source-policy.json",
    ]),
  ])
  const evidenceFiles = listedFiles
    .split(/\r?\n/u)
    .filter(Boolean)
    .map(normalizePath)
    .filter(
      (file) =>
        !/^frontend\/(node_modules|dist|coverage|reports|\.screenshots|\.stryker-tmp)\//u.test(file)
    )
    .sort()
  const duplicateCheck = new Set(evidenceFiles.map((file) => file.toLocaleLowerCase("en-US")))
  if (duplicateCheck.size !== evidenceFiles.length) {
    throw new Error("Frontend evidence contains path aliases")
  }
  const bytesByFile = new Map(
    await Promise.all(
      evidenceFiles.map(async (file) => [file, await readFile(path.join(repositoryRoot, file))])
    )
  )
  const hashes = Object.fromEntries(
    evidenceFiles.map((file) => [file, sha256(bytesByFile.get(file))])
  )
  const workflowIdentity = buildWorkflowEvidenceIdentity(headSha)
  const identity = buildEvidenceIdentity({
    headSha,
    ...workflowIdentity,
    dirtyPaths: status === "" ? [] : status.split(/\r?\n/u),
    inputHashes: hashes,
  })
  const sourceByFile = new Map(
    sourceFiles.map((file) => {
      const bytes = bytesByFile.get(`frontend/${file}`)
      if (!bytes) throw new Error(`Mutation source is absent from the immutable snapshot: ${file}`)
      return [file, bytes.toString("utf8")]
    })
  )
  return { identity, sourceByFile }
}

async function readPackageVersion(relativePath) {
  return JSON.parse(await readFile(path.join(frontendRoot, relativePath), "utf8")).version
}

async function readToolchain() {
  const [stryker, instrumenter, vitest] = await Promise.all([
    readPackageVersion("node_modules/@stryker-mutator/core/package.json"),
    readPackageVersion("node_modules/@stryker-mutator/instrumenter/package.json"),
    readPackageVersion("node_modules/vitest/package.json"),
  ])
  return {
    node: process.version,
    platform: process.platform,
    arch: process.arch,
    stryker,
    instrumenter,
    vitest,
  }
}

function requireWorkflowProvenance(sourceRevision, env = process.env) {
  const runId = env.GITHUB_RUN_ID
  const runAttempt = env.GITHUB_RUN_ATTEMPT
  const sha = env.GITHUB_SHA
  const workflowIdentity =
    typeof sha === "string" ? buildWorkflowEvidenceIdentity(sha, env) : undefined
  if (
    typeof runId !== "string" ||
    !/^[1-9]\d*$/u.test(runId) ||
    parseWorkflowRunAttempt(runAttempt) === undefined ||
    typeof sha !== "string" ||
    sha !== sourceRevision.headSha ||
    workflowIdentity?.sourceHeadSha !== sourceRevision.sourceHeadSha ||
    workflowIdentity?.baseSha !== sourceRevision.baseSha ||
    workflowIdentity?.baseRef !== sourceRevision.baseRef ||
    sourceRevision.repositoryDirty !== false
  ) {
    throw new Error(
      "Preflight artifact requires a clean workflow run bound to the checked-out exact Git SHA"
    )
  }
  return {
    runId,
    runAttempt,
    sha,
    sourceHeadSha: workflowIdentity.sourceHeadSha,
    baseSha: workflowIdentity.baseSha,
    baseRef: workflowIdentity.baseRef,
  }
}

function preflightArtifactMetadata({
  sourceRevision,
  workflow,
  toolchain,
  shardTargetMutants,
  shardCount,
}) {
  const sourcePolicySha256 = sourceRevision.inputHashes["quality/coverage-source-policy.json"]
  const configSha256 = sourceRevision.inputHashes["frontend/stryker.config.mjs"]
  assertSha256(sourcePolicySha256, "Canonical source policy digest")
  assertSha256(configSha256, "Canonical Stryker configuration digest")
  return {
    sourceRevision,
    workflow,
    toolchain,
    sourcePolicy: {
      path: "quality/coverage-source-policy.json",
      sha256: sourcePolicySha256,
    },
    config: {
      path: "frontend/stryker.config.mjs",
      sha256: configSha256,
      instrumenterOptions,
    },
    shardTargetMutants,
    shardCount,
  }
}

function preflightArtifactExecution(env = process.env) {
  const mode = env.STRYKER_PREFLIGHT_MODE ?? "execute"
  if (!["execute", "generate", "validate"].includes(mode)) {
    throw new Error("STRYKER_PREFLIGHT_MODE must be execute, generate, or validate")
  }
  const rawArtifact = env.STRYKER_PREFLIGHT_ARTIFACT
  if (rawArtifact !== undefined && rawArtifact !== "required") {
    throw new Error("STRYKER_PREFLIGHT_ARTIFACT must be the literal value required")
  }
  if (mode === "generate" && rawArtifact !== undefined) {
    throw new Error("Stryker preflight generation cannot consume a preflight artifact")
  }
  if (mode === "validate" && rawArtifact !== "required") {
    throw new Error("Stryker preflight validation requires an immutable artifact")
  }
  return { mode, artifactRequired: rawArtifact === "required" }
}

function preflightCandidateAttemptFromDirectory(directoryName, workflow) {
  if (
    !isRecord(workflow) ||
    typeof workflow.runId !== "string" ||
    !/^[1-9]\d*$/u.test(workflow.runId) ||
    parseWorkflowRunAttempt(workflow.runAttempt) === undefined ||
    typeof workflow.sha !== "string" ||
    !/^[a-f0-9]{40,64}$/u.test(workflow.sha)
  ) {
    throw new Error("Consumer Stryker workflow provenance is invalid")
  }
  const prefix = `frontend-mutation-preflight-${workflow.runId}-`
  const suffix = `-${workflow.sha}`
  if (!directoryName.startsWith(prefix) || !directoryName.endsWith(suffix)) {
    throw new Error(`Preflight candidate directory is not canonical: ${directoryName}`)
  }
  const attemptText = directoryName.slice(prefix.length, directoryName.length - suffix.length)
  const attempt = parseWorkflowRunAttempt(attemptText)
  if (attempt === undefined || attemptText !== String(attempt)) {
    throw new Error(`Preflight candidate directory is not canonical: ${directoryName}`)
  }
  return { attempt, attemptText }
}

async function readCanonicalPreflightCandidates({ candidateRoot, workflow }) {
  let rootStats
  let rootEntries
  try {
    rootStats = await lstat(candidateRoot)
    rootEntries = await readdir(candidateRoot, { withFileTypes: true })
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      throw new Error("Required immutable Stryker preflight candidate root is missing")
    }
    throw error
  }
  if (!rootStats.isDirectory() || rootStats.isSymbolicLink() || rootEntries.length === 0) {
    throw new Error("Required immutable Stryker preflight candidate root is malformed")
  }
  const candidates = []
  for (const entry of rootEntries.sort((left, right) => left.name.localeCompare(right.name))) {
    const candidatePath = path.join(candidateRoot, entry.name)
    if (!entry.isDirectory() || entry.isSymbolicLink()) {
      throw new Error(`Preflight candidate root contains an unexpected entry: ${entry.name}`)
    }
    const candidateStats = await lstat(candidatePath)
    if (!candidateStats.isDirectory() || candidateStats.isSymbolicLink()) {
      throw new Error(`Preflight candidate root contains an unexpected entry: ${entry.name}`)
    }
    const directoryAttempt = preflightCandidateAttemptFromDirectory(entry.name, workflow)
    const files = await readdir(candidatePath, { withFileTypes: true })
    if (
      files.length !== 1 ||
      files[0].name !== "PREFLIGHT_ARTIFACT.json" ||
      !files[0].isFile() ||
      files[0].isSymbolicLink()
    ) {
      throw new Error(`Preflight candidate directory has unexpected contents: ${entry.name}`)
    }
    const artifactPath = path.join(candidatePath, files[0].name)
    const artifactStats = await lstat(artifactPath)
    if (!artifactStats.isFile() || artifactStats.isSymbolicLink()) {
      throw new Error(`Preflight candidate directory has unexpected contents: ${entry.name}`)
    }
    candidates.push({
      artifactPath,
      artifactText: await readFile(artifactPath, "utf8"),
      directoryAttempt,
    })
  }
  return candidates
}

function serializePreflight(preflightByFile) {
  if (!(preflightByFile instanceof Map)) {
    throw new Error("Instrumenter preflight must be provided as a Map")
  }
  return Object.fromEntries(
    [...preflightByFile.entries()]
      .map(([file, entry]) => [canonicalMutationSourcePath(file), entry])
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([file, entry]) => {
        if (!isRecord(entry) || !Array.isArray(entry.mutants)) {
          throw new Error(`Instrumenter preflight is malformed for ${file}`)
        }
        assertSha256(entry.sourceSha256, `Instrumenter preflight source digest for ${file}`)
        return [
          file,
          {
            sourceSha256: entry.sourceSha256,
            mutantSignatures: entry.mutants.map((mutant) => mutantSignature(mutant, file)).sort(),
          },
        ]
      })
  )
}

function preflightDigest(serializedPreflight) {
  return sha256(JSON.stringify(serializedPreflight))
}

function historicalCostModelCosts({ model, sourceRevision, config, serializedPreflight }) {
  assertExactObjectKeys(
    model,
    ["schemaVersion", "sourceRevision", "config", "preflightDigest", "costs"],
    "Historical Stryker cost model"
  )
  if (model.schemaVersion !== historicalCostArtifactSchemaVersion) {
    throw new Error("Historical Stryker cost model schema version is unsupported")
  }
  if (JSON.stringify(model.sourceRevision) !== JSON.stringify(sourceRevision)) {
    throw new Error("Historical Stryker cost model source revision does not match this execution")
  }
  if (JSON.stringify(model.config) !== JSON.stringify(config)) {
    throw new Error("Historical Stryker cost model configuration does not match this execution")
  }
  assertSha256(model.preflightDigest, "Historical Stryker cost model preflight digest")
  if (model.preflightDigest !== preflightDigest(serializedPreflight)) {
    throw new Error("Historical Stryker cost model preflight digest does not match this execution")
  }
  if (!Array.isArray(model.costs)) {
    throw new Error("Historical Stryker cost model costs must be an array")
  }
  const expectedByFile = new Map(
    Object.entries(serializedPreflight)
      .filter(([, entry]) => entry.mutantSignatures.length > 0)
      .map(([file, entry]) => [file, entry])
  )
  const costs = new Map()
  let previousFile
  for (const entry of model.costs) {
    assertExactObjectKeys(
      entry,
      ["file", "sourceSha256", "mutantCount", "estimatedDurationMs"],
      "Historical Stryker file cost"
    )
    const file = canonicalMutationSourcePath(entry.file)
    if (
      file !== entry.file ||
      (previousFile !== undefined && previousFile.localeCompare(file) >= 0)
    ) {
      throw new Error("Historical Stryker cost model paths must be canonical, sorted, and unique")
    }
    previousFile = file
    const expected = expectedByFile.get(file)
    if (!expected) {
      throw new Error(`Historical Stryker cost model has an unknown or zero-mutant source: ${file}`)
    }
    if (
      entry.sourceSha256 !== expected.sourceSha256 ||
      entry.mutantCount !== expected.mutantSignatures.length
    ) {
      throw new Error(`Historical Stryker cost model source snapshot is stale for ${file}`)
    }
    if (
      !Number.isFinite(entry.estimatedDurationMs) ||
      entry.estimatedDurationMs <= 0 ||
      entry.estimatedDurationMs > maximumHistoricalCostMs
    ) {
      throw new Error(`Historical Stryker cost is invalid for ${file}`)
    }
    costs.set(file, entry.estimatedDurationMs)
  }
  if (costs.size !== expectedByFile.size) {
    throw new Error(
      "Historical Stryker cost model does not cover the complete viable source inventory"
    )
  }
  return costs
}

export function buildHistoricalCostArtifact({ sourceRevision, config, preflightByFile, costs }) {
  if (!(preflightByFile instanceof Map)) {
    throw new Error("Historical Stryker cost artifact requires an instrumenter preflight Map")
  }
  const validatedCosts = validatedHistoricalCosts(preflightByFile, costs)
  if (!validatedCosts) {
    throw new Error("Historical Stryker cost artifact requires complete file costs")
  }
  const serializedPreflight = serializePreflight(preflightByFile)
  const payload = {
    schemaVersion: historicalCostArtifactSchemaVersion,
    sourceRevision,
    config,
    preflightDigest: preflightDigest(serializedPreflight),
    costs: [...validatedCosts.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([file, estimatedDurationMs]) => ({
        file,
        sourceSha256: serializedPreflight[file].sourceSha256,
        mutantCount: serializedPreflight[file].mutantSignatures.length,
        estimatedDurationMs,
      })),
  }
  historicalCostModelCosts({
    model: payload,
    sourceRevision,
    config,
    serializedPreflight,
  })
  return {
    schemaVersion: historicalCostArtifactSchemaVersion,
    payload,
    payloadSha256: sha256(jsonText(payload)),
  }
}

export function buildHistoricalCostArtifactFromShardTimings({
  sourceRevision,
  config,
  preflightByFile,
  shardResults,
}) {
  if (
    !(preflightByFile instanceof Map) ||
    !Array.isArray(shardResults) ||
    shardResults.length === 0
  ) {
    throw new Error("Historical Stryker cost artifact requires complete shard timing results")
  }
  const costs = new Map()
  const assignedMutantSignatures = new Set()
  for (const shard of shardResults) {
    const files = shard?.files
    const durationMs = shard?.durationMs ?? shard?.shardEvidence?.durationMs
    if (
      !Array.isArray(files) ||
      JSON.stringify(files) !== JSON.stringify([...new Set(files)].sort()) ||
      !Number.isSafeInteger(shard?.mutantCount) ||
      shard.mutantCount < 1 ||
      !Number.isFinite(durationMs) ||
      durationMs <= 0 ||
      durationMs > maximumHistoricalCostMs
    ) {
      throw new Error("Historical Stryker shard timing is malformed")
    }
    const assignments = files.map((pattern) => parseMutationPattern(pattern))
    let assignedMutants = 0
    for (const assignment of assignments) {
      const expected = expectedMutantsForPattern(assignment.pattern, preflightByFile)
      if (expected.length === 0) {
        throw new Error("Historical Stryker shard timings do not match the viable source inventory")
      }
      const signatures = expected.map((mutant) => mutationSignature(mutant, assignment.sourcePath))
      if (signatures.some((signature) => assignedMutantSignatures.has(signature))) {
        throw new Error(
          "Historical Stryker shard timings do not match the viable source inventory: mutant assigned more than once"
        )
      }
      signatures.forEach((signature) => assignedMutantSignatures.add(signature))
      assignedMutants += expected.length
      costs.set(
        assignment.sourcePath,
        (costs.get(assignment.sourcePath) ?? 0) + (durationMs * expected.length) / shard.mutantCount
      )
    }
    if (assignedMutants !== shard.mutantCount) {
      throw new Error("Historical Stryker shard timing mutant count is stale")
    }
  }
  const expectedMutantCount = [...preflightByFile.values()].reduce(
    (sum, entry) => sum + (Array.isArray(entry?.mutants) ? entry.mutants.length : 0),
    0
  )
  if (assignedMutantSignatures.size !== expectedMutantCount) {
    throw new Error("Historical Stryker shard timings do not cover the viable source inventory")
  }
  return buildHistoricalCostArtifact({ sourceRevision, config, preflightByFile, costs })
}

export function parseHistoricalCostArtifact({
  artifactText,
  sourceRevision,
  config,
  preflightByFile,
}) {
  if (typeof artifactText !== "string") {
    throw new Error("Historical Stryker cost artifact is missing")
  }
  let artifact
  try {
    artifact = JSON.parse(artifactText)
  } catch {
    throw new Error("Historical Stryker cost artifact contains invalid JSON")
  }
  if (artifactText !== jsonText(artifact)) {
    throw new Error("Historical Stryker cost artifact JSON is not canonical")
  }
  assertExactObjectKeys(
    artifact,
    ["schemaVersion", "payload", "payloadSha256"],
    "Historical Stryker cost artifact"
  )
  if (artifact.schemaVersion !== historicalCostArtifactSchemaVersion) {
    throw new Error("Historical Stryker cost artifact schema version is unsupported")
  }
  assertSha256(artifact.payloadSha256, "Historical Stryker cost artifact payload digest")
  if (artifact.payloadSha256 !== sha256(jsonText(artifact.payload))) {
    throw new Error("Historical Stryker cost artifact payload digest does not match its content")
  }
  if (!(preflightByFile instanceof Map)) {
    throw new Error("Historical Stryker cost artifact requires an instrumenter preflight Map")
  }
  return historicalCostModelCosts({
    model: artifact.payload,
    sourceRevision,
    config,
    serializedPreflight: serializePreflight(preflightByFile),
  })
}

function historicalCostArtifactRelativePath(env) {
  const raw = env.STRYKER_HISTORICAL_COSTS_ARTIFACT
  if (raw === undefined) return undefined
  let relativePath
  try {
    relativePath = canonicalMutationSourcePath(raw)
    assertPortableArtifactRelativePath(relativePath)
  } catch {
    throw new Error("STRYKER_HISTORICAL_COSTS_ARTIFACT must be a canonical cost-candidate path")
  }
  if (raw !== relativePath || path.posix.basename(relativePath) !== "HISTORICAL_COSTS.json") {
    throw new Error("STRYKER_HISTORICAL_COSTS_ARTIFACT must be a canonical cost-candidate path")
  }
  return relativePath
}

async function readRegularHistoricalCostArtifact({ candidateRoot, relativePath }) {
  const root = path.resolve(candidateRoot)
  let rootStats
  try {
    rootStats = await lstat(root)
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      throw new Error("Historical Stryker cost candidate root is missing")
    }
    throw error
  }
  if (!rootStats.isDirectory() || rootStats.isSymbolicLink()) {
    throw new Error("Historical Stryker cost candidate root is malformed")
  }
  let currentPath = root
  const components = relativePath.split("/")
  for (const [index, component] of components.entries()) {
    currentPath = path.join(currentPath, component)
    let stats
    try {
      stats = await lstat(currentPath)
    } catch (error) {
      if (error && typeof error === "object" && error.code === "ENOENT") {
        throw new Error("Historical Stryker cost artifact is missing")
      }
      throw error
    }
    const finalComponent = index === components.length - 1
    if (stats.isSymbolicLink() || (finalComponent ? !stats.isFile() : !stats.isDirectory())) {
      throw new Error("Historical Stryker cost artifact path is malformed")
    }
    if (finalComponent && stats.nlink !== 1) {
      throw new Error("Historical Stryker cost artifact must not be a hard link")
    }
  }
  return readFile(currentPath, "utf8")
}

export async function loadHistoricalCostArtifact({
  sourceRevision,
  config,
  preflightByFile,
  env = process.env,
  candidateRoot = historicalCostCandidateRoot,
}) {
  const relativePath = historicalCostArtifactRelativePath(env)
  if (relativePath === undefined) return undefined
  if (typeof candidateRoot !== "string" || candidateRoot === "") {
    throw new Error("Historical Stryker cost candidate root is invalid")
  }
  const artifactText = await readRegularHistoricalCostArtifact({ candidateRoot, relativePath })
  const costs = parseHistoricalCostArtifact({
    artifactText,
    sourceRevision,
    config,
    preflightByFile,
  })
  return { model: JSON.parse(artifactText).payload, costs }
}

function deserializePreflight({ serializedPreflight, sourceFiles, sourceByFile }) {
  if (!isRecord(serializedPreflight) || !(sourceByFile instanceof Map)) {
    throw new Error("Preflight artifact source snapshot is malformed")
  }
  const canonicalFiles = canonicalSourceFiles(sourceFiles)
  const artifactFiles = Object.keys(serializedPreflight).sort()
  if (JSON.stringify(artifactFiles) !== JSON.stringify(canonicalFiles)) {
    throw new Error(
      "Preflight artifact source denominator differs from the current source universe"
    )
  }
  const preflightByFile = new Map()
  for (const file of canonicalFiles) {
    const entry = serializedPreflight[file]
    assertExactObjectKeys(entry, ["sourceSha256", "mutantSignatures"], `Preflight artifact ${file}`)
    assertSha256(entry.sourceSha256, `Preflight artifact source digest for ${file}`)
    assertCanonicalStringArray(
      entry.mutantSignatures,
      `Preflight artifact mutant signatures for ${file}`
    )
    const source = sourceByFile.get(file)
    if (typeof source !== "string" || sha256(source) !== entry.sourceSha256) {
      throw new Error(`Preflight artifact source snapshot is stale or missing for ${file}`)
    }
    preflightByFile.set(file, {
      sourceSha256: entry.sourceSha256,
      // Producers need only a deterministic count to reconstruct their exact
      // logical assignment. Aggregate mode independently regenerates the
      // real mutants and compares their complete signatures below.
      mutants: entry.mutantSignatures,
    })
  }
  return preflightByFile
}

function assertCanonicalShardPlan({
  shardPlan,
  preflightByFile,
  shardTargetMutants,
  shardCount,
  historicalCosts,
}) {
  if (!Number.isInteger(shardCount) || shardCount < 1) {
    throw new Error("Preflight artifact shard count is invalid")
  }
  const expectedPlan = planMutationShards(
    preflightByFile,
    shardTargetMutants,
    shardCount,
    historicalCosts
  )
  if (expectedPlan.length !== shardCount) {
    throw new Error(
      `Preflight artifact shard plan has ${expectedPlan.length} logical shards; expected ${shardCount}`
    )
  }
  if (JSON.stringify(shardPlan) !== JSON.stringify(expectedPlan)) {
    throw new Error("Preflight artifact shard plan differs from the canonical assignment")
  }
  return expectedPlan
}

function assertPreflightArtifactWorkflowProvenance({
  payloadWorkflow,
  consumerWorkflow,
  producerAttemptPolicy,
}) {
  assertExactObjectKeys(
    payloadWorkflow,
    ["runId", "runAttempt", "sha", "sourceHeadSha", "baseSha", "baseRef"],
    "Preflight artifact workflow provenance"
  )
  assertExactObjectKeys(
    consumerWorkflow,
    ["runId", "runAttempt", "sha", "sourceHeadSha", "baseSha", "baseRef"],
    "Consumer Stryker workflow provenance"
  )
  const producerAttempt = parseWorkflowRunAttempt(payloadWorkflow.runAttempt)
  const consumerAttempt = parseWorkflowRunAttempt(consumerWorkflow.runAttempt)
  if (
    payloadWorkflow.runId !== consumerWorkflow.runId ||
    payloadWorkflow.sha !== consumerWorkflow.sha ||
    payloadWorkflow.sourceHeadSha !== consumerWorkflow.sourceHeadSha ||
    payloadWorkflow.baseSha !== consumerWorkflow.baseSha ||
    payloadWorkflow.baseRef !== consumerWorkflow.baseRef ||
    producerAttempt === undefined ||
    consumerAttempt === undefined
  ) {
    throw new Error("Preflight artifact workflow provenance does not match this execution")
  }
  if (producerAttemptPolicy === "exact") {
    if (producerAttempt !== consumerAttempt) {
      throw new Error("Preflight artifact workflow provenance does not match this execution")
    }
  } else if (producerAttemptPolicy === "at-or-before") {
    if (producerAttempt > consumerAttempt) {
      throw new Error("Preflight artifact producer attempt is from the future")
    }
  } else {
    throw new Error("Preflight artifact producer-attempt policy is invalid")
  }
  return producerAttempt
}

function assertExactPreflightArtifactMetadata({
  payload,
  sourceRevision,
  workflow,
  toolchain,
  sourcePolicy,
  config,
  producerAttemptPolicy,
}) {
  const expectedPayloadFields = [
    "schemaVersion",
    "workflow",
    "sourceRevision",
    "sourcePolicy",
    "config",
    "toolchain",
    "preflight",
    "shardPlan",
  ]
  if (Object.hasOwn(payload, "historicalCostModel")) {
    expectedPayloadFields.push("historicalCostModel")
  }
  assertExactObjectKeys(payload, expectedPayloadFields, "Preflight artifact payload")
  if (payload.schemaVersion !== preflightArtifactSchemaVersion) {
    throw new Error("Preflight artifact schema version is unsupported")
  }
  const producerAttempt = assertPreflightArtifactWorkflowProvenance({
    payloadWorkflow: payload.workflow,
    consumerWorkflow: workflow,
    producerAttemptPolicy,
  })
  if (JSON.stringify(payload.sourceRevision) !== JSON.stringify(sourceRevision)) {
    throw new Error("Preflight artifact source revision does not match this execution")
  }
  if (JSON.stringify(payload.sourcePolicy) !== JSON.stringify(sourcePolicy)) {
    throw new Error("Preflight artifact source policy does not match this execution")
  }
  if (JSON.stringify(payload.config) !== JSON.stringify(config)) {
    throw new Error("Preflight artifact configuration does not match this execution")
  }
  if (JSON.stringify(payload.toolchain) !== JSON.stringify(toolchain)) {
    throw new Error("Preflight artifact toolchain does not match this execution")
  }
  return producerAttempt
}

export function buildPreflightArtifact({
  sourceRevision,
  workflow,
  toolchain,
  sourcePolicy,
  config,
  preflightByFile,
  shardTargetMutants,
  shardCount,
  historicalCostModel,
}) {
  const serializedPreflight = serializePreflight(preflightByFile)
  const historicalCosts =
    historicalCostModel === undefined
      ? undefined
      : historicalCostModelCosts({
          model: historicalCostModel,
          sourceRevision,
          config,
          serializedPreflight,
        })
  const shardPlan = planMutationShards(
    preflightByFile,
    shardTargetMutants,
    shardCount,
    historicalCosts
  )
  if (shardPlan.length !== shardCount) {
    throw new Error(
      `Canonical Stryker preflight generated ${shardPlan.length}/${shardCount} logical shards`
    )
  }
  const payload = {
    schemaVersion: preflightArtifactSchemaVersion,
    workflow,
    sourceRevision,
    sourcePolicy,
    config,
    toolchain,
    preflight: {
      digest: preflightDigest(serializedPreflight),
      files: serializedPreflight,
    },
    shardPlan,
    ...(historicalCostModel === undefined ? {} : { historicalCostModel }),
  }
  return {
    schemaVersion: preflightArtifactSchemaVersion,
    payload,
    payloadSha256: sha256(jsonText(payload)),
  }
}

export function validatePreflightArtifact({
  artifactText,
  sourceFiles,
  sourceByFile,
  sourceRevision,
  workflow,
  toolchain,
  sourcePolicy,
  config,
  shardTargetMutants,
  shardCount,
  canonicalPreflightByFile,
  producerAttemptPolicy = "exact",
}) {
  if (typeof artifactText !== "string") {
    throw new Error("Preflight artifact is missing")
  }
  let artifact
  try {
    artifact = JSON.parse(artifactText)
  } catch {
    throw new Error("Preflight artifact contains invalid JSON")
  }
  // The producer emits this exact byte form. Requiring it detects duplicate
  // object keys (which JSON.parse would otherwise overwrite) and makes every
  // artifact hash reproducible across producer, shard and aggregate jobs.
  if (artifactText !== jsonText(artifact)) {
    throw new Error("Preflight artifact JSON is not canonical")
  }
  assertExactObjectKeys(
    artifact,
    ["schemaVersion", "payload", "payloadSha256"],
    "Preflight artifact"
  )
  if (artifact.schemaVersion !== preflightArtifactSchemaVersion) {
    throw new Error("Preflight artifact schema version is unsupported")
  }
  assertSha256(artifact.payloadSha256, "Preflight artifact payload digest")
  if (artifact.payloadSha256 !== sha256(jsonText(artifact.payload))) {
    throw new Error("Preflight artifact payload digest does not match its content")
  }
  const producerAttempt = assertExactPreflightArtifactMetadata({
    payload: artifact.payload,
    sourceRevision,
    workflow,
    toolchain,
    sourcePolicy,
    config,
    producerAttemptPolicy,
  })
  assertExactObjectKeys(
    artifact.payload.preflight,
    ["digest", "files"],
    "Preflight artifact preflight"
  )
  const serializedPreflight = artifact.payload.preflight.files
  assertSha256(artifact.payload.preflight.digest, "Preflight artifact preflight digest")
  if (artifact.payload.preflight.digest !== preflightDigest(serializedPreflight)) {
    throw new Error("Preflight artifact preflight digest does not match its source universe")
  }
  const preflightByFile = deserializePreflight({ serializedPreflight, sourceFiles, sourceByFile })
  const historicalCosts =
    artifact.payload.historicalCostModel === undefined
      ? undefined
      : historicalCostModelCosts({
          model: artifact.payload.historicalCostModel,
          sourceRevision,
          config,
          serializedPreflight,
        })
  const shardPlan = assertCanonicalShardPlan({
    shardPlan: artifact.payload.shardPlan,
    preflightByFile,
    shardTargetMutants,
    shardCount,
    historicalCosts,
  })
  if (canonicalPreflightByFile !== undefined) {
    if (!(canonicalPreflightByFile instanceof Map)) {
      throw new Error("Canonical instrumenter universe must be provided as a Map")
    }
    const canonicalSerializedPreflight = serializePreflight(canonicalPreflightByFile)
    if (JSON.stringify(canonicalSerializedPreflight) !== JSON.stringify(serializedPreflight)) {
      throw new Error("Preflight artifact differs from the canonical instrumenter universe")
    }
    assertCanonicalShardPlan({
      shardPlan,
      preflightByFile: canonicalPreflightByFile,
      shardTargetMutants,
      shardCount,
      historicalCosts,
    })
  }
  return {
    artifact,
    producerAttempt,
    preflightByFile: canonicalPreflightByFile ?? preflightByFile,
    preflightDigest: artifact.payload.preflight.digest,
    shardPlan,
  }
}

export async function selectPreflightArtifactCandidate({
  candidateRoot = preflightCandidateRoot,
  sourceFiles,
  sourceByFile,
  sourceRevision,
  workflow,
  toolchain,
  sourcePolicy,
  config,
  shardTargetMutants,
  shardCount,
  canonicalPreflightByFile,
}) {
  if (typeof candidateRoot !== "string" || candidateRoot === "") {
    throw new Error("Stryker preflight candidate root is invalid")
  }
  const candidates = await readCanonicalPreflightCandidates({ candidateRoot, workflow })
  const candidatesByAttempt = new Map()
  for (const candidate of candidates) {
    const validated = validatePreflightArtifact({
      artifactText: candidate.artifactText,
      sourceFiles,
      sourceByFile,
      sourceRevision,
      workflow,
      toolchain,
      sourcePolicy,
      config,
      shardTargetMutants,
      shardCount,
      canonicalPreflightByFile,
      producerAttemptPolicy: "at-or-before",
    })
    if (
      candidate.directoryAttempt.attempt !== validated.producerAttempt ||
      candidate.directoryAttempt.attemptText !== validated.artifact.payload.workflow.runAttempt
    ) {
      throw new Error("Preflight candidate directory attempt does not match its payload")
    }
    if (candidatesByAttempt.has(validated.producerAttempt)) {
      throw new Error(
        `Preflight candidates contain a duplicate producer attempt: ${validated.producerAttempt}`
      )
    }
    candidatesByAttempt.set(validated.producerAttempt, {
      ...validated,
      artifactPath: candidate.artifactPath,
      consumerWorkflow: workflow,
    })
  }
  return [...candidatesByAttempt.entries()].sort(
    ([leftAttempt], [rightAttempt]) => rightAttempt - leftAttempt
  )[0][1]
}

function assertOwnedTemporaryDirectory(temporaryRoot, runId) {
  const resolved = path.resolve(temporaryRoot)
  const allowed = path.resolve(os.tmpdir(), "university-ecosystem-stryker-runs")
  if (!resolved.startsWith(`${allowed}${path.sep}`) || !resolved.endsWith(`${path.sep}${runId}`)) {
    throw new Error(`Refusing to clean an unowned Stryker temp directory: ${resolved}`)
  }
}

async function runPool(items, concurrency, worker) {
  let nextIndex = 0
  const results = new Array(items.length)
  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, async () => {
      while (nextIndex < items.length) {
        const index = nextIndex
        nextIndex += 1
        results[index] = await worker(items[index], index)
      }
    })
  )
  return results
}

function jsonText(value) {
  return `${JSON.stringify(value, null, 2)}\n`
}

function optionalEnvironmentInteger(name, minimum, maximum) {
  if (process.env[name] === undefined) return undefined
  const value = Number(process.env[name])
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`)
  }
  return value
}

function externalAggregateRoot() {
  if (!process.env.STRYKER_AGGREGATE_ROOT) return undefined
  const resolved = path.resolve(frontendRoot, process.env.STRYKER_AGGREGATE_ROOT)
  const allowed = path.join(outputRoot, "external")
  if (resolved !== allowed && !resolved.startsWith(`${allowed}${path.sep}`)) {
    throw new Error(`STRYKER_AGGREGATE_ROOT must be within ${allowed}`)
  }
  return resolved
}

export async function loadExternalShardResults({
  aggregateRoot,
  shardPlan,
  before,
  preflightDigest,
  workflowRunId,
  workflowRunAttempt,
}) {
  const aggregateAttempt = parseWorkflowRunAttempt(workflowRunAttempt)
  if (aggregateAttempt === undefined) {
    throw new Error("Aggregate workflow run attempt is invalid")
  }
  const evidencePaths = []
  for await (const file of glob("**/SHARD_EVIDENCE.json", { cwd: aggregateRoot })) {
    evidencePaths.push(normalizePath(file))
  }
  const candidates = await Promise.all(
    evidencePaths.sort().map(async (relativeEvidencePath) => {
      const evidencePath = path.join(aggregateRoot, relativeEvidencePath)
      const evidenceText = await readFile(evidencePath, "utf8")
      const evidence = JSON.parse(evidenceText)
      const expected = shardPlan.find((shard) => shard.id === evidence.shardId)
      const producerAttempt = parseWorkflowRunAttempt(evidence.workflowRunAttempt)
      if (
        !expected ||
        evidence.schemaVersion !== "1.0" ||
        typeof evidence.runId !== "string" ||
        evidence.runId === "" ||
        evidence.shardIndex !== shardPlan.findIndex((shard) => shard.id === evidence.shardId) ||
        evidence.shardCount !== shardPlan.length ||
        evidence.revision !== before.revision ||
        evidence.sourceHeadSha !== before.sourceHeadSha ||
        evidence.baseSha !== before.baseSha ||
        evidence.baseRef !== before.baseRef ||
        evidence.evidenceDigest !== before.evidenceDigest ||
        evidence.preflightDigest !== preflightDigest ||
        evidence.workflowRunId !== workflowRunId ||
        producerAttempt === undefined ||
        producerAttempt > aggregateAttempt ||
        JSON.stringify(evidence.files) !== JSON.stringify(expected.files) ||
        evidence.mutantCount !== expected.mutantCount
      ) {
        throw new Error(
          `External Stryker shard evidence is stale or malformed: ${relativeEvidencePath}`
        )
      }
      const reportPath = path.join(path.dirname(evidencePath), "mutation.json")
      const reportText = await readFile(reportPath, "utf8")
      if (sha256(reportText) !== evidence.reportSha256) {
        throw new Error(`External Stryker shard report hash mismatch: ${evidence.shardId}`)
      }
      return {
        ...expected,
        reportPath,
        reportText,
        report: normalizeStrykerRuntimeReport(JSON.parse(reportText)),
        shardEvidencePath: evidencePath,
        shardEvidenceText: evidenceText,
        shardEvidence: evidence,
        producerAttempt,
      }
    })
  )
  const candidatesByShard = new Map()
  for (const candidate of candidates) {
    const byAttempt = candidatesByShard.get(candidate.id) ?? new Map()
    if (byAttempt.has(candidate.producerAttempt)) {
      throw new Error(
        `External Stryker evidence contains a duplicate producer attempt for ${candidate.id}: ${candidate.producerAttempt}`
      )
    }
    byAttempt.set(candidate.producerAttempt, candidate)
    candidatesByShard.set(candidate.id, byAttempt)
  }
  if (candidatesByShard.size !== shardPlan.length) {
    throw new Error(
      `External Stryker evidence contains ${candidatesByShard.size}/${shardPlan.length} shards`
    )
  }
  return shardPlan.map((shard) => {
    const byAttempt = candidatesByShard.get(shard.id)
    if (!byAttempt || byAttempt.size === 0) {
      throw new Error(`External Stryker evidence omitted ${shard.id}`)
    }
    return [...byAttempt.values()].sort(
      (left, right) => right.producerAttempt - left.producerAttempt
    )[0]
  })
}

async function main() {
  assertRunnerArguments(process.argv.slice(2))
  const started = Date.now()
  const runId = randomUUID()
  const lock = await acquireRunLock(path.join(outputRoot, ".run.lock"), runId)
  let temporaryRoot
  let markerWritten = false
  let releaseError
  try {
    const artifactExecution = preflightArtifactExecution()
    if (artifactExecution.mode !== "validate") {
      await cleanupCanonicalArtifacts(outputRoot)
    }
    const policy = JSON.parse(await readFile(sourcePolicyPath, "utf8"))
    const sourceFiles = await listPolicyFiles(policy)
    const beforeSnapshot = await captureEvidence(sourceFiles)
    const { identity: before, sourceByFile } = beforeSnapshot
    const shardTarget = boundedEnvironmentInteger("STRYKER_SHARD_TARGET", 750, 50, 2_000)
    const shardParallelism = boundedEnvironmentInteger("STRYKER_SHARD_PARALLELISM", 2, 1, 4)
    const shardTimeoutMs = boundedEnvironmentInteger(
      "STRYKER_SHARD_TIMEOUT_MS",
      7_200_000,
      60_000,
      14_400_000
    )
    const runnerConcurrency = boundedEnvironmentInteger("STRYKER_CONCURRENCY", 2, 1, 4)
    if (runnerConcurrency * shardParallelism > 8) {
      throw new Error("Combined Stryker concurrency must not exceed 8 test runners")
    }
    const externalShardCount = optionalEnvironmentInteger("STRYKER_SHARD_COUNT", 2, 256)
    const externalShardIndex = optionalEnvironmentInteger("STRYKER_SHARD_INDEX", 0, 255)
    const aggregateRoot = externalAggregateRoot()
    if ((externalShardIndex !== undefined || aggregateRoot) && externalShardCount === undefined) {
      throw new Error("External Stryker shard/aggregate mode requires STRYKER_SHARD_COUNT")
    }
    if (externalShardIndex !== undefined && aggregateRoot) {
      throw new Error("Stryker shard execution and aggregation modes are mutually exclusive")
    }
    if (
      artifactExecution.artifactRequired &&
      artifactExecution.mode === "execute" &&
      externalShardIndex === undefined &&
      !aggregateRoot
    ) {
      throw new Error(
        "Immutable Stryker preflight artifacts require a shard or aggregate execution"
      )
    }
    if (artifactExecution.mode === "generate") {
      if (
        externalShardCount === undefined ||
        externalShardIndex !== undefined ||
        aggregateRoot ||
        artifactExecution.artifactRequired
      ) {
        throw new Error("Stryker preflight generation requires exactly a canonical shard count")
      }
    }
    if (artifactExecution.mode === "validate" && aggregateRoot) {
      throw new Error("Stryker preflight validation cannot replace aggregate verification")
    }

    const toolchain = await readToolchain()
    const historicalCostConfig = {
      path: "frontend/stryker.config.mjs",
      sha256: before.inputHashes["frontend/stryker.config.mjs"],
      instrumenterOptions,
    }
    assertSha256(historicalCostConfig.sha256, "Canonical Stryker configuration digest")
    const workflow =
      artifactExecution.mode === "generate" || artifactExecution.artifactRequired
        ? requireWorkflowProvenance(before)
        : undefined
    const artifactMetadata = workflow
      ? preflightArtifactMetadata({
          sourceRevision: before,
          workflow,
          toolchain,
          shardTargetMutants: shardTarget,
          shardCount: externalShardCount,
        })
      : undefined

    let preflightByFile
    let shardPlan
    let currentPreflightDigest
    if (artifactExecution.mode === "generate") {
      const canonicalPreflightByFile = await generateInstrumenterPreflight({
        sourceFiles,
        sourceByFile,
        instrumenterOptions,
      })
      assertEvidenceUnchanged(before, (await captureEvidence(sourceFiles)).identity)
      const historicalCostArtifact = await loadHistoricalCostArtifact({
        sourceRevision: before,
        config: historicalCostConfig,
        preflightByFile: canonicalPreflightByFile,
      })
      const artifact = buildPreflightArtifact({
        ...artifactMetadata,
        preflightByFile: canonicalPreflightByFile,
        historicalCostModel: historicalCostArtifact?.model,
      })
      const artifactText = jsonText(artifact)
      validatePreflightArtifact({
        ...artifactMetadata,
        sourceFiles,
        sourceByFile,
        canonicalPreflightByFile,
        artifactText,
        producerAttemptPolicy: "exact",
      })
      await atomicText(preflightArtifactOutputPath, artifactText)
      assertEvidenceUnchanged(before, (await captureEvidence(sourceFiles)).identity)
      process.stdout.write(
        `Prepared canonical frontend Stryker preflight (${artifact.payload.preflight.digest}) for ${artifact.payload.shardPlan.length} logical shards\n`
      )
      return
    }
    if (artifactExecution.artifactRequired) {
      const canonicalPreflightByFile = aggregateRoot
        ? await generateInstrumenterPreflight({
            sourceFiles,
            sourceByFile,
            instrumenterOptions,
          })
        : undefined
      if (canonicalPreflightByFile) {
        assertEvidenceUnchanged(before, (await captureEvidence(sourceFiles)).identity)
      }
      const validatedArtifact = await selectPreflightArtifactCandidate({
        ...artifactMetadata,
        sourceFiles,
        sourceByFile,
        canonicalPreflightByFile,
      })
      preflightByFile = validatedArtifact.preflightByFile
      shardPlan = validatedArtifact.shardPlan
      currentPreflightDigest = validatedArtifact.preflightDigest
    } else {
      preflightByFile = await generateInstrumenterPreflight({
        sourceFiles,
        sourceByFile,
        instrumenterOptions,
      })
      assertEvidenceUnchanged(before, (await captureEvidence(sourceFiles)).identity)
      const historicalCostArtifact = await loadHistoricalCostArtifact({
        sourceRevision: before,
        config: historicalCostConfig,
        preflightByFile,
      })
      shardPlan = planMutationShards(
        preflightByFile,
        shardTarget,
        externalShardCount,
        historicalCostArtifact?.costs
      )
      currentPreflightDigest = sha256(JSON.stringify(serializePreflight(preflightByFile)))
    }
    if (shardPlan.length === 0) {
      throw new Error("Instrumenter preflight generated no viable frontend mutants")
    }
    if (externalShardIndex !== undefined && externalShardIndex >= shardPlan.length) {
      throw new Error(`STRYKER_SHARD_INDEX ${externalShardIndex} exceeds the generated shard plan`)
    }
    const serializedPreflight =
      artifactExecution.artifactRequired && !aggregateRoot
        ? undefined
        : serializePreflight(preflightByFile)
    if (
      serializedPreflight !== undefined &&
      currentPreflightDigest !== sha256(JSON.stringify(serializedPreflight))
    ) {
      throw new Error("Stryker preflight digest changed after canonical validation")
    }
    const preflightDigest = currentPreflightDigest
    assertEvidenceUnchanged(before, (await captureEvidence(sourceFiles)).identity)
    if (artifactExecution.mode === "validate") {
      process.stdout.write(
        `Validated immutable frontend Stryker preflight (${preflightDigest}) for ${shardPlan.length} logical shards\n`
      )
      return
    }

    let shardResults
    if (aggregateRoot) {
      shardResults = await loadExternalShardResults({
        aggregateRoot,
        shardPlan,
        before,
        preflightDigest,
        workflowRunId: process.env.GITHUB_RUN_ID ?? null,
        workflowRunAttempt: process.env.GITHUB_RUN_ATTEMPT ?? null,
      })
    } else {
      const repositoryHash = sha256(repositoryRoot).slice(0, 16)
      temporaryRoot = path.join(
        os.tmpdir(),
        "university-ecosystem-stryker-runs",
        repositoryHash,
        before.headSha,
        runId
      )
      assertOwnedTemporaryDirectory(temporaryRoot, runId)
      await mkdir(temporaryRoot, { recursive: true })
      const runRoot =
        externalShardIndex === undefined
          ? path.join(outputRoot, "runs", runId)
          : path.join(outputRoot, "shards")
      await mkdir(runRoot, { recursive: false })
      const executionPlan =
        externalShardIndex === undefined ? shardPlan : [shardPlan[externalShardIndex]]
      shardResults = await runPool(executionPlan, shardParallelism, async (shard) => {
        const shardRoot = path.join(runRoot, shard.id)
        const shardTemp = path.join(temporaryRoot, shard.id)
        const reportPath = path.join(shardRoot, "mutation.json")
        await Promise.all([
          mkdir(shardRoot, { recursive: false }),
          mkdir(shardTemp, { recursive: false }),
        ])
        // Stryker creates its working directory as `shardTemp/sandbox-*`.
        // Vitest's canonical config imports `../quality/coverage-source-policy.json`,
        // so place an exact, fail-closed copy beside (never inside) the sandbox.
        await stageStrykerSandboxInputs(shardTemp)
        const executionStartedAt = Date.now()
        await runNode(
          [strykerEntry, "run"],
          `Stryker ${shard.id}`,
          {
            ...process.env,
            STRYKER_CONCURRENCY: String(runnerConcurrency),
            STRYKER_TEMP_DIR: shardTemp,
            STRYKER_JSON_REPORT: reportPath,
            STRYKER_MUTATE_JSON: JSON.stringify(shard.files),
            STRYKER_SHARD_RUN: "1",
          },
          shardTimeoutMs
        )
        const durationMs = Math.max(1, Date.now() - executionStartedAt)
        const reportText = await readFile(reportPath, "utf8")
        const report = normalizeStrykerRuntimeReport(JSON.parse(reportText))
        mergeShardReports({
          shards: [{ ...shard, report }],
          expectedPatterns: shard.files,
          preflightByFile,
          sourceByFile,
        })
        const shardEvidence = {
          schemaVersion: "1.0",
          runId,
          shardId: shard.id,
          shardIndex: shardPlan.findIndex((entry) => entry.id === shard.id),
          shardCount: shardPlan.length,
          revision: before.revision,
          sourceHeadSha: before.sourceHeadSha,
          baseSha: before.baseSha,
          baseRef: before.baseRef,
          evidenceDigest: before.evidenceDigest,
          preflightDigest,
          workflowRunId: process.env.GITHUB_RUN_ID ?? null,
          workflowRunAttempt: process.env.GITHUB_RUN_ATTEMPT ?? null,
          files: shard.files,
          mutantCount: shard.mutantCount,
          durationMs,
          reportSha256: sha256(reportText),
          generatedAt: new Date().toISOString(),
        }
        const shardEvidencePath = path.join(shardRoot, "SHARD_EVIDENCE.json")
        const shardEvidenceText = jsonText(shardEvidence)
        await atomicText(shardEvidencePath, shardEvidenceText)
        return {
          ...shard,
          reportPath,
          reportText,
          report,
          shardEvidencePath,
          shardEvidenceText,
          shardEvidence,
          durationMs,
        }
      })
    }

    assertEvidenceUnchanged(before, (await captureEvidence(sourceFiles)).identity)
    if (externalShardIndex !== undefined) {
      const [shard] = shardResults
      process.stdout.write(
        `Completed ${shard.id}/${shardPlan.length} with ${shard.mutantCount} assigned mutants\n`
      )
      return
    }
    const shardTimingValues = shardResults.map(
      (shard) => shard.durationMs ?? shard.shardEvidence?.durationMs
    )
    if (shardTimingValues.every((durationMs) => durationMs !== undefined)) {
      const historicalCostArtifact = buildHistoricalCostArtifactFromShardTimings({
        sourceRevision: before,
        config: historicalCostConfig,
        preflightByFile,
        shardResults,
      })
      await atomicText(historicalCostArtifactOutputPath, jsonText(historicalCostArtifact))
    }
    if (serializedPreflight === undefined) {
      throw new Error("Aggregate Stryker evidence requires a canonical preflight universe")
    }
    const expectedPatterns = mutationPatternsFromPolicy(policy)
    const report = mergeShardReports({
      shards: shardResults,
      expectedPatterns,
      preflightByFile,
      sourceByFile,
    })
    const reportText = jsonText(report)
    const reportPath = path.join(outputRoot, "mutation.json")
    await atomicText(reportPath, reportText)
    const inventoryResult = buildMutationInventory({
      sourceFiles,
      sourceByFile,
      report,
      expectedPatterns,
      preflightByFile,
    })
    const {
      stryker: strykerVersion,
      instrumenter: instrumenterVersion,
      vitest: vitestVersion,
    } = toolchain
    const preflight = {
      schemaVersion: "1.0",
      runId,
      revision: before.revision,
      sourceEvidenceDigest: before.evidenceDigest,
      instrumenterOptions,
      files: serializedPreflight,
    }
    const preflightSha256 = sha256(jsonText(preflight))
    if (temporaryRoot) {
      assertOwnedTemporaryDirectory(temporaryRoot, runId)
      await rm(temporaryRoot, { recursive: true, force: true })
      temporaryRoot = undefined
    }
    const finalSnapshot = await captureEvidence(sourceFiles)
    assertEvidenceUnchanged(before, finalSnapshot.identity)
    const releaseEligible = isReleaseEligible(finalSnapshot.identity)
    const inventory = {
      schemaVersion: "2.0",
      runId,
      revision: before.revision,
      sourceRevision: before,
      generatedAt: new Date().toISOString(),
      durationMs: Date.now() - started,
      releaseEligible,
      provenance: {
        workflowRunId: process.env.GITHUB_RUN_ID ?? null,
        workflowRunAttempt: process.env.GITHUB_RUN_ATTEMPT ?? null,
        node: process.version,
        platform: process.platform,
        arch: process.arch,
        tools: {
          stryker: strykerVersion,
          instrumenter: instrumenterVersion,
          vitest: vitestVersion,
        },
      },
      sourcePolicy: {
        path: "quality/coverage-source-policy.json",
        sha256: before.inputHashes["quality/coverage-source-policy.json"],
        mutationPatterns: expectedPatterns,
      },
      config: {
        path: "frontend/stryker.config.mjs",
        sha256: before.inputHashes["frontend/stryker.config.mjs"],
        coverageAnalysis: "perTest",
        instrumenterOptions,
        concurrency: runnerConcurrency,
        shardParallelism,
        shardTargetMutants: shardTarget,
        shardTimeoutMs,
        shardCount: shardPlan.length,
        incremental: false,
        forceFresh: true,
      },
      preflight: {
        path: "frontend/reports/mutation/preflight.json",
        sha256: preflightSha256,
        files: sourceFiles.length,
        mutants: [...preflightByFile.values()].reduce(
          (sum, entry) => sum + entry.mutants.length,
          0
        ),
      },
      reports: [
        {
          path: normalizePath(path.relative(repositoryRoot, reportPath)),
          sha256: sha256(reportText),
          schemaVersion: report.schemaVersion,
        },
        ...shardResults.map((shard) => ({
          shardId: shard.id,
          assignedFiles: shard.files.length,
          assignedMutants: shard.mutantCount,
          path: normalizePath(path.relative(repositoryRoot, shard.reportPath)),
          sha256: sha256(shard.reportText),
          schemaVersion: shard.report.schemaVersion,
        })),
      ],
      shardEvidence: indexShardProducerEvidence(shardResults),
      ...inventoryResult,
    }
    const marker = await writeValidatedEvidence({ outputRoot, inventory, preflight })
    markerWritten = true
    process.stdout.write(
      `Validated ${inventory.summary.denominatorFiles} frontend source files and ${inventory.summary.totalMutants} mutants at ${inventory.summary.viableMutantScore}% (${marker.inventorySha256})\n`
    )
  } catch (error) {
    if (markerWritten) {
      await Promise.all([
        rm(path.join(outputRoot, "VALIDATED.json"), { force: true }),
        rm(path.join(outputRoot, "LOCAL_VALIDATION.json"), { force: true }),
      ])
      markerWritten = false
    }
    throw error
  } finally {
    if (temporaryRoot) {
      assertOwnedTemporaryDirectory(temporaryRoot, runId)
      await rm(temporaryRoot, { recursive: true, force: true })
    }
    try {
      await lock.release()
    } catch (error) {
      if (markerWritten) {
        await Promise.all([
          rm(path.join(outputRoot, "VALIDATED.json"), { force: true }),
          rm(path.join(outputRoot, "LOCAL_VALIDATION.json"), { force: true }),
        ])
      }
      releaseError = error
    }
  }
  if (releaseError) throw releaseError
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`)
    process.exitCode = 1
  })
}
