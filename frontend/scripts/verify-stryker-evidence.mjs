#!/usr/bin/env node

import { execFile } from "node:child_process"
import { createHash } from "node:crypto"
import { lstat, readdir, readFile } from "node:fs/promises"
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
const mutationEvidenceRoot = path.join(repositoryRoot, "frontend", "reports", "mutation")
const markerPath = path.join(mutationEvidenceRoot, "VALIDATED.json")
const evidencePathPrefix = "frontend/reports/mutation/"
const instrumenterOptions = { plugins: null, excludedMutations: [], ignorers: [] }

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

function jsonText(value) {
  return `${JSON.stringify(value, null, 2)}\n`
}

function parseCanonicalObject(text, description) {
  const value = parseObject(text, description)
  if (text !== jsonText(value)) {
    throw new Error(`${description} JSON is not canonical`)
  }
  return value
}

function sameCanonicalValue(left, right) {
  return JSON.stringify(canonicalJson(left)) === JSON.stringify(canonicalJson(right))
}

function validatedCandidateAttemptFromDirectory(directoryName, expectedWorkflowRunId) {
  if (typeof expectedWorkflowRunId !== "string" || !/^[1-9]\d*$/u.test(expectedWorkflowRunId)) {
    throw new Error("Validated artifact consumer workflow provenance is invalid")
  }
  const prefix = `frontend-mutation-validated-${expectedWorkflowRunId}-`
  if (!directoryName.startsWith(prefix)) {
    throw new Error(`Validated artifact candidate directory is not canonical: ${directoryName}`)
  }
  const attemptText = directoryName.slice(prefix.length)
  const attempt = parseWorkflowRunAttempt(attemptText)
  if (attempt === undefined || attemptText !== String(attempt)) {
    throw new Error(`Validated artifact candidate directory is not canonical: ${directoryName}`)
  }
  return { attempt, attemptText }
}

async function listValidatedCandidateFiles(candidateDirectory) {
  const files = []
  const directories = []
  const visit = async (directory, relativeDirectory = "") => {
    const entries = await readdir(directory, { withFileTypes: true })
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      const relativePath = relativeDirectory ? `${relativeDirectory}/${entry.name}` : entry.name
      const candidatePath = path.join(directory, entry.name)
      const stats = await lstat(candidatePath)
      if (stats.isSymbolicLink()) {
        throw new Error(`Validated artifact candidate contains a symbolic link: ${relativePath}`)
      }
      if (stats.isDirectory()) {
        directories.push(relativePath)
        await visit(candidatePath, relativePath)
      } else if (stats.isFile()) {
        files.push(relativePath)
      } else {
        throw new Error(
          `Validated artifact candidate contains an unsupported entry: ${relativePath}`
        )
      }
    }
  }
  await visit(candidateDirectory)
  const aliases = new Set(
    [...files, ...directories].map((entry) => entry.toLocaleLowerCase("en-US"))
  )
  if (aliases.size !== files.length + directories.length) {
    throw new Error("Validated artifact candidate contains path aliases")
  }
  return { files: files.sort(), directories: directories.sort() }
}

function candidateRelativeEvidencePath(evidencePath, description) {
  const canonical = assertCanonicalRelativePath(evidencePath)
  if (!canonical.startsWith(evidencePathPrefix)) {
    throw new Error(`${description} escapes the validated artifact root`)
  }
  const relativePath = canonical.slice(evidencePathPrefix.length)
  if (relativePath === "" || relativePath.startsWith("/")) {
    throw new Error(`${description} escapes the validated artifact root`)
  }
  return relativePath
}

function assertExactCandidateLayout({ actualFiles, actualDirectories, expectedFiles }) {
  const normalizedExpected = [...expectedFiles].sort()
  const expectedAliases = new Set(normalizedExpected.map((file) => file.toLocaleLowerCase("en-US")))
  const expectedDirectories = new Set()
  for (const file of normalizedExpected) {
    const segments = file.split("/")
    segments.pop()
    while (segments.length > 0) {
      expectedDirectories.add(segments.join("/"))
      segments.pop()
    }
  }
  if (
    expectedAliases.size !== normalizedExpected.length ||
    JSON.stringify(actualFiles) !== JSON.stringify(normalizedExpected) ||
    JSON.stringify(actualDirectories) !== JSON.stringify([...expectedDirectories].sort())
  ) {
    throw new Error("Validated artifact candidate directory has unexpected contents")
  }
}

