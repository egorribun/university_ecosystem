import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { link, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { load as yamlLoad } from "js-yaml"

const runnerUrl = new URL("./run-stryker.mjs", import.meta.url)

async function cachedShardPublicationFixture(t) {
  const { validateCachedShardPublication, verifyCachedShardPublication } = await import(runnerUrl)
  assert.equal(typeof validateCachedShardPublication, "function")
  assert.equal(typeof verifyCachedShardPublication, "function")
  const root = await realpath(await mkdtemp(path.join(os.tmpdir(), "stryker-cached-publication-")))
  t.after(() => rm(root, { recursive: true, force: true }))
  const candidateRoot = path.join(root, "cache")
  const publishedRoot = path.join(root, "download")
  const shardPlan = [
    { id: "shard-000", files: ["src/a.ts"], mutantCount: 3 },
    { id: "shard-001", files: ["src/b.ts"], mutantCount: 5 },
  ]
  const before = {
    revision: "a".repeat(40),
    sourceHeadSha: "b".repeat(40),
    baseSha: "c".repeat(40),
    baseRef: "main",
    evidenceDigest: "b".repeat(64),
  }
  const reportText = JSON.stringify({ schemaVersion: "1.0", config: {}, files: {} }, null, 2) + "\n"
  const evidence = {
    schemaVersion: "1.0",
    runId: "original-producer",
    shardId: "shard-000",
    shardIndex: 0,
    shardCount: 2,
    ...before,
    preflightDigest: "c".repeat(64),
    workflowRunId: "42",
    workflowRunAttempt: "1",
    files: shardPlan[0].files,
    mutantCount: 3,
    reportSha256: createHash("sha256").update(reportText).digest("hex"),
  }
  const evidenceText = JSON.stringify(evidence, null, 2) + "\n"
  const options = {
    candidateRoot,
    shardPlan,
    shardIndex: 0,
    before,
    preflightDigest: evidence.preflightDigest,
    workflowRunId: "42",
    workflowRunAttempt: "2",
  }
  const writePair = async (
    targetRoot,
    nextEvidenceText = evidenceText,
    nextReportText = reportText
  ) => {
    const directory = path.join(targetRoot, "shard-000")
    await mkdir(directory, { recursive: true })
    await writeFile(path.join(directory, "SHARD_EVIDENCE.json"), nextEvidenceText)
    await writeFile(path.join(directory, "mutation.json"), nextReportText)
  }
  await writePair(candidateRoot)
  return {
    root,
    candidateRoot,
    publishedRoot,
    options,
    evidence,
    evidenceText,
    reportText,
    writePair,
    expected: {
      artifactName: "nightly-frontend-mutation-shard-42-1-0",
      producerAttempt: 1,
      shardId: "shard-000",
      evidenceText,
      reportText,
    },
    validate: (overrides = {}) => validateCachedShardPublication({ ...options, ...overrides }),
    verify: (targetRoot = publishedRoot, overrides = {}) =>
      verifyCachedShardPublication({ ...options, ...overrides }, targetRoot),
  }
}

test("AUD455 validates cached bytes and an identical download", async (t) => {
  const fixture = await cachedShardPublicationFixture(t)
  assert.deepEqual(await fixture.validate(), fixture.expected)
  await fixture.writePair(fixture.publishedRoot)
  assert.deepEqual(await fixture.verify(), fixture.expected)
  assert.equal(
    await readFile(path.join(fixture.candidateRoot, "shard-000", "SHARD_EVIDENCE.json"), "utf8"),
    fixture.evidenceText
  )
  assert.equal(
    await readFile(path.join(fixture.candidateRoot, "shard-000", "mutation.json"), "utf8"),
    fixture.reportText
  )
})

test("AUD455 rejects cached producer identity and lineage changes", async (t) => {
  const cases = [
    ["schema", { schemaVersion: "2.0" }],
    ["empty producer", { runId: "" }],
    ["shard id", { shardId: "shard-001" }],
    ["shard index", { shardIndex: 1 }],
    ["shard count", { shardCount: 1 }],
    ["revision", { revision: "d".repeat(40) }],
    ["source head", { sourceHeadSha: "d".repeat(40) }],
    ["base sha", { baseSha: "d".repeat(40) }],
    ["base ref", { baseRef: "other" }],
    ["evidence digest", { evidenceDigest: "d".repeat(64) }],
    ["preflight digest", { preflightDigest: "d".repeat(64) }],
    ["workflow run", { workflowRunId: "43" }],
    ["future producer", { workflowRunAttempt: "3" }],
    ["noncanonical producer", { workflowRunAttempt: "01" }],
    ["zero producer", { workflowRunAttempt: "0" }],
    ["numeric producer", { workflowRunAttempt: 1 }],
    ["missing producer", { workflowRunAttempt: undefined }],
    ["files", { files: ["src/b.ts"] }],
    ["duplicate files", { files: ["src/a.ts", "src/a.ts"] }],
    ["mutant count", { mutantCount: 4 }],
    ["report digest", { reportSha256: "d".repeat(64) }],
    ["Windows metadata shape", { windowsProcessHost: {} }],
    [
      "Windows metadata digest",
      { windowsProcessHost: { sourceSha256: "invalid", binarySha256: "d".repeat(64) } },
    ],
  ]
  for (const [name, overrides] of cases) {
    await t.test(name, async (t) => {
      const fixture = await cachedShardPublicationFixture(t)
      assert.deepEqual(await fixture.validate(), fixture.expected)
      await fixture.writePair(
        fixture.candidateRoot,
        JSON.stringify({ ...fixture.evidence, ...overrides }) + "\n"
      )
      await assert.rejects(() => fixture.validate(), Error)
    })
  }
})

test("AUD455 rejects malformed cached publication inputs before transport", async (t) => {
  const cases = [
    ["negative index", { shardIndex: -1 }],
    ["out-of-range index", { shardIndex: 2 }],
    ["fractional index", { shardIndex: 0.5 }],
    ["string index", { shardIndex: "0" }],
    ["invalid consumer", { workflowRunAttempt: "02" }],
    ["zero consumer", { workflowRunAttempt: "0" }],
    ["foreign consumer run", { workflowRunId: "43" }],
    ["missing full plan", { shardPlan: [] }],
    [
      "oversized plan",
      {
        shardPlan: Array.from({ length: 257 }, (_, index) => ({
          id: "shard-" + String(index).padStart(3, "0"),
          files: ["src/file-" + index + ".ts"],
          mutantCount: 1,
        })),
      },
    ],
    [
      "single-shard plan",
      { shardPlan: [{ id: "shard-000", files: ["src/a.ts"], mutantCount: 3 }] },
    ],
    [
      "duplicate shard ids",
      {
        shardPlan: [
          { id: "shard-000", files: ["src/a.ts"], mutantCount: 3 },
          { id: "shard-000", files: ["src/b.ts"], mutantCount: 5 },
        ],
      },
    ],
  ]
  for (const [name, overrides] of cases) {
    await t.test(name, async (t) => {
      const fixture = await cachedShardPublicationFixture(t)
      assert.deepEqual(await fixture.validate(), fixture.expected)
      if (name === "single-shard plan" || name === "oversized plan") {
        const [shard] = overrides.shardPlan
        await fixture.writePair(
          fixture.candidateRoot,
          JSON.stringify({
            ...fixture.evidence,
            shardCount: overrides.shardPlan.length,
            files: shard.files,
            mutantCount: shard.mutantCount,
          }) + "\n"
        )
      }
      await assert.rejects(() => fixture.validate(overrides), Error)
    })
  }
  for (const kind of ["evidence JSON", "report JSON", "report bytes"]) {
    await t.test(kind, async (t) => {
      const fixture = await cachedShardPublicationFixture(t)
      assert.deepEqual(await fixture.validate(), fixture.expected)
      if (kind === "evidence JSON") {
        await fixture.writePair(fixture.candidateRoot, "{")
      } else if (kind === "report JSON") {
        const reportText = "{"
        const evidence = {
          ...fixture.evidence,
          reportSha256: createHash("sha256").update(reportText).digest("hex"),
        }
        await fixture.writePair(fixture.candidateRoot, JSON.stringify(evidence), reportText)
      } else {
        await fixture.writePair(
          fixture.candidateRoot,
          fixture.evidenceText,
          fixture.reportText + "\n"
        )
      }
      await assert.rejects(() => fixture.validate(), Error)
    })
  }
})

test("AUD455 rejects unsafe cache and download file layouts", async (t) => {
  const cases = [
    ["missing evidence", async (root) => rm(path.join(root, "shard-000", "SHARD_EVIDENCE.json"))],
    ["missing report", async (root) => rm(path.join(root, "shard-000", "mutation.json"))],
    ["missing publication root", async (root) => rm(root, { recursive: true })],
    ["extra root entry", async (root) => writeFile(path.join(root, "extra.json"), "{}")],
    ["extra shard", async (root) => mkdir(path.join(root, "shard-001"))],
    [
      "extra shard entry",
      async (root) => writeFile(path.join(root, "shard-000", "extra.json"), "{}"),
    ],
    [
      "evidence directory",
      async (root) => {
        const file = path.join(root, "shard-000", "SHARD_EVIDENCE.json")
        await rm(file)
        await mkdir(file)
      },
    ],
    [
      "report directory",
      async (root) => {
        const file = path.join(root, "shard-000", "mutation.json")
        await rm(file)
        await mkdir(file)
      },
    ],
    [
      "hardlinked report",
      async (root, fixture) => {
        const file = path.join(root, "shard-000", "mutation.json")
        const target = path.join(fixture.root, "linked-report.json")
        await writeFile(target, fixture.reportText)
        await rm(file)
        await link(target, file)
      },
    ],
    [
      "hardlinked evidence",
      async (root, fixture) => {
        const file = path.join(root, "shard-000", "SHARD_EVIDENCE.json")
        const target = path.join(fixture.root, "linked-evidence.json")
        await writeFile(target, fixture.evidenceText)
        await rm(file)
        await link(target, file)
      },
    ],
    [
      "symlinked evidence",
      async (root, fixture) => {
        const file = path.join(root, "shard-000", "SHARD_EVIDENCE.json")
        const target = path.join(fixture.root, "symlink-evidence.json")
        await writeFile(target, fixture.evidenceText)
        await rm(file)
        await symlink(target, file, "file")
      },
    ],
    [
      "symlinked report",
      async (root, fixture) => {
        const file = path.join(root, "shard-000", "mutation.json")
        const target = path.join(fixture.root, "symlink-report.json")
        await writeFile(target, fixture.reportText)
        await rm(file)
        await symlink(target, file, "file")
      },
    ],
    [
      "symlinked shard directory",
      async (root, fixture) => {
        const target = path.join(fixture.root, "symlink-shard")
        await fixture.writePair(target)
        await rm(path.join(root, "shard-000"), { recursive: true })
        await symlink(path.join(target, "shard-000"), path.join(root, "shard-000"), "junction")
      },
    ],
    [
      "symlinked publication root",
      async (root, fixture) => {
        const target = path.join(fixture.root, "symlink-root")
        await fixture.writePair(target)
        await rm(root, { recursive: true })
        await symlink(target, root, "junction")
      },
    ],
  ]
  for (const target of ["cache", "download"]) {
    for (const [name, mutate] of cases) {
      await t.test(target + ": " + name, async (t) => {
        const fixture = await cachedShardPublicationFixture(t)
        await fixture.writePair(fixture.publishedRoot)
        assert.deepEqual(await fixture.verify(), fixture.expected)
        await mutate(target === "cache" ? fixture.candidateRoot : fixture.publishedRoot, fixture)
        await assert.rejects(
          () => (target === "cache" ? fixture.validate() : fixture.verify()),
          Error
        )
      })
    }
  }
})

test("AUD455 rejects changed bytes in otherwise valid downloads", async (t) => {
  for (const change of ["evidence whitespace", "producer attempt", "report whitespace"]) {
    await t.test(change, async (t) => {
      const fixture = await cachedShardPublicationFixture(t)
      let evidenceText
      let reportText = fixture.reportText
      if (change === "evidence whitespace") {
        evidenceText = JSON.stringify(fixture.evidence) + "\n"
      } else if (change === "producer attempt") {
        evidenceText =
          JSON.stringify({ ...fixture.evidence, workflowRunAttempt: "2" }, null, 2) + "\n"
      } else {
        reportText += "\n"
        evidenceText =
          JSON.stringify(
            {
              ...fixture.evidence,
              reportSha256: createHash("sha256").update(reportText).digest("hex"),
            },
            null,
            2
          ) + "\n"
      }
      await fixture.writePair(fixture.publishedRoot, evidenceText, reportText)
      await fixture.validate({ candidateRoot: fixture.publishedRoot })
      await assert.rejects(() => fixture.verify(), Error)
      assert.deepEqual(await fixture.validate(), fixture.expected)
    })
  }
})

test("AUD455 appends producer outputs without changing prior bytes", async (t) => {
  const { appendCachedShardOutputs } = await import(runnerUrl)
  assert.equal(typeof appendCachedShardOutputs, "function")
  const fixture = await cachedShardPublicationFixture(t)
  const publication = await fixture.validate()
  const outputPath = path.join(fixture.root, "github-output")
  const prior = "existing_output=kept\n"
  await writeFile(outputPath, prior)
  await appendCachedShardOutputs(outputPath, publication)
  assert.equal(
    await readFile(outputPath, "utf8"),
    prior + "producer_attempt=1\nartifact_name=nightly-frontend-mutation-shard-42-1-0\n"
  )
})

test("AUD455 rejects unsafe output files and values without appending", async (t) => {
  const { appendCachedShardOutputs } = await import(runnerUrl)
  assert.equal(typeof appendCachedShardOutputs, "function")
  for (const kind of [
    "missing",
    "directory",
    "symlink",
    "hardlink",
    "partial prior line",
    "newline artifact name",
    "invalid producer",
  ]) {
    await t.test(kind, async (t) => {
      const fixture = await cachedShardPublicationFixture(t)
      let publication = await fixture.validate()
      const outputPath = path.join(fixture.root, "github-output")
      const target = path.join(fixture.root, "protected-output")
      const prior = "existing_output=kept\n"
      await writeFile(target, prior)
      if (kind === "directory") {
        await mkdir(outputPath)
      } else if (kind === "symlink") {
        await symlink(target, outputPath, "file")
      } else if (kind === "hardlink") {
        await link(target, outputPath)
      } else if (kind !== "missing") {
        await writeFile(outputPath, kind === "partial prior line" ? "incomplete=value" : prior)
      }
      if (kind === "newline artifact name") {
        publication = { ...publication, artifactName: publication.artifactName + "\nextra=value" }
      } else if (kind === "invalid producer") {
        publication = { ...publication, producerAttempt: 0 }
      }
      await assert.rejects(() => appendCachedShardOutputs(outputPath, publication), Error)
      assert.equal(await readFile(target, "utf8"), prior)
      if (kind === "missing") {
        await assert.rejects(() => readFile(outputPath), { code: "ENOENT" })
      } else if (kind !== "directory") {
        assert.equal(
          await readFile(outputPath, "utf8"),
          kind === "partial prior line" ? "incomplete=value" : prior
        )
      }
    })
  }
})

for (const [scenario, failFirstUpload] of [
  ["recovers a cached producer after its first upload failed", true],
  ["reuses already-published cached evidence without duplicating its producer", false],
]) {
  test(`AUD455 nightly shard publication ${scenario}`, async (t) => {
    const {
      loadExternalShardResults,
      validateCachedShardPublication,
      verifyCachedShardPublication,
      appendCachedShardOutputs,
    } = await import(runnerUrl)
    assert.equal(typeof validateCachedShardPublication, "function")
    assert.equal(typeof verifyCachedShardPublication, "function")
    assert.equal(typeof appendCachedShardOutputs, "function")
    const workflow = yamlLoad(
      await readFile(
        new URL("../../.github/workflows/nightly-full-gate.yml", import.meta.url),
        "utf8"
      )
    )
    const job = workflow.jobs["frontend-mutation-shards"]
    const restoreIndex = job.steps.findIndex(({ id }) => id === "restore_nightly_stryker_shard")
    assert.notEqual(restoreIndex, -1)
    const restore = job.steps[restoreIndex]
    const steps = job.steps.slice(restoreIndex)
    const selector = steps.find(({ id }) => id === "select_cached_shard")
    assert.ok(selector)
    assert.equal(selector.shell, "bash")
    assert.deepEqual(selector.env, {
      GH_TOKEN: "${{ github.token }}",
      PRODUCER_ATTEMPT: "${{ steps.validate_cached_shard.outputs.producer_attempt }}",
      SHARD_INDEX: "${{ matrix.shard-index }}",
    })
    assert.equal(
      selector.run
        .trim()
        .replace(/[ \t]*\\\r?\n[ \t]*/gu, " ")
        .replace(/[ \t]+/gu, " "),
      "set -euo pipefail\n" +
        [
          "python3 scripts/quality/select_same_run_artifact_cli.py",
          '--repository "$GITHUB_REPOSITORY"',
          '--run-id "$GITHUB_RUN_ID"',
          '--consumer-run-attempt "$GITHUB_RUN_ATTEMPT"',
          '--commit-sha "$GITHUB_SHA"',
          '--run-head-sha "$GITHUB_SHA"',
          '--event "$GITHUB_EVENT_NAME"',
          '--workflow-path ".github/workflows/nightly-full-gate.yml"',
          '--artifact-prefix "nightly-frontend-mutation-shard-"',
          '--artifact-suffix ""',
          '--producer-attempt "$PRODUCER_ATTEMPT"',
          '--shard-index "$SHARD_INDEX"',
          '--shard-count "$STRYKER_SHARD_COUNT"',
          "--attempt-policy current-or-earlier",
          "--allow-empty",
        ].join(" ")
    )
    const shardPlan = [
      { id: "shard-000", files: ["src/a.ts"], mutantCount: 3 },
      { id: "shard-001", files: ["src/b.ts"], mutantCount: 5 },
    ]
    const before = {
      revision: "a".repeat(40),
      sourceHeadSha: "b".repeat(40),
      baseSha: "c".repeat(40),
      baseRef: "main",
      evidenceDigest: "b".repeat(64),
    }
    const preflightDigest = "c".repeat(64)
    const reportText = `${JSON.stringify({
      schemaVersion: "1.0",
      config: {},
      files: {},
    })}\n`
    const original = shardPlan.map((shard, index) => ({
      index,
      reportText,
      evidenceText: `${JSON.stringify({
        schemaVersion: "1.0",
        runId: `producer-1-${index}`,
        shardId: shard.id,
        shardIndex: index,
        shardCount: 2,
        ...before,
        preflightDigest,
        workflowRunId: "42",
        workflowRunAttempt: "1",
        files: shard.files,
        mutantCount: shard.mutantCount,
        reportSha256: createHash("sha256").update(reportText).digest("hex"),
      })}\n`,
    }))
    const transportRoot = await realpath(
      await mkdtemp(path.join(os.tmpdir(), "stryker-publication-transport-"))
    )
    t.after(() => rm(transportRoot, { recursive: true, force: true }))
    const cache = new Map()
    const catalog = new Map()
    const artifactIds = new Map()
    const mutationCalls = []
    const helperCalls = []
    const uploadFailure = new Error("injected artifact upload transport failure")

    function render(value, attempt, index, outputs = {}) {
      const context = {
        "github.run_id": "42",
        "github.run_attempt": attempt,
        "github.sha": before.revision,
        "matrix.shard-index": String(index),
        "steps.validate_cached_shard.outputs.artifact_name":
          outputs.validate_cached_shard?.artifact_name,
        "steps.select_cached_shard.outputs.artifact_id": outputs.select_cached_shard?.artifact_id,
      }
      return value.replace(/\$\{\{\s*(.*?)\s*\}\}/gu, (_, expression) => {
        assert.ok(Object.hasOwn(context, expression), `unsupported template: ${expression}`)
        assert.equal(typeof context[expression], "string")
        return context[expression]
      })
    }

    // This remains a bounded decision adapter, not an Actions or shell emulator.
    function enabled(step, outputs, failed) {
      const match = /^\$\{\{\s*(.*?)\s*\}\}$/u.exec(step.if ?? "${{ success() }}")
      assert.ok(match, `unsupported condition: ${step.if}`)
      const terms = match[1].split("&&").map((term) => term.trim())
      let explicitStatus = false
      const values = terms.map((term) => {
        if (term === "always()" || term === "success()") {
          explicitStatus = true
          return term === "always()" || !failed
        }
        const comparison =
          /^steps\.([a-zA-Z0-9_]+)\.outputs\.(cache-hit|has_candidate)\s*(!=|==)\s*'(true|false)'$/u.exec(
            term
          )
        assert.ok(comparison, `unsupported condition term: ${term}`)
        assert.ok(
          (comparison[1] === restore.id && comparison[2] === "cache-hit") ||
            (comparison[1] === selector.id && comparison[2] === "has_candidate"),
          "condition must use an actual bounded transport output"
        )
        const actual = outputs[comparison[1]]?.[comparison[2]] ?? ""
        return comparison[3] === "!=" ? actual !== comparison[4] : actual === comparison[4]
      })
      return values.every(Boolean) && (explicitStatus || !failed)
    }

    // Validate every operation even when a condition would skip it.
    const operations = steps.map((step) => {
      let kind
      if (step.uses?.startsWith("actions/cache/restore@")) {
        assert.equal(step, restore)
        kind = "restore"
      } else if (step.uses?.startsWith("actions/cache/save@")) {
        kind = "save"
      } else if (step.uses?.startsWith("actions/upload-artifact@")) {
        kind = "upload"
      } else if (step.uses?.startsWith("actions/download-artifact@")) {
        assert.equal(step.name, "Download selected cached shard publication")
        assert.equal(
          step.with["artifact-ids"],
          "${{ steps.select_cached_shard.outputs.artifact_id }}"
        )
        assert.equal(step.with.repository, "${{ github.repository }}")
        assert.equal(step.with["run-id"], "${{ github.run_id }}")
        assert.equal(step.with["github-token"], "${{ github.token }}")
        assert.equal(step.with.path, "frontend/reports/mutation/cached-publication")
        assert.equal(step.with["digest-mismatch"] ?? "error", "error")
        assert.equal(step.with["skip-decompress"] ?? false, false)
        kind = "download"
      } else if (step === selector) {
        kind = "select"
      } else if (step.run === "npm run test:mutation" && step["working-directory"] === "frontend") {
        const mode = step.env?.STRYKER_PREFLIGHT_MODE
        assert.ok(
          mode === undefined ||
            mode === "validate" ||
            mode === "validate-cached" ||
            mode === "verify-cached"
        )
        if (mode === "validate-cached") assert.equal(step.id, "validate_cached_shard")
        kind = mode ?? "execute"
      }
      assert.ok(kind, `unsupported publication step: ${step.name}`)
      assert.equal(typeof (step["continue-on-error"] ?? false), "boolean")
      return { step, kind }
    })
    assert.equal(typeof (job["continue-on-error"] ?? false), "boolean")

    async function writeTransportPair(root, bytes) {
      const directory = path.join(root, shardPlan[bytes.index].id)
      await mkdir(directory, { recursive: true })
      await writeFile(path.join(directory, "mutation.json"), bytes.reportText)
      await writeFile(path.join(directory, "SHARD_EVIDENCE.json"), bytes.evidenceText)
    }

    function restoreOrSave(step, kind, state) {
      assert.equal(step.with.path, "frontend/reports/mutation/shards")
      const key = render(step.with.key, state.attempt, state.index, state.outputs)
      if (kind === "restore") {
        assert.equal(step.with["restore-keys"], undefined)
        state.workspace = cache.has(key) ? { ...cache.get(key) } : undefined
        state.outputs[restore.id]["cache-hit"] = state.workspace ? "true" : ""
      } else {
        assert.ok(state.workspace, "cache save requires completed producer evidence")
        if (!cache.has(key)) cache.set(key, { ...state.workspace })
      }
    }

    function executeProducer(state) {
      mutationCalls.push(`${state.attempt}:${state.index}`)
      assert.equal(state.attempt, "1", "cached producer must not be recomputed")
      state.workspace = { ...original[state.index] }
    }

    async function validateCachedProducer(step, state) {
      assert.ok(state.workspace)
      await writeTransportPair(state.candidateRoot, state.workspace)
      state.publication = await validateCachedShardPublication(state.options)
      helperCalls.push(`validate:${state.attempt}:${state.index}`)
      assert.equal(state.publication.evidenceText, state.workspace.evidenceText)
      assert.equal(state.publication.reportText, state.workspace.reportText)
      assert.equal(
        state.publication.artifactName,
        `nightly-frontend-mutation-shard-42-1-${state.index}`
      )
      const outputPath = path.join(
        transportRoot,
        `${state.attempt}-${state.index}`,
        "github-output"
      )
      await writeFile(outputPath, "")
      await appendCachedShardOutputs(outputPath, state.publication)
      const lines = (await readFile(outputPath, "utf8")).split("\n")
      assert.deepEqual(lines, [
        `producer_attempt=${state.publication.producerAttempt}`,
        `artifact_name=${state.publication.artifactName}`,
        "",
      ])
      state.outputs[step.id] = {
        producer_attempt: lines[0].slice("producer_attempt=".length),
        artifact_name: lines[1].slice("artifact_name=".length),
      }
    }

    function selectCachedProducer(step, state) {
      assert.ok(state.publication)
      // Only remote catalog transport is modeled. The exact Python command
      // above is exercised by its separate component tests, not this process.
      const present = catalog.has(state.publication.artifactName)
      state.outputs[step.id] = {
        has_candidate: String(present),
        artifact_id: present ? artifactIds.get(state.publication.artifactName) : "",
      }
    }

    async function downloadCachedProducer(step, state) {
      const id = render(step.with["artifact-ids"], state.attempt, state.index, state.outputs)
      const selected = [...artifactIds].find(([, value]) => value === id)
      assert.ok(selected, "download must use one selected immutable artifact id")
      await writeTransportPair(state.publishedRoot, catalog.get(selected[0]))
    }

    async function verifyCachedProducer(state) {
      assert.deepEqual(
        await verifyCachedShardPublication(state.options, state.publishedRoot),
        state.publication
      )
      helperCalls.push(`verify:${state.attempt}:${state.index}`)
    }

    function uploadProducerArtifact(step, state) {
      assert.equal(step.with["if-no-files-found"], "error")
      assert.notEqual(step.with.overwrite, true)
      assert.deepEqual(step.with.path.trim().split(/\r?\n/u), [
        "frontend/reports/mutation/shards/**/mutation.json",
        "frontend/reports/mutation/shards/**/SHARD_EVIDENCE.json",
      ])
      assert.ok(state.workspace, "artifact upload requires producer evidence")
      if (failFirstUpload && state.attempt === "1" && state.index === 1) throw uploadFailure
      const name = render(step.with.name, state.attempt, state.index, state.outputs)
      if (state.outputs[restore.id]["cache-hit"] === "true") {
        assert.equal(step.with.name, "${{ steps.validate_cached_shard.outputs.artifact_name }}")
        assert.equal(step.with.overwrite, false)
        assert.equal(name, state.publication.artifactName)
      }
      assert.equal(catalog.has(name), false, "artifact transport is immutable")
      catalog.set(name, { ...state.workspace })
      artifactIds.set(name, String(100 + artifactIds.size))
    }

    function executePublicationOperation(step, kind, state) {
      if (kind === "restore" || kind === "save") return restoreOrSave(step, kind, state)
      if (kind === "validate") {
        // Successful immutable preflight remains a fixed precondition.
        return
      }
      if (kind === "execute") return executeProducer(state)
      if (kind === "validate-cached") return validateCachedProducer(step, state)
      if (kind === "select") return selectCachedProducer(step, state)
      if (kind === "download") return downloadCachedProducer(step, state)
      if (kind === "verify-cached") return verifyCachedProducer(state)
      return uploadProducerArtifact(step, state)
    }

    async function runAttempt(attempt, index) {
      const candidateRoot = path.join(transportRoot, `${attempt}-${index}`, "cache")
      const publishedRoot = path.join(transportRoot, `${attempt}-${index}`, "download")
      const state = {
        attempt,
        index,
        outputs: { [restore.id]: { "cache-hit": "" } },
        candidateRoot,
        publishedRoot,
        options: {
          candidateRoot,
          shardPlan,
          shardIndex: index,
          before,
          preflightDigest,
          workflowRunId: "42",
          workflowRunAttempt: attempt,
        },
        workspace: undefined,
        publication: undefined,
        failed: false,
      }
      for (const { step, kind } of operations) {
        if (!enabled(step, state.outputs, state.failed)) continue
        try {
          const pending = executePublicationOperation(step, kind, state)
          if (pending !== undefined) await pending
        } catch (error) {
          if (error !== uploadFailure) throw error
          if (step["continue-on-error"] !== true) state.failed = true
        }
      }
      return state.failed && job["continue-on-error"] !== true
    }

    assert.equal(await runAttempt("1", 0), false)
    assert.equal(
      await runAttempt("1", 1),
      failFirstUpload,
      "an artifact upload failure must remain a hard job failure"
    )
    assert.equal(cache.size, 2, "completed computation must survive upload failure")
    assert.equal(await runAttempt("2", 1), false)
    assert.deepEqual(mutationCalls, ["1:0", "1:1"])
    assert.deepEqual(
      helperCalls,
      failFirstUpload ? ["validate:2:1"] : ["validate:2:1", "verify:2:1"]
    )
    assert.deepEqual([...catalog.keys()].sort(), [
      "nightly-frontend-mutation-shard-42-1-0",
      "nightly-frontend-mutation-shard-42-1-1",
    ])
    for (const bytes of [...cache.values(), ...catalog.values()]) {
      assert.deepEqual(
        bytes,
        original[bytes.index],
        "transport must not rewrite the producer attempt or either evidence file"
      )
    }

    const aggregate = workflow.jobs["frontend-mutation-tests-full"]
    const download = aggregate.steps.find(
      ({ name }) => name === "Download all nightly frontend mutation shards from same run"
    )
    assert.ok(download)
    assert.ok(download.uses.startsWith("actions/download-artifact@"))
    assert.equal(download.with["merge-multiple"], false)
    const pattern = render(download.with.pattern, "2", 0)
    assert.ok(pattern.endsWith("*"))
    assert.equal(pattern.indexOf("*"), pattern.length - 1)
    const prefix = pattern.slice(0, -1)
    const root = await mkdtemp(path.join(os.tmpdir(), "stryker-publication-"))
    t.after(() => rm(root, { recursive: true, force: true }))
    for (const [name, bytes] of catalog) {
      if (!name.startsWith(prefix)) continue
      await writeTransportPair(path.join(root, name), bytes)
    }
    const results = await loadExternalShardResults({
      aggregateRoot: root,
      shardPlan,
      before,
      preflightDigest,
      workflowRunId: "42",
      workflowRunAttempt: "2",
    })
    assert.deepEqual(
      results.map(({ id, producerAttempt }) => [id, producerAttempt]),
      [
        ["shard-000", 1],
        ["shard-001", 1],
      ]
    )
  })
}

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
    sourceHeadSha: "b".repeat(40),
    baseSha: "c".repeat(40),
    baseRef: "main",
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
      before: {
        revision: evidence.revision,
        sourceHeadSha: evidence.sourceHeadSha,
        baseSha: evidence.baseSha,
        baseRef: evidence.baseRef,
        evidenceDigest: evidence.evidenceDigest,
      },
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
