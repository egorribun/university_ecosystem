import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import {
  copyFileSync,
  cpSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
} from "node:fs"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
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
const installedSchema = compilerRequire("zod").z
const ruleId = "react-compiler/react-compiler"
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"))
const golden = JSON.parse(
  readFileSync(new URL("./react-compiler-zod-compat/legacy-baseline.json", import.meta.url), "utf8")
)
const postgraphSchemaObservations = JSON.parse(
  readFileSync(
    new URL("./react-compiler-zod-compat.postgraph-errors.json", import.meta.url),
    "utf8"
  )
)
const FACADE_NAME = "@university-ecosystem/react-compiler-zod-compat"
const FACADE_VERSION = "1.0.0"
const FACADE_SPEC = "file:./vendor/react-compiler-zod-compat-1.0.0.tgz"
const FACADE_INTEGRITY =
  "sha512-4M74nZuqffHkW97CJJq1q3dIyFNdwkv9ydjCtkyd43o/pwZMAVJlijqY5Scl+MudxRRBara/XqXY9HdqsT7cUg=="
const FACADE_SHA256 = "3887a71e809e5c427392ee521eec91296bffae536aa11f8bd04863922a193ff5"
const COMPILER_OVERRIDE_KEY = "eslint-plugin-react-compiler@>=19.1.0-rc.2 <=19.1.0-rc.2"
const COMPILER_OVERRIDE = Object.freeze({
  ".": "$eslint-plugin-react-compiler",
  zod: "$" + FACADE_NAME,
  "zod-validation-error": Object.freeze({ ".": "4.0.2", zod: "4.6.7" }),
})
const APPROVED_CONFIG_REASONS = Object.freeze({
  "provider-invalid-config": "InvalidConfig: Error in validating environment config.",
  "target-invalid-config": "InvalidConfig: Not a valid target.",
})

function assertRuleRecordsMatchBaseline(records, expectedRecords) {
  assert.equal(records.length, expectedRecords.length)
  const configurationChanges = []
  for (const [index, record] of records.entries()) {
    const expected = expectedRecords[index]
    assert.equal(record.name, expected.name)
    const reason = APPROVED_CONFIG_REASONS[record.name]
    if (!reason) {
      assert.deepEqual(record, expected, record.name)
      continue
    }

    assert.equal(expected.error?.name, "ReactCompilerError", record.name)
    assert.equal(record.error?.name, "ReactCompilerError", record.name)
    assert.equal(typeof record.error?.message, "string", record.name)
    assert.equal(record.error.message.startsWith(reason), true, record.name)
    configurationChanges.push({
      name: record.name,
      before: expected.error,
      after: record.error,
    })
  }
  assert.deepEqual(
    configurationChanges.map(({ name }) => name),
    Object.keys(APPROVED_CONFIG_REASONS)
  )
  return configurationChanges
}

function assertFacadeEngineIdentity(facadeManifest, engineManifest) {
  assert.equal(facadeManifest.name, FACADE_NAME)
  assert.equal(facadeManifest.version, FACADE_VERSION)
  assert.deepEqual(facadeManifest.dependencies, { "patched-zod": "npm:zod@4.6.7" })
  assert.equal(engineManifest.name, "zod")
  assert.equal(engineManifest.version, "4.6.7")
}

function assertCompilerOverrideScope(manifest) {
  assert.equal(manifest.devDependencies?.[FACADE_NAME], FACADE_SPEC)
  for (const section of ["dependencies", "optionalDependencies", "peerDependencies"]) {
    assert.equal(Object.hasOwn(manifest[section] ?? {}, FACADE_NAME), false, section)
  }
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    assert.equal(Object.hasOwn(manifest[section] ?? {}, "zod"), false, `${section}.zod`)
    assert.equal(
      Object.hasOwn(manifest[section] ?? {}, "patched-zod"),
      false,
      `${section}.patched-zod`
    )
  }
  const compilerOverrideKeys = Object.keys(manifest.overrides ?? {}).filter((key) =>
    key.startsWith("eslint-plugin-react-compiler")
  )
  assert.deepEqual(compilerOverrideKeys, [COMPILER_OVERRIDE_KEY])
  assert.deepEqual(manifest.overrides[COMPILER_OVERRIDE_KEY], COMPILER_OVERRIDE)
}

