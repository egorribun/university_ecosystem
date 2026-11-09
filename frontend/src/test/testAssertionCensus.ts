// AUD-428 (TypeScript part): classification logic for the test-result census. A test
// block must perform a result check, directly or through a helper it calls, and a helper
// may live in the same file or in another frontend module reached by a named import.
// The sources are parsed with the TypeScript compiler API so that a string match or a
// comment cannot satisfy the census.
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import ts from "typescript"

export const CENSUS_ROOTS = ["src", "tests", "scripts"] as const
const TEST_FILE = /\.(?:test|spec)\.(?:ts|tsx|mjs|js)$/u
export const ASSERTION_ROOTS: ReadonlySet<string> = new Set([
  "expect",
  "expectTypeOf",
  "assertType",
  "assert",
  "withExpectedConsole",
])
const EXPECTATION_MATCHERS: ReadonlySet<string> = new Set([
  "toBe",
  "toBeAttached",
  "toBeChecked",
  "toBeCloseTo",
  "toBeDefined",
  "toBeDisabled",
  "toBeEmptyDOMElement",
  "toBeEnabled",
  "toBeFalsy",
  "toBeFocused",
  "toBeGreaterThan",
  "toBeGreaterThanOrEqual",
  "toBeHidden",
  "toBeInTheDocument",
  "toBeInViewport",
  "toBeInstanceOf",
  "toBeLessThan",
  "toBeLessThanOrEqual",
  "toBeNull",
  "toBeTruthy",
  "toBeTypeOf",
  "toBeUndefined",
  "toBeVisible",
  "toContain",
  "toContainElement",
  "toContainEqual",
  "toContainHTML",
  "toContainText",
  "toEqual",
  "toEqualTypeOf",
  "toHaveAccessibleDescription",
  "toHaveAccessibleName",
  "toHaveAttribute",
  "toHaveBeenCalled",
  "toHaveBeenCalledExactlyOnceWith",
  "toHaveBeenCalledOnce",
  "toHaveBeenCalledTimes",
  "toHaveBeenCalledWith",
  "toHaveBeenLastCalledWith",
  "toHaveBeenNthCalledWith",
  "toHaveClass",
  "toHaveCount",
  "toHaveCSS",
  "toHaveFocus",
  "toHaveLength",
  "toHaveNoViolations",
  "toHaveProperty",
  "toHaveReturnedWith",
  "toHaveScreenshot",
  "toHaveStyle",
  "toHaveText",
  "toHaveTextContent",
  "toHaveURL",
  "toHaveValue",
  "toMatch",
  "toMatchObject",
  "toMatchSnapshot",
  "toMatchTypeOf",
  "toPass",
  "toSatisfy",
  "toStrictEqual",
  "toThrow",
  "toThrowError",
])
const TEST_BLOCK_ROOTS: ReadonlySet<string> = new Set(["it", "test"])
const EXECUTED_TEST_MODIFIERS: ReadonlySet<string> = new Set([
  "only",
  "concurrent",
  "sequential",
  "fails",
  "each",
  "skipIf",
  "runIf",
])
const TEST_MODIFIER_FACTORIES: ReadonlySet<string> = new Set(["each", "skipIf", "runIf"])
const NON_EXECUTED_TEST_MODIFIERS: ReadonlySet<string> = new Set(["skip", "todo"])
const GROUP_OR_HOOK_MODIFIERS: ReadonlySet<string> = new Set([
  "describe",
  "context",
  "beforeAll",
  "beforeEach",
  "afterAll",
  "afterEach",
])
const NON_BLOCK_TEST_MODIFIERS: ReadonlySet<string> = new Set([
  ...GROUP_OR_HOOK_MODIFIERS,
  "use",
  "extend",
  "setTimeout",
  "slow",
  "fail",
  "fixme",
  "info",
  "step",
  "expect",
])

export function parseTypeScript(path: string, text: string): ts.SourceFile {
  const kind = path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  return ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, kind)
}

