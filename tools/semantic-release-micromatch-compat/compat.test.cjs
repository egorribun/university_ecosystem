"use strict"

const assert = require("node:assert/strict")
const { spawnSync } = require("node:child_process")
const { createRequire } = require("node:module")
const { pathToFileURL } = require("node:url")
const path = require("node:path")
const test = require("node:test")
const micromatch = require("./index.cjs")

const fixtures = [
  { name: "branch literal", list: ["main", "release/1.2", "feature/x"], patterns: "main", expected: ["main"] },
  { name: "wildcard", list: ["a.js", "b.ts", "nested/a.js"], patterns: "*.js", expected: ["a.js"] },
  { name: "globstar", list: ["src/a.ts", "src/deep/a.ts", "test/a.ts"], patterns: "src/**/*.ts", expected: ["src/a.ts", "src/deep/a.ts"] },
  { name: "ordered include and exclude", list: ["src/a.ts", "src/test/a.ts", "lib/a.ts"], patterns: ["**/*.ts", "!**/test/**"], expected: ["src/a.ts", "lib/a.ts"] },
  { name: "negative-only pattern", list: ["a.ts", "b.test.ts", "c.ts"], patterns: "!*.test.ts", expected: ["a.ts", "c.ts"] },
  { name: "nested brace alternatives", list: ["a.js", "b.js", "c.js", "d.js", "x.ts"], patterns: "{a,b,{c,d}}.js", expected: ["a.js", "b.js", "c.js", "d.js"] },
  { name: "brace range", list: ["v1", "v2", "v3", "v4", "v5", "v6"], patterns: "v{1..5}", expected: ["v1", "v2", "v3", "v4", "v5"] },
  { name: "positive extglob", list: ["a.js", "b.js", "c.ts"], patterns: "+(a|b).js", expected: ["a.js", "b.js"] },
  { name: "negative extglob", list: ["app.ts", "test.ts", "app.spec.ts"], patterns: "!(*.spec).ts", expected: ["app.ts", "test.ts"] },
  { name: "character class", list: ["a1.js", "b2.js", "c3.js", "d4.js"], patterns: "[a-c][1-3].js", expected: ["a1.js", "b2.js", "c3.js"] },
  { name: "dotfiles excluded by default", list: [".env", "file.env"], patterns: "*", expected: ["file.env"] },
  { name: "dotfiles included explicitly", list: [".env", "file.env"], patterns: "*", options: { dot: true }, expected: [".env", "file.env"] },
  { name: "case-insensitive matching", list: ["README.md", "readme.md"], patterns: "readme.MD", options: { nocase: true }, expected: ["README.md", "readme.md"] },
  { name: "matchBase", list: ["a/readme.md", "x.md"], patterns: "readme.md", options: { matchBase: true }, expected: ["a/readme.md"] },
  { name: "non-strict trailing slash", list: ["dir", "dir/"], patterns: "dir/", options: { strictSlashes: false }, expected: ["dir/"] },
  { name: "ignore pattern", list: ["a.js", "b.js", "c.ts"], patterns: "*.js", options: { ignore: "b.js" }, expected: ["a.js"] },
  { name: "windows separators", list: ["a\\file.js", "a/file.js"], patterns: "a/*.js", options: { windows: true }, expected: ["a/file.js"] },
  { name: "contains option", list: ["xxfeatureyy", "feature"], patterns: "feature", options: { contains: true }, expected: ["xxfeatureyy", "feature"] },
  { name: "nobrace", list: ["a.js", "b.js"], patterns: "{a,b}.js", options: { nobrace: true }, expected: [] },
  { name: "noext", list: ["a.js", "b.js"], patterns: "+(a|b).js", options: { noext: true }, expected: [] },
  { name: "noglobstar", list: ["a.ts", "x/a.ts", "x/y/a.ts"], patterns: "**/*.ts", options: { noglobstar: true }, expected: ["a.ts", "x/a.ts"] },
  { name: "nonegate", list: ["a.ts", "b.ts"], patterns: "!a.ts", options: { nonegate: true }, expected: [] },
  { name: "nonull", list: ["a.ts"], patterns: "*.js", options: { nonull: true }, expected: ["*.js"] },
  { name: "unescape", list: ["a*.js"], patterns: "a\\*.js", options: { nonull: true, unescape: true }, expected: ["a*.js"] },
  { name: "posix option", list: ["a\\b.js", "a/b.js"], patterns: "a/b.js", options: { posix: true }, expected: ["a/b.js"] },
]

test("supported subset matches the audited upstream behavior corpus", () => {
  for (const fixture of fixtures) {
    assert.deepEqual(micromatch(fixture.list, fixture.patterns, fixture.options), fixture.expected, fixture.name)
  }
})

