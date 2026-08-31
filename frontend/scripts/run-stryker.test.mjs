import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { link, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
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
  await Promise.all([
    mkdir(path.join(root, "runs", "old"), { recursive: true }),
    mkdir(path.join(root, "historical-costs"), { recursive: true }),
  ])
  await Promise.all([
    writeFile(path.join(root, "mutation.json"), "stale"),
    writeFile(path.join(root, "mutation.html"), "stale"),
    writeFile(path.join(root, "inventory.json"), "stale"),
    writeFile(path.join(root, "VALIDATED.json"), "stale"),
    writeFile(path.join(root, "runs", "old", "report.json"), "stale"),
    writeFile(path.join(root, "historical-costs", "HISTORICAL_COSTS.json"), "stale"),
    writeFile(path.join(root, "keep.txt"), "keep"),
  ])

  await cleanupCanonicalArtifacts(root)
  assert.equal(await readFile(path.join(root, "keep.txt"), "utf8"), "keep")
  await assert.rejects(() => readFile(path.join(root, "mutation.json")), /ENOENT/u)
  await assert.rejects(() => readFile(path.join(root, "runs", "old", "report.json")), /ENOENT/u)
  await assert.rejects(
    () => readFile(path.join(root, "historical-costs", "HISTORICAL_COSTS.json")),
    /ENOENT/u
  )
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

test("historical file costs rebalance a deterministic complete shard plan", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const preflight = new Map([
    ["src/a.ts", { mutants: Array(10) }],
    ["src/b.ts", { mutants: Array(9) }],
    ["src/c.ts", { mutants: Array(8) }],
    ["src/d.ts", { mutants: Array(7) }],
    ["src/e.ts", { mutants: Array(6) }],
    ["src/zero.ts", { mutants: [] }],
  ])
  const historicalCosts = new Map([
    ["src/a.ts", 1],
    ["src/b.ts", 1],
    ["src/c.ts", 100],
    ["src/d.ts", 100],
    ["src/e.ts", 100],
  ])

  const countOnly = planMutationShards(preflight, 10, 3)
  const costAware = planMutationShards(preflight, 10, 3, historicalCosts)

  const maxEstimatedCost = (plan) =>
    Math.max(
      ...plan.map(({ files }) =>
        files.reduce((total, file) => total + historicalCosts.get(file), 0)
      )
    )
  assert.equal(maxEstimatedCost(countOnly), 200)
  assert.equal(maxEstimatedCost(costAware), 101)
  assert.deepEqual(
    costAware.map(({ files }) => files),
    [["src/a.ts", "src/c.ts"], ["src/b.ts", "src/d.ts"], ["src/e.ts"]]
  )
  assert.deepEqual(costAware.flatMap(({ files }) => files).sort(), [
    "src/a.ts",
    "src/b.ts",
    "src/c.ts",
    "src/d.ts",
    "src/e.ts",
  ])
})

test("splits a heavy source into disjoint mutation ranges when the requested fan-out needs it", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const mutants = Array.from({ length: 8 }, (_, index) => ({
    fileName: "src/heavy.ts",
    mutatorName: "BooleanLiteral",
    replacement: index % 2 === 0 ? "true" : "false",
    location: {
      start: { line: index * 2, column: 0 },
      end: { line: index * 2, column: 4 },
    },
  }))
  const preflight = new Map([
    ["src/heavy.ts", { mutants }],
    ["src/light.ts", { mutants: [mutants[0]] }],
  ])

  const plan = planMutationShards(preflight, 750, 4)
  const assignments = plan.flatMap(({ files }) => files)

  assert.equal(plan.length, 4)
  assert.equal(assignments.filter((pattern) => pattern === "src/heavy.ts").length, 0)
  assert.ok(assignments.some((pattern) => pattern.startsWith("src/heavy.ts:")))
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    9
  )
  assert.equal(new Set(assignments).size, assignments.length)
  assert.ok(plan.every(({ mutantCount }) => mutantCount <= 3))
})

test("keeps enclosing mutants inside complete disjoint mutation ranges", async () => {
  const { mutationPatternCoversMutant, parseMutationPattern, planMutationShards } = await import(
    runnerUrl
  )
  const file = "src/nested.ts"
  const mutants = [
    {
      fileName: file,
      mutatorName: "BlockStatement",
      replacement: "{}",
      location: {
        start: { line: 0, column: 0 },
        end: { line: 9, column: 1 },
      },
    },
    ...Array.from({ length: 8 }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: index + 1, column: 2 },
        end: { line: index + 1, column: 7 },
      },
    })),
    ...Array.from({ length: 6 }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: 20 + index * 2, column: 2 },
        end: { line: 20 + index * 2, column: 7 },
      },
    })),
  ]

  const plan = planMutationShards(new Map([[file, { mutants }]]), 750, 4)
  const assignments = plan.flatMap(({ files }) => files)

  // The enclosing block forces the first group to exceed the nominal unit
  // budget; splitting it would make Stryker drop the block mutant.
  assert.equal(plan.length, 3)
  assert.ok(assignments.every((pattern) => pattern.includes(":")))
  assert.equal(
    assignments.reduce(
      (total, pattern) =>
        total +
        mutants.filter((mutant) => mutationPatternCoversMutant(pattern, mutant, file)).length,
      0
    ),
    mutants.length
  )
  const compare = (left, right) => left.line - right.line || left.column - right.column
  const fullyContained = (pattern, mutant) => {
    const range = parseMutationPattern(pattern).range
    assert.ok(range)
    return (
      compare(range.start, mutant.location.start) <= 0 &&
      compare(range.end, mutant.location.end) >= 0
    )
  }
  assert.ok(
    mutants.every(
      (mutant) => assignments.filter((pattern) => fullyContained(pattern, mutant)).length === 1
    )
  )
  assert.ok(assignments.some((pattern) => pattern.endsWith("-10:1")))
})

