import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

const runnerUrl = new URL("./run-stryker.mjs", import.meta.url)
const expectedPatterns = ["src/**/*.{ts,tsx}", "!src/**/__tests__/**/*"]
const location = { start: { line: 1, column: 21 }, end: { line: 1, column: 25 } }

test("evidence identity makes dirty worktrees explicit and detects TOCTOU drift", async () => {
  const { buildEvidenceIdentity, assertEvidenceUnchanged } = await import(runnerUrl)
  const clean = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: { "frontend/src/a.ts": "1".repeat(64) },
  })
  const dirty = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [" M frontend/src/a.ts"],
    inputHashes: { "frontend/src/a.ts": "2".repeat(64) },
  })

  assert.equal(clean.repositoryDirty, false)
  assert.equal(clean.revision, clean.headSha)
  assert.equal(dirty.repositoryDirty, true)
  assert.match(dirty.revision, /^a{40}-dirty\.[a-f0-9]{12}$/u)
  assert.doesNotThrow(() => assertEvidenceUnchanged(clean, { ...clean }))
  assert.throws(() => assertEvidenceUnchanged(clean, dirty), /changed while Stryker was running/u)
})

test("canonical cleanup removes only stale mutation evidence", async (t) => {
  const { cleanupCanonicalArtifacts } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-cleanup-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  await mkdir(path.join(root, "runs", "old"), { recursive: true })
  await Promise.all([
    writeFile(path.join(root, "mutation.json"), "stale"),
    writeFile(path.join(root, "mutation.html"), "stale"),
    writeFile(path.join(root, "inventory.json"), "stale"),
    writeFile(path.join(root, "VALIDATED.json"), "stale"),
    writeFile(path.join(root, "runs", "old", "report.json"), "stale"),
    writeFile(path.join(root, "keep.txt"), "keep"),
  ])

  await cleanupCanonicalArtifacts(root)
  assert.equal(await readFile(path.join(root, "keep.txt"), "utf8"), "keep")
  await assert.rejects(() => readFile(path.join(root, "mutation.json")), /ENOENT/u)
  await assert.rejects(() => readFile(path.join(root, "runs", "old", "report.json")), /ENOENT/u)
})

test("stages the canonical coverage policy beside every Stryker sandbox", async (t) => {
  const { stageStrykerSandboxInputs } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-sandbox-inputs-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const sourceRoot = path.join(root, "source")
  const shardTemp = path.join(root, "shard-000")
  const sourcePolicy = path.join(sourceRoot, "coverage-source-policy.json")
  const policyText = '{"frontend":{"include":["src/**/*.ts"],"exclude":[]}}\n'
  await Promise.all([mkdir(sourceRoot, { recursive: true }), mkdir(shardTemp, { recursive: true })])
  await writeFile(sourcePolicy, policyText)

  const stagedPolicy = await stageStrykerSandboxInputs(shardTemp, sourcePolicy)

  assert.equal(stagedPolicy, path.join(shardTemp, "quality", "coverage-source-policy.json"))
  assert.equal(await readFile(stagedPolicy, "utf8"), policyText)
  await assert.rejects(
    () => stageStrykerSandboxInputs(shardTemp, sourcePolicy),
    /already exists|EEXIST/u,
    "A stale or pre-seeded sandbox policy must fail closed instead of being overwritten"
  )
})

test("exclusive run locks fail closed and release only their owner", async (t) => {
  const { acquireRunLock } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-lock-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const lockPath = path.join(root, ".run.lock")
  const first = await acquireRunLock(lockPath, "run-a")
  await assert.rejects(() => acquireRunLock(lockPath, "run-b"), /already active/u)
  await first.release()
  const second = await acquireRunLock(lockPath, "run-b")
  await second.release()
})

test("local evidence never creates a release VALIDATED marker", async (t) => {
  const { writeValidatedEvidence } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-marker-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const marker = await writeValidatedEvidence({
    outputRoot: root,
    inventory: {
      schemaVersion: "2.0",
      runId: "run-a",
      revision: "sha-dirty.digest",
      releaseEligible: false,
      summary: { viableMutantScore: 100 },
    },
    preflight: { schemaVersion: "1.0", runId: "run-a", files: {} },
  })
  const inventoryText = await readFile(path.join(root, "inventory.json"), "utf8")
  const markerText = await readFile(path.join(root, "LOCAL_VALIDATION.json"), "utf8")

  assert.equal(JSON.parse(markerText).inventorySha256, marker.inventorySha256)
  assert.equal(JSON.parse(markerText).releaseEligible, false)
  assert.equal(typeof JSON.parse(markerText).preflightSha256, "string")
  assert.match(inventoryText, /"schemaVersion": "2\.0"/u)
  await assert.rejects(() => readFile(path.join(root, "VALIDATED.json")), /ENOENT/u)
})

