import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

const runnerUrl = new URL("./run-stryker.mjs", import.meta.url)
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
  await first.release(async () => () => undefined)
  const second = await acquireRunLock(lockPath, "run-b")
  await second.release(async () => () => undefined)
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

test("focused evidence stays isolated from every canonical artifact", async (t) => {
  const {
    cleanupCanonicalArtifacts,
    mutationRunPaths,
    persistMutationEvidence,
    resolveMutationSourceSelection,
  } = await import(runnerUrl)
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-focused-evidence-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const canonicalRoot = path.join(root, "mutation")
  const canonicalArtifacts = [
    "mutation.json",
    "inventory.json",
    "preflight.json",
    "LOCAL_VALIDATION.json",
    "VALIDATED.json",
  ]
  await mkdir(path.join(canonicalRoot, "historical-costs"), { recursive: true })
  await Promise.all([
    ...canonicalArtifacts.map((name) => writeFile(path.join(canonicalRoot, name), "canonical")),
    writeFile(path.join(canonicalRoot, "historical-costs", "HISTORICAL_COSTS.json"), "canonical"),
  ])
  const selection = resolveMutationSourceSelection(["src/a.ts", "src/b.ts"], {
    STRYKER_LOCAL_MUTATE_JSON: '["src/a.ts"]',
  })
  const paths = mutationRunPaths(selection, canonicalRoot)
  await mkdir(path.join(paths.outputRoot, "runs", "stale"), { recursive: true })
  await writeFile(path.join(paths.outputRoot, "mutation.json"), "stale-focused")

  await cleanupCanonicalArtifacts(paths.outputRoot)

  for (const name of canonicalArtifacts) {
    assert.equal(await readFile(path.join(canonicalRoot, name), "utf8"), "canonical")
  }
  assert.equal(
    await readFile(path.join(canonicalRoot, "historical-costs", "HISTORICAL_COSTS.json"), "utf8"),
    "canonical"
  )

  const inventory = {
    schemaVersion: "2.0",
    runId: "focused-run",
    revision: "sha-dirty.digest",
    releaseEligible: false,
    summary: { viableMutantScore: 100 },
  }
  const preflight = { schemaVersion: "1.0", runId: "focused-run", files: {} }
  const persisted = await persistMutationEvidence({ paths, inventory, preflight })

  assert.equal(persisted.markerWritten, false)
  assert.match(persisted.inventorySha256, /^[a-f0-9]{64}$/u)
  assert.equal(
    JSON.parse(await readFile(path.join(paths.outputRoot, "inventory.json"))).runId,
    "focused-run"
  )
  assert.equal(
    JSON.parse(await readFile(path.join(paths.outputRoot, "preflight.json"))).runId,
    "focused-run"
  )
  await assert.rejects(
    () => readFile(path.join(paths.outputRoot, "LOCAL_VALIDATION.json")),
    /ENOENT/u
  )
  await assert.rejects(() => readFile(path.join(paths.outputRoot, "VALIDATED.json")), /ENOENT/u)
  await assert.rejects(
    () =>
      persistMutationEvidence({
        paths,
        inventory: { ...inventory, releaseEligible: true },
        preflight,
      }),
    /cannot be release eligible/u
  )
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
    sourceHeadSha: "b".repeat(40),
    baseSha: "c".repeat(40),
    baseRef: "main",
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
      sourceHeadSha: "b".repeat(40),
      baseSha: "c".repeat(40),
      baseRef: "main",
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

test("indexes and validates Windows process-host provenance when present", async () => {
  const { indexShardProducerEvidence } = await import(runnerUrl)
  const root = path.join(os.tmpdir(), "stryker-producer-index-windows")
  const windowsProcessHost = {
    sourceSha256: "d".repeat(64),
    binarySha256: "e".repeat(64),
  }
  const evidence = {
    schemaVersion: "1.0",
    shardId: "shard-000",
    revision: "a".repeat(40),
    sourceHeadSha: "b".repeat(40),
    baseSha: "c".repeat(40),
    baseRef: "main",
    evidenceDigest: "b".repeat(64),
    workflowRunId: "42",
    workflowRunAttempt: "2",
    reportSha256: "c".repeat(64),
    windowsProcessHost,
  }
  const evidenceText = `${JSON.stringify(evidence)}\n`
  const indexed = indexShardProducerEvidence(
    [
      {
        id: "shard-000",
        shardEvidencePath: path.join(root, "SHARD_EVIDENCE.json"),
        shardEvidenceText: evidenceText,
        shardEvidence: evidence,
      },
    ],
    root
  )
  assert.deepEqual(indexed[0].windowsProcessHost, windowsProcessHost)
  assert.throws(
    () =>
      indexShardProducerEvidence(
        [
          {
            id: "shard-000",
            shardEvidencePath: path.join(root, "SHARD_EVIDENCE.json"),
            shardEvidenceText: `${JSON.stringify({
              ...evidence,
              windowsProcessHost: { sourceSha256: "d".repeat(64) },
            })}\n`,
            shardEvidence: {
              ...evidence,
              windowsProcessHost: { sourceSha256: "d".repeat(64) },
            },
          },
        ],
        root
      ),
    /Windows process-host evidence has an unexpected shape/u
  )
})

test("local-focused producer evidence has truthful absent workflow identity and no release marker", async (t) => {
  const { indexShardProducerEvidence, mutationRunPaths, persistMutationEvidence } = await import(
    runnerUrl
  )
  const root = await mkdtemp(path.join(os.tmpdir(), "stryker-local-producer-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const scope = { kind: "local-focused", sourceFiles: ["src/a.ts"] }
  const paths = mutationRunPaths({ focused: true, sourceFiles: scope.sourceFiles }, root)
  for (const workflowIdentity of [{ workflowRunId: null, workflowRunAttempt: null }, {}]) {
    const evidence = {
      schemaVersion: "1.0",
      shardId: "shard-000",
      revision: "a".repeat(40),
      sourceHeadSha: "a".repeat(40),
      baseSha: "a".repeat(40),
      baseRef: null,
      evidenceDigest: "b".repeat(64),
      reportSha256: "c".repeat(64),
      ...workflowIdentity,
    }
    const shard = {
      id: evidence.shardId,
      shardEvidencePath: path.join(paths.outputRoot, "SHARD_EVIDENCE.json"),
      shardEvidenceText: `${JSON.stringify(evidence)}\n`,
      shardEvidence: evidence,
    }
    const indexed = indexShardProducerEvidence([shard], root, {
      scope,
      releaseEligible: false,
      env: {},
    })
    assert.equal(indexed[0].workflowRunId, evidence.workflowRunId)
    assert.equal(indexed[0].workflowRunAttempt, evidence.workflowRunAttempt)
    const inventory = {
      runId: "local-run",
      scope,
      releaseEligible: false,
      summary: { viableMutantScore: 100 },
      shardEvidence: indexed,
    }
    const persisted = await persistMutationEvidence({
      paths,
      inventory,
      preflight: { runId: inventory.runId },
    })
    assert.equal(persisted.markerWritten, false)
    assert.deepEqual(
      JSON.parse(await readFile(path.join(paths.outputRoot, "inventory.json"))),
      JSON.parse(JSON.stringify(inventory))
    )
    for (const name of ["VALIDATED.json", "LOCAL_VALIDATION.json"]) {
      await assert.rejects(() => readFile(path.join(paths.outputRoot, name)), /ENOENT/u)
    }
    assert.throws(() => indexShardProducerEvidence([shard], root), /malformed/u)
    assert.throws(
      () =>
        indexShardProducerEvidence([shard], root, {
          scope: { kind: "canonical" },
          releaseEligible: false,
          env: {},
        }),
      /malformed/u
    )
  }
})

test("local-focused producer identity rejects mixed, malformed, and claimed workflow identities", async () => {
  const { indexShardProducerEvidence } = await import(runnerUrl)
  const root = path.join(os.tmpdir(), "stryker-local-producer-negative")
  const scope = { kind: "local-focused", sourceFiles: ["src/a.ts"] }
  const evidence = {
    schemaVersion: "1.0",
    shardId: "shard-000",
    revision: "a".repeat(40),
    sourceHeadSha: "a".repeat(40),
    baseSha: "a".repeat(40),
    baseRef: null,
    evidenceDigest: "b".repeat(64),
    reportSha256: "c".repeat(64),
    workflowRunId: null,
    workflowRunAttempt: null,
  }
  const index = (identity, options = { scope, releaseEligible: false, env: {} }) => {
    const document = { ...evidence, ...identity }
    return indexShardProducerEvidence(
      [
        {
          id: document.shardId,
          shardEvidencePath: path.join(root, "SHARD_EVIDENCE.json"),
          shardEvidenceText: JSON.stringify(document),
          shardEvidence: document,
        },
      ],
      root,
      options
    )
  }
  for (const identity of [
    { workflowRunId: null, workflowRunAttempt: undefined },
    { workflowRunId: undefined, workflowRunAttempt: null },
    { workflowRunId: "42", workflowRunAttempt: null },
    { workflowRunId: null, workflowRunAttempt: "1" },
    { workflowRunId: "42", workflowRunAttempt: "1" },
    { workflowRunId: "", workflowRunAttempt: "0" },
    { workflowRunId: 42, workflowRunAttempt: 1 },
  ])
    assert.throws(() => index(identity), /malformed/u)
  for (const identity of [
    {},
    { workflowRunId: undefined, workflowRunAttempt: undefined },
    { workflowRunId: "42", workflowRunAttempt: null },
    { workflowRunId: null, workflowRunAttempt: "1" },
    { workflowRunId: "", workflowRunAttempt: "1" },
    { workflowRunId: "42", workflowRunAttempt: "0" },
    { workflowRunId: "42", workflowRunAttempt: "1.5" },
    { workflowRunId: "42", workflowRunAttempt: "9007199254740992" },
    { workflowRunId: 42, workflowRunAttempt: 1 },
  ]) {
    assert.throws(() => index(identity, {}), /malformed/u)
    assert.throws(
      () => index(identity, { scope: { kind: "canonical" }, releaseEligible: false, env: {} }),
      /malformed/u
    )
  }
  for (const options of [
    { scope, releaseEligible: true, env: {} },
    { scope, env: {} },
    { scope: { kind: "local-focused", sourceFiles: [] }, releaseEligible: false, env: {} },
    ...[
      { GITHUB_ACTIONS: "true" },
      { GITHUB_RUN_ID: "42" },
      { GITHUB_RUN_ATTEMPT: "1" },
      { STRYKER_SHARD_COUNT: "2" },
    ].map((env) => ({ scope, releaseEligible: false, env })),
  ])
    assert.throws(() => index({}, options), /local-only|Local-focused|denominator/u)
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

test("local focused mutation scope selects only canonical policy sources", async () => {
  const { mutationRunPaths, resolveMutationSourceSelection } = await import(runnerUrl)
  const canonicalSources = ["src/a.ts", "src/b.ts", "src/c.ts"]
  const canonicalOutputRoot = path.join("reports", "mutation")

  const canonical = resolveMutationSourceSelection(canonicalSources, {})
  assert.deepEqual(canonical, {
    focused: false,
    sourceFiles: canonicalSources,
  })
  assert.deepEqual(mutationRunPaths(canonical, canonicalOutputRoot), {
    allowReleaseMarkers: true,
    historicalCostOutputPath: path.join(
      canonicalOutputRoot,
      "historical-costs",
      "HISTORICAL_COSTS.json"
    ),
    lockPath: path.join(canonicalOutputRoot, ".run.lock"),
    outputRoot: canonicalOutputRoot,
  })

  const focused = resolveMutationSourceSelection(canonicalSources, {
    STRYKER_LOCAL_MUTATE_JSON: '["src/c.ts","src/a.ts"]',
  })
  assert.deepEqual(focused, {
    focused: true,
    sourceFiles: ["src/a.ts", "src/c.ts"],
  })
  const focusedPaths = mutationRunPaths(focused, canonicalOutputRoot)
  assert.equal(path.dirname(focusedPaths.outputRoot), path.join(canonicalOutputRoot, "focused"))
  assert.equal(focusedPaths.lockPath, path.join(focusedPaths.outputRoot, ".run.lock"))
  assert.equal(focusedPaths.historicalCostOutputPath, null)
  assert.equal(focusedPaths.allowReleaseMarkers, false)
  assert.notEqual(focusedPaths.outputRoot, canonicalOutputRoot)
  assert.deepEqual(mutationRunPaths(focused, canonicalOutputRoot), focusedPaths)

  assert.throws(
    () =>
      resolveMutationSourceSelection(canonicalSources, {
        STRYKER_MUTATE_JSON: '["src/a.ts"]',
      }),
    /reserved for child shards/u
  )

  for (const raw of [
    "not-json",
    "[]",
    '["src/a.ts","src/a.ts"]',
    '["src/missing.ts"]',
    '["../src/a.ts"]',
  ]) {
    assert.throws(
      () =>
        resolveMutationSourceSelection(canonicalSources, {
          STRYKER_LOCAL_MUTATE_JSON: raw,
        }),
      /focused mutation scope/u
    )
  }
})

test("workflow and producer evidence reject ad-hoc focused mutation scope", async () => {
  const { resolveMutationSourceSelection } = await import(runnerUrl)
  const canonicalSources = ["src/a.ts", "src/b.ts"]
  const scope = '["src/a.ts"]'
  const privilegedModes = [
    { GITHUB_ACTIONS: "true" },
    { GITHUB_RUN_ID: "42" },
    { STRYKER_SHARD_COUNT: "2" },
    { STRYKER_SHARD_INDEX: "0" },
    { STRYKER_AGGREGATE_ROOT: "reports/mutation/external" },
    { STRYKER_PREFLIGHT_MODE: "generate" },
    { STRYKER_PREFLIGHT_ARTIFACT: "required" },
    { STRYKER_SHARD_RUN: "1" },
  ]

  for (const env of privilegedModes) {
    assert.throws(
      () =>
        resolveMutationSourceSelection(canonicalSources, {
          ...env,
          STRYKER_LOCAL_MUTATE_JSON: scope,
        }),
      /local-only/u
    )
  }

  assert.deepEqual(resolveMutationSourceSelection(canonicalSources, { GITHUB_ACTIONS: "true" }), {
    focused: false,
    sourceFiles: canonicalSources,
  })
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

test("isolates measured API test-graph hotspots in dedicated first-attempt shards", async () => {
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
  const hotspotFiles = [
    ["src/api/interceptors/etagCache.ts", 239],
    ["src/api/hooks/users.ts", 8],
    ["src/api/hooks/events.ts", 301],
    ["src/api/hooks/news.ts", 170],
  ]
  const regularFiles = Array.from({ length: 10 }, (_, index) => {
    const file = `src/regular-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ...hotspotFiles.map(([file, count]) => [file, { mutants: makeMutants(file, count) }]),
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 64)

  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    10_718
  )
  const assignments = plan.flatMap(({ files }) => files)
  assert.equal(new Set(assignments).size, assignments.length)

  for (const [file, count] of hotspotFiles) {
    const assignedShardIndexes = plan.flatMap((shard, shardIndex) =>
      shard.files.some((pattern) => pattern === file || pattern.startsWith(`${file}:`))
        ? [shardIndex]
        : []
    )
    assert.ok(assignedShardIndexes.length > 0, `${file} is missing from the shard plan`)
    assert.ok(
      assignedShardIndexes.every((shardIndex) => shardIndex < 12),
      `${file} leaked into a regular first-attempt shard`
    )
    if (count > 8) {
      assert.ok(
        new Set(assignedShardIndexes).size > 1,
        `${file} should be split across the dedicated hotspot shards`
      )
    }
  }
  assert.ok(
    plan
      .slice(0, 12)
      .every((shard) =>
        shard.files.some((pattern) => hotspotFiles.some(([file]) => pattern.startsWith(file)))
      ),
    "each dedicated hotspot shard must receive a measured API source range"
  )
  assert.ok(
    plan
      .slice(12)
      .every((shard) =>
        shard.files.every((pattern) =>
          regularFiles.some(([file]) => pattern === file || pattern.startsWith(`${file}:`))
        )
      ),
    "regular shards must not inherit an expensive API graph"
  )
})

test("keeps the client enclosing graph separate from UI hotspot ranges", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count, startLine = 0) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: startLine + index * 2, column: 0 },
        end: { line: startLine + index * 2, column: 4 },
      },
    }))
  const clientMutants = [
    {
      fileName: "src/api/client.ts",
      mutatorName: "BlockStatement",
      replacement: "{}",
      location: {
        start: { line: 246, column: 46 },
        end: { line: 360, column: 0 },
      },
    },
    ...makeMutants("src/api/client.ts", 300, 400),
  ]
  const badgeMutants = [
    {
      fileName: "src/components/ui/Badge.tsx",
      mutatorName: "ObjectLiteral",
      replacement: "{}",
      location: {
        start: { line: 5, column: 1 },
        end: { line: 91, column: 2 },
      },
    },
    {
      fileName: "src/components/ui/Badge.tsx",
      mutatorName: "BlockStatement",
      replacement: "{}",
      location: {
        start: { line: 117, column: 20 },
        end: { line: 138, column: 26 },
      },
    },
  ]
  const regularFiles = Array.from({ length: 10 }, (_, index) => {
    const file = `src/regular-client-separation-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ["src/api/client.ts", { mutants: clientMutants }],
    ["src/components/ui/Badge.tsx", { mutants: badgeMutants }],
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )

  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )
  assert.ok(
    plan.every((shard) => {
      const hasClient = shard.files.some((pattern) => pattern.startsWith("src/api/client.ts"))
      const hasBadge = shard.files.some((pattern) =>
        pattern.startsWith("src/components/ui/Badge.tsx")
      )
      return !(hasClient && hasBadge)
    }),
    "client and Badge related-test graphs must not share a first-attempt shard"
  )
})

test("isolates the recurrent unmeasured API/core timeout graph in dedicated first-attempt shards", async () => {
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
  const recurrentHotspots = [
    ["src/api/backendOrigin.ts", 20],
    ["src/api/chat.ts", 200],
    ["src/api/client.ts", 500],
    ["src/api/events.ts", 40],
    ["src/api/hooks/activity.ts", 200],
    ["src/api/hooks/adminAudit.ts", 50],
    ["src/api/hooks/adminFeatureFlags.ts", 50],
    ["src/api/hooks/adminNotifications.ts", 50],
    ["src/api/hooks/adminUsers.ts", 100],
    ["src/api/hooks/sessions.ts", 50],
    ["src/api/hooks/weather.ts", 100],
    ["src/api/interceptors/language.ts", 100],
    ["src/api/interceptors/rateLimit.ts", 144],
    ["src/api/mfa.ts", 37],
    ["src/api/news.ts", 65],
    ["src/api/notifications.ts", 110],
    ["src/api/offlineMutationQueue.ts", 24],
    ["src/api/schemas/wsMessage.ts", 151],
    ["src/api/stories.ts", 16],
    ["src/App.tsx", 9],
    ["src/app/globalErrorHandlers.ts", 53],
    ["src/app/hydration.ts", 40],
  ]
  const measuredHotspots = [
    ["src/api/interceptors/etagCache.ts", 239],
    ["src/api/hooks/events.ts", 301],
  ]
  const regularFiles = Array.from({ length: 12 }, (_, index) => {
    const file = `src/regular-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ...recurrentHotspots.map(([file, count]) => [file, { mutants: makeMutants(file, count) }]),
    ...measuredHotspots.map(([file, count]) => [file, { mutants: makeMutants(file, count) }]),
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 64)
  const reversePlan = planMutationShards(new Map([...preflight].reverse()), 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )
  const assignments = plan.flatMap(({ files }) => files)

  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )
  assert.equal(new Set(assignments).size, assignments.length)
  assert.deepEqual(plan, reversePlan)

  const isRegularPattern = (pattern) =>
    regularFiles.some(([file]) => pattern === file || pattern.startsWith(`${file}:`))
  const regularStart = plan.findIndex(
    (shard) => shard.files.length > 0 && shard.files.every(isRegularPattern)
  )
  assert.ok(regularStart > 0, "the first-attempt prefix must precede regular work")

  for (const [file] of [...recurrentHotspots, ...measuredHotspots]) {
    const assignedShardIndexes = plan.flatMap((shard, shardIndex) =>
      shard.files.some((pattern) => pattern === file || pattern.startsWith(`${file}:`))
        ? [shardIndex]
        : []
    )
    assert.ok(assignedShardIndexes.length > 0, `${file} is missing from the shard plan`)
    assert.ok(
      assignedShardIndexes.every((shardIndex) => shardIndex < regularStart),
      `${file} leaked into a regular first-attempt shard`
    )
  }

  const backendOriginShard = plan.find((shard) =>
    shard.files.some((pattern) => pattern.startsWith("src/api/backendOrigin.ts"))
  )
  assert.ok(backendOriginShard)
  assert.ok(
    backendOriginShard.files.every((pattern) => pattern.startsWith("src/api/backendOrigin.ts"))
  )
  assert.ok(
    plan.slice(regularStart).every((shard) => shard.files.every(isRegularPattern)),
    "regular shards must not inherit the recurrent timeout graph"
  )
})

test("isolates every source from the observed UI and auth timeout shards", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count, startLine = 0) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: startLine + index * 2, column: 0 },
        end: { line: startLine + index * 2, column: 4 },
      },
    }))
  const makeProfileSyncMutants = (file) => [
    ...Array.from({ length: 353 }, (_, index) => ({
      fileName: file,
      mutatorName: "BlockStatement",
      replacement: "{}",
      location: {
        start: { line: 675, column: 88 },
        end: { line: 1200, column: 1 },
      },
      index,
    })),
    ...makeMutants(file, 385, 2_000),
  ]
  const uiHotspots = [
    "src/components/ui/Button.tsx",
    "src/components/ui/Card.tsx",
    "src/components/ui/CardActionArea.tsx",
    "src/components/ui/Checkbox.tsx",
    "src/components/ui/ConfirmDialog.tsx",
    "src/components/ui/ContentCard.tsx",
    "src/components/ui/ContentSummary.tsx",
    "src/components/ui/Dialog.tsx",
    "src/components/ui/EmptyState.tsx",
    "src/components/ui/GlassCard.tsx",
    "src/components/ui/GlobalHapticsListener.tsx",
    "src/components/ui/Input.tsx",
    "src/components/ui/LiveRegionProvider.tsx",
    "src/components/ui/MediaSlot.tsx",
    "src/components/ui/NewsCardSkeleton.tsx",
    "src/components/ui/NotificationRelevanceScore.tsx",
    "src/components/ui/ParticleAuthBackground.tsx",
    "src/components/ui/ProfileCardSkeleton.tsx",
    "src/components/ui/ProgressBar.tsx",
    "src/components/ui/RadioGroup.tsx",
    "src/components/ui/data-table/DataTable.tsx",
    "src/components/ui/data-table/DataTableColumnHeader.tsx",
    "src/components/ui/data-table/DataTablePagination.tsx",
    "src/components/ui/data-table/dataTableFeatures.ts",
    "src/components/ui/motion/FadeIn.tsx",
    "src/components/ui/motion/ScaleIn.tsx",
    "src/components/ui/motion/StaggerChildren.tsx",
    // Run 34634679511 shard 41/64: these files formed the unweighted UI
    // graph that reached the 120-minute producer limit. They must remain in
    // the first-attempt cost-aware prefix as the planner evolves.
    "src/components/stories/StoryViewer.tsx",
    "src/components/ui/ActionMenu.tsx",
    "src/components/ui/Badge.tsx",
    "src/components/ui/SEO.tsx",
    "src/components/ui/SafeHtml.tsx",
    "src/components/ui/ScheduleCardSkeleton.tsx",
    "src/components/ui/Select.tsx",
    "src/components/ui/Skeleton.tsx",
    "src/components/ui/SkeletonMorph.tsx",
    "src/components/ui/Snackbar.tsx",
    "src/components/ui/Spinner.tsx",
    "src/components/ui/SpotifyConnect.tsx",
    "src/components/ui/Spotlight.tsx",
    "src/components/ui/StoryCircle.tsx",
    "src/components/ui/Switch.tsx",
    "src/components/ui/TextField.tsx",
    "src/components/ui/Textarea.tsx",
    "src/components/ui/table.tsx",
  ]
  const authHotspots = ["src/hooks/auth/useProfileSync.ts", "src/hooks/auth/useSessionCrypto.ts"]
  const regularFiles = Array.from({ length: 12 }, (_, index) => {
    const file = `src/aaa-regular-timeout-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ["src/api/backendOrigin.ts", { mutants: makeMutants("src/api/backendOrigin.ts", 20) }],
    ...uiHotspots.map((file) => [file, { mutants: makeMutants(file, 32) }]),
    [authHotspots[0], { mutants: makeProfileSyncMutants(authHotspots[0]) }],
    [authHotspots[1], { mutants: makeMutants(authHotspots[1], 177) }],
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )

  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )

  const hotspotFiles = [...uiHotspots, ...authHotspots]
  const isRegularPattern = (pattern) =>
    regularFiles.some(([file]) => pattern === file || pattern.startsWith(`${file}:`))
  const regularStart = plan.findIndex(
    (shard) => shard.files.length > 0 && shard.files.every(isRegularPattern)
  )
  assert.ok(regularStart > 0, "the first-attempt prefix must precede regular work")
  for (const file of hotspotFiles) {
    const assignedShardIndexes = plan.flatMap((shard, shardIndex) =>
      shard.files.some((pattern) => pattern === file || pattern.startsWith(`${file}:`))
        ? [shardIndex]
        : []
    )
    assert.ok(assignedShardIndexes.length > 0, `${file} is missing from the shard plan`)
    assert.ok(
      assignedShardIndexes.every((shardIndex) => shardIndex < regularStart),
      `${file} leaked into a regular first-attempt shard`
    )
  }
  for (const file of authHotspots) {
    const authShardIndexes = plan.flatMap((shard, shardIndex) =>
      shard.files.some((pattern) => pattern === file || pattern.startsWith(`${file}:`))
        ? [shardIndex]
        : []
    )
    assert.ok(
      authShardIndexes.every((shardIndex) =>
        plan[shardIndex].files.every(
          (pattern) => pattern === file || pattern.startsWith(`${file}:`)
        )
      ),
      `${file} must not share an isolated auth range shard`
    )
  }

  const uiShardIndexes = plan.flatMap((shard, shardIndex) =>
    shard.files.some((pattern) => uiHotspots.some((file) => pattern.startsWith(file)))
      ? [shardIndex]
      : []
  )
  assert.ok(
    new Set(uiShardIndexes).size > 1,
    "the UI timeout graph must be distributed across multiple cost-aware shards"
  )
  assert.ok(
    plan.slice(regularStart).every((shard) => shard.files.every(isRegularPattern)),
    "regular shards must not inherit either observed timeout graph"
  )
})

test("keeps static reload hotspots within bounded first-attempt assignments", async () => {
  const { mutationPatternCoversMutant, planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: index * 5, column: 0 },
        end: { line: index * 5, column: 4 },
      },
    }))
  const staticHotspots = [
    ["src/contexts/LanguageContext.tsx", 64],
    ["src/db/index.ts", 36],
  ]
  const regularFiles = Array.from({ length: 12 }, (_, index) => {
    const file = `src/static-cost-regular-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ...staticHotspots.map(([file, count]) => [file, { mutants: makeMutants(file, count) }]),
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )
  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )

  // The bounded first-attempt lane may have fewer logical shards than source
  // ranges in a hotspot. In that case ranges from the same source can share a
  // shard, but must stay within the planner's conservative per-range budget.
  const staticUnitBudget = Math.max(1, Math.ceil(Math.ceil(expectedMutants / 64) / 16))

  for (const [file] of staticHotspots) {
    const assignedShards = plan.filter((shard) =>
      shard.files.some((pattern) => pattern === file || pattern.startsWith(`${file}:`))
    )
    assert.ok(assignedShards.length > 0, `${file} is missing from the shard plan`)
    assert.ok(
      assignedShards.every((shard) => {
        const assignedHotspotMutants = shard.files.reduce(
          (total, pattern) =>
            total +
            preflight
              .get(file)
              .mutants.filter((mutant) => mutationPatternCoversMutant(pattern, mutant, file))
              .length,
          0
        )
        return assignedHotspotMutants <= staticUnitBudget
      }),
      `${file} exceeds the conservative static reload budget`
    )
  }
  const hotspotShardSets = staticHotspots.map(
    ([file]) =>
      new Set(
        plan.flatMap((shard, index) =>
          shard.files.some((pattern) => pattern === file || pattern.startsWith(`${file}:`))
            ? [index]
            : []
        )
      )
  )
  const sharedHotspotShards = [...hotspotShardSets[0]].filter((index) =>
    hotspotShardSets[1].has(index)
  )
  assert.equal(
    sharedHotspotShards.length,
    0,
    "static reload hotspots must not share a first-attempt shard"
  )
})

test("rebalances the observed shard-33 timeout graph without changing coverage denominator", async () => {
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
  // These are the eleven sources assigned to shard 33 in run
  // 35160102569 (505 mutants, 71 static). The static-heavy sources are
  // intentionally checked as independent units; the remaining sources still
  // use the weighted first-attempt lane.
  const timeoutGraph = [
    ["src/api/chat.ts", 75],
    ["src/api/hooks/adminUsers.ts", 31],
    ["src/api/hooks/events.ts", 63],
    ["src/api/notifications.ts", 67],
    ["src/app/hydration.ts", 40],
    ["src/components/ui/Button.tsx", 45],
    ["src/components/ui/NotificationRelevanceScore.tsx", 25],
    ["src/components/ui/RadioGroup.tsx", 44],
    ["src/components/ui/data-table/DataTable.tsx", 29],
    ["src/components/ui/data-table/dataTableFeatures.ts", 8],
    ["src/hooks/useMediaQuery.ts", 58],
  ]
  const regularFiles = Array.from({ length: 12 }, (_, index) => {
    const file = `src/rebalance-regular-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ...timeoutGraph.map(([file, count]) => [file, { mutants: makeMutants(file, count) }]),
    ...regularFiles,
  ])
  const plan = planMutationShards(preflight, 750, 64)
  const reversePlan = planMutationShards(new Map([...preflight].reverse()), 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )

  assert.equal(plan.length, 64)
  assert.deepEqual(plan, reversePlan)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )
  const assignments = plan.flatMap(({ files }) => files)
  assert.equal(new Set(assignments).size, assignments.length)
  for (const [file] of timeoutGraph) {
    assert.ok(
      assignments.some((pattern) => pattern === file || pattern.startsWith(`${file}:`)),
      `${file} is missing from the rebalanced inventory`
    )
  }

  const staticSources = new Set([
    "src/api/hooks/adminUsers.ts",
    "src/api/notifications.ts",
    "src/components/ui/Button.tsx",
    "src/components/ui/NotificationRelevanceScore.tsx",
  ])
  const staticShardIndexes = plan.flatMap((shard, index) =>
    shard.files.some((pattern) => staticSources.has(pattern.split(":", 1)[0])) ? [index] : []
  )
  assert.ok(new Set(staticShardIndexes).size >= staticSources.size)
  assert.ok(
    new Set(staticShardIndexes).size > 1,
    "the formerly timed-out static graph must be spread across bounded runners"
  )
  assert.ok(
    plan.some((shard) => shard.files.some((pattern) => pattern.startsWith("src/api/chat.ts:"))),
    "the unsplittable chat range must remain in the complete inventory"
  )
})

test("does not mix independent static hotspot sources when the first-attempt lane has capacity", async () => {
  const { planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: index * 5, column: 0 },
        end: { line: index * 5, column: 4 },
      },
    }))
  const staticHotspots = [
    ["src/contexts/LanguageContext.tsx", 64],
    ["src/db/index.ts", 36],
    ["src/components/ui/table.tsx", 48],
    ["src/components/ui/Snackbar.tsx", 32],
  ]
  const apiHotspot = [
    "src/api/interceptors/etagCache.ts",
    { mutants: makeMutants("src/api/interceptors/etagCache.ts", 239) },
  ]
  const regularFiles = Array.from({ length: 12 }, (_, index) => {
    const file = `src/static-isolation-regular-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ...staticHotspots.map(([file, count]) => [file, { mutants: makeMutants(file, count) }]),
    apiHotspot,
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 64)
  assert.equal(plan.length, 64)
  assert.ok(
    plan.every(({ files }) => files.length > 0),
    "first-attempt shards must not be empty"
  )
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    12_419
  )

  const staticSources = new Set(staticHotspots.map(([file]) => file))
  const sourceOf = (pattern) => pattern.split(":", 1)[0]
  const staticShardIndexes = []
  for (const [index, shard] of plan.entries()) {
    const sources = new Set(shard.files.map(sourceOf).filter((source) => staticSources.has(source)))
    if (sources.size > 0) {
      staticShardIndexes.push(index)
      assert.equal(
        sources.size,
        1,
        `independent static sources must not share shard ${shard.id}: ${shard.files.join(", ")}`
      )
    }
  }
  assert.ok(staticShardIndexes.length >= staticHotspots.length)
})

test("isolates the unsplittable Select AST hotspot without changing the 64-way denominator", async () => {
  const { mutationPatternCoversMutant, planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: index, column: 0 },
        end: { line: index, column: 4 },
      },
    }))
  const selectFile = "src/components/ui/Select.tsx"
  const selectMutants = [
    {
      fileName: selectFile,
      mutatorName: "BlockStatement",
      replacement: "{}",
      // This enclosing AST mutation spans the component and makes the source
      // range unsplittable: narrowing it would drop the enclosing mutant.
      location: {
        start: { line: 47, column: 19 },
        end: { line: 304, column: 1 },
      },
    },
    ...Array.from({ length: 215 }, (_, index) => ({
      fileName: selectFile,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: 48 + index, column: 0 },
        end: { line: 48 + index, column: 4 },
      },
    })),
  ]
  const regularFiles = Array.from({ length: 10 }, (_, index) => {
    const file = `src/select-hotspot-regular-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    [selectFile, { mutants: selectMutants }],
    [
      "src/api/interceptors/etagCache.ts",
      {
        mutants: makeMutants("src/api/interceptors/etagCache.ts", 239),
      },
    ],
    ...regularFiles,
  ])
  const plan = planMutationShards(preflight, 750, 64)
  const reversePlan = planMutationShards(new Map([...preflight].reverse()), 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )

  assert.equal(plan.length, 64)
  assert.deepEqual(plan, reversePlan)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )
  const assignments = plan.flatMap(({ files }) => files)
  assert.equal(new Set(assignments).size, assignments.length)

  const selectShards = plan.filter((shard) =>
    shard.files.some((pattern) => pattern.startsWith(`${selectFile}:`))
  )
  assert.equal(selectShards.length, 1)
  assert.deepEqual(selectShards[0].files, [`${selectFile}:48:19-305:1`])
  assert.equal(
    selectMutants.filter((mutant) =>
      mutationPatternCoversMutant(selectShards[0].files[0], mutant, selectFile)
    ).length,
    selectMutants.length
  )
})