test("semantic-release branch and analyzer call shapes work", () => {
  assert.deepEqual(micromatch(["main", "release/1.2"], "main"), ["main"])
  assert.equal(micromatch.isMatch("feat", "feat"), true)
  assert.equal(micromatch.isMatch("fix", "feat"), false)
})

test("the installed commit analyzer uses this adapter for default release rules", async () => {
  const cwd = path.resolve(__dirname, "../..")
  const projectRequire = createRequire(path.join(cwd, "package.json"))
  const analyzerPath = projectRequire.resolve("@semantic-release/commit-analyzer")
  const analyzerRequire = createRequire(analyzerPath)
  assert.equal(analyzerRequire.resolve("micromatch"), projectRequire.resolve("micromatch"))

  const { analyzeCommits } = await import(pathToFileURL(analyzerPath).href)
  const logger = { log() {} }
  const cases = [
    ["feat: add a synthetic capability", "minor"],
    ["fix: correct a synthetic edge case", "patch"],
    ["feat: remove a public field\n\nBREAKING CHANGE: clients must migrate", "major"],
  ]

  for (const [message, expected] of cases) {
    const actual = await analyzeCommits({}, {
      commits: [{ hash: "synthetic-callsite-test", message }],
      cwd,
      logger,
    })
    assert.equal(actual, expected, message)
  }
})

test("the installed branch expander filters refs from a local repository path", async () => {
  const cwd = path.resolve(__dirname, "../..")
  const projectRequire = createRequire(path.join(cwd, "package.json"))
  const expandPath = projectRequire.resolve("semantic-release/lib/branches/expand.js")
  const expandRequire = createRequire(expandPath)
  assert.equal(expandRequire.resolve("micromatch"), projectRequire.resolve("micromatch"))

  const localRefs = spawnSync("git", ["ls-remote", "--heads", "--", cwd], {
    cwd,
    encoding: "utf8",
    timeout: 5000,
  })
  assert.equal(localRefs.error, undefined, localRefs.error && localRefs.error.message)
  assert.equal(localRefs.status, 0, localRefs.stderr)
  const names = localRefs.stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => line.match(/refs\/heads\/(?<name>.+)$/)?.groups?.name)
    .filter(Boolean)
  const pattern = names[0] ?? "__no_local_branch__"

  const { default: expandBranches } = await import(pathToFileURL(expandPath).href)
  const expanded = await expandBranches(cwd, { cwd }, [{ name: pattern, channel: "stable" }])
  assert.deepEqual(expanded.map(({ name }) => name), names.length ? [pattern] : [])
  assert.ok(expanded.every((branch) => branch.channel === "stable"))
})

test("isMatch preserves brace, extglob, negation, and dot behavior", () => {
  assert.equal(micromatch.isMatch("foo", "{bar,foo}"), true)
  assert.equal(micromatch.isMatch("foo", "+(bar|foo)"), true)
  assert.equal(micromatch.isMatch("a.ts", ["!*.spec.ts", "*.ts"]), true)
  assert.equal(micromatch.isMatch("a.spec.ts", "!(*.spec).ts"), false)
  assert.equal(micromatch.isMatch(".env", "*"), false)
  assert.equal(micromatch.isMatch(".env", "*", { dot: true }), true)
})

test("unsupported APIs, options, and argument shapes fail closed", () => {
  for (const name of ["match", "not", "matcher", "braces", "capture", "parse"]) {
    assert.equal(micromatch[name], undefined, `${name} is deliberately not implemented`)
  }
  assert.throws(() => micromatch(["main"], "main", { onResult() {} }), /Unsupported micromatch option/)
  assert.throws(() => micromatch(["main"], "main", { dot: "yes" }), /must be a boolean/)
  assert.throws(() => micromatch(["main"], "main", Object.create({ dot: true })), /plain object/)
  assert.throws(() => micromatch(["main"], "{".repeat(65)), RangeError)
  assert.throws(() => micromatch(["main"], "x".repeat(4097)), RangeError)
  assert.throws(() => micromatch(Array(10001).fill("main"), "main"), /10000/)
  assert.throws(() => micromatch(["main"], Array(257).fill("main")), RangeError)
})

test("adversarial nested braces reject in a bounded child process", () => {
  const adapterPath = path.join(__dirname, "index.cjs")
  const child = `
    const mm = require(${JSON.stringify(adapterPath)})
    const pattern = "{a,".repeat(2000) + "x" + "}".repeat(2000)
    try { mm(["x"], pattern); process.exit(2) }
    catch (error) { process.exit(error instanceof RangeError ? 0 : 3) }
  `
  const result = spawnSync(process.execPath, ["-e", child], { encoding: "utf8", timeout: 1000 })
  assert.equal(result.error, undefined, result.error && result.error.message)
  assert.equal(result.status, 0, result.stderr)
})

test("no-match options preserve upstream behavior", () => {
  assert.throws(() => micromatch(["a.ts"], "*.js", { failglob: true }), /No matches found/)
})
