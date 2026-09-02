import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  buildMutationInventory,
  generateInstrumenterPreflight,
  mutantSignature,
  mutationPatternsFromPolicy,
} from "./validate-stryker-inventory.mjs"
import {
  selectValidatedEvidenceCandidate,
  verifyEvidenceDocuments,
} from "./verify-stryker-evidence.mjs"

const hash = (value) => createHash("sha256").update(value).digest("hex")
const jsonText = (value) => `${JSON.stringify(value, null, 2)}\n`
const instrumenterOptions = { plugins: null, excludedMutations: [], ignorers: [] }
const toolchain = {
  node: "v24.15.0",
  platform: "linux",
  arch: "x64",
  tools: {
    stryker: "9.6.1",
    instrumenter: "9.6.1",
    vitest: "4.1.10",
  },
}

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
  const sourceHeadSha = "b".repeat(40)
  const baseSha = "c".repeat(40)
  const baseRef = "main"
  const sourceFile = "src/a.ts"
  const sourcePath = `frontend/${sourceFile}`
  const source = "export const choose = (value: boolean) => (value ? 1 : 2)\n"
  const policyPath = "quality/coverage-source-policy.json"
  const configPath = "frontend/stryker.config.mjs"
  const policy = { frontend: { include: ["src/**/*.ts"], exclude: [] } }
  const policyText = jsonText(policy)
  const configText = "export default {}\n"
  const expectedPatterns = mutationPatternsFromPolicy(policy)
  const sourceFiles = [sourceFile]
  const sourceByFile = new Map([[sourceFile, source]])
  const inputHashes = {
    [configPath]: hash(configText),
    [sourcePath]: hash(source),
    [policyPath]: hash(policyText),
  }
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
  const evidenceDigest = hash(
    JSON.stringify({
      baseRef,
      baseSha,
      headSha: sha,
      inputHashes: Object.fromEntries(
        Object.entries(inputHashes).sort(([left], [right]) => left.localeCompare(right))
      ),
      sourceHeadSha,
    })
  )
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
    sourceHeadSha,
    baseSha,
    baseRef,
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
      sourceHeadSha,
      baseSha,
      baseRef,
      revision: sha,
      evidenceDigest,
      repositoryDirty: false,
      dirtyPaths: [],
      inputHashes: { ...inputHashes },
    },
    provenance: {
      workflowRunId: "42",
      workflowRunAttempt: "3",
      ...toolchain,
      tools: { ...toolchain.tools },
    },
    sourcePolicy: {
      path: policyPath,
      sha256: hash(policyText),
      mutationPatterns: expectedPatterns,
    },
    config: {
      path: configPath,
      sha256: hash(configText),
      coverageAnalysis: "perTest",
      instrumenterOptions,
      incremental: false,
      forceFresh: true,
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
        sourceHeadSha,
        baseSha,
        baseRef,
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
    expectedSourceHeadSha: sourceHeadSha,
    expectedBaseSha: baseSha,
    expectedBaseRef: baseRef,
    expectedWorkflowRunId: "42",
    expectedWorkflowRunAttempt: "3",
    inputHashes,
    toolchain: { ...toolchain, tools: { ...toolchain.tools } },
    marker,
    inventory,
    inventoryText,
    preflightText,
    currentEvidenceFiles: [configPath, sourcePath, policyPath],
    fileBytes: new Map([
      [configPath, Buffer.from(configText)],
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

function setAggregateProducerAttempt(evidence, attempt) {
  evidence.inventory.provenance.workflowRunAttempt = attempt
  const producer = JSON.parse(evidence.shardEvidenceTexts.get(evidence.shardEvidencePath))
  producer.workflowRunAttempt = attempt
  evidence.shardEvidenceTexts.set(evidence.shardEvidencePath, jsonText(producer))
  evidence.inventory.shardEvidence[0].workflowRunAttempt = attempt
  resealShardEvidence(evidence)
}

function candidateRelativePath(evidencePath) {
  const prefix = "frontend/reports/mutation/"
  assert.ok(evidencePath.startsWith(prefix), `unexpected evidence path: ${evidencePath}`)
  return evidencePath.slice(prefix.length)
}

async function writeValidatedEvidenceCandidate(
  candidateRoot,
  evidence,
  directoryAttempt = evidence.inventory.provenance.workflowRunAttempt
) {
  const candidateDirectory = path.join(
    candidateRoot,
    `frontend-mutation-validated-${evidence.expectedWorkflowRunId}-${directoryAttempt}`
  )
  const write = async (relativePath, contents) => {
    const target = path.join(candidateDirectory, relativePath)
    await mkdir(path.dirname(target), { recursive: true })
    await writeFile(target, contents)
  }
  await write("VALIDATED.json", jsonText(evidence.marker))
  await write("inventory.json", evidence.inventoryText)
  await write("preflight.json", evidence.preflightText)
  for (const [evidencePath, text] of evidence.reportTexts) {
    await write(candidateRelativePath(evidencePath), text)
  }
  for (const [evidencePath, text] of evidence.shardEvidenceTexts) {
    await write(candidateRelativePath(evidencePath), text)
  }
}

function candidateSelectionOptions(evidence, candidateRoot, expectedWorkflowRunAttempt = "3") {
  return {
    candidateRoot,
    expectedSha: evidence.expectedSha,
    expectedSourceHeadSha: evidence.expectedSourceHeadSha,
    expectedBaseSha: evidence.expectedBaseSha,
    expectedBaseRef: evidence.expectedBaseRef,
    expectedWorkflowRunId: evidence.expectedWorkflowRunId,
    expectedWorkflowRunAttempt,
    expectedInputHashes: evidence.inputHashes,
    expectedPatterns: evidence.expectedPatterns,
    toolchain: evidence.toolchain,
  }
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

test("permits an earlier aggregate producer only for a selected retry candidate", async () => {
  const evidence = await fixture()
  setAggregateProducerAttempt(evidence, "2")
  evidence.expectedWorkflowRunAttempt = "3"

  await assert.rejects(verifyEvidenceDocuments(evidence), /workflow provenance/u)
  assert.equal(
    (await verifyEvidenceDocuments({ ...evidence, allowEarlierProducerAttempt: true })).runId,
    "run-a"
  )
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

test("selects a previous-attempt validated artifact for a rerun-failed roundtrip", async (t) => {
  const evidence = await fixture()
  setAggregateProducerAttempt(evidence, "2")
  const candidateRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-validated-candidates-"))
  t.after(() => rm(candidateRoot, { recursive: true, force: true }))
  await writeValidatedEvidenceCandidate(candidateRoot, evidence)

  const selected = await selectValidatedEvidenceCandidate(
    candidateSelectionOptions(evidence, candidateRoot)
  )

  assert.equal(selected.producerAttempt, 2)
  assert.equal(selected.inventory.provenance.workflowRunAttempt, "2")
  assert.equal(selected.candidateDirectory.endsWith("frontend-mutation-validated-42-2"), true)
})

test("selects the newest valid validated artifact candidate deterministically", async (t) => {
  const prior = await fixture()
  setAggregateProducerAttempt(prior, "1")
  const current = await fixture()
  const candidateRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-validated-candidates-"))
  t.after(() => rm(candidateRoot, { recursive: true, force: true }))
  await writeValidatedEvidenceCandidate(candidateRoot, prior)
  await writeValidatedEvidenceCandidate(candidateRoot, current)

  const selected = await selectValidatedEvidenceCandidate(
    candidateSelectionOptions(current, candidateRoot)
  )

  assert.equal(selected.producerAttempt, 3)
  assert.equal(selected.inventory.provenance.workflowRunAttempt, "3")
})

test("rejects malformed, foreign, future, and tampered validated artifact candidates", async (t) => {
  const cases = [
    {
      name: "future producer attempt",
      prepare: (evidence) => setAggregateProducerAttempt(evidence, "4"),
      expected: /producer attempt/u,
    },
    {
      name: "foreign workflow run",
      prepare: (evidence) => {
        evidence.inventory.provenance.workflowRunId = "43"
        reseal(evidence)
      },
      expected: /workflow provenance/u,
    },
    {
      name: "revision mismatch",
      prepare: (evidence) => {
        evidence.inventory.revision = "b".repeat(40)
        evidence.inventory.sourceRevision.revision = "b".repeat(40)
        evidence.marker.revision = "b".repeat(40)
        reseal(evidence)
      },
      expected: /revision/u,
    },
    {
      name: "source head identity mismatch",
      prepare: (evidence) => {
        evidence.inventory.sourceRevision.sourceHeadSha = "d".repeat(40)
        reseal(evidence)
      },
      expected: /revision/u,
    },
    {
      name: "base identity mismatch",
      prepare: (evidence) => {
        evidence.inventory.sourceRevision.baseSha = "e".repeat(40)
        reseal(evidence)
      },
      expected: /revision/u,
    },
    {
      name: "source input mismatch",
      prepare: (evidence) => {
        evidence.inventory.sourceRevision.inputHashes["frontend/src/a.ts"] = "f".repeat(64)
        reseal(evidence)
      },
      expected: /source input/u,
    },
    {
      name: "configuration mismatch",
      prepare: (evidence) => {
        evidence.inventory.config.sha256 = "f".repeat(64)
        reseal(evidence)
      },
      expected: /configuration/u,
    },
    {
      name: "toolchain mismatch",
      prepare: (evidence) => {
        evidence.inventory.provenance.tools.instrumenter = "9.6.2"
        reseal(evidence)
      },
      expected: /toolchain/u,
    },
  ]
  for (const { name, prepare, expected } of cases) {
    const evidence = await fixture()
    prepare(evidence)
    const candidateRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-validated-candidates-"))
    t.after(() => rm(candidateRoot, { recursive: true, force: true }))
    await writeValidatedEvidenceCandidate(candidateRoot, evidence)
    await assert.rejects(
      () => selectValidatedEvidenceCandidate(candidateSelectionOptions(evidence, candidateRoot)),
      expected,
      name
    )
  }

  const malformedRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-validated-candidates-"))
  t.after(() => rm(malformedRoot, { recursive: true, force: true }))
  await writeFile(path.join(malformedRoot, "unexpected.json"), "{}\n")
  const evidence = await fixture()
  await assert.rejects(
    () => selectValidatedEvidenceCandidate(candidateSelectionOptions(evidence, malformedRoot)),
    /candidate root/u
  )

  const extraDirectoryRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-validated-candidates-"))
  t.after(() => rm(extraDirectoryRoot, { recursive: true, force: true }))
  await writeValidatedEvidenceCandidate(extraDirectoryRoot, evidence)
  await mkdir(path.join(extraDirectoryRoot, "frontend-mutation-validated-42-3", "unexpected"), {
    recursive: true,
  })
  await assert.rejects(
    () => selectValidatedEvidenceCandidate(candidateSelectionOptions(evidence, extraDirectoryRoot)),
    /unexpected contents/u
  )
})