async function readValidatedEvidenceCandidate({ candidateDirectory, directoryAttempt }) {
  const { files: actualFiles, directories: actualDirectories } =
    await listValidatedCandidateFiles(candidateDirectory)
  const requiredFiles = ["VALIDATED.json", "inventory.json", "preflight.json"]
  if (!requiredFiles.every((file) => actualFiles.includes(file))) {
    throw new Error("Validated artifact candidate directory is missing required evidence")
  }
  const readCandidateFile = async (relativePath) =>
    readFile(path.join(candidateDirectory, ...relativePath.split("/")), "utf8")
  const [markerText, inventoryText, preflightText] = await Promise.all(
    requiredFiles.map(readCandidateFile)
  )
  const marker = parseCanonicalObject(markerText, "Validated artifact marker")
  const inventory = parseCanonicalObject(inventoryText, "Validated artifact inventory")
  const preflight = parseCanonicalObject(preflightText, "Validated artifact preflight")
  if (!Array.isArray(inventory.reports) || !Array.isArray(inventory.shardEvidence)) {
    throw new Error("Validated artifact candidate report inventory is malformed")
  }
  const reportEntries = inventory.reports.map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error("Validated artifact candidate report inventory is malformed")
    }
    return {
      evidencePath: assertCanonicalRelativePath(entry.path),
      relativePath: candidateRelativeEvidencePath(entry.path, "Mutation report"),
    }
  })
  const shardEvidenceEntries = inventory.shardEvidence.map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error("Validated artifact candidate shard evidence inventory is malformed")
    }
    return {
      evidencePath: assertCanonicalRelativePath(entry.path),
      relativePath: candidateRelativeEvidencePath(entry.path, "Mutation shard producer evidence"),
    }
  })
  const expectedFiles = new Set([
    ...requiredFiles,
    ...reportEntries.map(({ relativePath }) => relativePath),
    ...shardEvidenceEntries.map(({ relativePath }) => relativePath),
  ])
  if (expectedFiles.size !== 3 + reportEntries.length + shardEvidenceEntries.length) {
    throw new Error("Validated artifact candidate has duplicate evidence paths")
  }
  assertExactCandidateLayout({ actualFiles, actualDirectories, expectedFiles })
  const reportTexts = new Map(
    await Promise.all(
      reportEntries.map(async ({ evidencePath, relativePath }) => [
        evidencePath,
        await readCandidateFile(relativePath),
      ])
    )
  )
  const shardEvidenceTexts = new Map(
    await Promise.all(
      shardEvidenceEntries.map(async ({ evidencePath, relativePath }) => [
        evidencePath,
        await readCandidateFile(relativePath),
      ])
    )
  )
  return {
    candidateDirectory,
    directoryAttempt,
    markerText,
    marker,
    inventoryText,
    inventory,
    preflightText,
    preflight,
    reportTexts,
    shardEvidenceTexts,
  }
}

async function readValidatedEvidenceCandidates({ candidateRoot, expectedWorkflowRunId }) {
  let rootStats
  let rootEntries
  try {
    rootStats = await lstat(candidateRoot)
    rootEntries = await readdir(candidateRoot, { withFileTypes: true })
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") {
      throw new Error("Required validated artifact candidate root is missing")
    }
    throw error
  }
  if (!rootStats.isDirectory() || rootStats.isSymbolicLink() || rootEntries.length === 0) {
    throw new Error("Required validated artifact candidate root is malformed")
  }
  return Promise.all(
    rootEntries
      .sort((left, right) => left.name.localeCompare(right.name))
      .map(async (entry) => {
        const candidateDirectory = path.join(candidateRoot, entry.name)
        const stats = await lstat(candidateDirectory)
        if (
          !entry.isDirectory() ||
          entry.isSymbolicLink() ||
          !stats.isDirectory() ||
          stats.isSymbolicLink()
        ) {
          throw new Error(
            `Validated artifact candidate root contains an unexpected entry: ${entry.name}`
          )
        }
        const directoryAttempt = validatedCandidateAttemptFromDirectory(
          entry.name,
          expectedWorkflowRunId
        )
        return readValidatedEvidenceCandidate({ candidateDirectory, directoryAttempt })
      })
  )
}