function collectLeafIssuePaths(issues) {
  return issues.flatMap((issue) => {
    const nestedIssues = [
      ...(Array.isArray(issue.errors) ? issue.errors.flat(Infinity) : []),
      ...(Array.isArray(issue.unionErrors)
        ? issue.unionErrors.flatMap(({ issues }) => issues)
        : []),
      ...(issue.argumentsError?.issues ?? []),
    ]
    if (nestedIssues.length > 0) return collectLeafIssuePaths(nestedIssues)
    return [issue.path ?? []]
  })
}

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

async function collectRuleRecords(plugin) {
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
            plugins: { "react-compiler": plugin },
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
  return records
}

test("the installed rc.2 consumer graph preserves the reviewed compiler behavior", async () => {
  const compilerManifest = require("eslint-plugin-react-compiler/package.json")
  const compilerManifestPath = require.resolve("eslint-plugin-react-compiler/package.json")
  const compilerRecord = lock.packages["node_modules/eslint-plugin-react-compiler"]
  const installedFacadePath = compilerRequire.resolve("zod/package.json")
  const installedFacade = compilerRequire(installedFacadePath)
  const facadeRequire = createRequire(installedFacadePath)
  const installedEnginePath = facadeRequire.resolve("patched-zod/package.json")
  const installedEngine = facadeRequire(installedEnginePath)
  const formatterEntryPath = compilerRequire.resolve("zod-validation-error")
  const formatterRoot = path.resolve(path.dirname(formatterEntryPath), "..")
  const formatterManifest = JSON.parse(
    readFileSync(path.join(formatterRoot, "package.json"), "utf8")
  )
  const formatterRecord = lock.packages["node_modules/zod-validation-error"]

  assert.equal(compilerManifest.name, "eslint-plugin-react-compiler")
  assert.equal(compilerManifest.version, "19.1.0-rc.2")
  assert.equal(compilerRecord.version, "19.1.0-rc.2")
  assert.equal(compilerRecord.integrity, golden.compilerIntegrity)
  assertFacadeEngineIdentity(installedFacade, installedEngine)
  assert.equal(
    realpathSync(installedFacadePath),
    path.join(path.dirname(compilerManifestPath), "node_modules", "zod", "package.json")
  )
  assert.equal(
    realpathSync(installedEnginePath),
    path.join(frontendRoot, "node_modules", "patched-zod", "package.json")
  )
  assert.equal(golden.schemaVersionInstalled, "3.25.76")
  assert.deepEqual(postgraphSchemaObservations.engine, {
    name: installedEngine.name,
    version: installedEngine.version,
  })
  assert.equal(formatterManifest.name, "zod-validation-error")
  assert.equal(formatterManifest.version, "4.0.2")
  assert.equal(formatterRecord.version, formatterManifest.version)
  assert.equal(formatterRecord.integrity, postgraphSchemaObservations.formatter.integrity)
  assert.equal(formatterRecord.resolved, postgraphSchemaObservations.formatter.resolved)
  assert.equal(fixtures.length, 37)
  const records = await collectRuleRecords(reactCompiler)
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
  const configurationChanges = assertRuleRecordsMatchBaseline(records, golden.records)
  const schemaProbe = captureSchemaErrorObservations(installedSchema)
  const schemaErrors = schemaProbe.records
  assert.deepEqual(schemaErrors, postgraphSchemaObservations.cases)
  assert.deepEqual(
    schemaErrors.map(({ name }) => name),
    golden.schemaErrors.map(({ name }) => name)
  )
  assert.deepEqual(
    schemaErrors.map(({ issues }) => collectLeafIssuePaths(issues)),
    golden.schemaErrors.map(({ issues }) => collectLeafIssuePaths(issues))
  )
  const schemaErrorNameChanges = schemaErrors.flatMap((record, index) => {
    const previous = golden.schemaErrors[index]
    return previous.errorName === record.errorName
      ? []
      : [{ name: record.name, before: previous.errorName, after: record.errorName }]
  })
  assert.deepEqual(schemaErrorNameChanges, [
    { name: "provider-argument", before: "ZodError", after: "$ZodError" },
  ])
  const baselineCustomMessages = golden.schemaErrors
    .filter(({ name }) => name === "minimum-value")
    .flatMap(({ issues }) => issues.map(({ message }) => message))
  const installedCustomMessages = schemaErrors
    .filter(({ name }) => name === "minimum-value")
    .flatMap(({ issues }) => issues.map(({ message }) => message))
  assert.deepEqual(installedCustomMessages, baselineCustomMessages)
  assert.deepEqual(installedCustomMessages, ["at least one"])
  assert.equal(schemaProbe.callbackCalls, 0)
  const compilerBundleSha256 = createHash("sha256").update(readFileSync(compilerPath)).digest("hex")
  assert.equal(compilerBundleSha256, golden.compilerBundleSha256)
  const formatterEntrySha256 = createHash("sha256")
    .update(readFileSync(formatterEntryPath))
    .digest("hex")
  assert.equal(formatterEntrySha256, postgraphSchemaObservations.formatter.entrySha256)
  const report = {
    kind: "react-compiler-scoped-facade-compatibility",
    schemaVersion: 1,
    sourceSha: process.env.SOURCE_SHA ?? null,
    node: process.versions.node,
    eslint: require("eslint/package.json").version,
    compilerVersion: compilerManifest.version,
    compilerIntegrity: compilerRecord.integrity,
    compilerBundleSha256,
    installedSchemaFacade: { name: installedFacade.name, version: installedFacade.version },
    installedSchemaEngine: { name: installedEngine.name, version: installedEngine.version },
    baselineSchemaEngineVersion: golden.schemaVersionInstalled,
    baselineFormatterEntrySha256: golden.formatterEntrySha256,
    installedSchemaErrorObservations: schemaErrors,
    schemaErrorNameChanges,
    schemaCallbackCalls: schemaProbe.callbackCalls,
    installedFormatter: {
      name: formatterManifest.name,
      version: formatterManifest.version,
      integrity: formatterRecord.integrity,
      entrySha256: formatterEntrySha256,
    },
    records,
    configurationChanges,
  }
  const serialized = JSON.stringify(report)
  assert.ok(Buffer.byteLength(serialized) < 98304)
  console.log(serialized)
  assert.deepEqual(JSON.parse(serialized), report)
})

