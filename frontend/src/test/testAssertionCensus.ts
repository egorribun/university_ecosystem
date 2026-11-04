// AUD-428 (TypeScript part): classification logic for the test-result census. A test
// block must perform a result check, directly or through a helper it calls, and a helper
// may live in the same file or in another frontend module reached by a named import.
// The sources are parsed with the TypeScript compiler API so that a string match or a
// comment cannot satisfy the census.
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import ts from "typescript"

export const CENSUS_ROOTS = ["src", "tests"] as const
const TEST_FILE = /\.(?:test|spec)\.(?:ts|tsx|mjs|js)$/u
export const ASSERTION_ROOTS: ReadonlySet<string> = new Set([
  "expect",
  "expectTypeOf",
  "assertType",
  "assert",
  "withExpectedConsole",
])
const TEST_BLOCK_ROOTS: ReadonlySet<string> = new Set(["it", "test"])

export function parseTypeScript(path: string, text: string): ts.SourceFile {
  const kind = path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  return ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, kind)
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

// A test block is a call of `it` or `test` (or their `.each` table form, or `.only`) whose
// callback is the last function argument. Hooks and grouping calls such as `test.beforeEach`
// and `test.describe` are not test blocks; skipped and todo blocks are not executed.
export function isTestCallee(expression: ts.Expression): boolean {
  if (ts.isIdentifier(expression)) return TEST_BLOCK_ROOTS.has(expression.text)
  if (ts.isPropertyAccessExpression(expression)) {
    return (
      ts.isIdentifier(expression.expression) &&
      TEST_BLOCK_ROOTS.has(expression.expression.text) &&
      expression.name.text === "only"
    )
  }
  if (ts.isCallExpression(expression)) {
    const callee = expression.expression
    return (
      ts.isPropertyAccessExpression(callee) &&
      callee.name.text === "each" &&
      ts.isIdentifier(callee.expression) &&
      TEST_BLOCK_ROOTS.has(callee.expression.text)
    )
  }
  return false
}

export function testCallback(call: ts.CallExpression): ts.FunctionLikeDeclaration | undefined {
  if (!isTestCallee(call.expression)) return undefined
  const last = call.arguments.at(-1)
  return isFunctionLike(last) ? last : undefined
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

export function containsAssertion(node: ts.Node, helpers: ReadonlySet<string>): boolean {
  let found = false
  const visit = (child: ts.Node) => {
    if (found) return
    if (ts.isCallExpression(child)) {
      const root = rootIdentifier(child.expression)
      if (
        root !== undefined &&
        (ASSERTION_ROOTS.has(root) || root.startsWith("assert") || helpers.has(root))
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
  run(): { files: number; flagged: string[] }
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

  function unassertedTests(path: string): string[] {
    const source = parseTypeScript(path, readFileSync(path, "utf8"))
    const helpers = fileHelpers(source, path)
    const flagged: string[] = []
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node)) {
        const callback = testCallback(node)
        if (callback && !containsAssertion(callback, helpers)) {
          const { line } = source.getLineAndCharacterOfPosition(node.getStart(source))
          flagged.push(`${repoRelative(frontendRoot, path)}:${line + 1}`)
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(source)
    return flagged
  }

  function run() {
    const files = CENSUS_ROOTS.flatMap((root) => {
      try {
        return testFiles(join(frontendRoot, root))
      } catch {
        return []
      }
    })
    return { files: files.length, flagged: files.flatMap(unassertedTests) }
  }

  return { frontendRoot, fileHelpers, moduleHelpers, unassertedTests, run }
}