function assertValidatedCandidateMetadata({
  candidate,
  expectedSha,
  expectedWorkflowRunId,
  expectedWorkflowRunAttempt,
  expectedInputHashes,
  expectedPatterns,
  toolchain,
}) {
  const consumerAttempt = parseWorkflowRunAttempt(expectedWorkflowRunAttempt)
  if (
    typeof expectedSha !== "string" ||
    !/^[a-f0-9]{40,64}$/u.test(expectedSha) ||
    typeof expectedWorkflowRunId !== "string" ||
    !/^[1-9]\d*$/u.test(expectedWorkflowRunId) ||
    consumerAttempt === undefined ||
    !expectedInputHashes ||
    typeof expectedInputHashes !== "object" ||
    Array.isArray(expectedInputHashes) ||
    !Array.isArray(expectedPatterns) ||
    !toolchain ||
    typeof toolchain !== "object"
  ) {
    throw new Error("Validated artifact consumer metadata is invalid")
  }
  const { marker, inventory, preflight, directoryAttempt } = candidate
  const provenance = inventory.provenance
  const producerAttempt = parseWorkflowRunAttempt(provenance?.workflowRunAttempt)
  if (
    !provenance ||
    provenance.workflowRunId !== expectedWorkflowRunId ||
    producerAttempt === undefined
  ) {
    throw new Error("Validated artifact workflow provenance does not match this execution")
  }
  if (producerAttempt > consumerAttempt) {
    throw new Error("Validated artifact producer attempt is from the future")
  }
  if (
    directoryAttempt.attempt !== producerAttempt ||
    directoryAttempt.attemptText !== provenance.workflowRunAttempt
  ) {
    throw new Error("Validated artifact candidate directory attempt does not match its payload")
  }
  if (
    marker?.schemaVersion !== "1.0" ||
    marker.releaseEligible !== true ||
    marker.inventory !== `${evidencePathPrefix}inventory.json` ||
    marker.preflight !== `${evidencePathPrefix}preflight.json` ||
    marker.inventorySha256 !== sha256(candidate.inventoryText) ||
    marker.preflightSha256 !== sha256(candidate.preflightText) ||
    marker.runId !== inventory.runId ||
    marker.runId !== preflight.runId ||
    marker.revision !== inventory.revision
  ) {
    throw new Error("Validated artifact marker is malformed")
  }
  if (
    inventory.sourceRevision?.headSha !== expectedSha ||
    inventory.sourceRevision?.revision !== expectedSha ||
    inventory.revision !== expectedSha ||
    inventory.sourceRevision?.repositoryDirty !== false ||
    !Array.isArray(inventory.sourceRevision?.dirtyPaths) ||
    inventory.sourceRevision.dirtyPaths.length !== 0
  ) {
    throw new Error("Validated artifact revision does not match this execution")
  }
  if (!sameCanonicalValue(inventory.sourceRevision.inputHashes, expectedInputHashes)) {
    throw new Error("Validated artifact source inputs do not match this execution")
  }
  const canonicalInputHashes = Object.fromEntries(
    Object.entries(expectedInputHashes).sort(([left], [right]) => left.localeCompare(right))
  )
  const expectedEvidenceDigest = sha256(
    JSON.stringify({ headSha: expectedSha, inputHashes: canonicalInputHashes })
  )
  if (inventory.sourceRevision.evidenceDigest !== expectedEvidenceDigest) {
    throw new Error("Validated artifact source evidence digest does not match this execution")
  }
  if (
    inventory.sourcePolicy?.path !== "quality/coverage-source-policy.json" ||
    inventory.sourcePolicy?.sha256 !== expectedInputHashes["quality/coverage-source-policy.json"] ||
    !sameCanonicalValue(inventory.sourcePolicy?.mutationPatterns, expectedPatterns)
  ) {
    throw new Error("Validated artifact source policy does not match this execution")
  }
  if (
    inventory.config?.path !== "frontend/stryker.config.mjs" ||
    inventory.config?.sha256 !== expectedInputHashes["frontend/stryker.config.mjs"] ||
    inventory.config?.coverageAnalysis !== "perTest" ||
    !sameCanonicalValue(inventory.config?.instrumenterOptions, instrumenterOptions) ||
    inventory.config?.incremental !== false ||
    inventory.config?.forceFresh !== true
  ) {
    throw new Error("Validated artifact configuration does not match this execution")
  }
  if (
    provenance.node !== toolchain.node ||
    provenance.platform !== toolchain.platform ||
    provenance.arch !== toolchain.arch ||
    !sameCanonicalValue(provenance.tools, toolchain.tools)
  ) {
    throw new Error("Validated artifact toolchain does not match this execution")
  }
  if (
    preflight.schemaVersion !== "1.0" ||
    preflight.revision !== expectedSha ||
    preflight.sourceEvidenceDigest !== expectedEvidenceDigest ||
    !sameCanonicalValue(preflight.instrumenterOptions, instrumenterOptions)
  ) {
    throw new Error("Validated artifact preflight identity is malformed")
  }
  return producerAttempt
}