test("isolates the unsplittable StoryViewer AST hotspot without changing the 64-way denominator", async () => {
  const { mutationPatternCoversMutant, planMutationShards } = await import(runnerUrl)
  const makeMutants = (file, count, startLine = 0) =>
    Array.from({ length: count }, (_, index) => ({
      fileName: file,
      mutatorName: "BooleanLiteral",
      replacement: index % 2 === 0 ? "true" : "false",
      location: {
        start: { line: startLine + index, column: 0 },
        end: { line: startLine + index, column: 4 },
      },
    }))
  const storyFile = "src/components/stories/StoryViewer.tsx"
  const storyMutants = [
    {
      fileName: storyFile,
      mutatorName: "BlockStatement",
      replacement: "{}",
      location: {
        start: { line: 14, column: 17 },
        end: { line: 304, column: 1 },
      },
    },
    ...makeMutants(storyFile, 157, 20),
  ]
  const badgeFile = "src/components/ui/Badge.tsx"
  const preflight = new Map([
    [storyFile, { mutants: storyMutants }],
    [badgeFile, { mutants: makeMutants(badgeFile, 32) }],
    ...Array.from({ length: 10 }, (_, index) => {
      const file = `src/story-hotspot-regular-${index}.ts`
      return [file, { mutants: makeMutants(file, 1_000) }]
    }),
  ])

  const plan = planMutationShards(preflight, 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )

  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )
  const assignments = plan.flatMap(({ files }) => files)
  assert.equal(new Set(assignments).size, assignments.length)

  const storyShards = plan.filter((shard) =>
    shard.files.some((pattern) => pattern.startsWith(`${storyFile}:`))
  )
  assert.equal(storyShards.length, 1)
  assert.ok(storyShards[0].files.every((pattern) => pattern.startsWith(`${storyFile}:`)))
  assert.equal(
    storyMutants.filter((mutant) =>
      mutationPatternCoversMutant(storyShards[0].files[0], mutant, storyFile)
    ).length,
    storyMutants.length
  )
  assert.ok(
    plan.every(
      (shard) =>
        !shard.files.some((pattern) => pattern.startsWith(`${storyFile}:`)) ||
        !shard.files.some((pattern) => pattern.startsWith(`${badgeFile}:`))
    ),
    "StoryViewer must not share its enclosing graph with UI hotspots"
  )
})

