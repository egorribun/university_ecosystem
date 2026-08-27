#!/usr/bin/env node

import { spawn } from "node:child_process"
import { createHash, randomUUID } from "node:crypto"
import { execFile } from "node:child_process"
import { glob, mkdir, open, readFile, rename, rm, writeFile } from "node:fs/promises"
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

function sha256(value) {
  return createHash("sha256").update(value).digest("hex")
}

function normalizePath(value) {
  return value.replaceAll("\\", "/").replace(/^\.\//u, "")
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

export function planMutationShards(preflightByFile, targetMutants = 750, requestedShardCount) {
  if (!(preflightByFile instanceof Map) || !Number.isInteger(targetMutants) || targetMutants < 1) {
    throw new Error("Mutation shard planning inputs are invalid")
  }
  const weightedFiles = [...preflightByFile.entries()]
    .map(([file, entry]) => ({ file, mutantCount: entry?.mutants?.length }))
    .filter(({ mutantCount }) => mutantCount > 0)
    .sort(
      (left, right) => right.mutantCount - left.mutantCount || left.file.localeCompare(right.file)
    )
  if (weightedFiles.length === 0) return []
  const totalMutants = weightedFiles.reduce((sum, entry) => sum + entry.mutantCount, 0)
  if (
    requestedShardCount !== undefined &&
    (!Number.isInteger(requestedShardCount) || requestedShardCount < 1)
  ) {
    throw new Error("Requested mutation shard count is invalid")
  }
  const shardCount = Math.min(
    weightedFiles.length,
    requestedShardCount ?? Math.ceil(totalMutants / targetMutants)
  )
  const shards = Array.from({ length: shardCount }, (_, index) => ({
    id: `shard-${String(index).padStart(3, "0")}`,
    files: [],
    mutantCount: 0,
  }))
  for (const entry of weightedFiles) {
    const target = shards.reduce((lightest, shard) =>
      shard.mutantCount < lightest.mutantCount ? shard : lightest
    )
    target.files.push(entry.file)
    target.mutantCount += entry.mutantCount
  }
  for (const shard of shards) shard.files.sort()
  return shards
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

export function mergeShardReports({ shards, expectedPatterns }) {
  if (!Array.isArray(shards) || shards.length === 0 || !Array.isArray(expectedPatterns)) {
    throw new Error("Stryker shard aggregation inputs are invalid")
  }
  const mergedFiles = {}
  const assignedFiles = new Set()
  for (const { id, files, report } of shards) {
    assertShardReportConfig(report, files, id)
    for (const file of files) {
      if (assignedFiles.has(file))
        throw new Error(`Source file assigned to multiple shards: ${file}`)
      assignedFiles.add(file)
    }
    for (const [file, fileReport] of Object.entries(report.files)) {
      if (!files.includes(normalizePath(file))) {
        throw new Error(`Stryker ${id} reported an unassigned source file: ${file}`)
      }
      if (Object.hasOwn(mergedFiles, file)) {
        throw new Error(`Stryker shard reports overlap at ${file}`)
      }
      if (!Array.isArray(fileReport?.mutants)) {
        throw new Error(`Stryker ${id} mutant list is malformed for ${file}`)
      }
      mergedFiles[file] = {
        ...fileReport,
        mutants: fileReport.mutants.map((mutant) => ({ ...mutant, id: `${id}:${mutant.id}` })),
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

export function buildEvidenceIdentity({ headSha, dirtyPaths, inputHashes }) {
  if (typeof headSha !== "string" || !/^[a-f0-9]{40,64}$/u.test(headSha)) {
    throw new Error("Evidence HEAD must be a full Git SHA")
  }
  if (!Array.isArray(dirtyPaths) || dirtyPaths.some((entry) => typeof entry !== "string")) {
    throw new Error("Evidence dirty paths must be an array of strings")
  }
  if (!inputHashes || typeof inputHashes !== "object" || Array.isArray(inputHashes)) {
    throw new Error("Evidence input hashes must be an object")
  }
  const normalizedHashes = sortedObject(inputHashes)
  const evidenceDigest = sha256(JSON.stringify({ headSha, inputHashes: normalizedHashes }))
  const repositoryDirty = dirtyPaths.length > 0
  return {
    headSha,
    evidenceDigest,
    repositoryDirty,
    dirtyPaths: [...dirtyPaths].sort(),
    inputHashes: normalizedHashes,
    revision: repositoryDirty ? `${headSha}-dirty.${evidenceDigest.slice(0, 12)}` : headSha,
  }
}

export function assertEvidenceUnchanged(expected, actual) {
  if (
    expected.headSha !== actual.headSha ||
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
  const identity = buildEvidenceIdentity({
    headSha,
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
        report: JSON.parse(reportText),
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
    await cleanupCanonicalArtifacts(outputRoot)
    const policy = JSON.parse(await readFile(sourcePolicyPath, "utf8"))
    const sourceFiles = await listPolicyFiles(policy)
    const beforeSnapshot = await captureEvidence(sourceFiles)
    const { identity: before, sourceByFile } = beforeSnapshot
    const preflightByFile = await generateInstrumenterPreflight({
      sourceFiles,
      sourceByFile,
      instrumenterOptions,
    })
    assertEvidenceUnchanged(before, (await captureEvidence(sourceFiles)).identity)

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
    const shardPlan = planMutationShards(preflightByFile, shardTarget, externalShardCount)
    if (shardPlan.length === 0) {
      throw new Error("Instrumenter preflight generated no viable frontend mutants")
    }
    if (externalShardIndex !== undefined && externalShardIndex >= shardPlan.length) {
      throw new Error(`STRYKER_SHARD_INDEX ${externalShardIndex} exceeds the generated shard plan`)
    }
    const serializedPreflight = serializePreflight(preflightByFile)
    const preflightDigest = sha256(JSON.stringify(serializedPreflight))

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
        const reportText = await readFile(reportPath, "utf8")
        const shardEvidence = {
          schemaVersion: "1.0",
          runId,
          shardId: shard.id,
          shardIndex: shardPlan.findIndex((entry) => entry.id === shard.id),
          shardCount: shardPlan.length,
          revision: before.revision,
          evidenceDigest: before.evidenceDigest,
          preflightDigest,
          workflowRunId: process.env.GITHUB_RUN_ID ?? null,
          workflowRunAttempt: process.env.GITHUB_RUN_ATTEMPT ?? null,
          files: shard.files,
          mutantCount: shard.mutantCount,
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
          report: JSON.parse(reportText),
          shardEvidencePath,
          shardEvidenceText,
          shardEvidence,
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
    const expectedPatterns = mutationPatternsFromPolicy(policy)
    const report = mergeShardReports({ shards: shardResults, expectedPatterns })
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
    const [strykerVersion, instrumenterVersion, vitestVersion] = await Promise.all([
      readPackageVersion("node_modules/@stryker-mutator/core/package.json"),
      readPackageVersion("node_modules/@stryker-mutator/instrumenter/package.json"),
      readPackageVersion("node_modules/vitest/package.json"),
    ])
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