test("normalizes one-based Stryker runtime locations into the instrumenter preflight space", async () => {
  const { normalizeStrykerRuntimeReport } = await import(runnerUrl)
  const report = {
    schemaVersion: "1.0",
    config: {},
    files: {
      "src/a.ts": {
        source: "export const value = true\n",
        mutants: [
          {
            id: "0",
            mutatorName: "BooleanLiteral",
            replacement: "false",
            status: "Killed",
            location: {
              start: { line: 1, column: 22 },
              end: { line: 1, column: 26 },
            },
          },
        ],
      },
    },
  }

  const normalized = normalizeStrykerRuntimeReport(report)

  assert.deepEqual(normalized.files["src/a.ts"].mutants[0].location, {
    start: { line: 0, column: 21 },
    end: { line: 0, column: 25 },
  })
  assert.deepEqual(report.files["src/a.ts"].mutants[0].location, {
    start: { line: 1, column: 22 },
    end: { line: 1, column: 26 },
  })
  assert.throws(
    () =>
      normalizeStrykerRuntimeReport({
        ...report,
        files: {
          "src/a.ts": {
            ...report.files["src/a.ts"],
            mutants: [
              {
                ...report.files["src/a.ts"].mutants[0],
                location: { start: { line: 0, column: 1 }, end: { line: 1, column: 2 } },
              },
            ],
          },
        },
      }),
    /runtime mutant location/u
  )
})

test("fine-grains large first-attempt universes to distribute expensive source regions", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: index * 2, column: 0 },
        end: { line: index * 2, column: 4 },
      },
    }))
  const preflight = new Map([
    ["src/heavy.ts", { mutants: makeMutants("src/heavy.ts", 4_000) }],
    ...Array.from({ length: 8 }, (_, index) => {
      const file = `src/light-${index}.ts`
      return [file, { mutants: makeMutants(file, 1_000) }]
    }),
  ])

  const plan = planMutationShards(preflight, 750, 64)
  const assignments = plan.flatMap(({ files }) => files)

  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    12_000
  )
  assert.ok(
    assignments.filter((pattern) => pattern.startsWith("src/heavy.ts:")).length > 1,
    "large source regions must be split before logical shard packing"
  )
  assert.ok(assignments.every((pattern) => !pattern.endsWith(".ts")))
})

test("keeps related source domains local in a large first-attempt shard plan", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: index * 2, column: 0 },
        end: { line: index * 2, column: 4 },
      },
    }))
  const preflight = new Map(
    ["api", "content", "messenger", "settings"].flatMap((domain) =>
      Array.from({ length: 4 }, (_, index) => {
        const file = `src/${domain}/source-${index}.ts`
        return [file, { mutants: makeMutants(file, 750) }]
      })
    )
  )

  const plan = planMutationShards(preflight, 750, 8)

  assert.equal(plan.length, 8)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    12_000
  )
  for (const shard of plan) {
    const domains = new Set(shard.files.map((pattern) => pattern.split("/")[1]))
    assert.equal(domains.size, 1, `mixed unrelated related-test domains in ${shard.id}`)
  }
})

test("reconstructs locations and canonical signatures from serialized preflight entries", async () => {
  const { mutationPatternCoversMutant, mutationSignature, planMutationShards } = await import(
    runnerUrl
  )
  const signatures = Array.from({ length: 4 }, (_, index) =>
    JSON.stringify({
      sourcePath: "src/serialized.ts",
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      start: { line: index * 2, column: 0 },
      end: { line: index * 2, column: 4 },
    })
  )
  const preflight = new Map([["src/serialized.ts", { mutants: signatures }]])

  assert.equal(mutationSignature(signatures[0], "src/serialized.ts"), signatures[0])
  assert.equal(
    mutationPatternCoversMutant("src/serialized.ts:3-3", signatures[1], "src/serialized.ts"),
    true
  )
  const plan = planMutationShards(preflight, 1, 4)
  assert.equal(plan.length, 4)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    signatures.length
  )
  assert.ok(plan.every(({ files }) => files.every((pattern) => pattern.includes(":"))))
})

