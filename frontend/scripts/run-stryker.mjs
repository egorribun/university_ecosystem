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
import { rmSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { performance } from "node:perf_hooks"
import process from "node:process"
import { promisify } from "node:util"
import { fileURLToPath, pathToFileURL } from "node:url"

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
const sourcePolicyPath = path.join(repositoryRoot, "quality", "coverage-source-policy.json")
const strykerEntry = path.join(
  frontendRoot,
  "node_modules",
  "@stryker-mutator",
  "core",
  "bin",
  "stryker.js"
)
export const strykerSafeErrorStringPreloadOption = `--import=${
  pathToFileURL(path.join(frontendRoot, "scripts", "stryker-safe-error-string.mjs")).href
}`
const instrumenterOptions = { plugins: null, excludedMutations: [], ignorers: [] }
const preflightArtifactSchemaVersion = "1.0"
const historicalCostArtifactSchemaVersion = "1.0"
const maximumHistoricalCostMs = 14_400_000
const windowsDeviceNamePattern = /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9]|clock\$)(?:\..*)?$/iu

export function buildStrykerChildEnvironment(parentEnv = process.env) {
  const existingNodeOptions = parentEnv.NODE_OPTIONS?.trim()
  return {
    ...parentEnv,
    NODE_OPTIONS: [existingNodeOptions, strykerSafeErrorStringPreloadOption]
      .filter(Boolean)
      .join(" "),
  }
}

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

const focusedMutationForbiddenEnvironmentKeys = [
  "GITHUB_RUN_ID",
  "GITHUB_RUN_ATTEMPT",
  "GITHUB_SHA",
  "STRYKER_AGGREGATE_ROOT",
  "STRYKER_BASE_REF",
  "STRYKER_BASE_SHA",
  "STRYKER_HISTORICAL_COSTS_ARTIFACT",
  "STRYKER_PREFLIGHT_ARTIFACT",
  "STRYKER_SHARD_COUNT",
  "STRYKER_SHARD_INDEX",
  "STRYKER_SHARD_RUN",
  "STRYKER_SOURCE_HEAD_SHA",
]

export function resolveMutationSourceSelection(policySourceFiles, env = process.env) {
  const canonical = canonicalSourceFiles(policySourceFiles)
  if (env.STRYKER_MUTATE_JSON !== undefined) {
    throw new Error(
      "STRYKER_MUTATE_JSON is reserved for child shards; use STRYKER_LOCAL_MUTATE_JSON for focused local runs"
    )
  }
  const rawScope = env.STRYKER_LOCAL_MUTATE_JSON
  if (rawScope === undefined) return { focused: false, sourceFiles: canonical }
  if (
    env.GITHUB_ACTIONS === "true" ||
    env.STRYKER_PREFLIGHT_MODE === "generate" ||
    env.STRYKER_PREFLIGHT_MODE === "validate" ||
    focusedMutationForbiddenEnvironmentKeys.some((key) => env[key] !== undefined)
  ) {
    throw new Error("Focused mutation scope is local-only and cannot produce workflow evidence")
  }

  let requested
  try {
    requested = canonicalSourceFiles(JSON.parse(rawScope))
  } catch {
    throw new Error("Invalid focused mutation scope")
  }
  const allowed = new Set(canonical)
  if (requested.some((file) => !allowed.has(file))) {
    throw new Error("Invalid focused mutation scope: every source must belong to the policy")
  }
  return { focused: true, sourceFiles: requested }
}