test("release marker eligibility is derived from the complete inventory", async (t) => {
  const { writeValidatedEvidence } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-release-marker-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const marker = await writeValidatedEvidence({
    outputRoot: root,
    inventory: {
      schemaVersion: "2.0",
      runId: "run-release",
      revision: "a".repeat(40),
      releaseEligible: true,
      summary: { viableMutantScore: 100 },
    },
    preflight: { schemaVersion: "1.0", runId: "run-release", files: {} },
  })

  assert.equal(marker.releaseEligible, true)
  assert.equal(
    JSON.parse(await readFile(path.join(root, "VALIDATED.json"), "utf8")).runId,
    "run-release"
  )
  await assert.rejects(() => readFile(path.join(root, "LOCAL_VALIDATION.json")), /ENOENT/u)

  await assert.rejects(
    () =>
      writeValidatedEvidence({
        outputRoot: root,
        inventory: {
          schemaVersion: "2.0",
          runId: "bad",
          revision: "a".repeat(40),
          releaseEligible: true,
          summary: { viableMutantScore: 99 },
        },
        preflight: { schemaVersion: "1.0", runId: "bad", files: {} },
      }),
    /100% viable mutation score/u
  )
})

test("indexes every shard producer evidence document by content hash", async () => {
  const { indexShardProducerEvidence } = await import(runnerUrl)
  const root = path.join(os.tmpdir(), "stryker-producer-index")
  const evidence = {
    schemaVersion: "1.0",
    shardId: "shard-000",
    revision: "a".repeat(40),
    evidenceDigest: "b".repeat(64),
    workflowRunId: "42",
    workflowRunAttempt: "2",
    reportSha256: "c".repeat(64),
  }
  const evidenceText = `${JSON.stringify(evidence)}\n`
  const indexed = indexShardProducerEvidence(
    [
      {
        id: "shard-000",
        shardEvidencePath: path.join(root, "frontend", "reports", "SHARD_EVIDENCE.json"),
        shardEvidenceText: evidenceText,
        shardEvidence: evidence,
      },
    ],
    root
  )

  assert.deepEqual(indexed, [
    {
      shardId: "shard-000",
      path: "frontend/reports/SHARD_EVIDENCE.json",
      sha256: createHash("sha256").update(evidenceText).digest("hex"),
      schemaVersion: "1.0",
      revision: "a".repeat(40),
      evidenceDigest: "b".repeat(64),
      workflowRunId: "42",
      workflowRunAttempt: "2",
      reportSha256: "c".repeat(64),
    },
  ])
  assert.throws(() => indexShardProducerEvidence([], root), /producer evidence is missing/u)
  assert.throws(
    () =>
      indexShardProducerEvidence(
        [
          {
            id: "shard-000",
            shardEvidencePath: path.join(root, "outside.json"),
            shardEvidenceText: "{}",
            shardEvidence: evidence,
          },
        ],
        path.join(root, "repository")
      ),
    /malformed|escapes/u
  )
})

test("runner rejects all raw Stryker CLI overrides", async () => {
  const { assertRunnerArguments } = await import(runnerUrl)
  assert.doesNotThrow(() => assertRunnerArguments([]))
  for (const args of [
    ["--incremental"],
    ["--force"],
    ["--concurrency=99"],
    ["--mutate", "src/a.ts"],
  ]) {
    assert.throws(() => assertRunnerArguments(args), /does not accept Stryker CLI overrides/u)
  }
})

test("weighted shard plan is deterministic, complete, and bounded by the largest file", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const weights = new Map([
    ["src/a.ts", { mutants: Array(9) }],
    ["src/b.ts", { mutants: Array(8) }],
    ["src/c.ts", { mutants: Array(4) }],
    ["src/zero.ts", { mutants: [] }],
  ])
  const first = planMutationShards(weights, 10)
  const second = planMutationShards(new Map([...weights].reverse()), 10)

  assert.deepEqual(first, second)
  assert.deepEqual(first.flatMap(({ files }) => files).sort(), ["src/a.ts", "src/b.ts", "src/c.ts"])
  assert.ok(first.every(({ mutantCount }) => mutantCount <= 12))
  assert.equal(planMutationShards(weights, 10, 2).length, 2)
})

