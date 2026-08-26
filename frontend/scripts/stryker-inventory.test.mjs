import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

const inventoryModuleUrl = new URL("./validate-stryker-inventory.mjs", import.meta.url)

const policy = {
  frontend: {
    include: ["src/**/*.{ts,tsx}"],
    exclude: ["src/**/__tests__/**/*", "src/**/*.d.ts"],
  },
}
const expectedPatterns = ["src/**/*.{ts,tsx}", "!src/**/__tests__/**/*", "!src/**/*.d.ts"]
const location = { start: { line: 1, column: 17 }, end: { line: 1, column: 21 } }
const killedMutant = {
  id: "1",
  mutatorName: "BooleanLiteral",
  replacement: "false",
  location,
  status: "Killed",
}
const sources = {
  "src/a.ts": "export const a = true\n",
  "src/b.ts": "export type B = string\n",
}

function preflight(entries = [["src/a.ts", [killedMutant]]]) {
  return new Map(
    entries.map(([file, mutants]) => [
      file,
      {
        sourceSha256: createHash("sha256").update(sources[file]).digest("hex"),
        mutants,
      },
    ])
  )
}

function mutationReport(overrides = {}) {
  return {
    schemaVersion: "1.0",
    config: {
      mutate: expectedPatterns,
      coverageAnalysis: "perTest",
      incremental: false,
      mutator: { plugins: null, excludedMutations: [] },
      ignorers: [],
    },
    files: {
      "src/a.ts": {
        source: sources["src/a.ts"],
        mutants: [killedMutant],
      },
    },
    ...overrides,
  }
}

function buildArgs(overrides = {}) {
  return {
    sourceFiles: ["src/a.ts"],
    sourceByFile: new Map([["src/a.ts", sources["src/a.ts"]]]),
    report: mutationReport(),
    expectedPatterns,
    preflightByFile: preflight(),
    ...overrides,
  }
}

test("derives mutation patterns from the canonical coverage source policy", async () => {
  const { mutationPatternsFromPolicy } = await import(inventoryModuleUrl)
  assert.deepEqual(mutationPatternsFromPolicy(policy), expectedPatterns)
})

test("discovers only included authored files while applying broad exclusions in-place", async (t) => {
  const { listPolicyFiles } = await import(inventoryModuleUrl)
  const fixtureRoot = await mkdtemp(path.join(os.tmpdir(), "frontend-mutation-policy-"))
  t.after(() => rm(fixtureRoot, { recursive: true, force: true }))
  await Promise.all([
    mkdir(path.join(fixtureRoot, "src", "feature"), { recursive: true }),
    mkdir(path.join(fixtureRoot, "src", "__tests__"), { recursive: true }),
    mkdir(path.join(fixtureRoot, "node_modules", "dependency"), { recursive: true }),
  ])
  await Promise.all([
    writeFile(path.join(fixtureRoot, "src", "feature", "index.ts"), "export const ok = true\n"),
    writeFile(path.join(fixtureRoot, "src", "feature", "types.d.ts"), "export type T = string\n"),
    writeFile(path.join(fixtureRoot, "src", "__tests__", "index.test.ts"), "test('x', () => {})\n"),
    writeFile(
      path.join(fixtureRoot, "node_modules", "dependency", "index.d.ts"),
      "export type External = string\n"
    ),
  ])

  assert.deepEqual(await listPolicyFiles(policy, fixtureRoot), ["src/feature/index.ts"])
})

test("preflights each source with the same Stryker instrumenter semantics", async () => {
  const { generateInstrumenterPreflight } = await import(inventoryModuleUrl)
  const result = await generateInstrumenterPreflight({
    sourceFiles: ["src/a.ts", "src/b.ts"],
    sourceByFile: new Map(Object.entries(sources)),
    instrumenterOptions: { plugins: null, ignorers: [], excludedMutations: [] },
  })

  assert.ok(result.get("src/a.ts").mutants.length > 0)
  assert.equal(result.get("src/b.ts").mutants.length, 0)
  assert.equal(
    result.get("src/a.ts").sourceSha256,
    createHash("sha256").update(sources["src/a.ts"]).digest("hex")
  )
})

test("rejects Stryker ignore directives during instrumenter preflight", async () => {
  const { generateInstrumenterPreflight } = await import(inventoryModuleUrl)
  await assert.rejects(
    () =>
      generateInstrumenterPreflight({
        sourceFiles: ["src/ignored.ts"],
        sourceByFile: new Map([
          ["src/ignored.ts", "// Stryker disable all: forbidden\nexport const value = true\n"],
        ]),
        instrumenterOptions: { plugins: null, ignorers: [], excludedMutations: [] },
      }),
    /ignore directive.*src\/ignored\.ts/u
  )
})

test("accounts for a missing report file only after a zero-mutant instrumenter preflight", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  const inventory = buildMutationInventory(
    buildArgs({
      sourceFiles: ["src/a.ts", "src/b.ts"],
      sourceByFile: new Map(Object.entries(sources)),
      preflightByFile: preflight([
        ["src/a.ts", [killedMutant]],
        ["src/b.ts", []],
      ]),
    })
  )

  assert.deepEqual(inventory.files, [
    {
      path: "src/a.ts",
      classification: "mutated",
      mutantCount: 1,
      sourceSha256: createHash("sha256").update(sources["src/a.ts"]).digest("hex"),
    },
    {
      path: "src/b.ts",
      classification: "zero-mutant",
      mutantCount: 0,
      sourceSha256: createHash("sha256").update(sources["src/b.ts"]).digest("hex"),
    },
  ])
  assert.deepEqual(inventory.summary, {
    denominatorFiles: 2,
    mutatedFiles: 1,
    zeroMutantFiles: 1,
    totalMutants: 1,
    killedMutants: 1,
    nonViableMutants: 0,
    viableMutantScore: 100,
  })
})