function parserDiagnosticOffsets(source: ts.SourceFile): readonly number[] | undefined {
  // The pinned compiler exposes this at runtime, but its public SourceFile type
  // does not. Fail closed if the diagnostic positions are no longer readable.
  const diagnostics: unknown = (source as ts.SourceFile & { readonly parseDiagnostics?: unknown })
    .parseDiagnostics
  if (!Array.isArray(diagnostics)) return undefined
  const entries: readonly unknown[] = diagnostics
  const offsets: number[] = []
  for (const entry of entries) {
    if (typeof entry !== "object" || entry === null) return undefined
    const start = "start" in entry ? entry.start : undefined
    if (start === undefined) offsets.push(0)
    else if (
      typeof start === "number" &&
      Number.isInteger(start) &&
      start >= 0 &&
      start <= source.end
    ) {
      offsets.push(start)
    } else return undefined
  }
  return offsets
}

export function testFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    if (entry === "node_modules" || entry === "dist" || entry === "coverage") return []
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return testFiles(path)
    return TEST_FILE.test(entry) ? [path] : []
  })
}

export function rootIdentifier(expression: ts.Expression): string | undefined {
  let current: ts.Expression = expression
  while (true) {
    if (ts.isIdentifier(current)) return current.text
    if (ts.isPropertyAccessExpression(current) || ts.isElementAccessExpression(current)) {
      current = current.expression
      continue
    }
    if (ts.isCallExpression(current)) {
      current = current.expression
      continue
    }
    return undefined
  }
}

export function isFunctionLike(node: ts.Node | undefined): node is ts.FunctionLikeDeclaration {
  return (
    node !== undefined &&
    (ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node))
  )
}

export type TestCallback = ts.FunctionLikeDeclaration | ts.Identifier

// A test block is a call of `it` or `test` (or their `.each` table form, or `.only`) whose
// callback is the last function argument. Hooks and grouping calls such as `test.beforeEach`
// and `test.describe` are not test blocks; skipped and todo blocks are not executed.
export function isTestCallee(expression: ts.Expression): boolean {
  if (ts.isPropertyAccessExpression(expression) && expression.name.text === "each") return false
  const { root, modifiers } = testCalleeParts(expression)
  return root !== undefined && modifiers.every((modifier) => EXECUTED_TEST_MODIFIERS.has(modifier))
}

function testCalleeParts(expression: ts.Expression): {
  root: string | undefined
  modifiers: string[]
} {
  const modifiers: string[] = []
  const visit = (current: ts.Expression): string | undefined => {
    if (ts.isIdentifier(current))
      return TEST_BLOCK_ROOTS.has(current.text) ? current.text : undefined
    if (ts.isPropertyAccessExpression(current)) {
      modifiers.unshift(current.name.text)
      return visit(current.expression)
    }
    if (ts.isElementAccessExpression(current)) {
      modifiers.unshift("<element-access>")
      return visit(current.expression)
    }
    if (ts.isCallExpression(current)) return visit(current.expression)
    return undefined
  }
  return { root: visit(expression), modifiers }
}

function isNonExecutedTest(expression: ts.Expression): boolean {
  const { root, modifiers } = testCalleeParts(expression)
  return (
    root !== undefined && modifiers.some((modifier) => NON_EXECUTED_TEST_MODIFIERS.has(modifier))
  )
}

function looksLikeUnsupportedTestCall(call: ts.CallExpression): boolean {
  const { root, modifiers } = testCalleeParts(call.expression)
  const factoryOnly =
    ts.isPropertyAccessExpression(call.expression) &&
    TEST_MODIFIER_FACTORIES.has(call.expression.name.text)
  const isNonBlockCall = modifiers.some((modifier) => NON_BLOCK_TEST_MODIFIERS.has(modifier))
  return (
    root !== undefined &&
    !factoryOnly &&
    !isNonBlockCall &&
    !isNonExecutedTest(call.expression) &&
    (!modifiers.every((modifier) => EXECUTED_TEST_MODIFIERS.has(modifier)) ||
      testCallback(call) === undefined) &&
    call.arguments.length > 0
  )
}