test("merges split mutation-range reports without duplicate or misplaced mutants", async () => {
  const { mergeShardReports, mutationPatternCoversMutant, planMutationShards } = await import(
    runnerUrl
  )
  const source = "\n".repeat(20)
  const mutants = Array.from({ length: 6 }, (_, index) => ({
    mutatorName: "BooleanLiteral",
    replacement: index % 2 === 0 ? "true" : "false",
    location: {
      start: { line: index * 2, column: 0 },
      end: { line: index * 2, column: 4 },
    },
    id: `mutant-${index}`,
    status: "Killed",
  }))
  const preflight = new Map([["src/heavy.ts", { sourceSha256: "a".repeat(64), mutants }]])
  const plan = planMutationShards(preflight, 750, 2)
  const shardReports = plan.map((shard) => {
    const ranges = shard.files
    const selected = mutants.filter((mutant) =>
      ranges.some((pattern) => mutationPatternCoversMutant(pattern, mutant, "src/heavy.ts"))
    )
    return {
      ...shard,
      report: {
        schemaVersion: "1.0",
        config: {
          mutate: shard.files,
          coverageAnalysis: "perTest",
          incremental: false,
          mutator: { plugins: null, excludedMutations: [] },
          ignorers: [],
        },
        files: {
          "src/heavy.ts": {
            source,
            // Stryker runtime reports intentionally omit fileName; the
            // report map key is the authoritative source path.
            mutants: selected,
          },
        },
      },
    }
  })

  const merged = mergeShardReports({
    shards: shardReports,
    expectedPatterns,
    preflightByFile: preflight,
    sourceByFile: new Map([["src/heavy.ts", source]]),
  })
  assert.equal(merged.files["src/heavy.ts"].mutants.length, mutants.length)
  assert.equal(
    new Set(merged.files["src/heavy.ts"].mutants.map(({ id }) => id)).size,
    mutants.length
  )

  const forged = shardReports.map((shard) => ({
    ...shard,
    report: {
      ...shard.report,
      files: {
        "src/heavy.ts": {
          ...shard.report.files["src/heavy.ts"],
          mutants: mutants.slice(0, 1),
        },
      },
    },
  }))
  assert.throws(
    () =>
      mergeShardReports({
        shards: forged,
        expectedPatterns,
        preflightByFile: preflight,
        sourceByFile: new Map([["src/heavy.ts", source]]),
      }),
    /does not belong to its assigned mutation range|duplicate|incomplete/u
  )
})

test("historical Stryker costs are bound to the exact source SHA, config, and viable preflight", async () => {
  const { buildEvidenceIdentity, buildHistoricalCostArtifact, parseHistoricalCostArtifact } =
    await import(runnerUrl)
  const sourceByFile = new Map([
    ["src/a.ts", "export const a = true\n"],
    ["src/b.ts", "export const b = false\n"],
  ])
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: {
      "frontend/stryker.config.mjs": "1".repeat(64),
      "frontend/src/a.ts": sha256Text(sourceByFile.get("src/a.ts")),
      "frontend/src/b.ts": sha256Text(sourceByFile.get("src/b.ts")),
    },
  })
  const config = {
    path: "frontend/stryker.config.mjs",
    sha256: "1".repeat(64),
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  }
  const preflightByFile = new Map(
    [...sourceByFile.entries()].map(([file, source]) => [
      file,
      {
        sourceSha256: sha256Text(source),
        mutants: [
          { fileName: file, mutatorName: "BooleanLiteral", replacement: "false", location },
        ],
      },
    ])
  )
  const artifact = buildHistoricalCostArtifact({
    sourceRevision,
    config,
    preflightByFile,
    costs: new Map([
      ["src/a.ts", 1250],
      ["src/b.ts", 750],
    ]),
  })

  const parsed = parseHistoricalCostArtifact({
    artifactText: `${JSON.stringify(artifact, null, 2)}\n`,
    sourceRevision,
    config,
    preflightByFile,
  })

  assert.deepEqual(
    [...parsed],
    [
      ["src/a.ts", 1250],
      ["src/b.ts", 750],
    ]
  )
})

