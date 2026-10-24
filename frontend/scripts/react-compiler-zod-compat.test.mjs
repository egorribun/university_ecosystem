import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import path from "node:path"
import test from "node:test"

import { ESLint } from "eslint"
import reactCompiler from "eslint-plugin-react-compiler"
import tseslint from "typescript-eslint"

import adapter from "./react-compiler-zod-compat/index.cjs"

const require = createRequire(import.meta.url)
const frontendRoot = path.resolve(import.meta.dirname, "..")
const compilerPath = require.resolve("eslint-plugin-react-compiler")
const compilerRequire = createRequire(compilerPath)
const legacy = compilerRequire("zod").z
const ruleId = "react-compiler/react-compiler"
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"))

const shapes = [
  ["declaration", (body) => `function Widget() { ${body} }`],
  ["arrow", (body) => `const Widget = () => { ${body} }`],
  ["expression", (body) => `const Widget = function () { ${body} }`],
  ["default", (body) => `export default function () { ${body} }`],
  ["memo", (body) => `const Widget = React.memo(function Widget() { ${body} })`],
  ["forward-ref", (body) => `const Widget = React.forwardRef((props, ref) => { ${body} })`],
  ["nested", (body) => `function factory() { return function Widget() { ${body} } }`],
  ["ordinary", (body) => `function utility() { ${body} }`],
]
const hookSource = [
  "function useFixture(flag) {",
  "  if (flag) {",
  "    useConditionalHook();",
  "  }",
  "}",
].join("\n")
const todoSource = "function Widget(x) { var value = 1; return <div>{value * x}</div>; }"
const refSource = [
  'import { useRef } from "react";',
  "function Widget() { const ref = useRef(0); return <div>{ref.current}</div>; }",
].join("\n")
const fixtures = [
  ["valid", "function Widget({ value }) { return <span>{value}</span>; }"],
  ["conditional-hook", hookSource],
  [
    "state-mutation",
    'import { useState } from "react";\n' +
      "function Widget() { const [state] = useState({ value: 0 }); " +
      "const next: number = 1; state.value = next; return <div>{state.value}</div>; }",
  ],
  ["props-mutation", "function Widget(props) { props.value = 1; return <div />; }"],
  ["ref-default", refSource],
  ["ref-enabled", refSource, { environment: { validateRefAccessDuringRender: true } }],
  ["todo-default", todoSource],
  ["todo-reportable", todoSource, { reportableLevels: new Set(["Todo"]) }],
  ["all-bailouts", todoSource, { __unstable_donotuse_reportAllBailouts: true }],
  [
    "flow-suppression",
    hookSource.replace(
      "    useConditionalHook",
      "    // $FlowFixMe[react-rule-hook]\n    useConditionalHook"
    ),
  ],
  [
    "flow-wrong-line",
    hookSource.replace(
      "    useConditionalHook",
      "    // $FlowFixMe[react-rule-hook]\n\n    useConditionalHook"
    ),
  ],
  [
    "eslint-suppression",
    hookSource.replace(
      "    useConditionalHook",
      `    // eslint-disable-next-line ${ruleId}\n    useConditionalHook`
    ),
  ],
  [
    "file-wide-unused-suppression",
    todoSource + '\nfunction utility() { "use no memo"; return 1; }',
  ],
  [
    "provider-function-config",
    'import value from "tooling-fixture"; function Widget() { return <div>{value}</div>; }',
    { environment: { moduleTypeProvider: () => null } },
  ],
  [
    "provider-function-return-config",
    'import value from "tooling-fixture"; function Widget() { return <div>{value}</div>; }',
    { environment: { moduleTypeProvider: () => ({ kind: "invalid" }) } },
  ],
  [
    "provider-invalid-config",
    "function Widget() { return <div />; }",
    { environment: { moduleTypeProvider: "not-a-function" } },
  ],
  ["target-invalid-config", "function Widget() { return <div />; }", { target: "invalid" }],
]
for (const directive of ["use no memo", "use no forget"]) {
  for (const [shape, wrap] of shapes) {
    fixtures.push([`${shape}-${directive}`, wrap(`"${directive}"; return <span />;`)])
  }
}

for (const [shape, wrap] of shapes.filter(([name]) =>
  ["arrow", "memo", "forward-ref", "nested"].includes(name)
)) {
  fixtures.push([
    `${shape}-state-mutation`,
    wrap("const [state] = React.useState({ value: 0 }); state.value = 1; return <div />;"),
  ])
}