test("merges exact shard reports and namespaces otherwise colliding mutant ids", async () => {
  const { mergeShardReports } = await import(runnerUrl)
  const baseConfig = {
    coverageAnalysis: "perTest",
    incremental: false,
    mutator: { plugins: null, excludedMutations: [] },
    ignorers: [],
  }
  const file = (id, replacement) => ({
    source: `export const value = ${replacement === "false" ? "true" : "false"}\n`,
    mutants: [{ id, mutatorName: "BooleanLiteral", replacement, location, status: "Killed" }],
  })
  const merged = mergeShardReports({
    expectedPatterns,
    shards: [
      {
        id: "shard-000",
        files: ["src/a.ts"],
        report: {
          schemaVersion: "1.0",
          config: { ...baseConfig, mutate: ["src/a.ts"] },
          files: { "src/a.ts": file("0", "false") },
        },
      },
      {
        id: "shard-001",
        files: ["src/b.ts"],
        report: {
          schemaVersion: "1.0",
          config: { ...baseConfig, mutate: ["src/b.ts"] },
          files: { "src/b.ts": file("0", "true") },
        },
      },
    ],
  })

  assert.deepEqual(merged.config.mutate, expectedPatterns)
  assert.equal(merged.config.incremental, false)
  assert.deepEqual(
    Object.values(merged.files).map(({ mutants }) => mutants[0].id),
    ["shard-000:0", "shard-001:0"]
  )
})

test("loads a complete external shard set only when source, plan, and report hashes match", async (t) => {
  const { loadExternalShardResults } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-external-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const shardRoot = path.join(root, "artifact", "shard-000")
  await mkdir(shardRoot, { recursive: true })
  const reportText = `${JSON.stringify({ schemaVersion: "1.0", config: {}, files: {} })}\n`
  await writeFile(path.join(shardRoot, "mutation.json"), reportText)
  const digest = createHash("sha256").update(reportText).digest("hex")
  const shardPlan = [{ id: "shard-000", files: ["src/a.ts"], mutantCount: 3 }]
  const evidence = {
    schemaVersion: "1.0",
    runId: "producer-a",
    shardId: "shard-000",
    shardIndex: 0,
    shardCount: 1,
    revision: "a".repeat(40),
    evidenceDigest: "b".repeat(64),
    preflightDigest: "c".repeat(64),
    workflowRunId: "42",
    workflowRunAttempt: "3",
    files: ["src/a.ts"],
    mutantCount: 3,
    reportSha256: digest,
  }
  await writeFile(path.join(shardRoot, "SHARD_EVIDENCE.json"), JSON.stringify(evidence))

  const results = await loadExternalShardResults({
    aggregateRoot: root,
    shardPlan,
    before: { revision: evidence.revision, evidenceDigest: evidence.evidenceDigest },
    preflightDigest: evidence.preflightDigest,
    workflowRunId: evidence.workflowRunId,
    workflowRunAttempt: evidence.workflowRunAttempt,
  })
  assert.equal(results[0].report.schemaVersion, "1.0")

  await writeFile(path.join(shardRoot, "mutation.json"), "{}")
  await assert.rejects(
    () =>
      loadExternalShardResults({
        aggregateRoot: root,
        shardPlan,
        before: { revision: evidence.revision, evidenceDigest: evidence.evidenceDigest },
        preflightDigest: evidence.preflightDigest,
        workflowRunId: evidence.workflowRunId,
        workflowRunAttempt: evidence.workflowRunAttempt,
      }),
    /report hash mismatch/u
  )
})

