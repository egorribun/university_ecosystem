#!/usr/bin/env node

import { createHash } from "node:crypto"
import { glob } from "node:fs/promises"
import { fileURLToPath } from "node:url"

import { Instrumenter } from "@stryker-mutator/instrumenter"

const frontendRoot = fileURLToPath(new URL("..", import.meta.url))
const expectedInstrumenterOptions = {
  plugins: null,
  excludedMutations: [],
  ignorers: [],
}

function normalizePath(value) {
  if (typeof value !== "string" || value.includes("\0")) {
    throw new Error("Stryker source path is invalid")
  }
  const slashPath = value.replaceAll("\\", "/").replace(/^\.\//u, "")
  if (
    slashPath === "" ||
    slashPath.startsWith("/") ||
    /^[A-Za-z]:/u.test(slashPath) ||
    slashPath.split("/").some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new Error(`Stryker source path is not a canonical relative path: ${value}`)
  }
  return slashPath
}

function assertFrontendPolicy(policy) {
  if (
    !policy ||
    typeof policy !== "object" ||
    !policy.frontend ||
    !Array.isArray(policy.frontend.include) ||
    !Array.isArray(policy.frontend.exclude) ||
    policy.frontend.include.length === 0
  ) {
    throw new Error("Frontend coverage source policy is missing include/exclude arrays")
  }
}

export function mutationPatternsFromPolicy(policy) {
  assertFrontendPolicy(policy)
  return [...policy.frontend.include, ...policy.frontend.exclude.map((pattern) => `!${pattern}`)]
}

function assertStringArray(value, description) {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    throw new Error(`${description} must be an array of strings`)
  }
}

function sourceSha256(source) {
  return createHash("sha256").update(source).digest("hex")
}

function locationPoint(point) {
  if (
    !point ||
    typeof point !== "object" ||
    !Number.isInteger(point.line) ||
    !Number.isInteger(point.column) ||
    point.line < 0 ||
    point.column < 0
  ) {
    throw new Error("Stryker mutant location point is invalid")
  }
  return { line: point.line, column: point.column }
}

export function mutantSignature(mutant, sourcePath = mutant?.fileName) {
  if (
    !mutant ||
    typeof mutant !== "object" ||
    typeof mutant.mutatorName !== "string" ||
    typeof mutant.replacement !== "string" ||
    !mutant.location ||
    typeof mutant.location !== "object" ||
    typeof sourcePath !== "string"
  ) {
    throw new Error("Stryker mutant signature metadata is invalid")
  }
  const start = locationPoint(mutant.location.start)
  const end = locationPoint(mutant.location.end)
  if (end.line < start.line || (end.line === start.line && end.column < start.column)) {
    throw new Error("Stryker mutant location range is invalid")
  }
  return JSON.stringify({
    sourcePath: normalizePath(sourcePath),
    mutatorName: mutant.mutatorName,
    replacement: mutant.replacement,
    start,
    end,
  })
}

const quietLogger = {
  debug() {},
  info() {},
  isDebugEnabled() {
    return false
  },
}

export async function generateInstrumenterPreflight({
  sourceFiles,
  sourceByFile,
  instrumenterOptions,
}) {
  assertStringArray(sourceFiles, "Source denominator")
  if (!(sourceByFile instanceof Map)) {
    throw new Error("Current source snapshots must be provided as a Map")
  }
  if (!instrumenterOptions || typeof instrumenterOptions !== "object") {
    throw new Error("Instrumenter options must be provided")
  }

  const instrumenter = new Instrumenter(quietLogger)
  const preflightByFile = new Map()
  // Small batches keep Babel's transient AST memory bounded while preserving
  // the exact parser, mutator and ignorer semantics used by Stryker 9.
  for (let offset = 0; offset < sourceFiles.length; offset += 25) {
    const batch = sourceFiles.slice(offset, offset + 25)
    const files = batch.map((file) => {
      const source = sourceByFile.get(file)
      if (typeof source !== "string") {
        throw new Error(`Current source snapshot is missing for ${file}`)
      }
      return { name: file, content: source, mutate: true }
    })
    const result = await instrumenter.instrument(files, instrumenterOptions)
    const ignored = result.mutants.find(
      (mutant) => mutant.status === "Ignored" || typeof mutant.statusReason === "string"
    )
    if (ignored) {
      throw new Error(
        `Stryker ignore directive is forbidden in ${normalizePath(ignored.fileName)} (${ignored.statusReason ?? "no reason"})`
      )
    }
    for (const file of batch) {
      const source = sourceByFile.get(file)
      preflightByFile.set(file, {
        sourceSha256: sourceSha256(source),
        mutants: result.mutants.filter((mutant) => normalizePath(mutant.fileName) === file),
      })
    }
  }
  return preflightByFile
}

