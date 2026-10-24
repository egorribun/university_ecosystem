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
const legacy = compilerRequire("zod").z
const ruleId = "react-compiler/react-compiler"
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"))
const golden = JSON.parse(
  readFileSync(new URL("./react-compiler-zod-compat/legacy-baseline.json", import.meta.url), "utf8")
)

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

test("the installed rc.2 still matches the reviewed pre-override baseline", async () => {
  assert.equal(require("eslint-plugin-react-compiler/package.json").version, "19.1.0-rc.2")
  assert.equal(compilerRequire("zod/package.json").version, "3.25.76")
  assert.equal(lock.packages["node_modules/eslint-plugin-react-compiler"].version, "19.1.0-rc.2")
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
  const persisted = JSON.parse(serialized)
  for (const key of [
    "compilerVersion",
    "compilerIntegrity",
    "compilerBundleSha256",
    "schemaVersionInstalled",
    "formatterEntrySha256",
    "records",
    "schemaErrors",
  ]) {
    assert.deepEqual(persisted[key], golden[key], key)
  }
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

test("the isolated unchanged rc.2 rule retains every compiler diagnostic", async () => {
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
    const configurationChanges = []
    assert.equal(records.length, golden.records.length)
    for (const [index, record] of records.entries()) {
      const expected = golden.records[index]
      assert.equal(record.name, expected.name)
      if (["provider-invalid-config", "target-invalid-config"].includes(record.name)) {
        assert.equal(record.error?.name, "ReactCompilerError", record.name)
        const reason =
          record.name === "provider-invalid-config"
            ? "InvalidConfig: Error in validating environment config."
            : "InvalidConfig: Not a valid target."
        assert.equal(record.error.message.startsWith(reason), true, record.name)
        configurationChanges.push({
          name: record.name,
          before: expected.error,
          after: record.error,
        })
      } else {
        assert.deepEqual(record, expected, record.name)
      }
    }
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

test("the staged adapter engine is pinned, honestly named and development-only", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"))
  assert.equal(
    manifest.devDependencies["react-compiler-zod-compat"],
    "file:./scripts/react-compiler-zod-compat"
  )
  for (const section of ["dependencies", "optionalDependencies", "peerDependencies"]) {
    assert.equal(Object.hasOwn(manifest[section] ?? {}, "react-compiler-zod-compat"), false)
  }
  const adapterPath = require.resolve("./react-compiler-zod-compat/index.cjs")
  const adapterRequire = createRequire(adapterPath)
  const localManifest = adapterRequire("./package.json")
  assert.equal(localManifest.name, "@university-ecosystem/react-compiler-zod-compat")
  assert.deepEqual(localManifest.dependencies, { "patched-zod": "npm:zod@4.6.7" })
  assert.equal(localManifest.scripts, undefined)
  assert.equal(require("react-compiler-zod-compat"), adapter)
  assert.equal(
    realpathSync(adapterRequire.resolve("patched-zod/package.json")),
    path.join(frontendRoot, "node_modules", "patched-zod", "package.json")
  )
  const nestedEngine = path.join(
    import.meta.dirname,
    "react-compiler-zod-compat",
    "node_modules",
    "patched-zod"
  )
  assert.equal(lstatSync(nestedEngine, { throwIfNoEntry: false }), undefined)
  const engine = adapterRequire("patched-zod/package.json")
  assert.equal(engine.name, "zod")
  assert.equal(engine.version, "4.6.7")
  const local = lock.packages["scripts/react-compiler-zod-compat"]
  const alias = lock.packages["node_modules/patched-zod"]
  assert.equal(
    Object.hasOwn(lock.packages, "scripts/react-compiler-zod-compat/node_modules/patched-zod"),
    false
  )
  assert.equal(local.dev, true)
  assert.equal(alias.dev, true)
  assert.equal(alias.name, "zod")
  for (const key of ["version", "resolved", "integrity"]) {
    assert.equal(alias[key], lock.packages["node_modules/zod"][key], key)
  }
  // This stage does not route the real compiler through the adapter yet.
  assert.notEqual(compilerRequire.resolve("zod"), adapterPath)
  assert.equal(compilerRequire("zod/package.json").version, "3.25.76")
})

test("the Docker builder transfer preserves the observed hoisted engine", () => {
  const dockerfile = readFileSync(new URL("../../frontend.Dockerfile", import.meta.url), "utf8")
  const builder = dockerfile.split("FROM base AS builder")[1].split("FROM base AS prod-deps")[0]
  assert.match(
    builder,
    /COPY --from=deps \/app\/scripts\/react-compiler-zod-compat \.\/scripts\/react-compiler-zod-compat/
  )
  assert.match(builder, /COPY --from=deps \/app\/node_modules \.\/node_modules/)
  const runtime = dockerfile.split(" AS runtime")[1]
  assert.equal(runtime.includes("react-compiler-zod-compat"), false)
  const target = mkdtempSync(path.join(tmpdir(), "react-compiler-builder-"))
  try {
    const sourceAdapter = path.join(import.meta.dirname, "react-compiler-zod-compat")
    const targetAdapter = path.join(target, "scripts", "react-compiler-zod-compat")
    const sourceEngine = path.join(frontendRoot, "node_modules", "patched-zod")
    const targetEngine = path.join(target, "node_modules", "patched-zod")
    assert.equal(realpathSync(sourceEngine), sourceEngine)
    mkdirSync(path.join(target, "node_modules"), { recursive: true })
    cpSync(sourceEngine, targetEngine, { recursive: true })
    cpSync(sourceAdapter, targetAdapter, { recursive: true })
    symlinkSync(
      targetAdapter,
      path.join(target, "node_modules", "react-compiler-zod-compat"),
      "junction"
    )
    cpSync(sourceAdapter, targetAdapter, {
      recursive: true,
      filter: (entry) => !entry.split(path.sep).includes("node_modules"),
    })
    const builderRequire = createRequire(path.join(target, "package.json"))
    const copiedAdapterPath = builderRequire.resolve("react-compiler-zod-compat")
    const copiedRequire = createRequire(copiedAdapterPath)
    for (const name of ["patched-zod", "patched-zod/package.json"]) {
      const relative = path.relative(
        realpathSync(targetEngine),
        realpathSync(copiedRequire.resolve(name))
      )
      assert.notEqual(relative, "", name)
      assert.equal(relative.split(path.sep).includes(".."), false, name)
      assert.equal(path.isAbsolute(relative), false, name)
    }
    const engine = copiedRequire("patched-zod/package.json")
    assert.equal(engine.name, "zod")
    assert.equal(engine.version, "4.6.7")
    const copied = builderRequire("react-compiler-zod-compat")
    verifyProvider(copied.z)
    verifyMapDefaults(copied.z)
  } finally {
    rmSync(target, { recursive: true, force: true })
  }
})
