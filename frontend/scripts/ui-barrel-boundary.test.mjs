import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"
import ts from "typescript"

const frontendRoot = path.resolve(import.meta.dirname, "..")
const scanRoots = ["src", "tests", ".storybook", "scripts"]
const authoredExtensions = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"])
const ignoredDirectories = new Set([
  "node_modules",
  "dist",
  "build",
  "coverage",
  ".cache",
  ".vite",
  ".stryker-tmp",
  "playwright-report",
  "test-results",
])
const uiIndexPath = path.resolve(frontendRoot, "src/components/ui/index.ts")
const uiDirectoryPath = path.dirname(uiIndexPath)

function collectAuthoredFiles(root) {
  if (!fs.existsSync(root)) return []
  const files = []
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) {
        files.push(...collectAuthoredFiles(path.join(root, entry.name)))
      }
      continue
    }
    if (authoredExtensions.has(path.extname(entry.name))) {
      files.push(path.join(root, entry.name))
    }
  }
  return files
}

function sourceKind(node) {
  if (ts.isImportDeclaration(node)) return "import"
  if (ts.isExportDeclaration(node)) return "export"
  if (ts.isCallExpression(node)) {
    if (node.expression.kind === ts.SyntaxKind.ImportKeyword) return "dynamic-import"
    if (ts.isIdentifier(node.expression) && node.expression.text === "require") return "require"
    if (
      ts.isPropertyAccessExpression(node.expression) &&
      ts.isIdentifier(node.expression.expression) &&
      node.expression.expression.text === "require"
    ) {
      return "require.resolve"
    }
    if (ts.isPropertyAccessExpression(node.expression)) {
      const owner = node.expression.expression
      if (ts.isIdentifier(owner) && (owner.text === "vi" || owner.text === "jest")) {
        const method = node.expression.name.text
        if (["mock", "doMock", "importActual", "importMock"].includes(method)) {
          return `${owner.text}.${method}`
        }
      }
    }
  }
  return null
}

function moduleSpecifierFor(node) {
  if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
    return node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)
      ? node.moduleSpecifier
      : null
  }
  if (ts.isCallExpression(node)) {
    const firstArgument = node.arguments[0]
    return firstArgument && ts.isStringLiteral(firstArgument) ? firstArgument : null
  }
  return null
}

function resolvesToUiIndex(specifier, importerPath) {
  const value = specifier.text
  let candidate
  if (value === "@/components/ui" || value === "@/components/ui/index") {
    candidate = value.endsWith("/index") ? path.join(uiDirectoryPath, "index") : uiDirectoryPath
  } else if (value.startsWith("./") || value.startsWith("../")) {
    candidate = path.resolve(path.dirname(importerPath), value)
  } else {
    return false
  }
  const resolved = path.normalize(candidate)
  return (
    resolved === path.normalize(uiDirectoryPath) ||
    resolved === path.normalize(path.join(uiDirectoryPath, "index")) ||
    resolved === path.normalize(uiIndexPath)
  )
}

function findInboundReferences() {
  const references = []
  for (const root of scanRoots) {
    const absoluteRoot = path.join(frontendRoot, root)
    for (const filePath of collectAuthoredFiles(absoluteRoot)) {
      const source = fs.readFileSync(filePath, "utf8")
      const scriptKind = ts.getScriptKindFromFileName(filePath)
      const sourceFile = ts.createSourceFile(
        filePath,
        source,
        ts.ScriptTarget.Latest,
        true,
        scriptKind
      )
      function visit(node) {
        const kind = sourceKind(node)
        const specifier = kind ? moduleSpecifierFor(node) : null
        if (kind && specifier && resolvesToUiIndex(specifier, filePath)) {
          const start = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile))
          references.push({
            file: path.relative(frontendRoot, filePath).replaceAll(path.sep, "/"),
            line: start.line + 1,
            column: start.character + 1,
            kind,
            specifier: specifier.text,
          })
        }
        ts.forEachChild(node, visit)
      }
      visit(sourceFile)
    }
  }
  return references.sort((left, right) => {
    const leftKey = `${left.file}:${left.line}:${left.column} [${left.kind}] ${left.specifier}`
    const rightKey = `${right.file}:${right.line}:${right.column} [${right.kind}] ${right.specifier}`
    return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0
  })
}

function formatReferences(references) {
  return references
    .map(
      ({ file, line, column, kind, specifier }) =>
        `${file}:${line}:${column} [${kind}] ${specifier}`
    )
    .join("\n")
}

test("no authored module resolves to the deleted UI barrel", () => {
  const references = findInboundReferences()
  assert.equal(
    references.length,
    0,
    `UI barrel references must be migrated to exact leaf modules:\n${formatReferences(references)}`
  )
  assert.equal(
    fs.existsSync(uiIndexPath),
    false,
    "frontend/src/components/ui/index.ts must be deleted"
  )
})

export { findInboundReferences, resolvesToUiIndex }