function captureSchemaErrorObservations(z) {
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
  let callbackCalls = 0
  const callback = z
    .function()
    .args(z.string())
    .parse(() => {
      callbackCalls += 1
      return null
    })
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
  assert.equal(callbackCalls, 0)
  return { records, callbackCalls }
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
  let calls = 0
  const receiver = {
    marker,
    provider: schema.parse(function (name, extra) {
      calls += 1
      assert.equal(name, "module")
      assert.equal(extra, 42)
      return this.marker
    }),
  }
  assert.equal(receiver.provider("module", 42), marker)
  assert.throws(() => receiver.provider(42))
  assert.throws(() => receiver.provider())
  assert.equal(calls, 1, "invalid arguments must be rejected before invoking the provider")
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
  test(`installed compiler schema control: ${name}`, () => verify(installedSchema))
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

test("the isolated unchanged rc.2 rule retains diagnostics except approved config wording", async () => {
  assert.ok(adapter.z, "the compatibility facade is not implemented")
  const compilerRoot = path.dirname(
    compilerRequire.resolve("eslint-plugin-react-compiler/package.json")
  )
  const compilerManifest = compilerRequire("eslint-plugin-react-compiler/package.json")
  const dependencyNames = Object.keys(compilerManifest.dependencies).sort()
  assert.deepEqual(dependencyNames, [
    "@babel/core",
    "@babel/parser",
    "@babel/plugin-proposal-private-methods",
    "hermes-parser",
    "zod",
    "zod-validation-error",
  ])

  assert.equal(
    createHash("sha256").update(readFileSync(compilerPath)).digest("hex"),
    golden.compilerBundleSha256
  )
  const target = mkdtempSync(path.join(tmpdir(), "react-compiler-parity-"))
  try {
    const modules = path.join(target, "node_modules")
    const targetCompiler = path.join(modules, "eslint-plugin-react-compiler")
    const requiredFiles = ["package.json", "dist/index.js", "dist/index.d.ts"]
    const optionalDocs = ["LICENSE", "LICENCE", "README.md"]
    for (const relative of [...requiredFiles, ...optionalDocs]) {
      const source = path.join(compilerRoot, relative)
      const destination = path.join(targetCompiler, relative)
      const metadata = lstatSync(source, { throwIfNoEntry: false })
      if (metadata === undefined) {
        assert.equal(optionalDocs.includes(relative), true, relative)
        continue
      }
      assert.equal(metadata.isFile(), true, relative)
      assert.ok(metadata.size > 0 && metadata.size < 2 * 1024 * 1024, relative)
      mkdirSync(path.dirname(destination), { recursive: true })
      copyFileSync(source, destination)
      assert.deepEqual(readFileSync(destination), readFileSync(source), relative)
    }

    const hooksRequire = createRequire(require.resolve("eslint-plugin-react-hooks"))
    const formatterEntry = hooksRequire.resolve("zod-validation-error")
    const formatterRoot = path.resolve(path.dirname(formatterEntry), "..")
    const formatterManifest = JSON.parse(
      readFileSync(path.join(formatterRoot, "package.json"), "utf8")
    )
    assert.equal(formatterManifest.name, "zod-validation-error")
    assert.equal(formatterManifest.version, "4.0.2")
    for (const name of dependencyNames) {
      const dependencyRoot =
        name === "zod"
          ? path.join(import.meta.dirname, "react-compiler-zod-compat")
          : name === "zod-validation-error"
            ? formatterRoot
            : path.dirname(compilerRequire.resolve(`${name}/package.json`))
      const destination = path.join(modules, name)
      mkdirSync(path.dirname(destination), { recursive: true })
      symlinkSync(dependencyRoot, destination, "junction")
    }

    const isolatedRequire = createRequire(path.join(targetCompiler, "package.json"))
    assert.equal(isolatedRequire("zod"), adapter)
    assert.equal(isolatedRequire.resolve("zod-validation-error"), formatterEntry)
    const copiedBundle = path.join(targetCompiler, "dist", "index.js")
    assert.equal(
      createHash("sha256").update(readFileSync(copiedBundle)).digest("hex"),
      golden.compilerBundleSha256
    )
    const capturedRecords = await collectRuleRecords(isolatedRequire(copiedBundle))
    const records = JSON.parse(JSON.stringify(capturedRecords))
    const configurationChanges = assertRuleRecordsMatchBaseline(records, golden.records)
    // Only the two already rejected configuration values may change formatter wording.
    // Every rule diagnostic, suppression and suggestion above remains byte-for-byte equal.
    const serialized = JSON.stringify({
      kind: "react-compiler-config-error-diff",
      configurationChanges,
    })
    assert.ok(Buffer.byteLength(serialized) < 16384)
    console.log(serialized)
  } finally {
    rmSync(target, { recursive: true, force: true })
  }
})

test("the scoped facade is pinned, honestly named and development-only", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"))
  assertCompilerOverrideScope(manifest)

  const sourceFacadePath = require.resolve("./react-compiler-zod-compat/index.cjs")
  const sourceFacadeRequire = createRequire(sourceFacadePath)
  const sourceManifest = sourceFacadeRequire("./package.json")
  assert.equal(sourceManifest.license, "MIT")
  assert.equal(sourceManifest.scripts, undefined)

  const archive = readFileSync(
    path.join(frontendRoot, "vendor", "react-compiler-zod-compat-1.0.0.tgz")
  )
  assert.equal(archive.length, 2853)
  assert.equal(createHash("sha256").update(archive).digest("hex"), FACADE_SHA256)
  assert.equal(`sha512-${createHash("sha512").update(archive).digest("base64")}`, FACADE_INTEGRITY)

  const rootFacadeRecord = lock.packages[`node_modules/${FACADE_NAME}`]
  const consumerFacadeRecord =
    lock.packages["node_modules/eslint-plugin-react-compiler/node_modules/zod"]
  const rootEngineRecord = lock.packages["node_modules/zod"]
  const privateEngineRecord = lock.packages["node_modules/patched-zod"]
  const compilerRecord = lock.packages["node_modules/eslint-plugin-react-compiler"]
  assert.equal(rootFacadeRecord.resolved, "file:vendor/react-compiler-zod-compat-1.0.0.tgz")
  assert.equal(rootFacadeRecord.integrity, FACADE_INTEGRITY)
  assert.equal(rootFacadeRecord.version, FACADE_VERSION)
  assert.equal(rootFacadeRecord.dev, true)
  assert.equal(consumerFacadeRecord.name, FACADE_NAME)
  assert.equal(consumerFacadeRecord.version, FACADE_VERSION)
  assert.equal(consumerFacadeRecord.resolved, "file:vendor/react-compiler-zod-compat-1.0.0.tgz")
  assert.equal(consumerFacadeRecord.integrity, FACADE_INTEGRITY)
  assert.equal(consumerFacadeRecord.dev, true)
  assert.equal(compilerRecord.version, "19.1.0-rc.2")
  assert.equal(compilerRecord.dependencies.zod, "^3.22.4")
  assert.equal(compilerRecord.integrity, golden.compilerIntegrity)
  assert.equal(rootEngineRecord.version, "4.6.7")
  assert.equal(privateEngineRecord.name, "zod")
  assert.equal(privateEngineRecord.version, "4.6.7")
  assert.equal(privateEngineRecord.dev, true)
  assert.equal(privateEngineRecord.integrity, rootEngineRecord.integrity)

  const installedRootFacadePath = require.resolve(`${FACADE_NAME}/package.json`)
  const installedRootFacade = require(installedRootFacadePath)
  assert.deepEqual(installedRootFacade, sourceManifest)
  const installedRootFacadeRequire = createRequire(installedRootFacadePath)
  assert.equal(
    realpathSync(installedRootFacadeRequire.resolve("patched-zod/package.json")),
    path.join(frontendRoot, "node_modules", "patched-zod", "package.json")
  )
  const consumerFacadePath = compilerRequire.resolve("zod/package.json")
  const consumerFacade = compilerRequire(consumerFacadePath)
  const consumerFacadeRequire = createRequire(consumerFacadePath)
  assert.equal(
    realpathSync(consumerFacadePath),
    path.join(
      path.dirname(require.resolve("eslint-plugin-react-compiler/package.json")),
      "node_modules",
      "zod",
      "package.json"
    )
  )
  assert.deepEqual(consumerFacade, sourceManifest)
  const installedEnginePath = consumerFacadeRequire.resolve("patched-zod/package.json")
  const installedEngine = consumerFacadeRequire(installedEnginePath)
  assertFacadeEngineIdentity(consumerFacade, installedEngine)
  assert.equal(
    realpathSync(installedEnginePath),
    path.join(frontendRoot, "node_modules", "patched-zod", "package.json")
  )
  assert.equal(
    lstatSync(
      path.join(import.meta.dirname, "react-compiler-zod-compat", "node_modules", "patched-zod"),
      { throwIfNoEntry: false }
    ),
    undefined
  )
  assert.equal(
    Object.hasOwn(
      lock.packages,
      "node_modules/eslint-plugin-react-compiler/node_modules/zod/node_modules/patched-zod"
    ),
    false
  )
})