test("historical Stryker cost candidates fail closed for stale data and unsafe paths", async (t) => {
  const { buildEvidenceIdentity, buildHistoricalCostArtifact, loadHistoricalCostArtifact } =
    await import(runnerUrl)
  const sourceByFile = new Map([["src/a.ts", "export const a = true\n"]])
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: {
      "frontend/stryker.config.mjs": "1".repeat(64),
      "frontend/src/a.ts": sha256Text(sourceByFile.get("src/a.ts")),
    },
  })
  const config = {
    path: "frontend/stryker.config.mjs",
    sha256: "1".repeat(64),
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  }
  const preflightByFile = new Map([
    [
      "src/a.ts",
      {
        sourceSha256: sha256Text(sourceByFile.get("src/a.ts")),
        mutants: [
          { fileName: "src/a.ts", mutatorName: "BooleanLiteral", replacement: "false", location },
        ],
      },
    ],
  ])
  const artifact = buildHistoricalCostArtifact({
    sourceRevision,
    config,
    preflightByFile,
    costs: new Map([["src/a.ts", 1250]]),
  })
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-cost-candidates-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const writeCandidate = async (name, value) => {
    const candidate = path.join(root, name)
    await mkdir(candidate, { recursive: true })
    await writeFile(
      path.join(candidate, "HISTORICAL_COSTS.json"),
      `${JSON.stringify(value, null, 2)}\n`
    )
  }
  const load = (name) =>
    loadHistoricalCostArtifact({
      sourceRevision,
      config,
      preflightByFile,
      candidateRoot: root,
      env: { STRYKER_HISTORICAL_COSTS_ARTIFACT: `${name}/HISTORICAL_COSTS.json` },
    })
  await writeCandidate("valid", artifact)

  assert.deepEqual([...(await load("valid")).costs], [["src/a.ts", 1250]])
  const hardlinkedCandidate = path.join(root, "hardlinked")
  await mkdir(hardlinkedCandidate, { recursive: true })
  await link(
    path.join(root, "valid", "HISTORICAL_COSTS.json"),
    path.join(hardlinkedCandidate, "HISTORICAL_COSTS.json")
  )
  await assert.rejects(() => load("hardlinked"), /must not be a hard link/u)
  await assert.rejects(
    () =>
      loadHistoricalCostArtifact({
        sourceRevision,
        config,
        preflightByFile,
        candidateRoot: root,
        env: { STRYKER_HISTORICAL_COSTS_ARTIFACT: "../HISTORICAL_COSTS.json" },
      }),
    /canonical cost-candidate path/u
  )
  for (const unsafePath of [
    "COM1/HISTORICAL_COSTS.json",
    "attempt:1/HISTORICAL_COSTS.json",
    "attempt./HISTORICAL_COSTS.json",
  ]) {
    await assert.rejects(
      () =>
        loadHistoricalCostArtifact({
          sourceRevision,
          config,
          preflightByFile,
          candidateRoot: root,
          env: { STRYKER_HISTORICAL_COSTS_ARTIFACT: unsafePath },
        }),
      /canonical cost-candidate path/u
    )
  }

  const staleConfiguration = structuredClone(artifact)
  staleConfiguration.payload.config.sha256 = "2".repeat(64)
  staleConfiguration.payloadSha256 = sha256Text(
    `${JSON.stringify(staleConfiguration.payload, null, 2)}\n`
  )
  await writeCandidate("stale-configuration", staleConfiguration)
  await assert.rejects(() => load("stale-configuration"), /configuration does not match/u)

  const incomplete = structuredClone(artifact)
  incomplete.payload.costs = []
  incomplete.payloadSha256 = sha256Text(`${JSON.stringify(incomplete.payload, null, 2)}\n`)
  await writeCandidate("incomplete", incomplete)
  await assert.rejects(() => load("incomplete"), /complete viable source inventory/u)
})

test("historical shard timings produce a complete exact file-cost artifact", async () => {
  const {
    buildEvidenceIdentity,
    buildHistoricalCostArtifactFromShardTimings,
    parseHistoricalCostArtifact,
  } = await import(runnerUrl)
  const sourceByFile = new Map([
    ["src/a.ts", "export const a = true\n"],
    ["src/b.ts", "export const b = false\n"],
    ["src/c.ts", "export const c = true\n"],
  ])
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: {
      "frontend/stryker.config.mjs": "1".repeat(64),
      ...Object.fromEntries(
        [...sourceByFile.entries()].map(([file, source]) => [
          `frontend/${file}`,
          sha256Text(source),
        ])
      ),
    },
  })
  const config = {
    path: "frontend/stryker.config.mjs",
    sha256: "1".repeat(64),
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  }
  const mutant = (file, replacement) => ({
    fileName: file,
    mutatorName: "BooleanLiteral",
    replacement,
    location,
  })
  const preflightByFile = new Map([
    [
      "src/a.ts",
      {
        sourceSha256: sha256Text(sourceByFile.get("src/a.ts")),
        mutants: [mutant("src/a.ts", "false"), mutant("src/a.ts", "true")],
      },
    ],
    [
      "src/b.ts",
      {
        sourceSha256: sha256Text(sourceByFile.get("src/b.ts")),
        mutants: [mutant("src/b.ts", "true")],
      },
    ],
    [
      "src/c.ts",
      {
        sourceSha256: sha256Text(sourceByFile.get("src/c.ts")),
        mutants: [mutant("src/c.ts", "false")],
      },
    ],
  ])
  const artifact = buildHistoricalCostArtifactFromShardTimings({
    sourceRevision,
    config,
    preflightByFile,
    shardResults: [
      { files: ["src/a.ts", "src/b.ts"], mutantCount: 3, durationMs: 3000 },
      { files: ["src/c.ts"], mutantCount: 1, durationMs: 500 },
    ],
  })

  assert.deepEqual(
    [
      ...parseHistoricalCostArtifact({
        artifactText: `${JSON.stringify(artifact, null, 2)}\n`,
        sourceRevision,
        config,
        preflightByFile,
      }),
    ],
    [
      ["src/a.ts", 2000],
      ["src/b.ts", 1000],
      ["src/c.ts", 500],
    ]
  )
  assert.throws(
    () =>
      buildHistoricalCostArtifactFromShardTimings({
        sourceRevision,
        config,
        preflightByFile,
        shardResults: [{ files: ["src/a.ts"], mutantCount: 2, durationMs: 0 }],
      }),
    /timing is malformed/u
  )
  assert.throws(
    () =>
      buildHistoricalCostArtifactFromShardTimings({
        sourceRevision,
        config,
        preflightByFile,
        shardResults: [
          { files: ["src/a.ts"], mutantCount: 2, durationMs: 10 },
          { files: ["src/a.ts"], mutantCount: 2, durationMs: 10 },
        ],
      }),
    /do not match the viable source inventory/u
  )
})