export function testCallback(call: ts.CallExpression): TestCallback | undefined {
  if (
    !isTestCallee(call.expression) ||
    (ts.isPropertyAccessExpression(call.expression) &&
      TEST_MODIFIER_FACTORIES.has(call.expression.name.text))
  ) {
    return undefined
  }
  for (let index = call.arguments.length - 1; index >= 0; index -= 1) {
    const candidate = call.arguments[index]
    if (candidate !== undefined && (isFunctionLike(candidate) || ts.isIdentifier(candidate))) {
      return candidate
    }
  }
  return undefined
}

export function collectFunctionBodies(source: ts.SourceFile): Map<string, ts.Node> {
  const bodies = new Map<string, ts.Node>()
  const visit = (node: ts.Node) => {
    if (ts.isFunctionDeclaration(node) && node.name && node.body) {
      bodies.set(node.name.text, node.body)
    }
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.initializer &&
      isFunctionLike(node.initializer)
    ) {
      bodies.set(node.name.text, node.initializer)
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
  return bodies
}

// The subject of `expect(...)` reached through a matcher chain such as `.not`, if any.
function expectationSubject(call: ts.CallExpression): ts.Expression | undefined {
  let current: ts.Expression = call.expression
  while (ts.isPropertyAccessExpression(current)) current = current.expression
  if (
    ts.isCallExpression(current) &&
    ts.isIdentifier(current.expression) &&
    current.expression.text === "expect"
  ) {
    return current.arguments[0]
  }
  return undefined
}

function isConstantTruthValue(node: ts.Expression): boolean {
  return (
    node.kind === ts.SyntaxKind.TrueKeyword ||
    node.kind === ts.SyntaxKind.FalseKeyword ||
    node.kind === ts.SyntaxKind.NullKeyword
  )
}

function isConstantOperand(node: ts.Expression): boolean {
  return (
    isConstantTruthValue(node) ||
    ts.isStringLiteral(node) ||
    ts.isNoSubstitutionTemplateLiteral(node) ||
    ts.isNumericLiteral(node) ||
    (ts.isIdentifier(node) && node.text === "undefined")
  )
}

// `expect(true).toBe(true)` and similar checks compare a constant with constants. They
// cannot fail on the code under test, so they are not result checks. A constant subject
// compared with a computed value, or a computed subject, is still a result check.
function isTautologicalExpectation(call: ts.CallExpression): boolean {
  const subject = expectationSubject(call)
  return (
    subject !== undefined &&
    isConstantTruthValue(subject) &&
    call.arguments.every((argument) => isConstantOperand(argument))
  )
}

export function containsAssertion(node: ts.Node, helpers: ReadonlySet<string>): boolean {
  const branchThrowsError = (statement: ts.Statement): boolean => {
    let foundErrorThrow = false
    const findThrow = (child: ts.Node) => {
      if (foundErrorThrow) return
      if (
        ts.isThrowStatement(child) &&
        ts.isNewExpression(child.expression) &&
        rootIdentifier(child.expression.expression)?.endsWith("Error")
      ) {
        foundErrorThrow = true
        return
      }
      if (child !== statement && isFunctionLike(child)) return
      ts.forEachChild(child, findThrow)
    }
    findThrow(statement)
    return foundErrorThrow
  }

  let found = false
  const visit = (child: ts.Node) => {
    if (found) return
    if (
      child !== node &&
      (ts.isFunctionDeclaration(child) ||
        (isFunctionLike(child) &&
          ts.isVariableDeclaration(child.parent) &&
          child.parent.initializer === child))
    ) {
      return
    }
    if (
      ts.isIfStatement(child) &&
      (branchThrowsError(child.thenStatement) ||
        (child.elseStatement !== undefined && branchThrowsError(child.elseStatement)))
    ) {
      found = true
      return
    }
    if (ts.isCallExpression(child)) {
      const root = rootIdentifier(child.expression)
      const isExpectationMatcher =
        (root === "expect" || root === "expectTypeOf") &&
        ts.isPropertyAccessExpression(child.expression) &&
        EXPECTATION_MATCHERS.has(child.expression.name.text) &&
        !isTautologicalExpectation(child)
      if (
        root !== undefined &&
        (isExpectationMatcher ||
          (ASSERTION_ROOTS.has(root) && root !== "expect" && root !== "expectTypeOf") ||
          helpers.has(root))
      ) {
        found = true
        return
      }
    }
    ts.forEachChild(child, visit)
  }
  visit(node)
  return found
}

function isFile(candidate: string): boolean {
  try {
    return statSync(candidate).isFile()
  } catch {
    return false
  }
}

// Resolves a relative specifier or the `@/` alias (frontend/src) to an existing file.
// Bare package specifiers are not frontend helpers and resolve to undefined.
export function resolveModule(
  frontendRoot: string,
  fromPath: string,
  specifier: string
): string | undefined {
  let base: string
  if (specifier.startsWith(".")) base = resolve(join(fromPath, ".."), specifier)
  else if (specifier.startsWith("@/")) base = join(frontendRoot, "src", specifier.slice(2))
  else return undefined
  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    `${base}.mjs`,
    `${base}.js`,
    join(base, "index.ts"),
    join(base, "index.tsx"),
  ]
  return candidates.find(isFile)
}