export function buildMutationInventory({
  sourceFiles,
  sourceByFile,
  report,
  expectedPatterns,
  preflightByFile,
}) {
  assertStringArray(sourceFiles, "Source denominator")
  assertStringArray(expectedPatterns, "Expected mutation patterns")
  if (!(sourceByFile instanceof Map)) {
    throw new Error("Current source snapshots must be provided as a Map")
  }
  if (!report || typeof report !== "object" || Array.isArray(report)) {
    throw new Error("Stryker report must be an object")
  }
  if (report.schemaVersion !== "1.0") {
    throw new Error("Stryker report schemaVersion must equal 1.0")
  }
  if (!(preflightByFile instanceof Map)) {
    throw new Error("Instrumenter preflight must be provided as a Map")
  }

  const actualPatterns = report.config?.mutate
  assertStringArray(actualPatterns, "Stryker report mutation scope")
  if (JSON.stringify(actualPatterns) !== JSON.stringify(expectedPatterns)) {
    throw new Error("Stryker report mutation scope does not match the frontend denominator")
  }
  const reportInstrumenterOptions = {
    plugins: report.config?.mutator?.plugins,
    excludedMutations: report.config?.mutator?.excludedMutations,
    ignorers: report.config?.ignorers,
  }
  if (JSON.stringify(reportInstrumenterOptions) !== JSON.stringify(expectedInstrumenterOptions)) {
    throw new Error("Stryker report instrumenter options do not match the fail-closed contract")
  }
  if (report.config?.coverageAnalysis !== "perTest") {
    throw new Error("Stryker report coverageAnalysis must equal perTest")
  }
  if (report.config?.incremental !== false) {
    throw new Error("Stryker report incremental must be disabled for canonical evidence")
  }
  if (!report.files || typeof report.files !== "object" || Array.isArray(report.files)) {
    throw new Error("Stryker report files must be an object")
  }

  const normalizedSources = sourceFiles.map(normalizePath).sort()
  const sourceSet = new Set(normalizedSources)
  const caseFoldedSources = new Set(
    normalizedSources.map((file) => file.toLocaleLowerCase("en-US"))
  )
  if (
    sourceSet.size !== normalizedSources.length ||
    caseFoldedSources.size !== normalizedSources.length
  ) {
    throw new Error("Source denominator contains duplicate files")
  }
  if (sourceSet.size === 0) {
    throw new Error("Source denominator is empty")
  }

  const reportFiles = new Map()
  const reportFileAliases = new Set()
  for (const [rawFile, fileReport] of Object.entries(report.files)) {
    const file = normalizePath(rawFile)
    const alias = file.toLocaleLowerCase("en-US")
    if (reportFiles.has(file) || reportFileAliases.has(alias)) {
      throw new Error(`Stryker report contains a duplicate path alias: ${rawFile}`)
    }
    reportFiles.set(file, fileReport)
    reportFileAliases.add(alias)
  }
  for (const file of reportFiles.keys()) {
    if (!sourceSet.has(file)) {
      throw new Error(`Stryker report contains out-of-denominator file: ${file}`)
    }
  }

  let totalMutants = 0
  let killedMutants = 0
  let nonViableMutants = 0
  const mutantIds = new Set()
  const files = normalizedSources.map((file) => {
    const currentSource = sourceByFile.get(file)
    if (typeof currentSource !== "string") {
      throw new Error(`Current source snapshot is missing for ${file}`)
    }
    const currentSourceSha256 = sourceSha256(currentSource)
    const preflight = preflightByFile.get(file)
    if (!preflight || preflight.sourceSha256 !== currentSourceSha256) {
      throw new Error(`Instrumenter preflight source snapshot is stale or missing for ${file}`)
    }
    if (!Array.isArray(preflight.mutants)) {
      throw new Error(`Instrumenter preflight mutants must be an array for ${file}`)
    }
    const fileReport = reportFiles.get(file)
    if (!fileReport) {
      if (preflight.mutants.length > 0) {
        throw new Error(
          `Stryker report omitted ${file}, but the instrumenter preflight generated ${preflight.mutants.length} mutant(s)`
        )
      }
      return {
        path: file,
        classification: "zero-mutant",
        mutantCount: 0,
        sourceSha256: currentSourceSha256,
      }
    }
    if (fileReport.source !== currentSource) {
      throw new Error(`Stryker source snapshot is stale for ${file}`)
    }
    if (!Array.isArray(fileReport.mutants)) {
      throw new Error(`Stryker mutants must be an array for ${file}`)
    }
    const expectedSignatures = preflight.mutants
      .map((mutant) => mutantSignature(mutant, file))
      .sort()
    const actualSignatures = fileReport.mutants
      .map((mutant) => mutantSignature(mutant, file))
      .sort()
    if (JSON.stringify(actualSignatures) !== JSON.stringify(expectedSignatures)) {
      throw new Error(
        `Stryker mutant signatures differ from the instrumenter preflight for ${file}`
      )
    }

    for (const mutant of fileReport.mutants) {
      if (!mutant || typeof mutant !== "object" || typeof mutant.id !== "string") {
        throw new Error(`Stryker mutant metadata is invalid for ${file}`)
      }
      if (mutantIds.has(mutant.id)) {
        throw new Error(`Duplicate Stryker mutant id: ${mutant.id}`)
      }
      mutantIds.add(mutant.id)
      totalMutants += 1
      if (mutant.status === "Killed") {
        killedMutants += 1
        continue
      }
      if (mutant.status === "CompileError") {
        if (typeof mutant.statusReason !== "string" || mutant.statusReason.trim() === "") {
          throw new Error(`CompileError mutant ${mutant.id} lacks a status reason`)
        }
        nonViableMutants += 1
        continue
      }
      throw new Error(`Stryker mutant ${mutant.id} has unacceptable status ${mutant.status}`)
    }

    return {
      path: file,
      classification: fileReport.mutants.length === 0 ? "zero-mutant" : "mutated",
      mutantCount: fileReport.mutants.length,
      sourceSha256: currentSourceSha256,
    }
  })

  if (killedMutants === 0) {
    throw new Error("Stryker report contains no viable mutants")
  }
  const viableMutants = totalMutants - nonViableMutants
  const viableMutantScore = (killedMutants / viableMutants) * 100
  if (viableMutantScore !== 100) {
    throw new Error(`Stryker viable mutation score is ${viableMutantScore}, expected 100`)
  }

  const mutatedFiles = files.filter(({ classification }) => classification === "mutated").length
  return {
    files,
    summary: {
      denominatorFiles: files.length,
      mutatedFiles,
      zeroMutantFiles: files.length - mutatedFiles,
      totalMutants,
      killedMutants,
      nonViableMutants,
      viableMutantScore,
    },
  }
}

export async function listPolicyFiles(policy, root = frontendRoot) {
  assertFrontendPolicy(policy)
  const included = new Set()
  for (const pattern of policy.frontend.include) {
    for await (const file of glob(pattern, {
      cwd: root,
      exclude: policy.frontend.exclude,
    })) {
      included.add(normalizePath(file))
    }
  }
  return [...included].sort()
}
