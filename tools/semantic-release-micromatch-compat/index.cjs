"use strict"

const picomatch = require("picomatch")
const allowedOptions = new Set([
  "contains",
  "dot",
  "failglob",
  "ignore",
  "matchBase",
  "nobrace",
  "nocase",
  "noglobstar",
  "noext",
  "nonegate",
  "nonull",
  "nullglob",
  "posix",
  "strictSlashes",
  "unescape",
  "windows",
])
const booleanOptions = [...allowedOptions].filter((name) => name !== "ignore")
const maxPatternLength = 4096
const maxPatternCount = 256
const maxDelimiterDepth = 64

function checkPattern(pattern) {
  if (typeof pattern !== "string" || pattern.length === 0) {
    throw new TypeError("semantic-release micromatch adapter expects non-empty string patterns")
  }
  if (pattern.length > maxPatternLength) {
    throw new RangeError(`Glob pattern exceeds ${maxPatternLength} characters`)
  }

  let escaped = false
  let inClass = false
  let braces = 0
  let parentheses = 0
  for (const character of pattern) {
    if (escaped) {
      escaped = false
      continue
    }
    if (character === "\\") {
      escaped = true
      continue
    }
    if (character === "[" && !inClass) {
      inClass = true
      continue
    }
    if (character === "]" && inClass) {
      inClass = false
      continue
    }
    if (inClass) continue

    if (character === "{") braces += 1
    if (character === "}") braces = Math.max(0, braces - 1)
    if (character === "(") parentheses += 1
    if (character === ")") parentheses = Math.max(0, parentheses - 1)
    if (braces > maxDelimiterDepth || parentheses > maxDelimiterDepth) {
      throw new RangeError(`Glob pattern nesting exceeds ${maxDelimiterDepth}`)
    }
  }
}

function checkPatternList(value, label) {
  const patterns = Array.isArray(value) ? value : [value]
  if (patterns.length > maxPatternCount) {
    throw new RangeError(`At most ${maxPatternCount} ${label} patterns are supported`)
  }
  for (const pattern of patterns) checkPattern(pattern)
  return patterns
}

function checkOptions(options) {
  if (options === undefined) return {}
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("Glob options must be a plain object")
  }
  if (![Object.prototype, null].includes(Object.getPrototypeOf(options))) {
    throw new TypeError("Glob options must be a plain object")
  }
  for (const name of Object.keys(options)) {
    if (!allowedOptions.has(name)) {
      throw new TypeError(`Unsupported micromatch option: ${name}`)
    }
  }
  for (const name of booleanOptions) {
    if (options[name] !== undefined && typeof options[name] !== "boolean") {
      throw new TypeError(`Glob option ${name} must be a boolean`)
    }
  }
  if (options.ignore !== undefined) checkPatternList(options.ignore, "ignore")
  return options
}

function micromatch(list, patterns, options) {
  const entries = Array.isArray(list) ? list : [list]
  if (entries.length > 10000 || entries.some((entry) => typeof entry !== "string")) {
    throw new TypeError("semantic-release micromatch adapter expects at most 10000 string inputs")
  }
  const patternList = checkPatternList(patterns, "glob")
  const safeOptions = checkOptions(options)
  const omit = new Set()
  const keep = new Set()
  const items = new Set()
  let negatives = 0

  for (const pattern of patternList) {
    const matcher = picomatch(pattern, safeOptions, true)
    const negated = matcher.state.negated || matcher.state.negatedExtglob
    if (negated) negatives += 1

    for (const entry of entries) {
      const result = matcher(entry, true)
      items.add(result.output)
      const matches = negated ? !result.isMatch : result.isMatch
      if (!matches) continue
      if (negated) {
        omit.add(result.output)
      } else {
        omit.delete(result.output)
        keep.add(result.output)
      }
    }
  }

  const results = negatives === patternList.length ? [...items] : [...keep]
  const matches = results.filter((entry) => !omit.has(entry))
  if (matches.length === 0) {
    if (safeOptions.failglob === true) {
      throw new Error(`No matches found for "${patternList.join(", ")}"`)
    }
    if (safeOptions.nonull === true || safeOptions.nullglob === true) {
      return safeOptions.unescape ? patternList.map((pattern) => pattern.replace(/\\/g, "")) : patternList
    }
  }
  return matches
}

micromatch.isMatch = (input, patterns, options) => {
  if (typeof input !== "string") {
    throw new TypeError("Expected input to be a string")
  }
  const patternList = checkPatternList(patterns, "glob")
  return picomatch(patternList, checkOptions(options))(input)
}

module.exports = Object.freeze(micromatch)