export function repoRelative(frontendRoot: string, path: string): string {
  return relative(frontendRoot, path).replaceAll("\\", "/")
}

export interface AssertionCensus {
  readonly frontendRoot: string
  fileHelpers(source: ts.SourceFile, path: string): Set<string>
  moduleHelpers(path: string): Set<string>
  unassertedTests(path: string): string[]
  run(roots?: readonly string[]): {
    files: number
    blocks: number
    flagged: string[]
    unsupported: string[]
  }
}

// Creates a census bound to one frontend root. The helper memo lives on the instance so
// each census run sees the current files and no state leaks between runs.
export function createAssertionCensus(frontendRoot: string): AssertionCensus {
  const moduleMemo = new Map<string, Set<string>>()

  function importedAssertingHelpers(source: ts.SourceFile, path: string): Set<string> {
    const names = new Set<string>()
    for (const statement of source.statements) {
      if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) {
        continue
      }
      const bindings = statement.importClause?.namedBindings
      if (!bindings || !ts.isNamedImports(bindings)) continue
      const target = resolveModule(frontendRoot, path, statement.moduleSpecifier.text)
      if (target === undefined) continue
      const exported = moduleHelpers(target)
      for (const element of bindings.elements) {
        const original = (element.propertyName ?? element.name).text
        if (exported.has(original)) names.add(element.name.text)
      }
    }
    return names
  }

  function fileHelpers(source: ts.SourceFile, path: string): Set<string> {
    const helpers = importedAssertingHelpers(source, path)
    const bodies = collectFunctionBodies(source)
    let changed = true
    while (changed) {
      changed = false
      for (const [name, body] of bodies) {
        if (!helpers.has(name) && containsAssertion(body, helpers)) {
          helpers.add(name)
          changed = true
        }
      }
      const arrays = new Map<string, ts.ArrayLiteralExpression>()
      const collectArrays = (node: ts.Node) => {
        if (
          ts.isVariableDeclaration(node) &&
          ts.isIdentifier(node.name) &&
          node.initializer !== undefined &&
          ts.isArrayLiteralExpression(node.initializer)
        ) {
          arrays.set(node.name.text, node.initializer)
        }
        ts.forEachChild(node, collectArrays)
      }
      collectArrays(source)
      const collectAssertioningLoopBindings = (node: ts.Node) => {
        if (ts.isForOfStatement(node) && ts.isVariableDeclarationList(node.initializer)) {
          const [declaration] = node.initializer.declarations
          const rows = ts.isIdentifier(node.expression)
            ? arrays.get(node.expression.text)
            : ts.isArrayLiteralExpression(node.expression)
              ? node.expression
              : undefined
          if (
            declaration &&
            ts.isArrayBindingPattern(declaration.name) &&
            rows !== undefined &&
            rows.elements.length > 0
          ) {
            declaration.name.elements.forEach((binding, index) => {
              if (!ts.isBindingElement(binding) || !ts.isIdentifier(binding.name)) return
              const everyRowChecks = rows.elements.every((row) => {
                if (!ts.isArrayLiteralExpression(row)) return false
                const value = row.elements[index]
                return value !== undefined && ts.isIdentifier(value) && helpers.has(value.text)
              })
              if (everyRowChecks && !helpers.has(binding.name.text)) {
                helpers.add(binding.name.text)
                changed = true
              }
            })
          }
        }
        ts.forEachChild(node, collectAssertioningLoopBindings)
      }
      collectAssertioningLoopBindings(source)
    }
    return helpers
  }

  function moduleHelpers(path: string): Set<string> {
    const memoized = moduleMemo.get(path)
    if (memoized !== undefined) return memoized
    // Cycle guard: a module that imports itself transitively sees an empty set.
    moduleMemo.set(path, new Set())
    const source = parseTypeScript(path, readFileSync(path, "utf8"))
    const helpers = fileHelpers(source, path)
    moduleMemo.set(path, helpers)
    return helpers
  }

  function censusFile(path: string): { blocks: number; flagged: string[]; unsupported: string[] } {
    const source = parseTypeScript(path, readFileSync(path, "utf8"))
    const offsets = parserDiagnosticOffsets(source)
    if (offsets === undefined) {
      return {
        blocks: 0,
        flagged: [],
        unsupported: [
          `${repoRelative(frontendRoot, path)}:1: unsupported parser diagnostics shape`,
        ],
      }
    }
    if (offsets.length > 0) {
      const unsupported = offsets.map((offset) => {
        const { line } = source.getLineAndCharacterOfPosition(offset)
        return `${repoRelative(frontendRoot, path)}:${line + 1}: parse diagnostic`
      })
      return { blocks: 0, flagged: [], unsupported }
    }
    const helpers = fileHelpers(source, path)
    const flagged: string[] = []
    const unsupported: string[] = []
    let blocks = 0
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node)) {
        const callback = testCallback(node)
        if (callback) {
          blocks += 1
          const hasResultCheck = ts.isIdentifier(callback)
            ? helpers.has(callback.text)
            : containsAssertion(callback, helpers)
          if (!hasResultCheck) {
            const { line } = source.getLineAndCharacterOfPosition(node.getStart(source))
            flagged.push(`${repoRelative(frontendRoot, path)}:${line + 1}`)
          }
        } else if (looksLikeUnsupportedTestCall(node)) {
          const { line } = source.getLineAndCharacterOfPosition(node.getStart(source))
          unsupported.push(
            `${repoRelative(frontendRoot, path)}:${line + 1}: unsupported test-call form`
          )
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(source)
    return { blocks, flagged, unsupported }
  }

  function unassertedTests(path: string): string[] {
    return censusFile(path).flagged
  }

  function run(roots: readonly string[] = CENSUS_ROOTS) {
    const files = roots.flatMap((root) => {
      const directory = join(frontendRoot, root)
      return isFile(directory) ? [] : testFiles(directory)
    })
    const reports = files.map(censusFile)
    return {
      files: files.length,
      blocks: reports.reduce((total, report) => total + report.blocks, 0),
      flagged: reports.flatMap((report) => report.flagged),
      unsupported: reports.flatMap((report) => report.unsupported),
    }
  }

  return { frontendRoot, fileHelpers, moduleHelpers, unassertedTests, run }
}