test("historical shard timings aggregate disjoint ranges of one source", async () => {
  const {
    buildEvidenceIdentity,
    buildHistoricalCostArtifactFromShardTimings,
    parseHistoricalCostArtifact,
  } = await import(runnerUrl)
  const sourceByFile = new Map([["src/heavy.ts", "\n".repeat(12)]])
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: { "frontend/stryker.config.mjs": "1".repeat(64) },
  })
  const config = {
    path: "frontend/stryker.config.mjs",
    sha256: "1".repeat(64),
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  }
  const mutants = Array.from({ length: 4 }, (_, index) => ({
    fileName: "src/heavy.ts",
    mutatorName: "BooleanLiteral",
    replacement: index % 2 === 0 ? "true" : "false",
    location: {
      start: { line: index * 2, column: 0 },
      end: { line: index * 2, column: 4 },
    },
  }))
  const preflightByFile = new Map([
    ["src/heavy.ts", { sourceSha256: sha256Text(sourceByFile.get("src/heavy.ts")), mutants }],
  ])
  const artifact = buildHistoricalCostArtifactFromShardTimings({
    sourceRevision,
    config,
    preflightByFile,
    shardResults: [
      { files: ["src/heavy.ts:1-3"], mutantCount: 2, durationMs: 200 },
      { files: ["src/heavy.ts:5-7"], mutantCount: 2, durationMs: 100 },
    ],
  })
  assert.deepEqual(
    [
      ...parseHistoricalCostArtifact({
        artifactText: `${JSON.stringify(artifact, null, 2)}\n`,
        sourceRevision,
        config,
        preflightByFile,
      }),
    ],
    [["src/heavy.ts", 300]]
  )
})

function sha256Text(value) {
  return createHash("sha256").update(value).digest("hex")
}

function preflightArtifactText(artifact) {
  return `${JSON.stringify(artifact, null, 2)}\n`
}

function resealPreflightArtifact(artifact, mutatePayload) {
  const payload = structuredClone(artifact.payload)
  mutatePayload(payload)
  payload.preflight.digest = sha256Text(JSON.stringify(payload.preflight.files))
  return {
    schemaVersion: artifact.schemaVersion,
    payload,
    payloadSha256: sha256Text(`${JSON.stringify(payload, null, 2)}\n`),
  }
}