test("rejects an omitted runtime file when the preflight generated mutants", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          sourceFiles: ["src/a.ts", "src/b.ts"],
          sourceByFile: new Map(Object.entries(sources)),
          preflightByFile: preflight([
            ["src/a.ts", [killedMutant]],
            ["src/b.ts", [{ ...killedMutant, id: "preflight-b" }]],
          ]),
        })
      ),
    /omitted src\/b\.ts.*preflight generated 1 mutant/u
  )
})

test("rejects report mutants that differ from the instrumenter preflight", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          preflightByFile: preflight([["src/a.ts", [{ ...killedMutant, replacement: "null" }]]]),
        })
      ),
    /mutant signatures differ/u
  )
})

test("canonicalizes location key order while binding the signature to its file", async () => {
  const { buildMutationInventory, mutantSignature } = await import(inventoryModuleUrl)
  const reorderedLocation = {
    end: { column: 21, line: 1 },
    start: { column: 17, line: 1 },
  }
  const inventory = buildMutationInventory(
    buildArgs({
      preflightByFile: preflight([
        ["src/a.ts", [{ ...killedMutant, location: reorderedLocation }]],
      ]),
    })
  )

  assert.equal(inventory.summary.totalMutants, 1)
  assert.notEqual(
    mutantSignature(killedMutant, "src/a.ts"),
    mutantSignature(killedMutant, "src/b.ts")
  )
})

test("rejects malformed mutant locations and path aliases", async () => {
  const { buildMutationInventory, mutantSignature } = await import(inventoryModuleUrl)
  assert.throws(
    () => mutantSignature({ ...killedMutant, location: { start: {}, end: {} } }, "src/a.ts"),
    /location/u
  )
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          report: mutationReport({
            files: {
              "src/a.ts": mutationReport().files["src/a.ts"],
              "./src/a.ts": mutationReport().files["src/a.ts"],
            },
          }),
        })
      ),
    /alias|duplicate/u
  )
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          report: mutationReport({ files: { "../src/a.ts": mutationReport().files["src/a.ts"] } }),
        })
      ),
    /path/u
  )
})

test("fails closed on a missing or unsupported Stryker mutation schema", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  for (const schemaVersion of [undefined, "0.1", 1]) {
    assert.throws(
      () => buildMutationInventory(buildArgs({ report: mutationReport({ schemaVersion }) })),
      /schemaVersion must equal 1\.0/u
    )
  }
})

test("fails closed when effective instrumenter or coverage options drift", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  const baseConfig = mutationReport().config
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          report: mutationReport({
            config: {
              ...baseConfig,
              mutator: { plugins: null, excludedMutations: ["StringLiteral"] },
            },
          }),
        })
      ),
    /instrumenter options/u
  )
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          report: mutationReport({ config: { ...baseConfig, coverageAnalysis: "off" } }),
        })
      ),
    /coverageAnalysis must equal perTest/u
  )
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          report: mutationReport({ config: { ...baseConfig, incremental: true } }),
        })
      ),
    /incremental must be disabled/u
  )
})

test("fails closed when the report scope or current source differs", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({
          report: mutationReport({
            config: {
              mutate: ["src/a.ts"],
              coverageAnalysis: "perTest",
              incremental: false,
              mutator: { plugins: null, excludedMutations: [] },
              ignorers: [],
            },
          }),
        })
      ),
    /mutation scope does not match/u
  )
  assert.throws(
    () =>
      buildMutationInventory(
        buildArgs({ sourceByFile: new Map([["src/a.ts", "export const a = false\n"]]) })
      ),
    /source snapshot is stale/u
  )
})

test("rejects every non-killed viable mutant status", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  for (const status of ["Survived", "NoCoverage", "Timeout", "RuntimeError", "Ignored"]) {
    assert.throws(
      () =>
        buildMutationInventory(
          buildArgs({
            report: mutationReport({
              files: {
                "src/a.ts": {
                  source: sources["src/a.ts"],
                  mutants: [{ ...killedMutant, status }],
                },
              },
            }),
          })
        ),
      new RegExp(status, "u")
    )
  }
})

test("accounts for explained compile errors as non-viable", async () => {
  const { buildMutationInventory } = await import(inventoryModuleUrl)
  const compileError = {
    ...killedMutant,
    id: "2",
    replacement: "null",
    status: "CompileError",
    statusReason: "invalid mutant",
  }
  const inventory = buildMutationInventory(
    buildArgs({
      preflightByFile: preflight([["src/a.ts", [killedMutant, compileError]]]),
      report: mutationReport({
        files: {
          "src/a.ts": {
            source: sources["src/a.ts"],
            mutants: [killedMutant, compileError],
          },
        },
      }),
    })
  )

  assert.deepEqual(inventory.summary, {
    denominatorFiles: 1,
    mutatedFiles: 1,
    zeroMutantFiles: 0,
    totalMutants: 2,
    killedMutants: 1,
    nonViableMutants: 1,
    viableMutantScore: 100,
  })
})
