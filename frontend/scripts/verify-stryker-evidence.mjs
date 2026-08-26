#!/usr/bin/env node

import { execFile } from "node:child_process"
import { createHash } from "node:crypto"
import { readFile } from "node:fs/promises"
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
const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url))
const markerPath = path.join(repositoryRoot, "frontend", "reports", "mutation", "VALIDATED.json")

const sha256 = (value) => createHash("sha256").update(value).digest("hex")
const normalizePath = (value) => value.replaceAll("\\", "/").replace(/^\.\//u, "")

function parseWorkflowRunAttempt(value) {
  if (typeof value !== "string" || !/^[1-9]\d*$/u.test(value)) return undefined
  const attempt = Number(value)
  return Number.isSafeInteger(attempt) ? attempt : undefined
}

function assertCanonicalRelativePath(value) {
  const normalized = normalizePath(value)
  if (
    normalized === "" ||
    path.isAbsolute(value) ||
    normalized.split("/").some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new Error(`Evidence path is not canonical and relative: ${value}`)
  }
  return normalized
}

function parseObject(text, description) {
  const value = JSON.parse(text)
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${description} must be a JSON object`)
  }
  return value
}

function canonicalJson(value) {
  if (Array.isArray(value)) return value.map(canonicalJson)
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, canonicalJson(entry)])
    )
  }
  return value
}

function serializePreflight(preflightByFile) {
  return Object.fromEntries(
    [...preflightByFile.entries()].map(([file, entry]) => [
      file,
      {
        sourceSha256: entry.sourceSha256,
        mutantSignatures: entry.mutants.map((mutant) => mutantSignature(mutant, file)).sort(),
      },
    ])
  )
}

function assertEqualEvidence(actual, expected, description) {
  if (JSON.stringify(canonicalJson(actual)) !== JSON.stringify(canonicalJson(expected))) {
    throw new Error(`${description} differs from independently derived evidence`)
  }
}

function verifyShardProducerEvidence({
  inventory,
  preflight,
  reportTexts,
  shardEvidenceTexts,
  expectedWorkflowRunId,
  expectedWorkflowRunAttempt,
}) {
  const aggregateAttempt = parseWorkflowRunAttempt(expectedWorkflowRunAttempt)
  if (aggregateAttempt === undefined) {
    throw new Error("Aggregate workflow run attempt is invalid")
  }
  const shardReports = inventory.reports.filter((report) => report.shardId !== undefined)
  if (
    !Array.isArray(inventory.shardEvidence) ||
    inventory.shardEvidence.length !== shardReports.length
  ) {
    throw new Error("Mutation shard producer evidence inventory is incomplete")
  }
  const producerByShard = new Map()
  for (const entry of inventory.shardEvidence) {
    const evidencePath = assertCanonicalRelativePath(entry.path)
    const evidenceText = shardEvidenceTexts.get(evidencePath)
    if (typeof evidenceText !== "string" || sha256(evidenceText) !== entry.sha256) {
      throw new Error(`Mutation shard producer evidence hash mismatch for ${evidencePath}`)
    }
    const evidence = parseObject(evidenceText, `Mutation shard producer evidence ${evidencePath}`)
    if (evidence.schemaVersion !== entry.schemaVersion || evidence.schemaVersion !== "1.0") {
      throw new Error(`Mutation shard producer evidence schema mismatch for ${evidencePath}`)
    }
    if (
      typeof evidence.shardId !== "string" ||
      producerByShard.has(evidence.shardId) ||
      entry.shardId !== evidence.shardId
    ) {
      throw new Error("Mutation shard producer evidence has a duplicate or mismatched shard id")
    }
    producerByShard.set(evidence.shardId, { evidence, entry })
  }

  const preflightDigest = sha256(JSON.stringify(preflight.files))
  for (const [index, reportEntry] of shardReports.entries()) {
    const producer = producerByShard.get(reportEntry.shardId)
    const evidence = producer?.evidence
    const producerAttempt = parseWorkflowRunAttempt(evidence?.workflowRunAttempt)
    const reportPath = assertCanonicalRelativePath(reportEntry.path)
    const report = parseObject(reportTexts.get(reportPath), `Mutation report ${reportPath}`)
    if (
      !evidence ||
      typeof evidence.runId !== "string" ||
      evidence.runId === "" ||
      evidence.shardIndex !== index ||
      evidence.shardCount !== shardReports.length ||
      evidence.revision !== inventory.revision ||
      evidence.evidenceDigest !== inventory.sourceRevision.evidenceDigest ||
      evidence.preflightDigest !== preflightDigest ||
      evidence.workflowRunId !== expectedWorkflowRunId ||
      producerAttempt === undefined ||
      producerAttempt > aggregateAttempt ||
      JSON.stringify(evidence.files) !== JSON.stringify(report.config?.mutate) ||
      evidence.mutantCount !== reportEntry.assignedMutants ||
      evidence.reportSha256 !== reportEntry.sha256
    ) {
      throw new Error(
        `Mutation shard producer evidence is stale or malformed: ${reportEntry.shardId}`
      )
    }
    if (
      producer.entry.revision !== evidence.revision ||
      producer.entry.evidenceDigest !== evidence.evidenceDigest ||
      producer.entry.workflowRunId !== evidence.workflowRunId ||
      producer.entry.workflowRunAttempt !== evidence.workflowRunAttempt ||
      producer.entry.reportSha256 !== evidence.reportSha256
    ) {
      throw new Error(`Mutation shard producer evidence index mismatch: ${reportEntry.shardId}`)
    }
  }
}

function reconstructMergedReport({ inventory, reportTexts, preflightByFile, expectedPatterns }) {
  const canonicalReports = inventory.reports.filter((report) => report.shardId === undefined)
  const shardReports = inventory.reports.filter((report) => report.shardId !== undefined)
  if (canonicalReports.length !== 1 || shardReports.length === 0) {
    throw new Error("Mutation evidence requires one merged report and one or more shard reports")
  }

  const reconstructedFiles = {}
  const assignedFiles = new Set()
  const shardIds = new Set()
  for (const evidence of shardReports) {
    if (typeof evidence.shardId !== "string" || !/^shard-\d{3}$/u.test(evidence.shardId)) {
      throw new Error("Mutation shard id is malformed")
    }
    if (shardIds.has(evidence.shardId))
      throw new Error(`Duplicate mutation shard ${evidence.shardId}`)
    shardIds.add(evidence.shardId)
    const reportPath = assertCanonicalRelativePath(evidence.path)
    const report = parseObject(reportTexts.get(reportPath), `Mutation report ${reportPath}`)
    const files = report.config?.mutate
    if (
      !Array.isArray(files) ||
      files.some((file) => typeof file !== "string") ||
      report.config?.coverageAnalysis !== "perTest" ||
      report.config?.incremental !== false ||
      JSON.stringify(report.config?.mutator) !==
        JSON.stringify({ plugins: null, excludedMutations: [] }) ||
      JSON.stringify(report.config?.ignorers) !== JSON.stringify([])
    ) {
      throw new Error(`Mutation shard configuration is malformed: ${evidence.shardId}`)
    }
    if (evidence.assignedFiles !== files.length) {
      throw new Error(`Mutation shard file count mismatch: ${evidence.shardId}`)
    }
    let assignedMutants = 0
    for (const file of files) {
      if (assignedFiles.has(file)) throw new Error(`Mutation source assigned twice: ${file}`)
      assignedFiles.add(file)
      const preflight = preflightByFile.get(file)
      if (!preflight || preflight.mutants.length === 0) {
        throw new Error(`Mutation shard assigned a zero-mutant or unknown source: ${file}`)
      }
      assignedMutants += preflight.mutants.length
      const fileReport = report.files?.[file]
      if (!fileReport || !Array.isArray(fileReport.mutants)) {
        throw new Error(`Mutation shard omitted assigned source: ${file}`)
      }
      reconstructedFiles[file] = {
        ...fileReport,
        mutants: fileReport.mutants.map((mutant) => ({
          ...mutant,
          id: `${evidence.shardId}:${mutant.id}`,
        })),
      }
    }
    for (const reportedFile of Object.keys(report.files ?? {})) {
      if (!files.includes(reportedFile)) {
        throw new Error(`Mutation shard reported an unassigned source: ${reportedFile}`)
      }
    }
    if (evidence.assignedMutants !== assignedMutants) {
      throw new Error(`Mutation shard mutant count mismatch: ${evidence.shardId}`)
    }
  }

  const expectedAssignedFiles = [...preflightByFile.entries()]
    .filter(([, entry]) => entry.mutants.length > 0)
    .map(([file]) => file)
    .sort()
  if (JSON.stringify([...assignedFiles].sort()) !== JSON.stringify(expectedAssignedFiles)) {
    throw new Error("Mutation shard assignments do not cover the complete instrumenter preflight")
  }

  const reconstructed = {
    schemaVersion: "1.0",
    config: {
      mutate: expectedPatterns,
      coverageAnalysis: "perTest",
      incremental: false,
      mutator: { plugins: null, excludedMutations: [] },
      ignorers: [],
    },
    files: reconstructedFiles,
  }
  const canonicalPath = assertCanonicalRelativePath(canonicalReports[0].path)
  const canonical = parseObject(reportTexts.get(canonicalPath), `Mutation report ${canonicalPath}`)
  assertEqualEvidence(canonical, reconstructed, "Merged mutation report")
  return canonical
}

export async function verifyEvidenceDocuments({
  expectedSha,
  expectedWorkflowRunId,
  expectedWorkflowRunAttempt,
  marker,
  inventoryText,
  preflightText,
  currentEvidenceFiles,
  fileBytes,
  reportTexts,
  shardEvidenceTexts,
  gitStatus,
  sourceFiles,
  expectedPatterns,
}) {
  if (marker?.schemaVersion !== "1.0" || marker.releaseEligible !== true) {
    throw new Error("Canonical mutation marker must be release eligible with schema 1.0")
  }
  if (gitStatus !== "") throw new Error("Release mutation evidence requires a clean repository")
  if (sha256(inventoryText) !== marker.inventorySha256) {
    throw new Error("Mutation inventory hash mismatch")
  }
  if (sha256(preflightText) !== marker.preflightSha256) {
    throw new Error("Mutation preflight hash mismatch")
  }
  const inventory = parseObject(inventoryText, "Mutation inventory")
  const preflight = parseObject(preflightText, "Mutation preflight")
  if (inventory.schemaVersion !== "2.0" || inventory.releaseEligible !== true) {
    throw new Error("Mutation inventory is incomplete or not release eligible")
  }
  if (
    marker.runId !== inventory.runId ||
    marker.runId !== preflight.runId ||
    marker.revision !== inventory.revision
  ) {
    throw new Error("Mutation evidence run identity mismatch")
  }
  if (
    inventory.sourceRevision?.headSha !== expectedSha ||
    inventory.sourceRevision?.revision !== expectedSha ||
    inventory.revision !== expectedSha
  ) {
    throw new Error("Mutation evidence does not match the expected HEAD SHA")
  }
  if (
    inventory.sourceRevision.repositoryDirty !== false ||
    inventory.sourceRevision.dirtyPaths?.length !== 0 ||
    typeof expectedWorkflowRunId !== "string" ||
    expectedWorkflowRunId === "" ||
    typeof expectedWorkflowRunAttempt !== "string" ||
    expectedWorkflowRunAttempt === "" ||
    inventory.provenance?.workflowRunId !== expectedWorkflowRunId ||
    inventory.provenance?.workflowRunAttempt !== expectedWorkflowRunAttempt
  ) {
    throw new Error("Mutation evidence lacks clean workflow provenance")
  }
  if (
    assertCanonicalRelativePath(marker.preflight) !==
      assertCanonicalRelativePath(inventory.preflight?.path) ||
    marker.preflightSha256 !== inventory.preflight?.sha256
  ) {
    throw new Error("Mutation preflight provenance mismatch")
  }

  const inputHashes = inventory.sourceRevision.inputHashes
  if (!inputHashes || typeof inputHashes !== "object" || Array.isArray(inputHashes)) {
    throw new Error("Mutation source hash inventory is missing")
  }
  const expectedFiles = Object.keys(inputHashes).map(assertCanonicalRelativePath).sort()
  const actualFiles = currentEvidenceFiles.map(assertCanonicalRelativePath).sort()
  if (JSON.stringify(expectedFiles) !== JSON.stringify(actualFiles)) {
    throw new Error("Current frontend file inventory differs from mutation evidence")
  }
  for (const file of expectedFiles) {
    const bytes = fileBytes.get(file)
    if (!bytes || sha256(bytes) !== inputHashes[file]) {
      throw new Error(`Mutation source hash mismatch for ${file}`)
    }
  }

  if (!Array.isArray(inventory.reports) || inventory.reports.length === 0) {
    throw new Error("Mutation report inventory is empty")
  }
  for (const report of inventory.reports) {
    const reportPath = assertCanonicalRelativePath(report.path)
    const text = reportTexts.get(reportPath)
    if (typeof text !== "string" || sha256(text) !== report.sha256) {
      throw new Error(`Mutation report hash mismatch for ${reportPath}`)
    }
    if (parseObject(text, `Mutation report ${reportPath}`).schemaVersion !== report.schemaVersion) {
      throw new Error(`Mutation report schema mismatch for ${reportPath}`)
    }
  }

  if (!Array.isArray(sourceFiles) || sourceFiles.length === 0 || !Array.isArray(expectedPatterns)) {
    throw new Error("Independent mutation source denominator is missing")
  }
  const sourceByFile = new Map(
    sourceFiles.map((file) => {
      const bytes = fileBytes.get(`frontend/${file}`)
      if (!bytes) throw new Error(`Independent source snapshot is missing for ${file}`)
      return [file, bytes.toString("utf8")]
    })
  )
  const preflightByFile = await generateInstrumenterPreflight({
    sourceFiles,
    sourceByFile,
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  })
  if (
    preflight.schemaVersion !== "1.0" ||
    preflight.revision !== inventory.revision ||
    preflight.sourceEvidenceDigest !== inventory.sourceRevision.evidenceDigest ||
    JSON.stringify(preflight.instrumenterOptions) !==
      JSON.stringify({ plugins: null, excludedMutations: [], ignorers: [] })
  ) {
    throw new Error("Mutation preflight identity or instrumenter configuration is malformed")
  }
  assertEqualEvidence(
    preflight.files,
    serializePreflight(preflightByFile),
    "Mutation instrumenter preflight"
  )
  verifyShardProducerEvidence({
    inventory,
    preflight,
    reportTexts,
    shardEvidenceTexts,
    expectedWorkflowRunId,
    expectedWorkflowRunAttempt,
  })
  if (
    inventory.sourcePolicy?.path !== "quality/coverage-source-policy.json" ||
    inventory.sourcePolicy?.sha256 !== inputHashes["quality/coverage-source-policy.json"] ||
    JSON.stringify(inventory.sourcePolicy?.mutationPatterns) !== JSON.stringify(expectedPatterns)
  ) {
    throw new Error("Mutation source policy differs from the independent denominator")
  }
  const canonicalReport = reconstructMergedReport({
    inventory,
    reportTexts,
    preflightByFile,
    expectedPatterns,
  })
  const derived = buildMutationInventory({
    sourceFiles,
    sourceByFile,
    report: canonicalReport,
    expectedPatterns,
    preflightByFile,
  })
  assertEqualEvidence(inventory.files, derived.files, "Mutation file inventory")
  assertEqualEvidence(inventory.summary, derived.summary, "Mutation summary")
  return {
    runId: inventory.runId,
    revision: inventory.revision,
    reportCount: inventory.reports.length,
    sourceFileCount: sourceFiles.length,
  }
}

async function git(args) {
  const { stdout } = await execFileAsync("git", args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  })
  return stdout.trim()
}

function resolveEvidencePath(relativePath) {
  const canonical = assertCanonicalRelativePath(relativePath)
  const resolved = path.resolve(repositoryRoot, canonical)
  if (!resolved.startsWith(`${repositoryRoot}${path.sep}`)) {
    throw new Error(`Evidence path escapes the repository: ${relativePath}`)
  }
  return resolved
}

async function main() {
  const [markerText, headSha, gitStatus, listedFiles] = await Promise.all([
    readFile(markerPath, "utf8"),
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
  const marker = parseObject(markerText, "Mutation marker")
  const [inventoryText, preflightText] = await Promise.all([
    readFile(resolveEvidencePath(marker.inventory), "utf8"),
    readFile(resolveEvidencePath(marker.preflight), "utf8"),
  ])
  const inventory = parseObject(inventoryText, "Mutation inventory")
  const currentEvidenceFiles = listedFiles
    .split(/\r?\n/u)
    .filter(Boolean)
    .map(normalizePath)
    .filter(
      (file) =>
        !/^frontend\/(node_modules|dist|coverage|reports|\.screenshots|\.stryker-tmp)\//u.test(file)
    )
    .sort()
  const fileBytes = new Map(
    await Promise.all(
      currentEvidenceFiles.map(async (file) => [file, await readFile(resolveEvidencePath(file))])
    )
  )
  const reportTexts = new Map(
    await Promise.all(
      inventory.reports.map(async ({ path: report }) => [
        assertCanonicalRelativePath(report),
        await readFile(resolveEvidencePath(report), "utf8"),
      ])
    )
  )
  const shardEvidenceTexts = new Map(
    await Promise.all(
      (Array.isArray(inventory.shardEvidence) ? inventory.shardEvidence : []).map(
        async ({ path: evidence }) => [
          assertCanonicalRelativePath(evidence),
          await readFile(resolveEvidencePath(evidence), "utf8"),
        ]
      )
    )
  )
  const policy = parseObject(
    fileBytes.get("quality/coverage-source-policy.json").toString("utf8"),
    "Coverage source policy"
  )
  const sourceFiles = await listPolicyFiles(policy)
  const expectedPatterns = mutationPatternsFromPolicy(policy)
  const expectedSha = process.env.GITHUB_SHA ?? headSha
  const result = await verifyEvidenceDocuments({
    expectedSha,
    expectedWorkflowRunId: process.env.GITHUB_RUN_ID,
    expectedWorkflowRunAttempt: process.env.GITHUB_RUN_ATTEMPT,
    marker,
    inventoryText,
    preflightText,
    currentEvidenceFiles,
    fileBytes,
    reportTexts,
    shardEvidenceTexts,
    gitStatus,
    sourceFiles,
    expectedPatterns,
  })
  process.stdout.write(
    `Verified release mutation evidence ${result.runId} at ${result.revision} (${result.sourceFileCount} sources, ${result.reportCount} reports)\n`
  )
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`)
    process.exitCode = 1
  })
}