test("preflight artifact binds a complete deterministic shard universe to one workflow attempt", async () => {
  const {
    buildEvidenceIdentity,
    buildHistoricalCostArtifact,
    buildPreflightArtifact,
    validatePreflightArtifact,
  } = await import(runnerUrl)
  const sourceByFile = new Map([
    ["src/a.ts", "export const a = true\n"],
    ["src/b.ts", "export const b = false\n"],
  ])
  const sourceFiles = [...sourceByFile.keys()]
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: {
      "frontend/package-lock.json": "1".repeat(64),
      "frontend/stryker.config.mjs": "2".repeat(64),
      "frontend/src/a.ts": sha256Text(sourceByFile.get("src/a.ts")),
      "frontend/src/b.ts": sha256Text(sourceByFile.get("src/b.ts")),
      "quality/coverage-source-policy.json": "3".repeat(64),
    },
  })
  const workflow = { runId: "42", runAttempt: "3", sha: sourceRevision.headSha }
  const toolchain = {
    node: "v24.0.0",
    platform: "linux",
    arch: "x64",
    stryker: "9.6.1",
    instrumenter: "9.6.1",
    vitest: "4.1.10",
  }
  const sourcePolicy = {
    path: "quality/coverage-source-policy.json",
    sha256: "3".repeat(64),
  }
  const config = {
    path: "frontend/stryker.config.mjs",
    sha256: "2".repeat(64),
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  }
  const mutant = (replacement, file) => ({
    fileName: file,
    mutatorName: "BooleanLiteral",
    replacement,
    location,
  })
  const preflightByFile = new Map([
    [
      "src/a.ts",
      {
        sourceSha256: sha256Text(sourceByFile.get("src/a.ts")),
        mutants: [mutant("false", "src/a.ts")],
      },
    ],
    [
      "src/b.ts",
      {
        sourceSha256: sha256Text(sourceByFile.get("src/b.ts")),
        mutants: [mutant("true", "src/b.ts")],
      },
    ],
  ])
  const common = {
    sourceRevision,
    workflow,
    toolchain,
    sourcePolicy,
    config,
    shardTargetMutants: 750,
    shardCount: 2,
  }
  const historicalCostArtifact = buildHistoricalCostArtifact({
    sourceRevision,
    config,
    preflightByFile,
    costs: new Map([
      ["src/a.ts", 2000],
      ["src/b.ts", 1000],
    ]),
  })
  const artifact = buildPreflightArtifact({
    ...common,
    preflightByFile,
    historicalCostModel: historicalCostArtifact.payload,
  })
  const validated = validatePreflightArtifact({
    ...common,
    sourceFiles,
    sourceByFile,
    artifactText: preflightArtifactText(artifact),
  })

  assert.equal(validated.preflightDigest, artifact.payload.preflight.digest)
  assert.deepEqual(validated.shardPlan, artifact.payload.shardPlan)
  assert.equal(validated.preflightByFile.get("src/a.ts").mutants.length, 1)
  assert.deepEqual(validated.artifact.payload.historicalCostModel, historicalCostArtifact.payload)

  const aggregateValidated = validatePreflightArtifact({
    ...common,
    sourceFiles,
    sourceByFile,
    canonicalPreflightByFile: preflightByFile,
    artifactText: preflightArtifactText(artifact),
  })
  assert.equal(aggregateValidated.preflightDigest, validated.preflightDigest)
})

test("preflight artifact fails closed for provenance, source, and shard-plan tampering", async () => {
  const { buildEvidenceIdentity, buildPreflightArtifact, validatePreflightArtifact } = await import(
    runnerUrl
  )
  const sourceByFile = new Map([
    ["src/a.ts", "export const a = true\n"],
    ["src/b.ts", "export const b = false\n"],
  ])
  const sourceFiles = [...sourceByFile.keys()]
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: {
      "frontend/stryker.config.mjs": "2".repeat(64),
      "quality/coverage-source-policy.json": "3".repeat(64),
    },
  })
  const workflow = { runId: "42", runAttempt: "3", sha: sourceRevision.headSha }
  const toolchain = {
    node: "v24.0.0",
    platform: "linux",
    arch: "x64",
    stryker: "9.6.1",
    instrumenter: "9.6.1",
    vitest: "4.1.10",
  }
  const sourcePolicy = {
    path: "quality/coverage-source-policy.json",
    sha256: "3".repeat(64),
  }
  const config = {
    path: "frontend/stryker.config.mjs",
    sha256: "2".repeat(64),
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  }
  const preflightByFile = new Map(
    sourceFiles.map((file) => [
      file,
      {
        sourceSha256: sha256Text(sourceByFile.get(file)),
        mutants: [
          {
            fileName: file,
            mutatorName: "BooleanLiteral",
            replacement: file === "src/a.ts" ? "false" : "true",
            location,
          },
        ],
      },
    ])
  )
  const common = {
    sourceRevision,
    workflow,
    toolchain,
    sourcePolicy,
    config,
    shardTargetMutants: 750,
    shardCount: 2,
    sourceFiles,
    sourceByFile,
  }
  const artifact = buildPreflightArtifact({ ...common, preflightByFile })
  const validate = (overrides = {}) =>
    validatePreflightArtifact({
      ...common,
      ...overrides,
      artifactText: preflightArtifactText(overrides.artifact ?? artifact),
    })

  assert.throws(
    () => validatePreflightArtifact({ ...common, artifactText: undefined }),
    /artifact is missing/u
  )
  assert.throws(
    () => validate({ workflow: { ...workflow, sha: "b".repeat(40) } }),
    /workflow provenance/u
  )
  assert.throws(() => validate({ workflow: { ...workflow, runId: "43" } }), /workflow provenance/u)
  assert.throws(
    () => validate({ workflow: { ...workflow, runAttempt: "4" } }),
    /workflow provenance/u
  )
  assert.throws(
    () => validate({ sourcePolicy: { ...sourcePolicy, sha256: "4".repeat(64) } }),
    /source policy/u
  )
  assert.throws(() => validate({ config: { ...config, sha256: "5".repeat(64) } }), /configuration/u)
  assert.throws(
    () => validate({ toolchain: { ...toolchain, instrumenter: "9.6.2" } }),
    /toolchain/u
  )
  const changedSource = new Map(sourceByFile)
  changedSource.set("src/a.ts", "export const a = false\n")
  assert.throws(() => validate({ sourceByFile: changedSource }), /source snapshot/u)

  const missing = resealPreflightArtifact(artifact, (payload) => {
    delete payload.preflight.files["src/b.ts"]
  })
  assert.throws(() => validate({ artifact: missing }), /source denominator/u)

  const overlap = resealPreflightArtifact(artifact, (payload) => {
    payload.shardPlan[1].files = [payload.shardPlan[0].files[0]]
  })
  assert.throws(() => validate({ artifact: overlap }), /shard plan/u)

  const changedCanonical = new Map(preflightByFile)
  changedCanonical.set("src/a.ts", {
    ...changedCanonical.get("src/a.ts"),
    mutants: [
      {
        fileName: "src/a.ts",
        mutatorName: "BooleanLiteral",
        replacement: "true",
        location,
      },
    ],
  })
  assert.throws(
    () => validate({ canonicalPreflightByFile: changedCanonical }),
    /canonical instrumenter universe/u
  )

  const duplicateField = preflightArtifactText(artifact).replace(
    '  "payloadSha256":',
    '  "payloadSha256": "tampered",\n  "payloadSha256":'
  )
  assert.throws(
    () => validatePreflightArtifact({ ...common, artifactText: duplicateField }),
    /JSON is not canonical/u
  )
})