test("reuses the newest valid shard producer attempt from the same workflow run", async (t) => {
  const { loadExternalShardResults } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-attempt-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const reportText = `${JSON.stringify({ schemaVersion: "1.0", config: {}, files: {} })}\n`
  const baseEvidence = {
    schemaVersion: "1.0",
    runId: "producer-a",
    shardId: "shard-000",
    shardIndex: 0,
    shardCount: 1,
    revision: "a".repeat(40),
    evidenceDigest: "b".repeat(64),
    preflightDigest: "c".repeat(64),
    workflowRunId: "42",
    files: ["src/a.ts"],
    mutantCount: 3,
    reportSha256: createHash("sha256").update(reportText).digest("hex"),
  }
  for (const attempt of ["1", "2"]) {
    const shardRoot = path.join(root, `artifact-attempt-${attempt}`, "shard-000")
    await mkdir(shardRoot, { recursive: true })
    await writeFile(path.join(shardRoot, "mutation.json"), reportText)
    await writeFile(
      path.join(shardRoot, "SHARD_EVIDENCE.json"),
      JSON.stringify({ ...baseEvidence, runId: `producer-${attempt}`, workflowRunAttempt: attempt })
    )
  }

  const results = await loadExternalShardResults({
    aggregateRoot: root,
    shardPlan: [{ id: "shard-000", files: ["src/a.ts"], mutantCount: 3 }],
    before: { revision: baseEvidence.revision, evidenceDigest: baseEvidence.evidenceDigest },
    preflightDigest: baseEvidence.preflightDigest,
    workflowRunId: "42",
    workflowRunAttempt: "3",
  })

  assert.equal(results.length, 1)
  assert.equal(results[0].shardEvidence.workflowRunAttempt, "2")
})

test("rejects ambiguous, foreign-run, and future external shard candidates", async (t) => {
  const { loadExternalShardResults } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-attempt-invalid-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const reportText = `${JSON.stringify({ schemaVersion: "1.0", config: {}, files: {} })}\n`
  const evidence = {
    schemaVersion: "1.0",
    runId: "producer-a",
    shardId: "shard-000",
    shardIndex: 0,
    shardCount: 1,
    revision: "a".repeat(40),
    evidenceDigest: "b".repeat(64),
    preflightDigest: "c".repeat(64),
    workflowRunId: "42",
    workflowRunAttempt: "2",
    files: ["src/a.ts"],
    mutantCount: 3,
    reportSha256: createHash("sha256").update(reportText).digest("hex"),
  }
  const writeCandidate = async (name, overrides = {}) => {
    const shardRoot = path.join(root, name, "shard-000")
    await mkdir(shardRoot, { recursive: true })
    await writeFile(path.join(shardRoot, "mutation.json"), reportText)
    await writeFile(
      path.join(shardRoot, "SHARD_EVIDENCE.json"),
      JSON.stringify({ ...evidence, ...overrides })
    )
  }
  const load = () =>
    loadExternalShardResults({
      aggregateRoot: root,
      shardPlan: [{ id: "shard-000", files: ["src/a.ts"], mutantCount: 3 }],
      before: { revision: evidence.revision, evidenceDigest: evidence.evidenceDigest },
      preflightDigest: evidence.preflightDigest,
      workflowRunId: "42",
      workflowRunAttempt: "3",
    })

  await writeCandidate("first")
  await writeCandidate("duplicate", { runId: "producer-b" })
  await assert.rejects(load, /duplicate producer attempt/u)

  await rm(path.join(root, "duplicate"), { recursive: true })
  await writeCandidate("foreign", { workflowRunId: "43", workflowRunAttempt: "3" })
  await assert.rejects(load, /stale or malformed/u)

  await rm(path.join(root, "foreign"), { recursive: true })
  await writeCandidate("future", { workflowRunAttempt: "4" })

  await assert.rejects(load, /stale or malformed/u)
})

test("release eligibility requires a clean exact-SHA workflow run and attempt", async () => {
  const { isReleaseEligible } = await import(runnerUrl)
  const headSha = "a".repeat(40)
  const identity = { headSha, repositoryDirty: false }
  const complete = {
    GITHUB_RUN_ID: "42",
    GITHUB_RUN_ATTEMPT: "3",
    GITHUB_SHA: headSha,
  }

  assert.equal(isReleaseEligible(identity, complete), true)
  assert.equal(isReleaseEligible({ ...identity, repositoryDirty: true }, complete), false)
  assert.equal(isReleaseEligible(identity, { ...complete, GITHUB_RUN_ATTEMPT: "" }), false)
  assert.equal(isReleaseEligible(identity, { ...complete, GITHUB_RUN_ATTEMPT: undefined }), false)
  assert.equal(isReleaseEligible(identity, { ...complete, GITHUB_SHA: "b".repeat(40) }), false)
})