test("graph guards reject wrong package identities, engine versions and wider scopes", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"))
  const sourceFacadePath = require.resolve("./react-compiler-zod-compat/index.cjs")
  const sourceManifest = createRequire(sourceFacadePath)("./package.json")
  const engineManifest = createRequire(sourceFacadePath)("patched-zod/package.json")

  assert.throws(
    () => assertFacadeEngineIdentity({ ...sourceManifest, name: "zod" }, engineManifest),
    { name: "AssertionError" }
  )
  assert.throws(
    () => assertFacadeEngineIdentity(sourceManifest, { ...engineManifest, version: "3.25.76" }),
    { name: "AssertionError" }
  )

  const unscopedFacade = structuredClone(manifest)
  delete unscopedFacade.devDependencies[FACADE_NAME]
  unscopedFacade.devDependencies["react-compiler-zod-compat"] =
    "file:./scripts/react-compiler-zod-compat"
  assert.throws(() => assertCompilerOverrideScope(unscopedFacade), { name: "AssertionError" })

  const widenedOverride = structuredClone(manifest)
  delete widenedOverride.overrides[COMPILER_OVERRIDE_KEY]
  widenedOverride.overrides["eslint-plugin-react-compiler"] = {
    zod: "$" + FACADE_NAME,
  }
  assert.throws(() => assertCompilerOverrideScope(widenedOverride), { name: "AssertionError" })
})

