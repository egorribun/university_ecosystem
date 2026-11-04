// AUD-428 (TypeScript part): unit tests for the census classification and the whole-repo
// census assertion. The logic lives in src/test/testAssertionCensus.ts.
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import ts from "typescript"
import { beforeAll, describe, expect, it } from "vitest"
import {
  ASSERTION_ROOTS,
  collectFunctionBodies,
  containsAssertion,
  createAssertionCensus,
  isFunctionLike,
  isTestCallee,
  parseTypeScript,
  repoRelative,
  resolveModule,
  rootIdentifier,
  testCallback,
  testFiles,
} from "../testAssertionCensus"

// npm runs vitest from the frontend package root; the census walks its test sources.
const FRONTEND_ROOT = resolve(process.cwd())
const FIXTURE_PATH = join(FRONTEND_ROOT, "src", "test", "__tests__", "census-fixture.test.ts")

function callsOf(source: ts.SourceFile): ts.CallExpression[] {
  const calls: ts.CallExpression[] = []
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node)) calls.push(node)
    ts.forEachChild(node, visit)
  }
  visit(source)
  return calls
}

function expressionOf(code: string): ts.Expression {
  const statement = parseTypeScript("expr.ts", code).statements[0]
  if (!statement || !ts.isExpressionStatement(statement)) throw new Error("expected expression")
  return statement.expression
}

function callOf(code: string): ts.CallExpression {
  const expression = expressionOf(code)
  if (!ts.isCallExpression(expression)) throw new Error("expected call")
  return expression
}