test("capture the installed rc.2 baseline before changing its dependency graph", async () => {
  assert.equal(require("eslint-plugin-react-compiler/package.json").version, "19.1.0-rc.2")
  assert.equal(compilerRequire("zod/package.json").version, "3.25.76")
  assert.equal(lock.packages["node_modules/eslint-plugin-react-compiler"].version, "19.1.0-rc.2")
  assert.equal(fixtures.length, 37)
  const records = []
  for (const [name, source, options = {}] of fixtures) {
    assert.ok(source.length < 2048)
    try {
      const eslint = new ESLint({
        cwd: frontendRoot,
        overrideConfigFile: true,
        overrideConfig: [
          {
            files: ["**/*.tsx"],
            languageOptions: {
              parser: tseslint.parser,
              parserOptions: {
                ecmaVersion: "latest",
                sourceType: "module",
                ecmaFeatures: { jsx: true },
              },
            },
            plugins: { "react-compiler": reactCompiler },
            rules: { [ruleId]: ["error", options] },
          },
        ],
      })
      const [result] = await eslint.lintText(source, { filePath: "src/__compiler_fixture__.tsx" })
      assert.equal(result.fatalErrorCount, 0, name)
      assert.ok(result.messages.length <= 20, name)
      records.push({
        name,
        messages: result.messages,
        suppressedMessages: result.suppressedMessages,
      })
    } catch (error) {
      // Malformed options are part of the baseline, not evidence of compatibility.
      if (!name.endsWith("-config") || error.code === "ERR_ASSERTION") throw error
      records.push({
        name,
        error: {
          name: error.name,
          message: error.message.replaceAll(frontendRoot, "<frontend>"),
        },
      })
    }
  }
  // ESLint 10 clones rule options; functions are rejected before the compiler.
  // Preserve that real public boundary instead of injecting a bypassing wrapper.
  for (const record of records.filter(({ name }) => name.startsWith("provider-function"))) {
    assert.ok(record.error, record.name)
    assert.match(record.error.message, /could not be cloned/)
  }
  assert.deepEqual(records.find(({ name }) => name === "valid").messages, [])
  assert.ok(records.find(({ name }) => name === "conditional-hook").messages.length > 0)
  assert.match(
    records.find(({ name }) => name === "declaration-use no memo").messages[0].message,
    /Unused 'use no memo' directive/
  )
  const report = {
    kind: "react-compiler-legacy-baseline",
    schemaVersion: 1,
    sourceSha: process.env.SOURCE_SHA ?? null,
    node: process.versions.node,
    eslint: require("eslint/package.json").version,
    compilerVersion: require("eslint-plugin-react-compiler/package.json").version,
    compilerIntegrity: lock.packages["node_modules/eslint-plugin-react-compiler"].integrity,
    compilerBundleSha256: createHash("sha256").update(readFileSync(compilerPath)).digest("hex"),
    schemaVersionInstalled: compilerRequire("zod/package.json").version,
    schemaErrors: captureSchemaErrors(legacy),
    formatterEntrySha256: createHash("sha256")
      .update(readFileSync(compilerRequire.resolve("zod-validation-error")))
      .digest("hex"),
    records,
  }
  const serialized = JSON.stringify(report)
  assert.ok(Buffer.byteLength(serialized) < 98304)
  console.log(serialized)
})

function captureSchemaErrors(z) {
  const formatter = compilerRequire("zod-validation-error")
  const samples = [
    ["provider-value", z.function().args(z.string()), 42],
    ["record-value", z.record(z.string(), z.string()), { value: 42 }],
    ["union-value", z.union([z.literal("17"), z.literal("18")]), "invalid"],
    ["minimum-value", z.number().min(1, "at least one"), 0],
  ]
  const records = samples.map(([name, schema, input]) => {
    const result = schema.safeParse(input)
    assert.equal(result.success, false)
    return {
      name,
      errorName: result.error.name,
      issues: result.error.issues,
      text: result.error.toString(),
      formatted: formatter.fromZodError(result.error).message,
    }
  })
  const callback = z
    .function()
    .args(z.string())
    .parse(() => null)
  assert.throws(
    () => callback(42),
    (error) => {
      records.push({
        name: "provider-argument",
        errorName: error.name,
        issues: error.issues,
        text: error.toString(),
        formatted: formatter.fromZodError(error).message,
      })
      return true
    }
  )
  return records
}

function verifyPrimitives(z) {
  const schema = z.object({
    active: z.boolean().default(false),
    mode: z.enum(["infer", "all"]),
    effect: z.nativeEnum({ Read: "read", Capture: "capture" }),
    note: z.nullable(z.string()).default(null),
    tuple: z.tuple([z.literal("tag"), z.number()]),
  })
  assert.deepEqual(schema.parse({ mode: "infer", effect: "read", tuple: ["tag", 2] }), {
    active: false,
    mode: "infer",
    effect: "read",
    note: null,
    tuple: ["tag", 2],
  })
  assert.equal(schema.safeParse({ mode: "other" }).success, false)
}