test("keeps the dedicated first-attempt planner total with two requested shards", async () => {
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
    ["src/api/backendOrigin.ts", { mutants: makeMutants("src/api/backendOrigin.ts", 100) }],
    ["src/api/client.ts", { mutants: makeMutants("src/api/client.ts", 10_000) }],
    ["src/regular.ts", { mutants: makeMutants("src/regular.ts", 100) }],
  ])

  const plan = planMutationShards(preflight, 750, 2)
  assert.equal(plan.length, 2)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    10_200
  )
  const assignments = plan.flatMap(({ files }) => files)
  assert.equal(new Set(assignments).size, assignments.length)
  assert.ok(assignments.length >= 3)
  assert.ok(plan[0]?.files.every((pattern) => pattern.startsWith("src/api/backendOrigin.ts")))
  assert.ok(plan[1]?.files.some((pattern) => pattern.startsWith("src/api/client.ts")))
  assert.ok(plan[1]?.files.some((pattern) => pattern === "src/regular.ts"))
})

test("isolates proven non-API test-graph hotspots without dropping regular work", async () => {
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
  const hotspotFiles = [
    "src/app/logger.ts",
    "src/components/media/SmartImage.tsx",
    "src/components/schedule/scheduleUtils.ts",
    "src/contexts/LanguageContext.tsx",
    "src/db/index.ts",
  ]
  const preflight = new Map([
    ...hotspotFiles.map((file) => [file, { mutants: makeMutants(file, 500) }]),
    ...Array.from({ length: 10 }, (_, index) => {
      const file = `src/regular-${index}.ts`
      return [file, { mutants: makeMutants(file, 1_000) }]
    }),
  ])

  const plan = planMutationShards(preflight, 750, 64)
  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    12_500
  )
  const isRegularPattern = (pattern) => pattern.startsWith("src/regular-")
  const regularStart = plan.findIndex(
    (shard) => shard.files.length > 0 && shard.files.every(isRegularPattern)
  )
  assert.ok(regularStart > 0, "the first-attempt prefix must precede regular work")

  for (const file of hotspotFiles) {
    const assignedShardIndexes = plan.flatMap((shard, shardIndex) =>
      shard.files.some((pattern) => pattern === file || pattern.startsWith(`${file}:`))
        ? [shardIndex]
        : []
    )
    assert.ok(assignedShardIndexes.length > 0, `${file} is missing from the shard plan`)
    assert.ok(
      assignedShardIndexes.every((shardIndex) => shardIndex < regularStart),
      `${file} leaked into a regular first-attempt shard`
    )
  }
  assert.ok(
    plan
      .slice(regularStart)
      .every((shard) => shard.files.every((pattern) => pattern.startsWith("src/regular-"))),
    "regular shards must not inherit a proven expensive graph"
  )
})