describe("census classification", () => {
  it("resolves the root identifier through member, element and call chains", () => {
    expect(rootIdentifier(expressionOf("expect(1).resolves.toBe"))).toBe("expect")
    expect(rootIdentifier(expressionOf("a['b'].c"))).toBe("a")
    expect(rootIdentifier(expressionOf("1 + 1"))).toBeUndefined()
  })

  it("recognises function-like nodes and rejects other values", () => {
    const source = parseTypeScript("f.ts", "const a = () => 1; const b = function () {}; 2")
    const initializers = callsOf(source)
    expect(initializers).toHaveLength(0)
    const arrow = source.statements[0]
    if (!arrow || !ts.isVariableStatement(arrow)) throw new Error("expected declaration")
    const declaration = arrow.declarationList.declarations[0]
    expect(isFunctionLike(declaration?.initializer)).toBe(true)
    expect(isFunctionLike(undefined)).toBe(false)
    expect(isFunctionLike(expressionOf("2"))).toBe(false)
  })

  it.each([
    ["it('n', () => {})", true],
    ["test('n', () => {})", true],
    // Built at runtime: the repository's focus-marker scan matches the literal suffix.
    [`it.${["o", "nly"].join("")}('n', () => {})`, true],
    ["it.each([1])('n', () => {})", true],
    ["test.each([1])('n', () => {})", true],
    ["test.beforeEach(() => {})", false],
    ["test.describe('g', () => {})", false],
    ["it.skip('n', () => {})", false],
    ["other('n', () => {})", false],
    ["other.each([1])('n', () => {})", false],
    ["it.each([1])", false],
  ])("classifies %s as a test block: %s", (code, expected) => {
    const call = callOf(code)
    expect(isTestCallee(call.expression)).toBe(expected)
  })

  it("returns the callback only for a test block with a trailing function", () => {
    expect(testCallback(callOf("it('n', () => {})"))).toBeDefined()
    expect(testCallback(callOf("it('n', 'not a function')"))).toBeUndefined()
    expect(testCallback(callOf("test.beforeEach(() => {})"))).toBeUndefined()
  })

  it("collects function declarations and function-valued variables by name", () => {
    const source = parseTypeScript(
      "bodies.ts",
      [
        "function named() { return 1 }",
        "const arrow = () => 2",
        "const value = 3",
        "const notFn = 4",
        "let pending",
        "const [first] = [1]",
        "export default function () { return 5 }",
        "declare function declared(): void",
      ].join("\n")
    )
    expect([...collectFunctionBodies(source).keys()].sort()).toStrictEqual(["arrow", "named"])
  })

  it("finds an assertion root, an assert-prefixed call and a known helper", () => {
    const body = (code: string) => {
      const source = parseTypeScript("c.ts", `const f = () => { ${code} }`)
      return collectFunctionBodies(source).get("f")!
    }
    expect(containsAssertion(body("expect(1).toBe(1)"), new Set())).toBe(true)
    expect(containsAssertion(body("assertType<number>(1)"), new Set())).toBe(true)
    expect(containsAssertion(body("assert.ok(true)"), new Set())).toBe(true)
    expect(containsAssertion(body("checkThing(1)"), new Set(["checkThing"]))).toBe(true)
    expect(containsAssertion(body("checkThing(1)"), new Set())).toBe(false)
    expect(containsAssertion(body("expect(1).toBe(1); expect(2).toBe(2)"), new Set())).toBe(true)
    expect(containsAssertion(body("const value = 1"), new Set())).toBe(false)
    expect(ASSERTION_ROOTS.has("withExpectedConsole")).toBe(true)
  })

  it("resolves relative, alias and index module specifiers and rejects package names", () => {
    const fromPath = FIXTURE_PATH
    expect(resolveModule(FRONTEND_ROOT, fromPath, "../testAssertionCensus")).toBe(
      join(FRONTEND_ROOT, "src", "test", "testAssertionCensus.ts")
    )
    expect(resolveModule(FRONTEND_ROOT, fromPath, "@/test/testAssertionCensus")).toBe(
      join(FRONTEND_ROOT, "src", "test", "testAssertionCensus.ts")
    )
    expect(resolveModule(FRONTEND_ROOT, fromPath, "@/tests/helpers/expectInlineBackground")).toBe(
      join(FRONTEND_ROOT, "src", "tests", "helpers", "expectInlineBackground.ts")
    )
    expect(resolveModule(FRONTEND_ROOT, fromPath, "@/tests/helpers")).toBeUndefined()
    expect(resolveModule(FRONTEND_ROOT, fromPath, "./does-not-exist")).toBeUndefined()
    expect(resolveModule(FRONTEND_ROOT, fromPath, "typescript")).toBeUndefined()
  })

  it("lists test sources and renders repository-relative locations with forward slashes", () => {
    const files = testFiles(join(FRONTEND_ROOT, "src", "test"))
    expect(files).toContain(
      join(FRONTEND_ROOT, "src", "test", "__tests__", "testAssertionCensus.test.ts")
    )
    expect(repoRelative(FRONTEND_ROOT, join(FRONTEND_ROOT, "src", "a", "b.ts"))).toBe("src/a/b.ts")
    expect(callsOf(parseTypeScript("x.ts", "f()"))).toHaveLength(1)
  })
})