async function preflightCandidateFixture() {
  const { buildEvidenceIdentity, buildPreflightArtifact, selectPreflightArtifactCandidate } =
    await import(runnerUrl)
  const sourceByFile = new Map([["src/a.ts", "export const a = true\n"]])
  const sourceFiles = [...sourceByFile.keys()]
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    dirtyPaths: [],
    inputHashes: {
      "frontend/package-lock.json": "1".repeat(64),
      "frontend/stryker.config.mjs": "2".repeat(64),
      "frontend/src/a.ts": sha256Text(sourceByFile.get("src/a.ts")),
      "quality/coverage-source-policy.json": "3".repeat(64),
    },
  })
  const consumerWorkflow = { runId: "42", runAttempt: "3", sha: sourceRevision.headSha }
  const toolchain = {
    node: "v24.15.0",
    platform: "linux",
    arch: "x64",
    stryker: "9.6.1",
    instrumenter: "9.6.1",
    vitest: "4.1.10",
  }
  const sourcePolicy = {
    path: "quality/coverage-source-policy.json",
    sha256: "3".repeat(64),
  }
  const config = {
    path: "frontend/stryker.config.mjs",
    sha256: "2".repeat(64),
    instrumenterOptions: { plugins: null, excludedMutations: [], ignorers: [] },
  }
  const preflightByFile = new Map([
    [
      "src/a.ts",
      {
        sourceSha256: sha256Text(sourceByFile.get("src/a.ts")),
        mutants: [
          {
            fileName: "src/a.ts",
            mutatorName: "BooleanLiteral",
            replacement: "false",
            location,
          },
        ],
      },
    ],
  ])
  const common = {
    sourceRevision,
    workflow: consumerWorkflow,
    toolchain,
    sourcePolicy,
    config,
    sourceFiles,
    sourceByFile,
    shardTargetMutants: 750,
    shardCount: 1,
  }
  return {
    consumerWorkflow,
    createArtifact: (runAttempt) =>
      buildPreflightArtifact({
        ...common,
        workflow: { ...consumerWorkflow, runAttempt },
        preflightByFile,
      }),
    select: (candidateRoot) => selectPreflightArtifactCandidate({ ...common, candidateRoot }),
  }
}

function preflightCandidateDirectoryName(workflow) {
  return `frontend-mutation-preflight-${workflow.runId}-${workflow.runAttempt}-${workflow.sha}`
}

async function writePreflightCandidate(
  candidateRoot,
  artifact,
  directoryWorkflow = artifact.payload.workflow
) {
  const candidateDirectory = path.join(
    candidateRoot,
    preflightCandidateDirectoryName(directoryWorkflow)
  )
  await mkdir(candidateDirectory, { recursive: true })
  await writeFile(
    path.join(candidateDirectory, "PREFLIGHT_ARTIFACT.json"),
    preflightArtifactText(artifact)
  )
}

test("selects a previous-attempt Stryker preflight for a rerun-failed consumer", async (t) => {
  const { consumerWorkflow, createArtifact, select } = await preflightCandidateFixture()
  const candidateRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-preflight-candidates-"))
  t.after(() => rm(candidateRoot, { recursive: true, force: true }))
  await writePreflightCandidate(candidateRoot, createArtifact("2"))

  const selected = await select(candidateRoot)

  assert.equal(selected.producerAttempt, 2)
  assert.equal(selected.artifact.payload.workflow.runAttempt, "2")
  assert.deepEqual(selected.consumerWorkflow, consumerWorkflow)
})

test("selects the highest valid Stryker preflight attempt deterministically", async (t) => {
  const { createArtifact, select } = await preflightCandidateFixture()
  const candidateRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-preflight-candidates-"))
  t.after(() => rm(candidateRoot, { recursive: true, force: true }))
  await writePreflightCandidate(candidateRoot, createArtifact("1"))
  await writePreflightCandidate(candidateRoot, createArtifact("3"))

  const selected = await select(candidateRoot)

  assert.equal(selected.producerAttempt, 3)
  assert.equal(selected.artifact.payload.workflow.runAttempt, "3")
})

