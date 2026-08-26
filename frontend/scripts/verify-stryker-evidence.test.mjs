import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import test from "node:test"

import {
  buildMutationInventory,
  generateInstrumenterPreflight,
  mutantSignature,
  mutationPatternsFromPolicy,
} from "./validate-stryker-inventory.mjs"
import { verifyEvidenceDocuments } from "./verify-stryker-evidence.mjs"

const hash = (value) => createHash("sha256").update(value).digest("hex")
const jsonText = (value) => `${JSON.stringify(value, null, 2)}\n`
const instrumenterOptions = { plugins: null, excludedMutations: [], ignorers: [] }

function reportConfig(mutate) {
  return {
    mutate,
    coverageAnalysis: "perTest",
    incremental: false,
    mutator: { plugins: null, excludedMutations: [] },
    ignorers: [],
  }
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

async function fixture() {
  const sha = "a".repeat(40)
  const sourceFile = "src/a.ts"
  const sourcePath = `frontend/${sourceFile}`
  const source = "export const choose = (value: boolean) => (value ? 1 : 2)\n"
  const policyPath = "quality/coverage-source-policy.json"
  const policy = { frontend: { include: ["src/**/*.ts"], exclude: [] } }
  const policyText = jsonText(policy)
  const expectedPatterns = mutationPatternsFromPolicy(policy)
  const sourceFiles = [sourceFile]
  const sourceByFile = new Map([[sourceFile, source]])
  const preflightByFile = await generateInstrumenterPreflight({
    sourceFiles,
    sourceByFile,
    instrumenterOptions,
  })
  assert.ok(preflightByFile.get(sourceFile).mutants.length > 0)

  const shardId = "shard-000"
  const shardMutants = preflightByFile.get(sourceFile).mutants.map((mutant, index) => ({
    ...mutant,
    id: String(index),
    status: "Killed",
  }))
  const shardReport = {
    schemaVersion: "1.0",
    config: reportConfig([sourceFile]),
    files: { [sourceFile]: { source, mutants: shardMutants } },
  }
  const mergedReport = {
    schemaVersion: "1.0",
    config: reportConfig(expectedPatterns),
    files: {
      [sourceFile]: {
        source,
        mutants: shardMutants.map((mutant) => ({ ...mutant, id: `${shardId}:${mutant.id}` })),
      },
    },
  }
  const derived = buildMutationInventory({
    sourceFiles,
    sourceByFile,
    report: mergedReport,
    expectedPatterns,
    preflightByFile,
  })
  const runId = "run-a"
  const evidenceDigest = "b".repeat(64)
  const preflight = {
    schemaVersion: "1.0",
    runId,
    revision: sha,
    sourceEvidenceDigest: evidenceDigest,
    instrumenterOptions,
    files: serializePreflight(preflightByFile),
  }
  const preflightText = jsonText(preflight)
  const mergedPath = "frontend/reports/mutation/mutation.json"
  const shardPath = "frontend/reports/mutation/runs/run-a/shard-000/mutation.json"
  const reportTexts = new Map([
    [mergedPath, jsonText(mergedReport)],
    [shardPath, jsonText(shardReport)],
  ])
  const shardEvidencePath = "frontend/reports/mutation/runs/run-a/shard-000/SHARD_EVIDENCE.json"
  const shardEvidence = {
    schemaVersion: "1.0",
    runId: "producer-a",
    shardId,
    shardIndex: 0,
    shardCount: 1,
    revision: sha,
    evidenceDigest,
    preflightDigest: hash(JSON.stringify(preflight.files)),
    workflowRunId: "42",
    workflowRunAttempt: "3",
    files: [sourceFile],
    mutantCount: shardMutants.length,
    reportSha256: hash(reportTexts.get(shardPath)),
  }
  const shardEvidenceTexts = new Map([[shardEvidencePath, jsonText(shardEvidence)]])
  const inventory = {
    schemaVersion: "2.0",
    runId,
    revision: sha,
    releaseEligible: true,
    sourceRevision: {
      headSha: sha,
      revision: sha,
      evidenceDigest,
      repositoryDirty: false,
      dirtyPaths: [],
      inputHashes: {
        [sourcePath]: hash(source),
        [policyPath]: hash(policyText),
      },
    },
    provenance: { workflowRunId: "42", workflowRunAttempt: "3" },
    sourcePolicy: {
      path: policyPath,
      sha256: hash(policyText),
      mutationPatterns: expectedPatterns,
    },
    preflight: {
      path: "frontend/reports/mutation/preflight.json",
      sha256: hash(preflightText),
    },
    reports: [
      {
        path: mergedPath,
        sha256: hash(reportTexts.get(mergedPath)),
        schemaVersion: "1.0",
      },
      {
        shardId,
        assignedFiles: 1,
        assignedMutants: shardMutants.length,
        path: shardPath,
        sha256: hash(reportTexts.get(shardPath)),
        schemaVersion: "1.0",
      },
    ],
    shardEvidence: [
      {
        shardId,
        path: shardEvidencePath,
        sha256: hash(shardEvidenceTexts.get(shardEvidencePath)),
        schemaVersion: "1.0",
        revision: sha,
        evidenceDigest,
        workflowRunId: "42",
        workflowRunAttempt: "3",
        reportSha256: hash(reportTexts.get(shardPath)),
      },
    ],
    ...derived,
  }
  const inventoryText = jsonText(inventory)
  const marker = {
    schemaVersion: "1.0",
    runId,
    revision: sha,
    inventory: "frontend/reports/mutation/inventory.json",
    inventorySha256: hash(inventoryText),
    preflight: "frontend/reports/mutation/preflight.json",
    preflightSha256: hash(preflightText),
    releaseEligible: true,
  }
  return {
    expectedSha: sha,
    expectedWorkflowRunId: "42",
    expectedWorkflowRunAttempt: "3",
    marker,
    inventory,
    inventoryText,
    preflightText,
    currentEvidenceFiles: [sourcePath, policyPath],
    fileBytes: new Map([
      [sourcePath, Buffer.from(source)],
      [policyPath, Buffer.from(policyText)],
    ]),
    reportTexts,
    shardEvidenceTexts,
    gitStatus: "",
    sourceFiles,
    expectedPatterns,
    mergedPath,
    shardPath,
    shardEvidencePath,
  }
}

function reseal(evidence) {
  for (const report of evidence.inventory.reports) {
    report.sha256 = hash(evidence.reportTexts.get(report.path))
  }
  evidence.inventoryText = jsonText(evidence.inventory)
  evidence.marker.inventorySha256 = hash(evidence.inventoryText)
}

function resealShardEvidence(evidence) {
  const entry = evidence.inventory.shardEvidence[0]
  entry.sha256 = hash(evidence.shardEvidenceTexts.get(entry.path))
  reseal(evidence)
}

function mutateReports(evidence, mutate) {
  for (const reportPath of [evidence.mergedPath, evidence.shardPath]) {
    const report = JSON.parse(evidence.reportTexts.get(reportPath))
    mutate(report.files["src/a.ts"].mutants)
    evidence.reportTexts.set(reportPath, jsonText(report))
  }
  reseal(evidence)
  const producer = JSON.parse(evidence.shardEvidenceTexts.get(evidence.shardEvidencePath))
  producer.reportSha256 = evidence.inventory.reports.find(
    ({ shardId }) => shardId === "shard-000"
  ).sha256
  evidence.shardEvidenceTexts.set(evidence.shardEvidencePath, jsonText(producer))
  evidence.inventory.shardEvidence[0].reportSha256 = producer.reportSha256
  resealShardEvidence(evidence)
}

test("independently accepts SHA-bound complete release evidence", async () => {
  const evidence = await fixture()
  assert.deepEqual(await verifyEvidenceDocuments(evidence), {
    runId: "run-a",
    revision: "a".repeat(40),
    reportCount: 2,
    sourceFileCount: 1,
  })
})

test("rejects local markers, dirty repositories, stale sources, and report hash drift", async () => {
  const local = await fixture()
  local.marker.releaseEligible = false
  await assert.rejects(verifyEvidenceDocuments(local), /release eligible/u)

  const dirty = await fixture()
  dirty.gitStatus = " M frontend/src/a.ts"
  await assert.rejects(verifyEvidenceDocuments(dirty), /clean repository/u)

  const stale = await fixture()
  stale.fileBytes.set("frontend/src/a.ts", Buffer.from("changed"))
  await assert.rejects(verifyEvidenceDocuments(stale), /source hash mismatch/u)

  const reportDrift = await fixture()
  reportDrift.reportTexts.set(reportDrift.mergedPath, jsonText({ schemaVersion: "1.0" }))
  await assert.rejects(verifyEvidenceDocuments(reportDrift), /report hash mismatch/u)
})

test("rejects SHA mismatch and incomplete or extra evidence file inventories", async () => {
  const shaMismatch = await fixture()
  shaMismatch.expectedSha = "b".repeat(40)
  await assert.rejects(verifyEvidenceDocuments(shaMismatch), /HEAD SHA/u)

  const missing = await fixture()
  missing.currentEvidenceFiles = []
  await assert.rejects(verifyEvidenceDocuments(missing), /file inventory/u)

  const extra = await fixture()
  extra.currentEvidenceFiles.push("frontend/src/unbound.ts")
  await assert.rejects(verifyEvidenceDocuments(extra), /file inventory/u)
})

test("rejects survivor and NoCoverage statuses even when every evidence hash is forged", async () => {
  for (const status of ["Survived", "NoCoverage"]) {
    const evidence = await fixture()
    mutateReports(evidence, (mutants) => {
      mutants[0].status = status
    })
    await assert.rejects(verifyEvidenceDocuments(evidence), /unacceptable status/u)
  }
})

test("rejects a mutant omitted from both merged and shard reports", async () => {
  const evidence = await fixture()
  mutateReports(evidence, (mutants) => mutants.pop())
  await assert.rejects(verifyEvidenceDocuments(evidence), /signatures differ/u)
})

test("rejects a forged mutation summary derived from otherwise valid reports", async () => {
  const evidence = await fixture()
  evidence.inventory.summary.totalMutants += 1
  reseal(evidence)
  await assert.rejects(verifyEvidenceDocuments(evidence), /Mutation summary differs/u)
})

test("binds release evidence to the exact workflow run and attempt", async () => {
  const wrongRun = await fixture()
  wrongRun.expectedWorkflowRunId = "43"
  await assert.rejects(verifyEvidenceDocuments(wrongRun), /workflow provenance/u)

  const wrongAttempt = await fixture()
  wrongAttempt.expectedWorkflowRunAttempt = "4"
  await assert.rejects(verifyEvidenceDocuments(wrongAttempt), /workflow provenance/u)

  const local = await fixture()
  local.expectedWorkflowRunId = undefined
  local.expectedWorkflowRunAttempt = undefined
  await assert.rejects(verifyEvidenceDocuments(local), /workflow provenance/u)
})

test("rejects missing or tampered shard producer evidence", async () => {
  const missing = await fixture()
  missing.inventory.shardEvidence = []
  reseal(missing)
  await assert.rejects(verifyEvidenceDocuments(missing), /producer evidence inventory/u)

  const hashDrift = await fixture()
  hashDrift.shardEvidenceTexts.set(hashDrift.shardEvidencePath, "{}\n")
  await assert.rejects(verifyEvidenceDocuments(hashDrift), /producer evidence hash mismatch/u)

  const forged = await fixture()
  const producer = JSON.parse(forged.shardEvidenceTexts.get(forged.shardEvidencePath))
  producer.reportSha256 = "f".repeat(64)
  forged.shardEvidenceTexts.set(forged.shardEvidencePath, jsonText(producer))
  resealShardEvidence(forged)
  await assert.rejects(verifyEvidenceDocuments(forged), /producer evidence is stale/u)

  const indexedAttemptDrift = await fixture()
  indexedAttemptDrift.inventory.shardEvidence[0].workflowRunAttempt = "2"
  reseal(indexedAttemptDrift)
  await assert.rejects(verifyEvidenceDocuments(indexedAttemptDrift), /producer evidence index/u)
})

test("accepts an earlier producer attempt from the exact workflow run", async () => {
  const evidence = await fixture()
  const producer = JSON.parse(evidence.shardEvidenceTexts.get(evidence.shardEvidencePath))
  producer.workflowRunAttempt = "2"
  evidence.shardEvidenceTexts.set(evidence.shardEvidencePath, jsonText(producer))
  evidence.inventory.shardEvidence[0].workflowRunAttempt = "2"
  resealShardEvidence(evidence)

  assert.equal((await verifyEvidenceDocuments(evidence)).runId, "run-a")
})

test("rejects shard producer evidence from a future workflow attempt", async () => {
  const evidence = await fixture()
  const producer = JSON.parse(evidence.shardEvidenceTexts.get(evidence.shardEvidencePath))
  producer.workflowRunAttempt = "4"
  evidence.shardEvidenceTexts.set(evidence.shardEvidencePath, jsonText(producer))
  resealShardEvidence(evidence)

  await assert.rejects(verifyEvidenceDocuments(evidence), /producer evidence is stale/u)
})