describe("census helper resolution across modules", () => {
  it("counts a named import of an asserting helper from another module", () => {
    const census = createAssertionCensus(FRONTEND_ROOT)
    const source = parseTypeScript(
      FIXTURE_PATH,
      [
        'import { expectInlineBackground } from "@/tests/helpers/expectInlineBackground"',
        "it('uses the imported assertion', () => { expectInlineBackground(el, 'x') })",
      ].join("\n")
    )
    const helpers = census.fileHelpers(source, FIXTURE_PATH)
    expect(helpers.has("expectInlineBackground")).toBe(true)
    // Import shapes that bind no named helper must be ignored, not mistaken for one.
    const shapes = parseTypeScript(
      FIXTURE_PATH,
      [
        'import "@/tests/helpers/expectInlineBackground"',
        'import * as everything from "@/tests/helpers/expectInlineBackground"',
        'import fallback from "@/tests/helpers/expectInlineBackground"',
        'import { expectInlineBackground as bound } from "@/tests/helpers/expectInlineBackground"',
        "it('uses the aliased import', () => { bound(el, 'x') })",
      ].join("\n")
    )
    expect(census.fileHelpers(shapes, FIXTURE_PATH).has("bound")).toBe(true)
    expect(census.fileHelpers(shapes, FIXTURE_PATH).has("everything")).toBe(false)
    const [block] = callsOf(source).filter((call) => testCallback(call) !== undefined)
    expect(containsAssertion(testCallback(block!)!, helpers)).toBe(true)
  })

  it("flags a test block whose callback performs no result check and ignores hooks and skips", () => {
    const census = createAssertionCensus(FRONTEND_ROOT)
    const source = parseTypeScript(
      FIXTURE_PATH,
      [
        "const check = (value: number) => { expect(value).toBe(1) }",
        "it('asserts directly', () => { expect(1).toBe(1) })",
        "it('asserts through a helper', () => { check(1) })",
        "it('asserts nothing', () => { const value = 1 + 1; void value })",
        "it.skip('is not executed', () => { void 0 })",
        "test.beforeEach(() => { void 0 })",
      ].join("\n")
    )
    const helpers = census.fileHelpers(source, FIXTURE_PATH)
    const names: string[] = []
    for (const call of callsOf(source)) {
      const callback = testCallback(call)
      if (callback && !containsAssertion(callback, helpers)) {
        const label = call.arguments[0]
        if (label && ts.isStringLiteral(label)) names.push(label.text)
      }
    }
    expect(names).toStrictEqual(["asserts nothing"])
  })

  it("memoises module helper sets and reuses the same answer on a second query", () => {
    const census = createAssertionCensus(FRONTEND_ROOT)
    const helpersPath = join(FRONTEND_ROOT, "src", "tests", "helpers", "expectInlineBackground.ts")
    const first = census.moduleHelpers(helpersPath)
    expect(census.moduleHelpers(helpersPath)).toBe(first)
    expect(first.has("expectInlineBackground")).toBe(true)
  })
})

describe("census on temporary repositories", () => {
  it("collects test sources recursively and skips dependency and build output folders", () => {
    const root = mkdtempSync(join(tmpdir(), "census-walk-"))
    for (const folder of ["nested", "node_modules", "dist", "coverage"]) {
      mkdirSync(join(root, folder), { recursive: true })
    }
    writeFileSync(join(root, "nested", "deep.spec.ts"), "")
    writeFileSync(join(root, "nested", "module.mjs"), "")
    writeFileSync(join(root, "nested", "plain.ts"), "")
    writeFileSync(join(root, "node_modules", "skip.test.ts"), "")
    writeFileSync(join(root, "dist", "skip.test.ts"), "")
    writeFileSync(join(root, "coverage", "skip.test.ts"), "")
    const names = testFiles(root).map((path) => path.slice(root.length + 1).replaceAll("\\", "/"))
    expect(names.sort()).toStrictEqual(["nested/deep.spec.ts"])
  })

  it("reports the file and line of a test block with no result check", () => {
    const root = mkdtempSync(join(tmpdir(), "census-"))
    mkdirSync(join(root, "src"))
    const path = join(root, "src", "unchecked.test.ts")
    writeFileSync(path, "it('does nothing', () => {\n  const value = 1\n  void value\n})\n")
    const census = createAssertionCensus(root)
    expect(census.unassertedTests(path)).toStrictEqual(["src/unchecked.test.ts:1"])
    expect(census.run()).toStrictEqual({
      files: 1,
      flagged: ["src/unchecked.test.ts:1"],
    })
  })

  it("treats a missing census root as an empty source tree", () => {
    const root = mkdtempSync(join(tmpdir(), "census-empty-"))
    expect(createAssertionCensus(root).run()).toStrictEqual({ files: 0, flagged: [] })
  })
})

describe("AUD-428 TypeScript test result census", () => {
  // One whole-repository parse is shared by both assertions. It takes about
  // 30 s on a coverage-instrumented CI shard, so the hook gets its own budget
  // instead of re-parsing every source inside each 20 s test.
  const WHOLE_REPO_CENSUS_TIMEOUT_MS = 180_000
  let result: ReturnType<ReturnType<typeof createAssertionCensus>["run"]>

  beforeAll(() => {
    result = createAssertionCensus(FRONTEND_ROOT).run()
  }, WHOLE_REPO_CENSUS_TIMEOUT_MS)

  it("finds the frontend test sources", () => {
    expect(result.files).toBeGreaterThan(500)
  })

  it("has no unasserted test block in frontend test sources", () => {
    expect(result.flagged).toStrictEqual([])
  })
})