test("rejects future and tampered Stryker preflight candidates before selection", async (t) => {
  const { createArtifact, select } = await preflightCandidateFixture()
  const cases = [
    ["future attempt", createArtifact("4"), /producer attempt/u],
    [
      "revision tamper",
      resealPreflightArtifact(createArtifact("2"), (payload) => {
        payload.sourceRevision = { ...payload.sourceRevision, revision: "b".repeat(40) }
      }),
      /source revision/u,
    ],
    [
      "configuration tamper",
      resealPreflightArtifact(createArtifact("2"), (payload) => {
        payload.config = { ...payload.config, sha256: "4".repeat(64) }
      }),
      /configuration/u,
    ],
    [
      "source tamper",
      resealPreflightArtifact(createArtifact("2"), (payload) => {
        payload.preflight.files["src/a.ts"].sourceSha256 = "5".repeat(64)
      }),
      /source snapshot/u,
    ],
    [
      "toolchain tamper",
      resealPreflightArtifact(createArtifact("2"), (payload) => {
        payload.toolchain = { ...payload.toolchain, instrumenter: "9.6.2" }
      }),
      /toolchain/u,
    ],
  ]
  for (const [name, artifact, expectedError] of cases) {
    const candidateRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-preflight-candidates-"))
    t.after(() => rm(candidateRoot, { recursive: true, force: true }))
    await writePreflightCandidate(candidateRoot, artifact)
    await assert.rejects(() => select(candidateRoot), expectedError, name)
  }
})

test("rejects malformed candidate directories and duplicate producer attempts", async (t) => {
  const { createArtifact, select } = await preflightCandidateFixture()
  const malformedRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-preflight-candidates-"))
  const duplicateRoot = await mkdtemp(path.join(os.tmpdir(), "stryker-preflight-candidates-"))
  t.after(() => rm(malformedRoot, { recursive: true, force: true }))
  t.after(() => rm(duplicateRoot, { recursive: true, force: true }))
  await writeFile(path.join(malformedRoot, "unexpected.json"), "{}\n")
  await writePreflightCandidate(duplicateRoot, createArtifact("2"))
  await writePreflightCandidate(duplicateRoot, createArtifact("2"), {
    runId: "42",
    runAttempt: "02",
    sha: "a".repeat(40),
  })

  await assert.rejects(() => select(malformedRoot), /candidate root/u)
  await assert.rejects(
    () => select(duplicateRoot),
    /duplicate producer attempt|candidate directory/u
  )
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

test("aggregates mixed prior and current same-run shard candidates on a failed-jobs retry", async (t) => {
  const { loadExternalShardResults } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-mixed-attempts-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const reportText = `${JSON.stringify({ schemaVersion: "1.0", config: {}, files: {} })}\n`
  const shardPlan = [
    { id: "shard-000", files: ["src/a.ts"], mutantCount: 3 },
    { id: "shard-001", files: ["src/b.ts"], mutantCount: 5 },
  ]
  const writeCandidate = async ({ attempt, shard, artifactIndex }) => {
    const shardRoot = path.join(
      root,
      `frontend-mutation-shard-42-${attempt}-${artifactIndex}`,
      "shards",
      shard.id
    )
    await mkdir(shardRoot, { recursive: true })
    await writeFile(path.join(shardRoot, "mutation.json"), reportText)
    await writeFile(
      path.join(shardRoot, "SHARD_EVIDENCE.json"),
      JSON.stringify({
        schemaVersion: "1.0",
        runId: `producer-${attempt}-${shard.id}`,
        shardId: shard.id,
        shardIndex: shardPlan.indexOf(shard),
        shardCount: shardPlan.length,
        revision: "a".repeat(40),
        evidenceDigest: "b".repeat(64),
        preflightDigest: "c".repeat(64),
        workflowRunId: "42",
        workflowRunAttempt: attempt,
        files: shard.files,
        mutantCount: shard.mutantCount,
        reportSha256: createHash("sha256").update(reportText).digest("hex"),
      })
    )
  }
  await writeCandidate({ attempt: "1", shard: shardPlan[0], artifactIndex: "0" })
  await writeCandidate({ attempt: "2", shard: shardPlan[1], artifactIndex: "1" })

  const results = await loadExternalShardResults({
    aggregateRoot: root,
    shardPlan,
    before: { revision: "a".repeat(40), evidenceDigest: "b".repeat(64) },
    preflightDigest: "c".repeat(64),
    workflowRunId: "42",
    workflowRunAttempt: "2",
  })

  assert.deepEqual(
    results.map(({ id, producerAttempt }) => [id, producerAttempt]),
    [
      ["shard-000", 1],
      ["shard-001", 2],
    ]
  )
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