test("reserves a regular shard when a first-attempt plan has eight requested shards", async () => {
  const { buildHistoricalCostArtifactFromShardTimings, planMutationShards } = await import(
    runnerUrl
  )
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
  const hotspotFile = "src/api/interceptors/etagCache.ts"
  const regularFile = "src/regular.ts"
  const preflight = new Map([
    [hotspotFile, { sourceSha256: "b".repeat(64), mutants: makeMutants(hotspotFile, 5_000) }],
    [regularFile, { sourceSha256: "c".repeat(64), mutants: makeMutants(regularFile, 5_000) }],
  ])

  const plan = planMutationShards(preflight, 750, 8)
  const assignments = plan.flatMap(({ files }) => files)

  assert.equal(plan.length, 8)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    10_000
  )
  assert.equal(new Set(assignments).size, assignments.length)
  const hotspotShardIndexes = plan.flatMap((shard, shardIndex) =>
    shard.files.some((pattern) => pattern === hotspotFile || pattern.startsWith(`${hotspotFile}:`))
      ? [shardIndex]
      : []
  )
  const regularShardIndexes = plan.flatMap((shard, shardIndex) =>
    shard.files.some((pattern) => pattern === regularFile || pattern.startsWith(`${regularFile}:`))
      ? [shardIndex]
      : []
  )
  assert.ok(hotspotShardIndexes.length > 1)
  assert.ok(regularShardIndexes.length > 0)
  assert.ok(regularShardIndexes.every((shardIndex) => shardIndex >= 7))
  for (const shard of plan) {
    assert.deepEqual(shard.files, [...shard.files].sort())
    assert.equal(new Set(shard.files).size, shard.files.length)
  }

  const historicalCostArtifact = buildHistoricalCostArtifactFromShardTimings({
    sourceRevision: { headSha: "a".repeat(40) },
    config: {},
    preflightByFile: preflight,
    shardResults: plan.map((shard) => ({ ...shard, durationMs: 1_000 })),
  })
  assert.deepEqual(
    historicalCostArtifact.payload.costs.map(({ file }) => file),
    [hotspotFile, regularFile].sort()
  )

  const singleShardPlan = planMutationShards(preflight, 750, 1)
  assert.equal(singleShardPlan.length, 1)
  assert.equal(singleShardPlan[0].mutantCount, 10_000)
  assert.equal(new Set(singleShardPlan[0].files).size, singleShardPlan[0].files.length)
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

test("bounds the lexical utility tail across a dedicated first-attempt lane", async () => {
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
  const tailFiles = [
    ["src/utils/animations.ts", 1_200],
    ["src/utils/sanitizeArticleHtml.ts", 900],
    ["src/workers/crypto.worker.ts", 700],
  ]
  const regularFiles = Array.from({ length: 12 }, (_, index) => {
    const file = `src/aaa-regular-tail-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    ...tailFiles.map(([file, count]) => [file, { mutants: makeMutants(file, count) }]),
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 64)
  const expectedMutants = [...preflight.values()].reduce(
    (total, entry) => total + entry.mutants.length,
    0
  )
  const isTailPattern = (pattern) =>
    pattern.startsWith("src/utils/") || pattern.startsWith("src/workers/")
  const tailShardIndexes = plan.flatMap((shard, shardIndex) =>
    shard.files.some(isTailPattern) ? [shardIndex] : []
  )

  assert.equal(plan.length, 64)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    expectedMutants
  )
  assert.equal(
    new Set(plan.flatMap(({ files }) => files)).size,
    plan.flatMap(({ files }) => files).length
  )
  assert.equal(
    new Set(tailShardIndexes).size,
    4,
    "utility and worker related-test graphs must use the bounded tail lane"
  )
  assert.ok(
    tailShardIndexes.every((shardIndex) => plan[shardIndex].files.every(isTailPattern)),
    "tail-lane shards must not inherit unrelated source graphs"
  )
  assert.ok(
    Math.max(...tailShardIndexes.map((shardIndex) => plan[shardIndex].mutantCount)) < 1_000,
    "tail-lane shards must remain below the observed two-shard overload"
  )
})

test("preserves non-tail work when a small plan has one regular shard", async () => {
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
  const expensiveFile = "src/hooks/useMediaQuery.ts"
  const tailFile = "src/utils/animations.ts"
  const regularFiles = Array.from({ length: 8 }, (_, index) => {
    const file = `src/regular-${index}.ts`
    return [file, { mutants: makeMutants(file, 1_000) }]
  })
  const preflight = new Map([
    [expensiveFile, { mutants: makeMutants(expensiveFile, 1_000) }],
    [tailFile, { mutants: makeMutants(tailFile, 1_000) }],
    ...regularFiles,
  ])

  const plan = planMutationShards(preflight, 750, 2)
  const expectedPatterns = [...preflight.keys()]
  const assignedPatterns = plan.flatMap(({ files }) => files)
  const assignedSources = assignedPatterns.map((pattern) => pattern.split(":", 1)[0])

  assert.equal(plan.length, 2)
  assert.equal(
    plan.reduce((total, shard) => total + shard.mutantCount, 0),
    10_000
  )
  assert.deepEqual([...new Set(assignedSources)].sort(), expectedPatterns.sort())
})