function verifyProvider(z) {
  const schema = z.nullable(z.function().args(z.string())).default(null)
  assert.equal(schema.parse(undefined), null)
  assert.equal(schema.safeParse("invalid").success, false)
  const marker = { name: "result" }
  const receiver = {
    marker,
    provider: schema.parse(function (name, extra) {
      assert.equal(name, "module")
      assert.equal(extra, 42)
      return this.marker
    }),
  }
  assert.equal(receiver.provider("module", 42), marker)
  assert.throws(() => receiver.provider(42))
  assert.throws(() => receiver.provider())
  assert.equal(schema.parse(() => undefined)("module"), undefined)
  assert.equal(schema.parse(() => null)("module"), null)
}

function verifyMapDefaults(z) {
  const hook = z.object({ active: z.boolean().default(false) })
  const defaultValue = new Map([["useFixture", {}]])
  const schema = z.map(z.string(), hook).default(defaultValue)
  const first = schema.parse(undefined)
  const second = schema.parse(undefined)
  assert.notEqual(first, second)
  assert.notEqual(first, defaultValue)
  assert.deepEqual(first.get("useFixture"), { active: false })
  assert.notEqual(first.get("useFixture"), second.get("useFixture"))
  first.set("other", { active: true })
  assert.equal(second.has("other"), false)
  assert.equal(schema.safeParse(new Map([[1, {}]])).success, false)
}

function verifyRecursiveRecords(z) {
  const tree = z.union([
    z.object({ kind: z.literal("leaf"), value: z.string() }),
    z.object({
      kind: z.literal("object"),
      properties: z
        .record(
          z.string(),
          z.lazy(() => tree)
        )
        .refine(
          (record) => Object.keys(record).every((key) => ["default", "*", "value"].includes(key)),
          "invalid property"
        ),
    }),
  ])
  const input = {
    kind: "object",
    properties: { default: { kind: "leaf", value: "ok", extra: 1 } },
  }
  assert.deepEqual(tree.parse(input), {
    kind: "object",
    properties: { default: { kind: "leaf", value: "ok" } },
  })
  assert.equal(tree.safeParse({ kind: "object", properties: { invalid: input } }).success, false)
}

function verifyArraysAndMinima(z) {
  const schema = z.object({
    values: z.array(z.string()),
    flag: z.boolean().nullable().optional(),
    count: z.number().min(1, "at least one"),
  })
  assert.deepEqual(schema.parse({ values: ["a"], count: 1 }), { values: ["a"], count: 1 })
  assert.deepEqual(schema.parse({ values: [], flag: null, count: 2 }), {
    values: [],
    flag: null,
    count: 2,
  })
  for (const input of [
    { values: [1], count: 1 },
    { values: [], count: 0 },
  ]) {
    const result = schema.safeParse(input)
    assert.equal(result.success, false)
    assert.equal(typeof result.error.toString(), "string")
    assert.ok(result.error.issues.length > 0)
  }
}

const contracts = [
  ["primitives, enums and nullable defaults", verifyPrimitives],
  ["provider arguments, this, extra arguments and unknown results", verifyProvider],
  ["map defaults are parsed and cloned", verifyMapDefaults],
  ["recursive records retain refinement and key stripping", verifyRecursiveRecords],
  ["arrays, nullable optional fields and numeric minima", verifyArraysAndMinima],
]
for (const [name, verify] of contracts) {
  test(`legacy control: ${name}`, () => verify(legacy))
}
test("adapter exposes only the source-inventoried factory surface", () => {
  assert.ok(adapter.z, "the compatibility facade is not implemented")
  assert.deepEqual(Object.keys(adapter.z).sort(), [
    "array",
    "boolean",
    "enum",
    "function",
    "lazy",
    "literal",
    "map",
    "nativeEnum",
    "nullable",
    "number",
    "object",
    "record",
    "string",
    "tuple",
    "union",
  ])
})
for (const [name, verify] of contracts) {
  test(`adapter contract: ${name}`, () => {
    assert.ok(adapter.z, "the compatibility facade is not implemented")
    verify(adapter.z)
  })
}

test("adapter array upper bounds reject before element refinements", () => {
  assert.ok(adapter.z, "the compatibility facade is not implemented")
  let calls = 0
  const item = adapter.z.string().refine(() => {
    calls += 1
    return true
  })
  const result = adapter.z.array(item).max(1).safeParse(["a", "b"])
  assert.equal(result.success, false)
  assert.equal(calls, 0)
  assert.deepEqual(
    result.error.issues.map(({ code }) => code),
    ["too_big"]
  )
})

test("adapter map upper bounds reject before key and value refinements", () => {
  assert.ok(adapter.z, "the compatibility facade is not implemented")
  let calls = 0
  const item = adapter.z.string().refine(() => {
    calls += 1
    return true
  })
  const result = adapter.z
    .map(item, item)
    .max(1)
    .safeParse(
      new Map([
        ["a", "b"],
        ["c", "d"],
      ])
    )
  assert.equal(result.success, false)
  assert.equal(calls, 0)
  assert.deepEqual(
    result.error.issues.map(({ code }) => code),
    ["too_big"]
  )
})
