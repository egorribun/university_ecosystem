import assert from "node:assert/strict"
import test from "node:test"

import { Instrumenter } from "@stryker-mutator/instrumenter"

import {
  PRESENTATION_IGNORE_REASON,
  PRESENTATION_IGNORER,
  canonicalInstrumenterConfig,
  isGovernedIgnoredMutant,
  presentationIgnorer,
  resolveInstrumenterOptions,
  strykerPlugins,
} from "./stryker-presentation-ignorer.mjs"

const quietLogger = {
  debug() {},
  info() {},
  isDebugEnabled() {
    return false
  },
}

async function instrument(content, fileName = "src/sample.tsx") {
  const result = await new Instrumenter(quietLogger).instrument(
    [{ name: fileName, content, mutate: true }],
    resolveInstrumenterOptions()
  )
  // Instrumenter locations are zero-based lines and columns.
  const lines = content.split("\n")
  return result.mutants.map((mutant) => ({
    text: lines[mutant.location.start.line].slice(
      mutant.location.start.column,
      mutant.location.start.line === mutant.location.end.line
        ? mutant.location.end.column
        : undefined
    ),
    mutator: mutant.mutatorName,
    ignored: mutant.status === "Ignored",
    reason: mutant.statusReason,
  }))
}

const ignoredTexts = (mutants) => mutants.filter((m) => m.ignored).map((m) => m.text)
const activeTexts = (mutants) => mutants.filter((m) => !m.ignored).map((m) => m.text)

test("ignores class lists in className attributes and class helpers", async () => {
  const mutants = await instrument(`
import { cn } from "@/utils/cn"
export const A = ({ active }: { active: boolean }) => (
  <div className="flex gap-2" panelClassName={"p-4"}>
    <span className={cn("base", active ? "on" : "off", active && "ring")} />
  </div>
)
`)
  // Stryker never mutates a bare JSX string attribute such as className="flex".
  assert.deepEqual(ignoredTexts(mutants).sort(), ['"base"', '"off"', '"on"', '"p-4"', '"ring"'])
  assert.ok(mutants.filter((m) => m.ignored).every((m) => m.reason === PRESENTATION_IGNORE_REASON))
  // The styling decision itself stays under mutation.
  assert.deepEqual(
    mutants.filter((m) => !m.ignored && m.text === 'active && "ring"').map((m) => m.mutator),
    ["ConditionalExpression", "ConditionalExpression", "LogicalOperator"]
  )
})

test("ignores cva variant maps and class-named bindings, not other strings", async () => {
  const mutants = await instrument(
    `
import { cva } from "class-variance-authority"
export const button = cva("rounded", { variants: { size: { sm: "px-2" } } })
export const sizeClasses = { sm: "text-sm", lg: \`text-lg\` }
export const label = "Visible label"
export const kind = { sm: "text-sm" }
`,
    "src/sample.ts"
  )
  assert.deepEqual(ignoredTexts(mutants).sort(), ['"px-2"', '"rounded"', '"text-sm"', "`text-lg`"])
  // Object shapes stay mutated even inside class maps; only their leaves are ignored.
  assert.deepEqual(
    activeTexts(mutants).sort(),
    [
      '"Visible label"',
      '"text-sm"',
      '{ size: { sm: "px-2" } }',
      '{ sm: "px-2" }',
      '{ sm: "text-sm", lg: `text-lg` }',
      '{ sm: "text-sm" }',
      '{ variants: { size: { sm: "px-2" } } }',
    ].sort()
  )
})

test("ignores literal inline style values but keeps state-driven styles mutated", async () => {
  const mutants = await instrument(`
export const A = ({ reduced, height }: { reduced: boolean; height?: number }) => (
  <div
    style={{ fontSize: "0.45em", transition: reduced ? "none" : "opacity 200ms", minHeight: height }}
    title={"Hint"}
  />
)
`)
  assert.deepEqual(ignoredTexts(mutants).sort(), ['"0.45em"', '"none"', '"opacity 200ms"'])
  const active = activeTexts(mutants)
  assert.ok(active.includes('"Hint"'), "non-presentation attributes stay mutated")
  assert.ok(
    active.some((text) => text.startsWith("{ fontSize")),
    "the style object stays mutated"
  )
})

test("keeps template literals with interpolations and non-value positions mutated", async () => {
  const mutants = await instrument(`
export const A = ({ tone }: { tone: string }) => (
  <div className={\`chip \${tone}\`} data-state={tone === "ok" ? "a" : "b"} />
)
`)
  assert.deepEqual(ignoredTexts(mutants), [])
  assert.ok(activeTexts(mutants).includes("`chip ${tone}`"))
})

test("exposes one serializable policy and fails closed on any other configuration", () => {
  assert.equal(PRESENTATION_IGNORER, "presentation-class-names")
  assert.deepEqual(strykerPlugins, [
    { kind: "Ignore", name: PRESENTATION_IGNORER, value: presentationIgnorer },
  ])
  assert.deepEqual(JSON.parse(JSON.stringify(canonicalInstrumenterConfig)), {
    plugins: null,
    excludedMutations: [],
    ignorers: [PRESENTATION_IGNORER],
  })
  assert.deepEqual(resolveInstrumenterOptions(), {
    plugins: null,
    excludedMutations: [],
    ignorers: [presentationIgnorer],
  })
  assert.throws(
    () => resolveInstrumenterOptions({ plugins: null, excludedMutations: [], ignorers: [] }),
    /governed ignore policy/u
  )
  assert.equal(presentationIgnorer.shouldIgnore({ node: { type: "Identifier" } }), undefined)
})

test("accepts only mutants ignored by this policy", () => {
  assert.equal(
    isGovernedIgnoredMutant({ status: "Ignored", statusReason: PRESENTATION_IGNORE_REASON }),
    true
  )
  assert.equal(
    isGovernedIgnoredMutant({ status: "Ignored", statusReason: "disable comment" }),
    false
  )
  assert.equal(
    isGovernedIgnoredMutant({ status: "Survived", statusReason: PRESENTATION_IGNORE_REASON }),
    false
  )
  assert.equal(isGovernedIgnoredMutant(undefined), false)
})
