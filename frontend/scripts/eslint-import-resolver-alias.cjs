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

function createResolver({ realpathSync = fs.realpathSync.native } = {}) {
  return function resolve(source, _sourceFile, options = {}) {
    const alias = options.alias ?? "@"
    if (source !== alias && !source.startsWith(`${alias}/`)) {
      return { found: false }
    }

    const target = options.target
    if (typeof target !== "string" || !path.isAbsolute(target)) {
      return { found: false }
    }

    let targetRoot
    try {
      targetRoot = realpathSync(target)
    } catch {
      return { found: false }
    }

    const suffix = source === alias ? "" : source.slice(alias.length + 1)
    const candidate = path.resolve(targetRoot, suffix)
    const relativeCandidate = path.relative(targetRoot, candidate)
    if (
      path.isAbsolute(relativeCandidate) ||
      relativeCandidate === ".." ||
      relativeCandidate.startsWith(`..${path.sep}`)
    ) {
      return { found: false }
    }

    const resolvedPath = resolveExistingPath(candidate, options.extensions ?? DEFAULT_EXTENSIONS)
    if (!resolvedPath) {
      return { found: false }
    }

    const realPath = realpathSync(resolvedPath)
    const relativeRealPath = path.relative(targetRoot, realPath)
    if (
      path.isAbsolute(relativeRealPath) ||
      relativeRealPath === ".." ||
      relativeRealPath.startsWith(`..${path.sep}`)
    ) {
      return { found: false }
    }

    return { found: true, path: realPath }
  }
}

exports.createResolver = createResolver
exports.resolve = createResolver()
