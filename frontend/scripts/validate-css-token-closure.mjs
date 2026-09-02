import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const DEFAULT_ROOT = path.resolve(__dirname, "../src")
const SOURCE_EXTENSIONS = new Set([".css", ".html", ".js", ".jsx", ".mjs", ".ts", ".tsx"])
const IGNORED_DIRECTORIES = new Set(["coverage", "dist", "node_modules", "storybook-static"])
const NON_RUNTIME_DIRECTORIES = new Set(["__snapshots__", "__tests__"])

function resolveRoot(argv) {
  const rootIndex = argv.indexOf("--root")
  if (rootIndex === -1) return DEFAULT_ROOT
  const candidate = argv[rootIndex + 1]
  if (!candidate) throw new Error("--root requires a directory")
  return path.resolve(candidate)
}

function collectSourceFiles(root) {
  const files = []
  const visit = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!IGNORED_DIRECTORIES.has(entry.name) && !NON_RUNTIME_DIRECTORIES.has(entry.name)) {
          visit(path.join(directory, entry.name))
        }
        continue
      }
      if (
        SOURCE_EXTENSIONS.has(path.extname(entry.name)) &&
        !/\.(?:spec|stories|test)\.[^.]+$/.test(entry.name)
      ) {
        files.push(path.join(directory, entry.name))
      }
    }
  }
  visit(root)
  return files.sort()
}

function withoutComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "")
}

function lineNumberAt(source, index) {
  return source.slice(0, index).split("\n").length
}

function addReference(references, token, file, source, index) {
  if (token.startsWith("--_") || token.endsWith("-")) return
  const locations = references.get(token) ?? []
  locations.push(`${file}:${lineNumberAt(source, index)}`)
  references.set(token, locations)
}

function inventoryTokens(root) {
  const definitions = new Set()
  const references = new Map()

  for (const absolutePath of collectSourceFiles(root)) {
    const relativePath = path.relative(root, absolutePath).replaceAll("\\", "/")
    const source = withoutComments(fs.readFileSync(absolutePath, "utf8"))

    for (const match of source.matchAll(/--([a-zA-Z0-9_-]+)["']?\s*:/g)) {
      definitions.add(`--${match[1]}`)
    }

    for (const match of source.matchAll(/var\(\s*(--[a-zA-Z0-9_-]+)(\s*,)?/g)) {
      const [, token, fallbackMarker] = match
      if (fallbackMarker) continue
      addReference(references, token, relativePath, source, match.index)
    }

    for (const match of source.matchAll(/(?:^|[^a-zA-Z])\(--([a-zA-Z0-9_-]+)\)/g)) {
      addReference(references, `--${match[1]}`, relativePath, source, match.index)
    }
  }

  return { definitions, references }
}

function main() {
  const root = resolveRoot(process.argv.slice(2))
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    throw new Error(`Token source root is not a directory: ${root}`)
  }

  const { definitions, references } = inventoryTokens(root)
  const unresolved = [...references.entries()]
    .filter(([token]) => !definitions.has(token))
    .sort(([left], [right]) => left.localeCompare(right))

  if (unresolved.length > 0) {
    console.error(`Unresolved custom properties (${unresolved.length}):`)
    for (const [token, locations] of unresolved) {
      console.error(`  ${token}: ${[...new Set(locations)].join(", ")}`)
    }
    process.exitCode = 1
    return
  }

  console.log(
    `CSS token closure valid: ${definitions.size} definitions cover ${references.size} referenced tokens.`
  )
}

main()