test("compiler parity guard rejects wording changes outside the two InvalidConfig reasons", () => {
  const changedDiagnostic = structuredClone(golden.records)
  const ordinaryDiagnostic = changedDiagnostic.find(({ name }) => name === "conditional-hook")
  assert.ok(ordinaryDiagnostic.messages.length > 0)
  ordinaryDiagnostic.messages[0].message += " altered wording"
  assert.throws(() => assertRuleRecordsMatchBaseline(changedDiagnostic, golden.records), {
    name: "AssertionError",
  })

  const changedConfigReason = structuredClone(golden.records)
  const targetError = changedConfigReason.find(({ name }) => name === "target-invalid-config")
  targetError.error.message = "InvalidConfig: A different target reason."
  assert.throws(() => assertRuleRecordsMatchBaseline(changedConfigReason, golden.records), {
    name: "AssertionError",
  })
})

test("the Docker stages carry the archive and builder keeps native compiler resolution", () => {
  const dockerfile = readFileSync(new URL("../../frontend.Dockerfile", import.meta.url), "utf8")
  const fromLinesFor = (source) => [
    ...source.matchAll(
      /^[ \t]*FROM[ \t]+(?:--platform=(\S+)[ \t]+)?(\S+)[ \t]+AS[ \t]+([A-Za-z0-9_.-]+)[ \t]*\r?$/gimu
    ),
  ]
  const fromLines = fromLinesFor(dockerfile)
  assert.deepEqual(
    fromLines.map((match) => match[3].toLowerCase()),
    ["base", "wasm-builder", "deps", "builder", "prod-deps", "runtime"]
  )
  const stage = (alias) => {
    const index = fromLines.findIndex((match) => match[3].toLowerCase() === alias)
    assert.notEqual(index, -1, "Dockerfile must define the " + alias + " stage")
    const match = fromLines[index]
    return {
      platform: match[1] ?? null,
      image: match[2],
      body: dockerfile.slice(
        match.index + match[0].length,
        fromLines[index + 1]?.index ?? dockerfile.length
      ),
    }
  }
  const base = stage("base")
  const wasmBuilder = stage("wasm-builder")
  const deps = stage("deps")
  const builder = stage("builder")
  const prodDeps = stage("prod-deps")
  const runtime = stage("runtime")
  const nodeImagePin = /^node:24\.21\.0-alpine@sha256:[a-f0-9]{64}$/
  assert.match(base.image, nodeImagePin)
  assert.match(wasmBuilder.image, /^rust:1\.99\.0-slim-bookworm@sha256:[a-f0-9]{64}$/)
  assert.equal(wasmBuilder.platform, "$WASM_BUILDPLATFORM")
  assert.equal(runtime.image, base.image)
  assert.equal(deps.image, "base")
  assert.equal(builder.image, "deps")
  assert.equal(prodDeps.image, "base")

  const archiveCopy = "COPY frontend/vendor/react-compiler-zod-compat-1.0.0.tgz ./vendor/"
  assert.equal(deps.body.split(archiveCopy).length - 1, 1)
  assert.equal(prodDeps.body.split(archiveCopy).length - 1, 1)
  assert.ok(deps.body.indexOf(archiveCopy) < deps.body.indexOf("npm ci"))
  assert.ok(prodDeps.body.indexOf(archiveCopy) < prodDeps.body.indexOf("npm ci"))
  const scriptsCopy = "COPY frontend/scripts ./scripts/"
  const depsNpmCiIndex = deps.body.indexOf("until npm ci")
  assert.equal(deps.body.split(scriptsCopy).length - 1, 1)
  assert.notEqual(depsNpmCiIndex, -1, "deps stage must run npm ci")
  assert.ok(deps.body.indexOf(scriptsCopy) < depsNpmCiIndex)
  assert.match(builder.body, /COPY frontend \.\//)
  assert.equal(runtime.body.includes("react-compiler-zod-compat"), false)
  assert.equal(runtime.body.includes("eslint-plugin-react-compiler"), false)
  assert.equal(runtime.body.includes("patched-zod"), false)
  assert.equal(runtime.body.includes("vendor/react-compiler-zod-compat-1.0.0.tgz"), false)

  const baseInstruction = "FROM " + base.image + " AS base"
  const unpinnedDockerfile = dockerfile.replace(
    baseInstruction,
    "FROM " + base.image.split("@sha256:")[0] + " AS base"
  )
  assert.notEqual(unpinnedDockerfile, dockerfile)
  const unpinnedBase = fromLinesFor(unpinnedDockerfile).find((match) => match[3] === "base")
  assert.throws(() => assert.match(unpinnedBase[2], nodeImagePin), { name: "AssertionError" })
  const wrongBuilderParent = dockerfile.replace("FROM deps AS builder", "FROM base AS builder")
  assert.notEqual(wrongBuilderParent, dockerfile)
  const wrongBuilder = fromLinesFor(wrongBuilderParent).find((match) => match[3] === "builder")
  assert.throws(() => assert.equal(wrongBuilder[2], "deps"), { name: "AssertionError" })
  const target = mkdtempSync(path.join(tmpdir(), "react-compiler-builder-"))
  try {
    const sourceAdapter = path.join(import.meta.dirname, "react-compiler-zod-compat")
    const targetAdapter = path.join(target, "scripts", "react-compiler-zod-compat")
    const sourceEngine = path.join(frontendRoot, "node_modules", "patched-zod")
    const targetEngine = path.join(target, "node_modules", "patched-zod")
    const sourceFacadeManifest = require.resolve(`${FACADE_NAME}/package.json`)
    const sourceFacade = path.dirname(sourceFacadeManifest)
    const sourceCompilerManifest = require.resolve("eslint-plugin-react-compiler/package.json")
    const sourceCompiler = path.dirname(sourceCompilerManifest)
    const sourceFormatterEntry = compilerRequire.resolve("zod-validation-error")
    const sourceFormatter = path.resolve(path.dirname(sourceFormatterEntry), "..")
    const targetModules = path.join(target, "node_modules")
    const targetCompiler = path.join(targetModules, "eslint-plugin-react-compiler")
    const targetFacade = path.join(targetModules, FACADE_NAME)
    const targetFormatter = path.join(targetModules, "zod-validation-error")
    const sourceArchive = path.join(frontendRoot, "vendor", "react-compiler-zod-compat-1.0.0.tgz")
    const targetArchive = path.join(target, "vendor", "react-compiler-zod-compat-1.0.0.tgz")

    copyFileSync(path.join(frontendRoot, "package.json"), path.join(target, "package.json"))
    mkdirSync(path.dirname(targetArchive), { recursive: true })
    copyFileSync(sourceArchive, targetArchive)
    mkdirSync(path.dirname(targetAdapter), { recursive: true })
    cpSync(sourceAdapter, targetAdapter, { recursive: true })
    mkdirSync(path.join(targetModules, "@university-ecosystem"), { recursive: true })
    cpSync(sourceFacade, targetFacade, { recursive: true })
    cpSync(sourceCompiler, targetCompiler, { recursive: true })
    cpSync(sourceEngine, targetEngine, { recursive: true })
    cpSync(sourceFormatter, targetFormatter, { recursive: true })

    const copiedArchive = readFileSync(targetArchive)
    assert.equal(createHash("sha256").update(copiedArchive).digest("hex"), FACADE_SHA256)
    const targetCompilerRequire = createRequire(path.join(targetCompiler, "package.json"))
    const consumerFacadePath = targetCompilerRequire.resolve("zod/package.json")
    assert.equal(
      realpathSync(consumerFacadePath),
      path.join(targetCompiler, "node_modules", "zod", "package.json")
    )
    const consumerFacade = targetCompilerRequire(consumerFacadePath)
    const consumerFacadeRequire = createRequire(consumerFacadePath)
    const enginePath = consumerFacadeRequire.resolve("patched-zod/package.json")
    const engine = consumerFacadeRequire(enginePath)
    assertFacadeEngineIdentity(consumerFacade, engine)
    assert.equal(realpathSync(enginePath), path.join(targetEngine, "package.json"))
    assert.equal(
      realpathSync(targetCompilerRequire.resolve("zod-validation-error")),
      path.join(targetFormatter, "v4", "index.js")
    )
    assert.equal(
      createHash("sha256")
        .update(readFileSync(path.join(targetCompiler, "dist", "index.js")))
        .digest("hex"),
      golden.compilerBundleSha256
    )
    assert.deepEqual(
      readFileSync(path.join(targetAdapter, "package.json")),
      readFileSync(path.join(sourceAdapter, "package.json"))
    )

    const transferred = createRequire(path.join(targetFacade, "package.json"))("./index.cjs")
    verifyProvider(transferred.z)
    verifyMapDefaults(transferred.z)
  } finally {
    rmSync(target, { recursive: true, force: true })
  }
})