export function mutationRunPaths(selection, canonicalRoot = outputRoot) {
  if (
    !selection ||
    typeof selection.focused !== "boolean" ||
    !Array.isArray(selection.sourceFiles) ||
    selection.sourceFiles.length === 0
  ) {
    throw new Error("Mutation source selection is invalid")
  }
  const targetRoot = selection.focused
    ? path.join(canonicalRoot, "focused", sha256(JSON.stringify(selection.sourceFiles)))
    : canonicalRoot
  return {
    allowReleaseMarkers: !selection.focused,
    historicalCostOutputPath: selection.focused
      ? null
      : path.join(targetRoot, "historical-costs", "HISTORICAL_COSTS.json"),
    lockPath: path.join(targetRoot, ".run.lock"),
    outputRoot: targetRoot,
  }
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
// provenance-bound Stryker mutation graph for source files whose complete
// preflight inventory was present in successful shards (run 33863748227,
// source 3e54ca9b5a6ccc03ec887df188572cdcac2ac091).  They are intentionally
// checked in: a first attempt has no historical timing model, but these
// modules fan out to materially different related-test graphs.  A weight of
// one means that the regular locality-aware count model remains in effect.
// Explicit timeout guard weights below are annotated separately and are based
// on complete, provenance-bound shard inventories rather than coverage claims.
const firstAttemptSourceCostWeights = new Map([
  // The first attempt in runs 33863748227 and 33994803565 repeatedly placed
  // this API/core block in logical shard 8.  That shard reached the 120-minute
  // hard timeout despite having only 677 mutants.  Keep conservative guard
  // weights explicit so a fresh SHA cannot silently fall back to the count-only
  // locality planner for the same hotspot.  These guard weights are relative
  // placement costs, not coverage claims; measured test-graph counts below
  // retain their evidence comments.
  ["src/api/backendOrigin.ts", 24], // timeout guard weight
  ["src/api/chat.ts", 180], // timeout guard weight
  ["src/api/client.ts", 650], // timeout guard weight
  ["src/api/events.ts", 50], // timeout guard weight
  ["src/api/hooks/activity.ts", 120], // timeout guard weight
  ["src/api/hooks/adminAudit.ts", 60], // timeout guard weight
  ["src/api/hooks/adminFeatureFlags.ts", 60], // timeout guard weight
  ["src/api/hooks/adminNotifications.ts", 60], // timeout guard weight
  ["src/api/hooks/adminUsers.ts", 120], // timeout guard weight
  ["src/api/hooks/sessions.ts", 60], // timeout guard weight
  ["src/api/hooks/weather.ts", 101], // timeout guard weight
  ["src/api/hooks/events.ts", 74], // 301 mutants / 74 tests
  ["src/api/hooks/messenger.ts", 135], // 35 mutants / 135 tests
  ["src/api/hooks/news.ts", 62], // 170 mutants / 62 tests
  ["src/api/hooks/schedule.ts", 33], // 23 mutants / 33 tests
  ["src/api/hooks/users.ts", 235], // 8 mutants / 235 tests
  ["src/api/interceptors/etagCache.ts", 2882], // 239 mutants / 2882 tests
  ["src/api/interceptors/language.ts", 120], // timeout guard weight
  ["src/api/interceptors/rateLimit.ts", 342], // 144 mutants / 342 tests
  ["src/api/interceptors/traceContext.ts", 285], // 16 mutants / 285 tests
  ["src/api/mfa.ts", 18], // 37 mutants / 18 tests
  ["src/api/news.ts", 14], // 65 mutants / 14 tests
  ["src/api/notifications.ts", 47], // 110 mutants / 47 tests
  ["src/api/offlineMutationQueue.ts", 5], // 24 mutants / 5 tests
  ["src/api/schemas/wsMessage.ts", 71], // 151 mutants / 71 tests
  ["src/api/stories.ts", 12], // 16 mutants / 12 tests
  ["src/api/validation.ts", 46], // 20 mutants / 46 tests
  ["src/api/weather.ts", 101], // 174 mutants / 101 tests
  ["src/App.tsx", 3], // 9 mutants / 3 tests
  ["src/app/globalErrorHandlers.ts", 6], // 53 mutants / 6 tests
  ["src/app/hydration.ts", 20], // 40 mutants / 20 tests
  ["src/app/logger.ts", 417], // 117 mutants / 417 tests
  ["src/components/media/SmartImage.tsx", 169], // 89 mutants / 169 tests
  ["src/components/schedule/scheduleUtils.ts", 173], // 169 mutants / 173 tests
  ["src/components/settings/ui/Form.tsx", 164], // 26 mutants / 164 tests
  ["src/components/ui/Tooltip.tsx", 42], // 11 mutants / 42 tests
  ["src/contexts/AuthContext.tsx", 176], // 35 mutants / 176 tests
  ["src/contexts/LanguageContext.tsx", 325], // 70 mutants / 325 tests
  ["src/db/index.ts", 650], // 38 mutants / 650 tests
  ["src/hooks/auth/legacyTokenCleanup.ts", 226], // 12 mutants / 226 tests
  ["src/hooks/auth/ssrAuthHint.ts", 166], // 32 mutants / 166 tests
  ["src/hooks/useFocusTrap.ts", 226], // 31 mutants / 226 tests
  ["src/hooks/useMediaQuery.ts", 217], // 57 mutants / 217 tests
  // Run 34336062499 timed out while the UI primitives below were kept in one
  // locality shard (730 mutants across 27 source files).  These conservative
  // guard weights move each source range into the bounded cost-aware group so
  // a fresh first attempt cannot recreate that all-or-nothing graph.
  ["src/components/ui/Button.tsx", 8],
  ["src/components/ui/Card.tsx", 8],
  ["src/components/ui/CardActionArea.tsx", 8],
  ["src/components/ui/Checkbox.tsx", 8],
  ["src/components/ui/ConfirmDialog.tsx", 8],
  ["src/components/ui/ContentCard.tsx", 8],
  ["src/components/ui/ContentSummary.tsx", 8],
  ["src/components/ui/Dialog.tsx", 8],
  ["src/components/ui/EmptyState.tsx", 8],
  ["src/components/ui/GlassCard.tsx", 8],
  ["src/components/ui/GlobalHapticsListener.tsx", 8],
  ["src/components/ui/Input.tsx", 8],
  ["src/components/ui/LiveRegionProvider.tsx", 8],
  ["src/components/ui/MediaSlot.tsx", 8],
  ["src/components/ui/NewsCardSkeleton.tsx", 8],
  ["src/components/ui/NotificationRelevanceScore.tsx", 8],
  ["src/components/ui/ParticleAuthBackground.tsx", 8],
  ["src/components/ui/ProfileCardSkeleton.tsx", 8],
  ["src/components/ui/ProgressBar.tsx", 8],
  ["src/components/ui/RadioGroup.tsx", 8],
  ["src/components/ui/data-table/DataTable.tsx", 8],
  ["src/components/ui/data-table/DataTableColumnHeader.tsx", 8],
  ["src/components/ui/data-table/DataTablePagination.tsx", 8],
  ["src/components/ui/data-table/dataTableFeatures.ts", 8],
  ["src/components/ui/motion/FadeIn.tsx", 8],
  ["src/components/ui/motion/ScaleIn.tsx", 8],
  ["src/components/ui/motion/StaggerChildren.tsx", 8],
  // The same run timed out with the unsplittable useProfileSync enclosing
  // range and useSessionCrypto mixed into a regular shard. Keep every emitted
  // range from both auth graphs isolated on its own first-attempt shard. A
  // range can contain an enclosing AST mutation and therefore cannot always
  // be split further without dropping a mutation from the canonical
  // denominator.
  ["src/hooks/auth/useProfileSync.ts", 600],
  ["src/hooks/auth/useSessionCrypto.ts", 260],
])
// The previous first-attempt plan reserved only eight cost-aware shards.  The
// immutable CI evidence for run 34003977528 shows that two of those shards
// still hit the 120-minute job timeout (one carried 709 mutants and one never
// produced a report).  Twelve keeps the public 64-shard denominator and
// max-parallel contract unchanged while spreading the measured static-heavy
// API ranges across enough isolated runners to stay below the observed cap.
const firstAttemptCostAwareShardCount = 12
// backendOrigin is imported by the SSR/client bootstrap graph, so even its
// tiny source file selects a broad static test set. The auth sources below
// were observed in the same multi-hour related-test graph as the timed-out
// shard 11/64. The order is deterministic so shard zero remains the
// backendOrigin-only boundary used by existing contracts. LanguageContext and
// db/index were both present in the exact 551-mutant shard 22/64 that spent
// 82% of its estimated runtime on static mutants; their ranges are therefore
// fine-grained below before the remaining weighted placement.
const firstAttemptDedicatedFiles = [
  "src/api/backendOrigin.ts",
  "src/hooks/auth/useProfileSync.ts",
  "src/hooks/auth/useSessionCrypto.ts",
]

// These module-level sources were present in the timed-out shard 22/64. Their
// static mutants force a complete test-environment reload, so keep their
// first-attempt ranges below the normal count budget before cost-aware
// packing. This changes only placement granularity; no mutant is removed.
const firstAttemptStaticHotspotFiles = new Set([
  "src/contexts/LanguageContext.tsx",
  "src/db/index.ts",
])

function firstAttemptUnitBudget(file, budget) {
  return firstAttemptStaticHotspotFiles.has(file) ? Math.max(1, Math.floor(budget / 2)) : budget
}

function mutationPatternStartsWithSource(pattern, sourcePath) {
  return pattern === sourcePath || pattern.startsWith(`${sourcePath}:`)
}

function mutationPatternSource(pattern) {
  return pattern.split(":", 1)[0]
}

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
    const source = mutationPatternSource(entry.pattern)
    const sourceFreeShards = firstAttemptStaticHotspotFiles.has(source)
      ? shards.filter(
          (shard) => !shard.files.some((pattern) => mutationPatternSource(pattern) === source)
        )
      : shards
    const staticHotspotFreeShards = firstAttemptStaticHotspotFiles.has(source)
      ? sourceFreeShards.filter(
          (shard) =>
            !shard.files.some((pattern) =>
              firstAttemptStaticHotspotFiles.has(mutationPatternSource(pattern))
            )
        )
      : sourceFreeShards
    const candidateShards =
      staticHotspotFreeShards.length > 0
        ? staticHotspotFreeShards
        : sourceFreeShards.length > 0
          ? sourceFreeShards
          : shards
    const target = candidateShards.reduce((lightest, shard) => {
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
  // Keep each dedicated range on a separate shard. This is intentionally
  // range-based: useProfileSync and useSessionCrypto contain enclosing AST
  // mutations that are not safely splittable, but their independent ranges
  // must not share a related-test graph with another source.
  const dedicatedUnits = expensiveUnits
    .filter((entry) =>
      firstAttemptDedicatedFiles.some((sourcePath) =>
        mutationPatternStartsWithSource(entry.pattern, sourcePath)
      )
    )
    .sort((left, right) => {
      const leftRank = firstAttemptDedicatedFiles.findIndex((sourcePath) =>
        mutationPatternStartsWithSource(left.pattern, sourcePath)
      )
      const rightRank = firstAttemptDedicatedFiles.findIndex((sourcePath) =>
        mutationPatternStartsWithSource(right.pattern, sourcePath)
      )
      return (
        leftRank - rightRank ||
        right.estimatedCost - left.estimatedCost ||
        right.mutantCount - left.mutantCount ||
        left.pattern.localeCompare(right.pattern)
      )
    })
  const remainingExpensiveUnits = expensiveUnits.filter((entry) => !dedicatedUnits.includes(entry))

  // Leave at least one shard for non-dedicated work whenever it exists. The
  // fallback is relevant only to tiny local inventories that request fewer
  // shards than isolated ranges; production's 64-shard universe has ample
  // capacity and gets one range per dedicated shard.
  const dedicatedShardCount = Math.min(
    dedicatedUnits.length,
    Math.max(0, shards.length - (remainingExpensiveUnits.length + regularUnits.length > 0 ? 1 : 0))
  )
  for (let index = 0; index < dedicatedShardCount; index += 1) {
    assignWeightedMutationUnits([dedicatedUnits[index]], [shards[index]])
  }
  const spilledDedicatedUnits = dedicatedUnits.slice(dedicatedShardCount)
  const remainingShards = shards.slice(dedicatedShardCount)
  if (remainingShards.length === 0) {
    assignWeightedMutationUnits(
      [...remainingExpensiveUnits, ...regularUnits, ...spilledDedicatedUnits],
      [shards[shards.length - 1]]
    )
    return
  }
  if (remainingShards.length === 1) {
    // A dedicated source already occupies the prefix. When only one shard
    // remains, it must carry both residual expensive and regular work; keep
    // any spilled dedicated ranges here rather than dropping them.
    assignWeightedMutationUnits(
      [...remainingExpensiveUnits, ...regularUnits, ...spilledDedicatedUnits],
      remainingShards
    )
    return
  }
  // Keep the expensive related-test graphs in a bounded group of dedicated shards.  The
  // lower bound guarantees that the regular units can still seed every
  // remaining shard when the inventory is small or unusually fragmented.
  const minimumExpensiveShards = Math.max(1, remainingShards.length - regularUnits.length)
  const maximumExpensiveShards =
    regularUnits.length > 0 ? remainingShards.length - 1 : remainingShards.length
  const staticHotspotUnitCount = remainingExpensiveUnits.filter((entry) =>
    firstAttemptStaticHotspotFiles.has(mutationPatternSource(entry.pattern))
  ).length
  const expensiveShardCount = Math.min(
    remainingExpensiveUnits.length,
    maximumExpensiveShards,
    Math.max(
      minimumExpensiveShards,
      Math.min(firstAttemptCostAwareShardCount, remainingShards.length),
      staticHotspotUnitCount
    )
  )
  const expensiveShards = remainingShards.slice(0, expensiveShardCount)
  const regularShards = remainingShards.slice(expensiveShardCount)

  assignWeightedMutationUnits(
    [...remainingExpensiveUnits, ...spilledDedicatedUnits],
    expensiveShards
  )
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
      budget: firstAttempt ? firstAttemptUnitBudget(file, unitBudget) : unitBudget,
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

export function isMutationRunReleaseEligible(identity, focused, env = process.env) {
  return focused === false && isReleaseEligible(identity, env)
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

export async function createExclusiveRunDirectory(runRoot) {
  await mkdir(path.dirname(runRoot), { recursive: true })
  await mkdir(runRoot, { recursive: false })
}

const windowsTemporaryCleanupRetryDelaysMs = [50, 100, 200, 400]
const transientWindowsCleanupCodes = new Set(["EPERM", "EBUSY", "ENOTEMPTY"])

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

export async function removeOwnedTemporaryDirectory(
  temporaryRoot,
  runId,
  {
    remove = rm,
    inspect = lstat,
    delay = wait,
    now = Date.now,
    platform = process.platform,
    retryDelaysMs = windowsTemporaryCleanupRetryDelaysMs,
  } = {}
) {
  const startedAt = now()
  for (let attempt = 0; ; attempt += 1) {
    try {
      assertOwnedTemporaryDirectory(temporaryRoot, runId)
      await remove(temporaryRoot, { recursive: true, force: true })
      try {
        await inspect(temporaryRoot)
      } catch (error) {
        if (error && typeof error === "object" && error.code === "ENOENT") return
        throw error
      }
      throw Object.assign(
        new Error(`Owned Stryker temp directory still exists after removal: ${temporaryRoot}`),
        { code: "ENOTEMPTY", path: temporaryRoot }
      )
    } catch (error) {
      const transient =
        platform === "win32" &&
        error &&
        typeof error === "object" &&
        transientWindowsCleanupCodes.has(error.code)
      if (!transient) throw error
      if (attempt >= retryDelaysMs.length) {
        const attempts = attempt + 1
        const elapsedMs = Math.max(0, now() - startedAt)
        throw Object.assign(
          new Error(
            `Failed to remove owned Stryker temp directory ${temporaryRoot} after ${attempts} attempts over ${elapsedMs}ms; terminal code ${error.code}: ${error.message}`,
            { cause: error }
          ),
          { attempts, code: error.code, elapsedMs, path: temporaryRoot }
        )
      }
      await delay(retryDelaysMs[attempt])
    }
  }
}

export async function finalizeMutationRun({
  primaryError,
  cancellationSignal,
  cleanupTemporary,
  releaseLock,
  revokeMarker,
}) {
  let effectivePrimaryError = primaryError
  const finalizationErrors = []
  let markerRevocationAttempted = false
  let markerRevoked = false
  const captureCancellation = () => {
    if (!effectivePrimaryError && cancellationSignal?.aborted) {
      effectivePrimaryError = cancellationReason(cancellationSignal)
    }
  }
  const runOperation = async (operation) => {
    if (!operation) return true
    try {
      await operation()
      return true
    } catch (error) {
      finalizationErrors.push(error)
      return false
    }
  }
  const requireMarkerRevocation = async () => {
    if (markerRevoked) return true
    if (markerRevocationAttempted) return false
    markerRevocationAttempted = true
    if (!revokeMarker) {
      finalizationErrors.push(
        new Error(
          "Stryker marker revocation is required but unavailable; the run lock was retained"
        )
      )
      return false
    }
    markerRevoked = await runOperation(revokeMarker)
    return markerRevoked
  }
  const ownsRunArtifacts = Boolean(releaseLock || revokeMarker)
  const markerRevocationRequired = () =>
    ownsRunArtifacts && Boolean(effectivePrimaryError || finalizationErrors.length > 0)
  captureCancellation()
  const processQuiesced = effectivePrimaryError?.processQuiesced !== false
  if (!processQuiesced) {
    if (ownsRunArtifacts) {
      finalizationErrors.push(
        new Error(
          "Stryker child close was not confirmed; the temporary directory and run lock were retained for manual process termination and cleanup"
        )
      )
      await requireMarkerRevocation()
    }
  } else {
    await runOperation(cleanupTemporary)
    captureCancellation()
    if (markerRevocationRequired()) await requireMarkerRevocation()
    if (!markerRevocationRequired() || markerRevoked) {
      let releasePreparationCalled = false
      let releaseGuardError
      const prepareRelease = async () => {
        releasePreparationCalled = true
        captureCancellation()
        if (markerRevocationRequired() && !(await requireMarkerRevocation())) {
          releaseGuardError = new Error(
            "Stryker run lock retained because marker revocation was not confirmed"
          )
          throw releaseGuardError
        }
        return () => {
          captureCancellation()
          if (markerRevocationRequired() && !markerRevoked) {
            releaseGuardError = new Error(
              "Stryker run lock retained because cancellation raced with lock release"
            )
            throw releaseGuardError
          }
        }
      }
      let releaseSucceeded = true
      if (releaseLock) {
        try {
          await releaseLock(prepareRelease)
        } catch (error) {
          releaseSucceeded = false
          if (error !== releaseGuardError) finalizationErrors.push(error)
        }
        if (!releasePreparationCalled) {
          releaseSucceeded = false
          finalizationErrors.push(
            new Error("Stryker run lock release bypassed its fail-closed preparation guard")
          )
        }
      }
      captureCancellation()
      if ((!releaseSucceeded || markerRevocationRequired()) && !markerRevoked) {
        await requireMarkerRevocation()
      }
    }
  }
  captureCancellation()
  if (!effectivePrimaryError && finalizationErrors.length === 0) return
  if (effectivePrimaryError && finalizationErrors.length === 0) throw effectivePrimaryError
  if (!effectivePrimaryError && finalizationErrors.length === 1) throw finalizationErrors[0]
  const errors = effectivePrimaryError
    ? [effectivePrimaryError, ...finalizationErrors]
    : finalizationErrors
  const cause = effectivePrimaryError ?? finalizationErrors[0]
  throw new AggregateError(
    errors,
    effectivePrimaryError?.message ?? "Mutation run finalization failed",
    { cause }
  )
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
    async release(prepareRelease) {
      if (released) return
      if (typeof prepareRelease !== "function") {
        throw new Error("Stryker run lock release requires a fail-closed preparation guard")
      }
      const current = JSON.parse(await readFile(lockPath, "utf8"))
      if (current.runId !== runId) {
        throw new Error("Refusing to release a Stryker lock owned by another run")
      }
      const commitRelease = await prepareRelease()
      if (typeof commitRelease !== "function") {
        throw new Error("Stryker run lock preparation did not return a commit guard")
      }
      commitRelease()
      rmSync(lockPath)
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

export async function persistMutationEvidence({ paths, inventory, preflight }) {
  if (paths?.allowReleaseMarkers === true) {
    const marker = await writeValidatedEvidence({
      outputRoot: paths.outputRoot,
      inventory,
      preflight,
    })
    return { inventorySha256: marker.inventorySha256, markerWritten: true }
  }
  if (paths?.allowReleaseMarkers !== false || typeof paths.outputRoot !== "string") {
    throw new Error("Mutation evidence paths are invalid")
  }
  if (inventory?.releaseEligible !== false) {
    throw new Error("Focused mutation evidence cannot be release eligible")
  }
  if (inventory?.summary?.viableMutantScore !== 100) {
    throw new Error("Focused evidence requires a 100% viable mutation score")
  }
  if (preflight?.runId !== inventory?.runId) {
    throw new Error("Preflight and inventory must belong to the same Stryker run")
  }
  const inventoryText = `${JSON.stringify(inventory, null, 2)}\n`
  const preflightText = `${JSON.stringify(preflight, null, 2)}\n`
  await Promise.all([
    atomicText(path.join(paths.outputRoot, "inventory.json"), inventoryText),
    atomicText(path.join(paths.outputRoot, "preflight.json"), preflightText),
  ])
  return { inventorySha256: sha256(inventoryText), markerWritten: false }
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
    if (shard.shardEvidence.windowsProcessHost !== undefined) {
      assertWindowsProcessHostEvidence(shard.shardEvidence.windowsProcessHost)
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
      ...(shard.shardEvidence.windowsProcessHost
        ? { windowsProcessHost: shard.shardEvidence.windowsProcessHost }
        : {}),
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

const childTerminationCommandTimeoutMs = 10_000
const childTerminationGraceMs = 15_000
const processTreeQuiescencePollMs = 25
const windowsProcessHostProtocolVersion = 1
const windowsProcessHostStatusTimeoutMs = childTerminationCommandTimeoutMs
const windowsProcessHostProjectPath = path.join(
  frontendRoot,
  "tools",
  "stryker-process-host",
  "Cargo.toml"
)
const windowsProcessHostBinaryPath = path.join(
  frontendRoot,
  "tools",
  "stryker-process-host",
  "target",
  "release",
  "stryker-process-host.exe"
)
const windowsProcessHostSourcePaths = [
  path.join(frontendRoot, "tools", "stryker-process-host", "Cargo.toml"),
  path.join(frontendRoot, "tools", "stryker-process-host", "Cargo.lock"),
  path.join(frontendRoot, "tools", "stryker-process-host", "src", "main.rs"),
]
let windowsProcessHostBuildPromise

function cancellationReason(signal) {
  if (signal?.reason instanceof Error) return signal.reason
  return new Error("Stryker execution was interrupted")
}

export function throwIfCancellationRequested(signal) {
  if (signal?.aborted) throw cancellationReason(signal)
}

export function installProcessSignalCancellation({
  processEvents = process,
  controller = new AbortController(),
} = {}) {
  const handlers = new Map()
  for (const signalName of ["SIGINT", "SIGTERM"]) {
    const handler = () => {
      if (controller.signal.aborted) return
      const error = Object.assign(new Error(`Stryker execution interrupted by ${signalName}`), {
        code: "STRYKER_INTERRUPTED",
        signalName,
      })
      controller.abort(error)
    }
    handlers.set(signalName, handler)
    processEvents.on(signalName, handler)
  }
  let disposed = false
  return {
    signal: controller.signal,
    dispose() {
      if (disposed) return
      disposed = true
      for (const [signalName, handler] of handlers) {
        processEvents.removeListener(signalName, handler)
      }
    },
  }
}

function interruptedSignal(error, seen = new Set()) {
  if (!error || typeof error !== "object" || seen.has(error)) return undefined
  seen.add(error)
  if (error.code === "STRYKER_INTERRUPTED") {
    if (error.signalName === "SIGINT" || error.signalName === "SIGTERM") {
      return error.signalName
    }
  }
  return interruptedSignal(error.cause, seen)
}

export function runnerExitCode(error) {
  const signal = interruptedSignal(error)
  if (signal === "SIGINT") return 130
  if (signal === "SIGTERM") return 143
  return 1
}

function assertPositiveProcessId(pid, description) {
  if (!Number.isSafeInteger(pid) || pid <= 0) {
    throw new Error(`${description} must be a positive safe integer`)
  }
}

export function processTreeSpawnOptions(platform = process.platform) {
  return {
    detached: platform !== "win32",
    windowsHide: true,
  }
}

function assertWindowsJobToken(value, description = "Windows process-host job token") {
  if (typeof value !== "string" || !/^[a-z0-9_-]{1,128}$/iu.test(value) || value.length > 128) {
    throw new Error(`${description} has an unsafe shape`)
  }
}

function assertWindowsProcessHostEvidence(value, description = "Windows process-host evidence") {
  assertExactObjectKeys(value, ["sourceSha256", "binarySha256"], description)
  assertSha256(value.sourceSha256, `${description} source digest`)
  assertSha256(value.binarySha256, `${description} binary digest`)
  return value
}

function isAbsoluteWindowsPath(value) {
  return path.isAbsolute(value) || path.win32.isAbsolute(value)
}

export function createWindowsJobOwnership(
  child,
  {
    statusPath,
    jobToken,
    control,
    hostSourceSha256,
    hostBinarySha256,
    protocolVersion = windowsProcessHostProtocolVersion,
  } = {}
) {
  assertPositiveProcessId(child?.pid, "Stryker Windows process-host PID")
  if (
    typeof statusPath !== "string" ||
    !isAbsoluteWindowsPath(statusPath) ||
    statusPath.includes("\0")
  ) {
    throw new Error("Windows process-host status path is required")
  }
  assertWindowsJobToken(jobToken)
  if (protocolVersion !== windowsProcessHostProtocolVersion) {
    throw new Error("Windows process-host protocol version is unsupported")
  }
  if (!control || typeof control.write !== "function") {
    throw new Error("Windows process-host control pipe is required")
  }
  if (hostSourceSha256 !== undefined) assertSha256(hostSourceSha256, "Windows host source digest")
  if (hostBinarySha256 !== undefined) assertSha256(hostBinarySha256, "Windows host binary digest")
  return Object.freeze({
    kind: "windows-job-object",
    rootPid: child.pid,
    hostPid: child.pid,
    statusPath,
    jobToken,
    protocolVersion,
    control,
    ...(hostSourceSha256 ? { hostSourceSha256 } : {}),
    ...(hostBinarySha256 ? { hostBinarySha256 } : {}),
  })
}

export function createProcessTreeOwnership(
  child,
  { platform = process.platform, windowsJob } = {}
) {
  assertPositiveProcessId(child.pid, "Stryker child PID")
  if (platform === "win32") {
    if (windowsJob) return createWindowsJobOwnership(child, windowsJob)
    return Object.freeze({ kind: "windows-process-tree", rootPid: child.pid })
  }
  return Object.freeze({
    kind: "posix-process-group",
    rootPid: child.pid,
    groupId: child.pid,
  })
}

function assertProcessTreeOwnership(child, ownership) {
  if (!ownership || typeof ownership !== "object") {
    throw new Error("Stryker process-tree ownership is required")
  }
  assertPositiveProcessId(child.pid, "Stryker child PID")
  assertPositiveProcessId(ownership.rootPid, "Stryker process-tree root PID")
  if (ownership.rootPid !== child.pid) {
    throw new Error("Stryker process-tree ownership does not match the child PID")
  }
  if (ownership.kind === "windows-process-tree") return
  if (ownership.kind === "windows-job-object") {
    if (ownership.hostPid !== ownership.rootPid) {
      throw new Error("Windows process-host identity does not match its owned root")
    }
    assertPositiveProcessId(ownership.hostPid, "Stryker Windows process-host PID")
    if (
      typeof ownership.statusPath !== "string" ||
      !isAbsoluteWindowsPath(ownership.statusPath) ||
      ownership.statusPath.includes("\0")
    ) {
      throw new Error("Windows process-host status path is invalid")
    }
    assertWindowsJobToken(ownership.jobToken)
    if (ownership.protocolVersion !== windowsProcessHostProtocolVersion) {
      throw new Error("Windows process-host protocol version is unsupported")
    }
    if (!ownership.control || typeof ownership.control.write !== "function") {
      throw new Error("Windows process-host control pipe is required")
    }
    return
  }
  if (ownership.kind !== "posix-process-group") {
    throw new Error("Stryker process-tree ownership kind is invalid")
  }
  assertPositiveProcessId(ownership.groupId, "Stryker process-group ID")
  if (ownership.groupId !== ownership.rootPid) {
    throw new Error("Stryker process group must be led by the owned child")
  }
}

const windowsProcessHostStatusKeys = [
  "schemaVersion",
  "protocolVersion",
  "state",
  "hostPid",
  "targetPid",
  "jobToken",
  "exitCode",
  "quiesced",
  "readyAcknowledged",
  "reason",
]
const windowsProcessHostFinalStates = new Set(["job_empty", "job_terminated"])

export function parseWindowsProcessHostStatus(text) {
  let status
  try {
    status = JSON.parse(text)
  } catch (error) {
    throw new Error(`Windows process-host status is not valid JSON: ${error.message}`)
  }
  assertExactObjectKeys(status, windowsProcessHostStatusKeys, "Windows process-host status")
  if (status.schemaVersion !== 1 || status.protocolVersion !== windowsProcessHostProtocolVersion) {
    throw new Error("Windows process-host status protocol version is unsupported")
  }
  if (
    typeof status.state !== "string" ||
    !/^(?:starting|ready|job_empty|job_terminated|error)$/u.test(status.state)
  ) {
    throw new Error("Windows process-host status state is invalid")
  }
  if (!Number.isSafeInteger(status.hostPid) || status.hostPid <= 0) {
    throw new Error("Windows process-host status host PID is invalid")
  }
  if (
    status.targetPid !== null &&
    (!Number.isSafeInteger(status.targetPid) || status.targetPid <= 0)
  ) {
    throw new Error("Windows process-host status target PID is invalid")
  }
  assertWindowsJobToken(status.jobToken, "Windows process-host status job token")
  if (status.exitCode !== null && (!Number.isInteger(status.exitCode) || status.exitCode < 0)) {
    throw new Error("Windows process-host status exit code is invalid")
  }
  if (typeof status.quiesced !== "boolean") {
    throw new Error("Windows process-host status quiescence flag is invalid")
  }
  if (typeof status.readyAcknowledged !== "boolean") {
    throw new Error("Windows process-host READY acknowledgement is invalid")
  }
  if (status.reason !== null && typeof status.reason !== "string") {
    throw new Error("Windows process-host status reason is invalid")
  }
  return status
}

async function readWindowsProcessHostStatus(statusPath) {
  try {
    return parseWindowsProcessHostStatus(await readFile(statusPath, "utf8"))
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") return undefined
    throw error
  }
}

function assertWindowsProcessHostStatusIdentity(status, ownership) {
  if (
    status.hostPid !== ownership.hostPid ||
    status.jobToken !== ownership.jobToken ||
    status.protocolVersion !== ownership.protocolVersion
  ) {
    throw new Error("Windows process-host status identity does not match its owned job")
  }
}

async function waitForWindowsProcessHostTerminalStatus(
  ownership,
  {
    readStatus = readWindowsProcessHostStatus,
    delay = wait,
    now = () => performance.now(),
    timeoutMs = windowsProcessHostStatusTimeoutMs,
    requireReady = false,
  } = {}
) {
  const startedAt = now()
  let readySeen = false
  for (;;) {
    const status = await readStatus(ownership.statusPath)
    if (status) {
      assertWindowsProcessHostStatusIdentity(status, ownership)
      if (status.state === "ready") readySeen = true
      if (status.state === "error") {
        throw new Error(
          `Windows process-host reported ${status.reason ?? "an unspecified lifecycle failure"}`
        )
      }
      if (windowsProcessHostFinalStates.has(status.state)) {
        if (requireReady && !readySeen && status.readyAcknowledged !== true) {
          throw new Error("Windows process-host closed without a READY acknowledgement")
        }
        if (status.quiesced !== true) {
          throw new Error("Windows process-host did not confirm an empty owned job")
        }
        return status
      }
    }
    const elapsedMs = Math.max(0, now() - startedAt)
    if (elapsedMs >= timeoutMs) {
      throw new Error(`Windows process-host status did not prove quiescence within ${timeoutMs}ms`)
    }
    await delay(Math.min(processTreeQuiescencePollMs, timeoutMs - elapsedMs))
  }
}

export async function verifyWindowsJobQuiescence(ownership, options = {}) {
  if (ownership?.kind !== "windows-job-object") {
    throw new Error("Only an owned Windows Job Object supports independent liveness verification")
  }
  assertWindowsJobToken(ownership.jobToken)
  const status = await waitForWindowsProcessHostTerminalStatus(ownership, {
    ...options,
    requireReady: true,
  })
  return status.quiesced === true
}

const windowsJobTerminationPromises = new WeakMap()

async function terminateWindowsJobHost(child, ownership, options = {}) {
  if (child.exitCode !== null || child.signalCode !== null) {
    throw new Error(
      "Stryker Windows process-host exited before durable job termination could be proven"
    )
  }
  const existing = windowsJobTerminationPromises.get(ownership)
  if (existing) return existing
  const termination = (async () => {
    await new Promise((resolve, reject) => {
      try {
        ownership.control.write("TERMINATE\n", (error) => (error ? reject(error) : resolve()))
      } catch (error) {
        reject(error)
      }
    })
    await waitForWindowsProcessHostTerminalStatus(ownership, {
      ...options,
      requireReady: false,
    })
    return true
  })()
  windowsJobTerminationPromises.set(ownership, termination)
  return termination
}

function directChildKillFailure(child) {
  try {
    if (child.kill("SIGKILL") === false) {
      return new Error("Stryker direct child kill returned false")
    }
  } catch (error) {
    return error
  }
  return undefined
}

function treeTerminationFailure(treeError, directError) {
  if (!directError) return treeError
  return new AggregateError(
    [treeError, directError],
    `${treeError.message}; direct child fallback also failed`,
    { cause: treeError }
  )
}

export async function verifyOwnedProcessTreeQuiescence(
  ownership,
  {
    signalProcess = (pid, signal) => process.kill(pid, signal),
    delay = wait,
    now = () => performance.now(),
    groupVerificationTimeoutMs = childTerminationCommandTimeoutMs,
    groupVerificationPollMs = processTreeQuiescencePollMs,
  } = {}
) {
  if (ownership?.kind !== "posix-process-group") {
    throw new Error("Only an owned POSIX process group supports independent liveness verification")
  }
  assertPositiveProcessId(ownership.groupId, "Stryker process-group ID")
  const startedAt = now()
  for (;;) {
    try {
      signalProcess(-ownership.groupId, 0)
    } catch (error) {
      if (error?.code === "ESRCH") return true
      throw error
    }
    const elapsedMs = Math.max(0, now() - startedAt)
    if (elapsedMs >= groupVerificationTimeoutMs) {
      throw new Error(
        `Stryker process group ${ownership.groupId} remained live after ${groupVerificationTimeoutMs}ms`
      )
    }
    await delay(Math.min(groupVerificationPollMs, groupVerificationTimeoutMs - elapsedMs))
  }
}

export async function terminateOwnedProcessTree(
  child,
  ownership,
  {
    execFileCommand = execFileAsync,
    signalProcess = (pid, signal) => process.kill(pid, signal),
    delay = wait,
    now = () => performance.now(),
    readStatus = readWindowsProcessHostStatus,
    groupVerificationTimeoutMs = childTerminationCommandTimeoutMs,
    groupVerificationPollMs = processTreeQuiescencePollMs,
  } = {}
) {
  assertProcessTreeOwnership(child, ownership)
  if (child.exitCode !== null || child.signalCode !== null) {
    if (ownership.kind === "posix-process-group") {
      return verifyOwnedProcessTreeQuiescence(ownership, {
        signalProcess,
        delay,
        now,
        groupVerificationTimeoutMs,
        groupVerificationPollMs,
      })
    }
    throw new Error(
      ownership.kind === "windows-job-object"
        ? "Stryker Windows process-host exited before durable job termination could be proven"
        : "Stryker Windows process-tree root exited before tree termination could be proven"
    )
  }
  if (ownership.kind === "windows-job-object") {
    return terminateWindowsJobHost(child, ownership, {
      readStatus,
      delay,
      now,
      timeoutMs: groupVerificationTimeoutMs,
    })
  }
  if (ownership.kind === "windows-process-tree") {
    try {
      await execFileCommand("taskkill", ["/pid", String(ownership.rootPid), "/t", "/f"], {
        timeout: childTerminationCommandTimeoutMs,
        windowsHide: true,
      })
      const failure = new Error(
        "Legacy Windows PID tree termination is diagnostic-only and cannot prove process quiescence"
      )
      failure.processQuiesced = false
      throw failure
    } catch (treeError) {
      if (treeError?.processQuiesced === false) throw treeError
      throw treeTerminationFailure(treeError, directChildKillFailure(child))
    }
  }

  try {
    signalProcess(-ownership.groupId, "SIGKILL")
  } catch (treeError) {
    if (treeError?.code === "ESRCH") return true
    throw treeTerminationFailure(treeError, directChildKillFailure(child))
  }
  return verifyOwnedProcessTreeQuiescence(ownership, {
    signalProcess,
    delay,
    now,
    groupVerificationTimeoutMs,
    groupVerificationPollMs,
  })
}

export function waitForChildClose(
  child,
  {
    description,
    timeoutMs,
    abortSignal,
    processTreeOwnership,
    terminate = terminateOwnedProcessTree,
    verifyProcessTree = verifyOwnedProcessTreeQuiescence,
    verifyWindowsJob = verifyWindowsJobQuiescence,
    terminationGraceMs = childTerminationGraceMs,
    scheduleTimeout = setTimeout,
    cancelTimeout = clearTimeout,
  }
) {
  return new Promise((resolve, reject) => {
    let settled = false
    let terminationStarted = false
    let primaryTerminationError
    let primaryTerminationSecondaryErrors = []
    let processError
    let exitResult
    let closeResult
    let terminationSettled = false
    let terminationError
    let terminationConfirmed = false
    let processErrorDuringTermination = false
    let postCloseVerificationStarted = false
    let postExitFailure
    let graceTimer
    let timeoutTimer

    const detachListeners = () => {
      child.removeListener("error", onError)
      child.removeListener("exit", onExit)
      child.removeListener("close", onClose)
      abortSignal?.removeEventListener("abort", onAbort)
    }
    const settle = (error) => {
      if (settled) return
      settled = true
      if (timeoutTimer !== undefined) cancelTimeout(timeoutTimer)
      if (graceTimer !== undefined) cancelTimeout(graceTimer)
      detachListeners()
      if (error) reject(error)
      else resolve()
    }
    const terminationFailure = (secondaryErrors = [], processQuiesced = true) => {
      const primaryError = primaryTerminationError
      const allSecondaryErrors = [...primaryTerminationSecondaryErrors, ...secondaryErrors]
      const failure =
        allSecondaryErrors.length === 0
          ? primaryError
          : new AggregateError(
              [primaryError, ...allSecondaryErrors],
              `${primaryError.message}; process shutdown failed`,
              { cause: primaryError }
            )
      failure.processQuiesced = processQuiesced
      return failure
    }
    const finishTerminatedExecution = () => {
      if (!closeResult || !terminationSettled) return
      settle(
        terminationFailure(
          terminationError ? [terminationError] : [],
          terminationError === undefined && terminationConfirmed && !processErrorDuringTermination
        )
      )
    }
    const beginTermination = (primaryError) => {
      if (settled || terminationStarted) return
      terminationStarted = true
      primaryTerminationError = processError ?? primaryError
      primaryTerminationSecondaryErrors = processError ? [primaryError] : []
      if (timeoutTimer !== undefined) cancelTimeout(timeoutTimer)
      graceTimer = scheduleTimeout(() => {
        if (settled) return
        const secondaryErrors = terminationError ? [terminationError] : []
        secondaryErrors.push(
          new Error(`${description} did not terminate and close within ${terminationGraceMs}ms`)
        )
        settle(terminationFailure(secondaryErrors, false))
      }, terminationGraceMs)
      void Promise.resolve()
        .then(() => terminate(child, processTreeOwnership))
        .then(
          (confirmation) => {
            if (confirmation !== true) {
              terminationError = new Error(
                `${description} tree terminator did not confirm process-tree quiescence`
              )
            } else {
              terminationConfirmed = true
            }
            terminationSettled = true
            finishTerminatedExecution()
          },
          (error) => {
            terminationError = error
            terminationSettled = true
            finishTerminatedExecution()
          }
        )
    }
    const postCloseFailure = (primaryError, secondaryErrors, processQuiesced) => {
      const failure =
        secondaryErrors.length === 0
          ? primaryError
          : new AggregateError(
              [primaryError, ...secondaryErrors],
              `${primaryError.message}; process-tree quiescence was not confirmed`,
              { cause: primaryError }
            )
      failure.processQuiesced = processQuiesced
      return failure
    }
    const beginPostExitFailure = (error) => {
      if (!postExitFailure) postExitFailure = error
      if (timeoutTimer !== undefined) cancelTimeout(timeoutTimer)
      if (graceTimer !== undefined) return
      graceTimer = scheduleTimeout(() => {
        if (settled) return
        const primaryError = processError ?? postExitFailure
        const secondaryErrors = processError ? [postExitFailure] : []
        secondaryErrors.push(
          new Error(`${description} did not close after its process-tree root exited`)
        )
        settle(postCloseFailure(primaryError, secondaryErrors, false))
      }, terminationGraceMs)
    }
    const onTimeout = () => {
      const error = new Error(`${description} exceeded ${timeoutMs}ms`)
      if (exitResult) beginPostExitFailure(error)
      else beginTermination(error)
    }
    const onAbort = () => {
      const error = cancellationReason(abortSignal)
      if (exitResult) beginPostExitFailure(error)
      else beginTermination(error)
    }
    const onError = (error) => {
      processError = error
      if (terminationStarted) {
        processErrorDuringTermination = true
        primaryTerminationSecondaryErrors.push(error)
      }
    }
    const onExit = (code, signal) => {
      exitResult = { code, signal }
    }
    const verifyPostCloseProcessTree = (primaryError) => {
      if (postCloseVerificationStarted) return
      postCloseVerificationStarted = true
      if (timeoutTimer !== undefined) cancelTimeout(timeoutTimer)
      const finishVerification = (verificationError, processQuiesced) => {
        if (settled) return
        let effectivePrimary = primaryError
        const secondaryErrors = []
        if (postExitFailure && postExitFailure !== effectivePrimary) {
          if (effectivePrimary) secondaryErrors.push(postExitFailure)
          else effectivePrimary = postExitFailure
        }
        if (verificationError) {
          if (effectivePrimary) secondaryErrors.push(verificationError)
          else effectivePrimary = verificationError
        }
        if (!effectivePrimary) {
          settle()
          return
        }
        settle(postCloseFailure(effectivePrimary, secondaryErrors, processQuiesced))
      }
      if (processTreeOwnership?.kind === "windows-job-object") {
        void Promise.resolve()
          .then(() => verifyWindowsJob(processTreeOwnership))
          .then(
            (confirmation) => {
              if (confirmation !== true) {
                finishVerification(
                  new Error(
                    `${description} verifier did not confirm durable Windows job quiescence after exit`
                  ),
                  false
                )
                return
              }
              finishVerification(undefined, true)
            },
            (error) => {
              finishVerification(error, false)
            }
          )
        return
      }
      if (processTreeOwnership?.kind === "windows-process-tree") {
        if (primaryError || postExitFailure) {
          // Preserve the established diagnostics for an already-failed legacy
          // injected seam, while refusing to release a normal PID-only close.
          finishVerification(undefined, false)
          return
        }
        finishVerification(
          new Error("Windows process-tree completion requires durable Windows job proof"),
          false
        )
        return
      }
      if (processTreeOwnership?.kind !== "posix-process-group") {
        finishVerification(undefined, !Number.isSafeInteger(child.pid))
        return
      }
      void Promise.resolve()
        .then(() => verifyProcessTree(processTreeOwnership))
        .then(
          (confirmation) => {
            if (confirmation !== true) {
              finishVerification(
                new Error(
                  `${description} verifier did not confirm process-tree quiescence after exit`
                ),
                false
              )
              return
            }
            finishVerification(undefined, true)
          },
          (error) => {
            finishVerification(error, false)
          }
        )
    }
    const onClose = (code, signal) => {
      closeResult = { code, signal }
      if (terminationStarted) {
        finishTerminatedExecution()
        return
      }
      const result = exitResult ?? closeResult
      let primaryError = processError
      if (!primaryError && result.signal) {
        primaryError = new Error(`${description} exited due to signal ${result.signal}`)
      }
      if (!primaryError && result.code !== 0) {
        primaryError = new Error(`${description} exited with code ${result.code}`)
      }
      if (primaryError || postExitFailure) {
        verifyPostCloseProcessTree(primaryError)
      } else if (processTreeOwnership) {
        verifyPostCloseProcessTree()
      } else if (result.code === 0) settle()
    }
    child.once("error", onError)
    child.once("exit", onExit)
    child.once("close", onClose)
    abortSignal?.addEventListener("abort", onAbort)
    timeoutTimer = scheduleTimeout(onTimeout, timeoutMs)
    if (abortSignal?.aborted) onAbort()
  })
}

async function windowsProcessHostProvenance() {
  const sourceBytes = await Promise.all(windowsProcessHostSourcePaths.map((file) => readFile(file)))
  const sourceSha256 = sha256(
    Buffer.concat(
      sourceBytes.map((bytes, index) => {
        const relative = normalizePath(
          path.relative(repositoryRoot, windowsProcessHostSourcePaths[index])
        )
        return Buffer.concat([
          Buffer.from(`${relative}\0`, "utf8"),
          bytes,
          Buffer.from("\0", "utf8"),
        ])
      })
    )
  )
  return { sourceSha256 }
}

async function ensureWindowsProcessHost() {
  if (process.platform !== "win32") {
    throw Object.assign(new Error("Windows process-host requested on an unsupported platform"), {
      processQuiesced: false,
    })
  }
  if (!windowsProcessHostBuildPromise) {
    windowsProcessHostBuildPromise = (async () => {
      let provenance
      try {
        provenance = await windowsProcessHostProvenance()
      } catch (error) {
        const failure = new Error(
          `Windows process-host source provenance is unavailable: ${error instanceof Error ? error.message : String(error)}`
        )
        failure.cause = error
        failure.processQuiesced = false
        throw failure
      }
      try {
        await execFileAsync(
          "cargo",
          [
            "build",
            "--release",
            "--locked",
            "--offline",
            "--manifest-path",
            windowsProcessHostProjectPath,
          ],
          {
            cwd: frontendRoot,
            encoding: "utf8",
            maxBuffer: 8 * 1024 * 1024,
          }
        )
      } catch (error) {
        const failure = new Error(
          `Windows process-host build failed closed: ${error instanceof Error ? error.message : String(error)}`
        )
        failure.cause = error
        failure.processQuiesced = false
        throw failure
      }
      let postBuildProvenance
      try {
        postBuildProvenance = await windowsProcessHostProvenance()
      } catch (error) {
        const failure = new Error(
          `Windows process-host source provenance changed or became unavailable after build: ${error instanceof Error ? error.message : String(error)}`
        )
        failure.cause = error
        failure.processQuiesced = false
        throw failure
      }
      if (postBuildProvenance.sourceSha256 !== provenance.sourceSha256) {
        const failure = new Error("Windows process-host source changed during its trusted build")
        failure.processQuiesced = false
        throw failure
      }
      let binary
      try {
        const binaryStats = await lstat(windowsProcessHostBinaryPath)
        if (!binaryStats.isFile() || binaryStats.isSymbolicLink()) {
          throw new Error("Windows process-host executable is not a regular file")
        }
        binary = await readFile(windowsProcessHostBinaryPath)
      } catch (error) {
        const failure = new Error("Windows process-host build produced no trusted executable")
        failure.cause = error
        failure.processQuiesced = false
        throw failure
      }
      if (binary.length === 0) {
        const failure = new Error("Windows process-host executable is empty")
        failure.processQuiesced = false
        throw failure
      }
      return {
        binaryPath: windowsProcessHostBinaryPath,
        hostSourceSha256: provenance.sourceSha256,
        hostBinarySha256: sha256(binary),
      }
    })()
  }
  return windowsProcessHostBuildPromise
}

async function spawnWindowsJobHost(args, env) {
  const provenance = await ensureWindowsProcessHost()
  const temporaryRoot = env?.STRYKER_TEMP_DIR
  if (typeof temporaryRoot !== "string" || !path.isAbsolute(temporaryRoot)) {
    const error = new Error("Windows process-host requires an absolute STRYKER_TEMP_DIR")
    error.processQuiesced = false
    throw error
  }
  const statusPath = path.join(temporaryRoot, `.windows-process-host-${randomUUID()}.json`)
  const jobToken = randomUUID()
  const hostArgs = [
    "--target",
    process.execPath,
    "--cwd",
    frontendRoot,
    "--status",
    statusPath,
    "--token",
    jobToken,
  ]
  for (const argument of args) {
    if (typeof argument !== "string" || argument.includes("\0")) {
      const error = new Error("Windows process-host target arguments must be NUL-free strings")
      error.processQuiesced = false
      throw error
    }
    hostArgs.push("--arg", argument)
  }
  let child
  try {
    child = spawn(provenance.binaryPath, hostArgs, {
      cwd: frontendRoot,
      env,
      shell: false,
      stdio: ["pipe", "inherit", "inherit"],
      windowsHide: true,
    })
  } catch (error) {
    const failure = new Error(
      `Windows process-host could not start: ${error instanceof Error ? error.message : String(error)}`
    )
    failure.cause = error
    failure.processQuiesced = false
    throw failure
  }
  return {
    child,
    statusPath,
    jobToken,
    hostSourceSha256: provenance.hostSourceSha256,
    hostBinarySha256: provenance.hostBinarySha256,
    protocolVersion: windowsProcessHostProtocolVersion,
  }
}

async function runNode(args, description, env, timeoutMs, abortSignal) {
  throwIfCancellationRequested(abortSignal)
  if (process.platform === "win32") {
    const hosted = await spawnWindowsJobHost(args, env)
    if (!Number.isSafeInteger(hosted.child.pid)) {
      const error = new Error(`${description} process-host did not expose a safe PID`)
      error.processQuiesced = false
      throw error
    }
    const processTreeOwnership = createProcessTreeOwnership(hosted.child, {
      platform: "win32",
      windowsJob: {
        statusPath: hosted.statusPath,
        jobToken: hosted.jobToken,
        control: hosted.child.stdin,
        protocolVersion: hosted.protocolVersion,
        hostSourceSha256: hosted.hostSourceSha256,
        hostBinarySha256: hosted.hostBinarySha256,
      },
    })
    await waitForChildClose(hosted.child, {
      description,
      timeoutMs,
      abortSignal,
      processTreeOwnership,
    })
    return {
      sourceSha256: hosted.hostSourceSha256,
      binarySha256: hosted.hostBinarySha256,
    }
  }
  const child = spawn(process.execPath, args, {
    cwd: frontendRoot,
    env,
    stdio: "inherit",
    shell: false,
    ...processTreeSpawnOptions(process.platform),
  })
  const processTreeOwnership = Number.isSafeInteger(child.pid)
    ? createProcessTreeOwnership(child)
    : undefined
  await waitForChildClose(child, {
    description,
    timeoutMs,
    abortSignal,
    processTreeOwnership,
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

export async function captureEvidence(sourceFiles) {
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

export async function runPool(items, concurrency, worker, { abortSignal } = {}) {
  throwIfCancellationRequested(abortSignal)
  let nextIndex = 0
  let stopScheduling = false
  const results = new Array(items.length)
  const workers = await Promise.allSettled(
    Array.from({ length: Math.min(concurrency, items.length) }, async () => {
      while (!stopScheduling && nextIndex < items.length) {
        throwIfCancellationRequested(abortSignal)
        const index = nextIndex
        nextIndex += 1
        try {
          results[index] = await worker(items[index], index)
        } catch (error) {
          stopScheduling = true
          throw error
        }
      }
    })
  )
  const errors = workers
    .filter((result) => result.status === "rejected")
    .map((result) => result.reason)
  if (errors.length === 1) throw errors[0]
  if (errors.length > 1) {
    const failure = new AggregateError(
      errors,
      `Multiple Stryker shard workers failed: ${errors[0]?.message ?? "unknown error"}`,
      { cause: errors[0] }
    )
    failure.processQuiesced = errors.every((error) => error?.processQuiesced !== false)
    throw failure
  }
  throwIfCancellationRequested(abortSignal)
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
      if (evidence.windowsProcessHost !== undefined) {
        assertWindowsProcessHostEvidence(evidence.windowsProcessHost)
      }
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
  const cancellation = installProcessSignalCancellation()
  const started = Date.now()
  const runId = randomUUID()
  let lock
  let runPaths
  let focusedMutationRun = false
  let temporaryRoot
  let primaryError
  try {
    throwIfCancellationRequested(cancellation.signal)
    const artifactExecution = preflightArtifactExecution()
    const policy = JSON.parse(await readFile(sourcePolicyPath, "utf8"))
    const policySourceFiles = await listPolicyFiles(policy)
    const sourceSelection = resolveMutationSourceSelection(policySourceFiles)
    focusedMutationRun = sourceSelection.focused
    const sourceFiles = sourceSelection.sourceFiles
    runPaths = mutationRunPaths(sourceSelection)
    throwIfCancellationRequested(cancellation.signal)
    lock = await acquireRunLock(runPaths.lockPath, runId)
    throwIfCancellationRequested(cancellation.signal)
    if (artifactExecution.mode !== "validate") {
      await cleanupCanonicalArtifacts(runPaths.outputRoot)
    }
    throwIfCancellationRequested(cancellation.signal)
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
      const historicalCostArtifact = focusedMutationRun
        ? undefined
        : await loadHistoricalCostArtifact({
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
    throwIfCancellationRequested(cancellation.signal)
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
          ? path.join(runPaths.outputRoot, "runs", runId)
          : path.join(runPaths.outputRoot, "shards")
      await createExclusiveRunDirectory(runRoot)
      const executionPlan =
        externalShardIndex === undefined ? shardPlan : [shardPlan[externalShardIndex]]
      shardResults = await runPool(
        executionPlan,
        shardParallelism,
        async (shard) => {
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
          const windowsProcessHost = await runNode(
            [strykerEntry, "run"],
            `Stryker ${shard.id}`,
            {
              ...buildStrykerChildEnvironment(),
              STRYKER_CONCURRENCY: String(runnerConcurrency),
              STRYKER_TEMP_DIR: shardTemp,
              STRYKER_JSON_REPORT: reportPath,
              STRYKER_MUTATE_JSON: JSON.stringify(shard.files),
              STRYKER_SHARD_RUN: "1",
            },
            shardTimeoutMs,
            cancellation.signal
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
            ...(windowsProcessHost ? { windowsProcessHost } : {}),
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
            ...(windowsProcessHost ? { windowsProcessHost } : {}),
          }
        },
        { abortSignal: cancellation.signal }
      )
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
    if (
      runPaths.historicalCostOutputPath !== null &&
      shardTimingValues.every((durationMs) => durationMs !== undefined)
    ) {
      const historicalCostArtifact = buildHistoricalCostArtifactFromShardTimings({
        sourceRevision: before,
        config: historicalCostConfig,
        preflightByFile,
        shardResults,
      })
      await atomicText(runPaths.historicalCostOutputPath, jsonText(historicalCostArtifact))
    }
    if (serializedPreflight === undefined) {
      throw new Error("Aggregate Stryker evidence requires a canonical preflight universe")
    }
    const expectedPatterns = focusedMutationRun ? sourceFiles : mutationPatternsFromPolicy(policy)
    const report = mergeShardReports({
      shards: shardResults,
      expectedPatterns,
      preflightByFile,
      sourceByFile,
    })
    const reportText = jsonText(report)
    const reportPath = path.join(runPaths.outputRoot, "mutation.json")
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
      await removeOwnedTemporaryDirectory(temporaryRoot, runId)
      temporaryRoot = undefined
    }
    const finalSnapshot = await captureEvidence(sourceFiles)
    assertEvidenceUnchanged(before, finalSnapshot.identity)
    const releaseEligible = isMutationRunReleaseEligible(finalSnapshot.identity, focusedMutationRun)
    const windowsProcessHosts = shardResults.map(
      (shard) => shard.windowsProcessHost ?? shard.shardEvidence?.windowsProcessHost
    )
    const windowsProcessHost = windowsProcessHosts.find((value) => value !== undefined)
    if (windowsProcessHost !== undefined) {
      assertWindowsProcessHostEvidence(windowsProcessHost)
      if (
        windowsProcessHosts.some(
          (value) =>
            value === undefined || JSON.stringify(value) !== JSON.stringify(windowsProcessHost)
        )
      ) {
        throw new Error("Stryker shard evidence has inconsistent Windows process-host provenance")
      }
    }
    const inventory = {
      schemaVersion: "2.0",
      runId,
      revision: before.revision,
      sourceRevision: before,
      generatedAt: new Date().toISOString(),
      durationMs: Date.now() - started,
      releaseEligible,
      scope: focusedMutationRun
        ? { kind: "local-focused", sourceFiles }
        : { kind: "canonical", sourceFiles },
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
        ...(windowsProcessHost ? { windowsProcessHost } : {}),
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
        path: normalizePath(
          path.relative(repositoryRoot, path.join(runPaths.outputRoot, "preflight.json"))
        ),
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
    const persisted = await persistMutationEvidence({ paths: runPaths, inventory, preflight })
    process.stdout.write(
      `Validated ${inventory.summary.denominatorFiles} frontend source files and ${inventory.summary.totalMutants} mutants at ${inventory.summary.viableMutantScore}% (${persisted.inventorySha256})\n`
    )
  } catch (error) {
    primaryError = error
  } finally {
    try {
      await finalizeMutationRun({
        primaryError,
        cancellationSignal: cancellation.signal,
        cleanupTemporary: temporaryRoot
          ? async () => removeOwnedTemporaryDirectory(temporaryRoot, runId)
          : undefined,
        releaseLock: lock ? async (prepareRelease) => lock.release(prepareRelease) : undefined,
        revokeMarker:
          lock && runPaths
            ? async () => {
                await Promise.all([
                  rm(path.join(runPaths.outputRoot, "VALIDATED.json"), { force: true }),
                  rm(path.join(runPaths.outputRoot, "LOCAL_VALIDATION.json"), { force: true }),
                ])
              }
            : undefined,
      })
    } finally {
      cancellation.dispose()
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`)
    process.exitCode = runnerExitCode(error)
  })
}