export async function selectValidatedEvidenceCandidate({
  candidateRoot,
  expectedSha,
  expectedWorkflowRunId,
  expectedWorkflowRunAttempt,
  expectedInputHashes,
  expectedPatterns,
  toolchain,
}) {
  const candidates = await readValidatedEvidenceCandidates({
    candidateRoot,
    expectedWorkflowRunId,
  })
  const candidatesByAttempt = new Map()
  for (const candidate of candidates) {
    const producerAttempt = assertValidatedCandidateMetadata({
      candidate,
      expectedSha,
      expectedWorkflowRunId,
      expectedWorkflowRunAttempt,
      expectedInputHashes,
      expectedPatterns,
      toolchain,
    })
    if (candidatesByAttempt.has(producerAttempt)) {
      throw new Error(
        `Validated artifact candidates contain a duplicate producer attempt: ${producerAttempt}`
      )
    }
    candidatesByAttempt.set(producerAttempt, { ...candidate, producerAttempt })
  }
  return [...candidatesByAttempt.entries()].sort(
    ([leftAttempt], [rightAttempt]) => rightAttempt - leftAttempt
  )[0][1]
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
  allowEarlierProducerAttempt = false,
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
  const consumerAttempt = parseWorkflowRunAttempt(expectedWorkflowRunAttempt)
  const producerAttempt = parseWorkflowRunAttempt(inventory.provenance?.workflowRunAttempt)
  if (
    inventory.sourceRevision.repositoryDirty !== false ||
    inventory.sourceRevision.dirtyPaths?.length !== 0 ||
    typeof expectedWorkflowRunId !== "string" ||
    expectedWorkflowRunId === "" ||
    consumerAttempt === undefined ||
    inventory.provenance?.workflowRunId !== expectedWorkflowRunId ||
    producerAttempt === undefined ||
    (allowEarlierProducerAttempt
      ? producerAttempt > consumerAttempt
      : producerAttempt !== consumerAttempt)
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
    expectedWorkflowRunAttempt: inventory.provenance.workflowRunAttempt,
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

async function readPackageVersion(relativePath) {
  return JSON.parse(await readFile(path.join(repositoryRoot, "frontend", relativePath), "utf8"))
    .version
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
    tools: { stryker, instrumenter, vitest },
  }
}

function validatedCandidateRootFromEnvironment(env = process.env) {
  const configured = env.STRYKER_VALIDATED_CANDIDATE_ROOT
  if (configured === undefined) return undefined
  const expectedRoot = path.join(mutationEvidenceRoot, "validated-candidates")
  const resolved = path.resolve(repositoryRoot, "frontend", configured)
  if (resolved !== expectedRoot) {
    throw new Error("STRYKER_VALIDATED_CANDIDATE_ROOT must be the dedicated candidate root")
  }
  return resolved
}

async function readCanonicalEvidenceDocuments() {
  const markerText = await readFile(markerPath, "utf8")
  const marker = parseObject(markerText, "Mutation marker")
  const [inventoryText, preflightText] = await Promise.all([
    readFile(resolveEvidencePath(marker.inventory), "utf8"),
    readFile(resolveEvidencePath(marker.preflight), "utf8"),
  ])
  const inventory = parseObject(inventoryText, "Mutation inventory")
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
  return { marker, inventoryText, preflightText, reportTexts, shardEvidenceTexts }
}

async function main() {
  const [headSha, gitStatus, listedFiles] = await Promise.all([
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
  const policy = parseObject(
    fileBytes.get("quality/coverage-source-policy.json").toString("utf8"),
    "Coverage source policy"
  )
  const sourceFiles = await listPolicyFiles(policy)
  const expectedPatterns = mutationPatternsFromPolicy(policy)
  const expectedSha = process.env.GITHUB_SHA ?? headSha
  const expectedInputHashes = Object.fromEntries(
    currentEvidenceFiles.map((file) => [file, sha256(fileBytes.get(file))])
  )
  const candidateRoot = validatedCandidateRootFromEnvironment()
  const evidenceDocuments = candidateRoot
    ? await selectValidatedEvidenceCandidate({
        candidateRoot,
        expectedSha,
        expectedWorkflowRunId: process.env.GITHUB_RUN_ID,
        expectedWorkflowRunAttempt: process.env.GITHUB_RUN_ATTEMPT,
        expectedInputHashes,
        expectedPatterns,
        toolchain: await readToolchain(),
      })
    : await readCanonicalEvidenceDocuments()
  const result = await verifyEvidenceDocuments({
    expectedSha,
    expectedWorkflowRunId: process.env.GITHUB_RUN_ID,
    expectedWorkflowRunAttempt: process.env.GITHUB_RUN_ATTEMPT,
    allowEarlierProducerAttempt: candidateRoot !== undefined,
    ...evidenceDocuments,
    currentEvidenceFiles,
    fileBytes,
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
