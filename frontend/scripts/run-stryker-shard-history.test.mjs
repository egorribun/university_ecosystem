import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { link, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { load as yamlLoad } from "js-yaml"
import {
  PRESENTATION_IGNORER,
  canonicalInstrumenterConfig,
} from "./stryker-presentation-ignorer.mjs"
import { canonicalTypeScriptCheckerConfig } from "./stryker-checker-config.mjs"

const runnerUrl = new URL("./run-stryker.mjs", import.meta.url)
const expectedPatterns = ["src/**/*.{ts,tsx}", "!src/**/__tests__/**/*"]
const location = { start: { line: 1, column: 21 }, end: { line: 1, column: 25 } }
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
          ...canonicalTypeScriptCheckerConfig,
          coverageAnalysis: "perTest",
          incremental: false,
          mutator: { plugins: null, excludedMutations: [] },
          ignorers: [PRESENTATION_IGNORER],
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
    instrumenterOptions: canonicalInstrumenterConfig,
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

test("nightly Stryker preflight selection binds SHA, run attempt, and immutable selector output", async () => {
  const workflow = yamlLoad(
    await readFile(
      new URL("../../.github/workflows/nightly-full-gate.yml", import.meta.url),
      "utf8"
    )
  )
  const producer = workflow.jobs["frontend-mutation-preflight"]
  const generation = producer.steps.find(
    ({ name }) => name === "Generate canonical immutable Stryker preflight"
  )
  const upload = producer.steps.find(({ name }) => name === "Upload immutable Stryker preflight")
  assert.equal(producer.if, "${{ github.ref == 'refs/heads/main' }}")
  assert.equal(generation.run, "npm run test:mutation")

  const runId = "42"
  const runAttempt = "2"
  const sourceSha = "a".repeat(40)
  const testedSha = sourceSha
  const artifactNameTemplate = upload.with.name
  assert.equal(
    artifactNameTemplate,
    "frontend-mutation-preflight-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}"
  )
  const artifactName = artifactNameTemplate
    .replace("${{ github.run_id }}", runId)
    .replace("${{ github.run_attempt }}", runAttempt)
    .replace("${{ github.sha }}", testedSha)
  assert.equal(artifactName, `frontend-mutation-preflight-${runId}-${runAttempt}-${testedSha}`)

  const shards = workflow.jobs["frontend-mutation-shards"]
  const selector = shards.steps.find(
    ({ name }) => name === "Select immutable same-run Stryker preflight candidate"
  )
  assert.equal(selector.id, "select_stryker_preflight")
  assert.equal(selector.env.GH_TOKEN, "${{ github.token }}")
  assert.ok(selector.run.includes("scripts/quality/select_same_run_artifact_cli.py"))
  for (const argument of [
    '--run-id "$GITHUB_RUN_ID"',
    '--consumer-run-attempt "$GITHUB_RUN_ATTEMPT"',
    '--commit-sha "$GITHUB_SHA"',
    '--run-head-sha "$GITHUB_SHA"',
    '--workflow-path ".github/workflows/nightly-full-gate.yml"',
    '--artifact-prefix "frontend-mutation-preflight-"',
    '--artifact-suffix "$GITHUB_SHA"',
    "--attempt-policy current-or-earlier",
  ]) {
    assert.ok(selector.run.includes(argument), argument)
  }
  assert.equal(sourceSha, testedSha)

  const download = shards.steps.find(
    ({ name }) => name === "Download selected Stryker preflight candidate"
  )
  assert.equal(
    download.with["artifact-ids"],
    "${{ steps.select_stryker_preflight.outputs.artifact_id }}"
  )
  assert.equal(download.with.repository, "${{ github.repository }}")
  assert.equal(download.with["run-id"], "${{ github.run_id }}")
  assert.equal(download.with["github-token"], "${{ github.token }}")
  assert.equal(
    download.with.path,
    "frontend/reports/mutation/preflight-candidates/${{ steps.select_stryker_preflight.outputs.artifact_name }}"
  )
  const verification = shards.steps.find(
    ({ name }) => name === "Verify selected Stryker preflight payload"
  )
  assert.equal(
    verification.env.ARTIFACT_NAME,
    "${{ steps.select_stryker_preflight.outputs.artifact_name }}"
  )

  const validatePayload = shards.steps.find(
    ({ name }) => name === "Validate immutable Stryker preflight before execution"
  )
  assert.equal(validatePayload["working-directory"], "frontend")
  assert.equal(validatePayload.env.STRYKER_PREFLIGHT_MODE, "validate")
  assert.equal(validatePayload.run, "npm run test:mutation")
  assert.ok(shards.steps.indexOf(validatePayload) > shards.steps.indexOf(verification))
  assert.ok(
    shards.steps.indexOf(validatePayload) <
      shards.steps.findIndex(({ name }) => name === "Run fresh nightly Stryker shard")
  )
})
test("offline cross-run replan consumes immutable baseline without rerunning instrumenter", async () => {
  const {
    buildEvidenceIdentity,
    buildPreflightArtifact,
    replanPreflightWithHistoricalCosts,
    validatePreflightArtifact,
  } = await import(runnerUrl)
  const file = "src/a.ts"
  const source = "export const a = true\n"
  const sourceFiles = [file]
  const sourceByFile = new Map([[file, source]])
  const sourceRevision = buildEvidenceIdentity({
    headSha: "a".repeat(40),
    sourceHeadSha: "b".repeat(40),
    dirtyPaths: [],
    inputHashes: {
      "frontend/stryker.config.mjs": "2".repeat(64),
      "quality/coverage-source-policy.json": "3".repeat(64),
      "frontend/src/a.ts": sha256Text(source),
    },
  })
  const artifactMetadata = {
    sourceRevision,
    workflow: {
      runId: "42",
      runAttempt: "1",
      sha: sourceRevision.headSha,
      sourceHeadSha: sourceRevision.sourceHeadSha,
      baseSha: sourceRevision.baseSha,
      baseRef: sourceRevision.baseRef,
    },
    config: {
      path: "frontend/stryker.config.mjs",
      sha256: "2".repeat(64),
      instrumenterOptions: canonicalInstrumenterConfig,
    },
    sourcePolicy: { path: "quality/coverage-source-policy.json", sha256: "3".repeat(64) },
    toolchain: {
      node: "v24.15.0",
      platform: "linux",
      arch: "x64",
      stryker: "9.6.1",
      instrumenter: "9.6.1",
      vitest: "4.1.10",
    },
    shardTargetMutants: 750,
    shardCount: 1,
  }
  const preflightByFile = new Map([
    [
      file,
      {
        sourceSha256: sha256Text(source),
        mutants: [
          { fileName: file, mutatorName: "BooleanLiteral", replacement: "false", location },
        ],
      },
    ],
  ])
  const baseline = buildPreflightArtifact({ ...artifactMetadata, preflightByFile })
  const artifactText = `${JSON.stringify(baseline, null, 2)}\n`
  const receiptText = JSON.stringify({
    has_candidate: true,
    candidate_run_id: 32,
    costs: { [file]: 1234.5 },
    diagnostic: "compatible historical Stryker timing advice",
  })

  const replannedText = replanPreflightWithHistoricalCosts({
    artifactText,
    receiptText,
    sourceFiles,
    sourceByFile,
    artifactMetadata,
  })
  const replanned = validatePreflightArtifact({
    ...artifactMetadata,
    artifactText: replannedText,
    sourceFiles,
    sourceByFile,
  })
  assert.equal(baseline.payload.historicalCostModel, undefined)
  assert.equal(
    replanned.artifact.payload.historicalCostModel.sourceRevision.headSha,
    sourceRevision.headSha
  )
  assert.equal(replanned.artifact.payload.historicalCostModel.costs[0].estimatedDurationMs, 1234.5)
  assert.equal(replanned.preflightDigest, baseline.payload.preflight.digest)

  for (const malformedReceipt of [
    "not json",
    JSON.stringify({ ...JSON.parse(receiptText), costs: {} }),
  ]) {
    assert.throws(() =>
      replanPreflightWithHistoricalCosts({
        artifactText,
        receiptText: malformedReceipt,
        sourceFiles,
        sourceByFile,
        artifactMetadata,
      })
    )
  }
  assert.throws(
    () =>
      replanPreflightWithHistoricalCosts({
        artifactText,
        receiptText,
        sourceFiles,
        sourceByFile: new Map([[file, "changed source"]]),
        artifactMetadata,
      }),
    /stale|source snapshot/u
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
    instrumenterOptions: canonicalInstrumenterConfig,
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
    instrumenterOptions: canonicalInstrumenterConfig,
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
    instrumenterOptions: canonicalInstrumenterConfig,
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
  const workflow = {
    runId: "42",
    runAttempt: "3",
    sha: sourceRevision.headSha,
    sourceHeadSha: sourceRevision.sourceHeadSha,
    baseSha: sourceRevision.baseSha,
    baseRef: sourceRevision.baseRef,
  }
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
    instrumenterOptions: canonicalInstrumenterConfig,
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
  const workflow = {
    runId: "42",
    runAttempt: "3",
    sha: sourceRevision.headSha,
    sourceHeadSha: sourceRevision.sourceHeadSha,
    baseSha: sourceRevision.baseSha,
    baseRef: sourceRevision.baseRef,
  }
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
    instrumenterOptions: canonicalInstrumenterConfig,
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
  const consumerWorkflow = {
    runId: "42",
    runAttempt: "3",
    sha: sourceRevision.headSha,
    sourceHeadSha: sourceRevision.sourceHeadSha,
    baseSha: sourceRevision.baseSha,
    baseRef: sourceRevision.baseRef,
  }
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
    instrumenterOptions: canonicalInstrumenterConfig,
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
    ...canonicalTypeScriptCheckerConfig,
    coverageAnalysis: "perTest",
    incremental: false,
    mutator: { plugins: null, excludedMutations: [] },
    ignorers: [PRESENTATION_IGNORER],
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
  assert.deepEqual(
    Object.fromEntries(
      Object.keys(canonicalTypeScriptCheckerConfig).map((key) => [key, merged.config[key]])
    ),
    canonicalTypeScriptCheckerConfig
  )
  assert.equal(merged.config.incremental, false)
  assert.deepEqual(
    Object.values(merged.files).map(({ mutants }) => mutants[0].id),
    ["shard-000:0", "shard-001:0"]
  )
  assert.throws(
    () =>
      mergeShardReports({
        expectedPatterns,
        shards: [
          {
            id: "shard-000",
            files: ["src/a.ts"],
            report: {
              schemaVersion: "1.0",
              config: { ...baseConfig, checkers: [], mutate: ["src/a.ts"] },
              files: { "src/a.ts": file("0", "false") },
            },
          },
        ],
      }),
    /canonical TypeScript checker configuration/u
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
    sourceHeadSha: "b".repeat(40),
    baseSha: "c".repeat(40),
    baseRef: "main",
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
    before: {
      revision: evidence.revision,
      sourceHeadSha: evidence.sourceHeadSha,
      baseSha: evidence.baseSha,
      baseRef: evidence.baseRef,
      evidenceDigest: evidence.evidenceDigest,
    },
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
        before: {
          revision: evidence.revision,
          sourceHeadSha: evidence.sourceHeadSha,
          baseSha: evidence.baseSha,
          baseRef: evidence.baseRef,
          evidenceDigest: evidence.evidenceDigest,
        },
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
    sourceHeadSha: "b".repeat(40),
    baseSha: "c".repeat(40),
    baseRef: "main",
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
    before: {
      revision: baseEvidence.revision,
      sourceHeadSha: baseEvidence.sourceHeadSha,
      baseSha: baseEvidence.baseSha,
      baseRef: baseEvidence.baseRef,
      evidenceDigest: baseEvidence.evidenceDigest,
    },
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
        sourceHeadSha: "b".repeat(40),
        baseSha: "c".repeat(40),
        baseRef: "main",
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
    before: {
      revision: "a".repeat(40),
      sourceHeadSha: "b".repeat(40),
      baseSha: "c".repeat(40),
      baseRef: "main",
      evidenceDigest: "b".repeat(64),
    },
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
