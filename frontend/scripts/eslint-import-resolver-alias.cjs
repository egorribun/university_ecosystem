"use strict"

const fs = require("node:fs")
const path = require("node:path")

const DEFAULT_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"]

function resolveExistingPath(candidate, extensions) {
  if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
    return candidate
  }

  for (const extension of extensions) {
    const fileCandidate = `${candidate}${extension}`
    if (fs.existsSync(fileCandidate) && fs.statSync(fileCandidate).isFile()) {
      return fileCandidate
    }

    const indexCandidate = path.join(candidate, `index${extension}`)
    if (fs.existsSync(indexCandidate) && fs.statSync(indexCandidate).isFile()) {
      return indexCandidate
    }
  }

  return undefined
}

exports.interfaceVersion = 2

exports.resolve = function resolve(source, _sourceFile, options = {}) {
  const alias = options.alias ?? "@"
  if (source !== alias && !source.startsWith(`${alias}/`)) {
    return { found: false }
  }

  const target = options.target ?? "./src"
  const suffix = source === alias ? "" : source.slice(alias.length + 1)
  const candidate = path.resolve(process.cwd(), target, suffix)
  const resolvedPath = resolveExistingPath(candidate, options.extensions ?? DEFAULT_EXTENSIONS)

  return resolvedPath ? { found: true, path: resolvedPath } : { found: false }
}
