import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync } from "node:fs"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"

const require = createRequire(import.meta.url)
const micromatch = require("micromatch")
const adapterName = "@university-ecosystem/boundary-micromatch-compat"

test("both boundary consumers resolve the repository-owned adapter and its original engine", () => {
  const adapterPath = require.resolve("micromatch")
  assert.equal(require("micromatch/package.json").name, adapterName)
  assert.equal(require("micromatch/package.json").version, "1.0.0")
  assert.equal(createRequire(adapterPath)("picomatch/package.json").version, "2.3.2")

  for (const consumer of ["eslint-plugin-boundaries", "@boundaries/elements"]) {
    const consumerRequire = createRequire(require.resolve(consumer))
    assert.equal(consumerRequire.resolve("micromatch"), adapterPath)
    let resolvedBraces
    try {
      resolvedBraces = consumerRequire.resolve("braces")
    } catch (error) {
      assert.equal(error.code, "MODULE_NOT_FOUND")
    }
    if (resolvedBraces !== undefined) {
      // Node also searches the parent workspace, whose CLI dependencies are separate.
      const frontendRoot = path.resolve(import.meta.dirname, "..")
      assert.equal(
        path.relative(frontendRoot, resolvedBraces).startsWith(`..${path.sep}`),
        true,
        `braces must not resolve inside the frontend installation: ${resolvedBraces}`
      )
    }
  }
})

test("the lockfile contains no vulnerable braces package or upstream micromatch copy", () => {
  const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"))
  for (const [location, metadata] of Object.entries(lock.packages)) {
    assert.equal(/(?:^|\/)node_modules\/braces$/.test(location), false, location)
    assert.notEqual(metadata.name, "braces", location)
    if (/(?:^|\/)node_modules\/micromatch$/.test(location)) {
      assert.equal(metadata.link, true, location)
      assert.equal(lock.packages[metadata.resolved].name, adapterName)
    }
  }
})

test("only the three supported APIs are exposed and unsupported calls throw", () => {
  assert.deepEqual(Object.keys(micromatch).sort(), ["capture", "isMatch", "makeRe"])
  for (const method of ["braces", "braceExpand", "match", "matcher", "parse", "scan"]) {
    assert.throws(() => micromatch[method]("{a,b}"), TypeError)
  }
  assert.throws(() => micromatch(["a"], "*"), TypeError)
})

test("captures preserve order, empty optional groups, exact matches, and no-match results", () => {
  assert.deepEqual(micromatch.capture("src/*/*.ts", "src/news/index.ts"), ["news", "index"])
  assert.deepEqual(micromatch.capture("src/(*).{ts,tsx}", "src/Button.tsx"), [
    "Button",
    "Button",
    "tsx",
  ])
  assert.deepEqual(micromatch.capture("src/**/(*).ts", "src/index.ts"), ["", "index", "index"])
  assert.deepEqual(micromatch.capture("a?(b)c", "ac"), [""])
  assert.deepEqual(micromatch.capture("exact", "exact"), [])
  assert.equal(micromatch.capture("*.ts", "index.js"), undefined)
})

test("pattern arrays retain any-match semantics, including negation", () => {
  assert.equal(micromatch.isMatch("index.ts", ["*.js", "*.ts"]), true)
  assert.equal(micromatch.isMatch("index.css", ["*.js", "*.ts"]), false)
  assert.equal(micromatch.isMatch("index.ts", []), false)
  // isMatch is an OR over patterns, not ordered inclusion/exclusion filtering.
  assert.equal(micromatch.isMatch("src/app/a.ts", ["src/**", "!src/app/**"]), true)
  assert.equal(micromatch.isMatch("src/app/a.ts", "!src/app/**"), false)
  assert.equal(micromatch.isMatch("src/shared/a.ts", "!src/app/**"), true)
  assert.equal(micromatch.isMatch("!foo", "!foo", { nonegate: true }), true)
})

test("brace alternatives, ranges, extglobs, and character classes keep matching behavior", () => {
  for (const [pattern, matching, rejected] of [
    ["src/{components,features}/*.{ts,tsx}", "src/components/Button.tsx", "src/app/main.ts"],
    ["{a,b,{c,d}}", "d", "e"],
    ["file{1..5}.ts", "file3.ts", "file6.ts"],
    ["{a..z}.ts", "m.ts", "3.ts"],
    ["src/+(a|b).ts", "src/aba.ts", "src/c.ts"],
    ["src/!(app)/**", "src/shared/index.ts", "src/app/index.ts"],
    ["**/*.@(ts|tsx)", "src/Button.tsx", "src/Button.js"],
    ["[[:alpha:]]?.[jt]s", "ab.ts", "12.ts"],
  ]) {
    assert.equal(micromatch.isMatch(matching, pattern), true, pattern)
    assert.equal(micromatch.isMatch(rejected, pattern), false, pattern)
    assert.equal(micromatch.makeRe(pattern).test(matching), true, pattern)
    assert.equal(micromatch.makeRe(pattern).test(rejected), false, pattern)
  }
})

test("nested extglobs retain the original engine's semantics", () => {
  assert.equal(micromatch.isMatch("test/utils", "test?(/utils/**)"), false)
  assert.equal(micromatch.isMatch("b", "+(*(a)|*(b))"), false)
})

test("Docker's builder transfer retains the adapter engine after the filtered source copy", (t) => {
  const dockerfile = readFileSync(new URL("../../frontend.Dockerfile", import.meta.url), "utf8")
  const dockerignore = readFileSync(new URL("../../.dockerignore", import.meta.url), "utf8")
  const assertInheritedAdapter = (source, ignore) => {
    const stages = source.split(/(?=^FROM )/m)
    const deps = stages.find((stage) => /^FROM \S+ AS deps$/m.test(stage))
    const builder = stages.find((stage) => /^FROM \S+ AS builder$/m.test(stage))
    assert.ok(deps, "the dependency stage must exist")
    assert.ok(builder, "the builder stage must exist")
    assert.match(builder, /^FROM deps AS builder$/m)
    assert.match(deps, /^COPY frontend\/scripts \.\/scripts\/$/m)
    assert.match(deps, /until npm ci --legacy-peer-deps;/)
    assert.ok(
      deps.indexOf("COPY frontend/scripts ./scripts/") <
        deps.indexOf("until npm ci --legacy-peer-deps;")
    )
    assert.match(builder, /^COPY frontend \.\/$/m)
    assert.match(ignore, /^\*\*\/node_modules\/$/m)
  }
  assertInheritedAdapter(dockerfile, dockerignore)
  // Bind the filesystem model below to the actual inheritance and filtered overlay.
  for (const [name, before, after] of [
    ["lost inheritance", "FROM deps AS builder", "FROM base AS builder"],
    ["missing builder", "FROM deps AS builder", "FROM deps AS renamed-builder"],
    ["missing adapter source", "COPY frontend/scripts ./scripts/\n", ""],
    ["missing install", "until npm ci --legacy-peer-deps;", "until true;"],
    ["missing overlay", "COPY frontend ./\n", ""],
  ]) {
    assert.throws(
      () => assertInheritedAdapter(dockerfile.replace(before, after), dockerignore),
      { code: "ERR_ASSERTION" },
      name
    )
  }
  assert.throws(
    () => assertInheritedAdapter(dockerfile, dockerignore.replace("**/node_modules/\n", "")),
    { code: "ERR_ASSERTION" },
    "unfiltered nested dependencies"
  )

  const target = mkdtempSync(path.join(tmpdir(), "boundary-adapter-builder-"))
  t.after(() => rmSync(target, { recursive: true, force: true }))
  const targetAdapter = path.join(target, "scripts", "boundary-micromatch-compat")
  const sourceAdapter = new URL("./boundary-micromatch-compat", import.meta.url)

  // Model the local package transfer, including its installed nested dependency.
  cpSync(sourceAdapter, targetAdapter, { recursive: true })
  mkdirSync(path.join(target, "node_modules"), { recursive: true })
  symlinkSync(targetAdapter, path.join(target, "node_modules", "micromatch"), "junction")
  // COPY frontend ./ overlays authored files; .dockerignore excludes nested node_modules.
  cpSync(sourceAdapter, targetAdapter, {
    recursive: true,
    filter: (source) => !source.split(path.sep).includes("node_modules"),
  })

  const builderRequire = createRequire(path.join(target, "package.json"))
  const adapterRequire = createRequire(builderRequire.resolve("micromatch"))
  const nestedEngine = path.join(targetAdapter, "node_modules", "picomatch")
  assert.equal(
    adapterRequire.resolve("picomatch/package.json"),
    path.join(nestedEngine, "package.json")
  )
  assert.equal(adapterRequire("picomatch/package.json").version, "2.3.2")
  assert.equal(builderRequire("micromatch").isMatch("test/utils", "test?(/utils/**)"), false)
  assert.equal(builderRequire("micromatch").isMatch("b", "+(*(a)|*(b))"), false)

  // A fresh process cannot satisfy this negative control from the require cache.
  rmSync(nestedEngine, { recursive: true, force: true })
  const missingEngine = spawnSync(
    process.execPath,
    [
      "--no-global-search-paths",
      "-e",
      `const assert = require("node:assert/strict");
       assert.throws(() => require(process.argv[1]), {
         code: "MODULE_NOT_FOUND",
         message: /Cannot find module 'picomatch'/,
       });`,
      builderRequire.resolve("micromatch"),
    ],
    { encoding: "utf8", timeout: 15000 }
  )
  assert.ifError(missingEngine.error)
  assert.equal(missingEngine.status, 0, missingEngine.stderr)
})

test("path, dotfile, case, and globstar options remain intact", () => {
  assert.equal(micromatch.isMatch("src/a/b.ts", "src/**/*.ts"), true)
  assert.equal(micromatch.isMatch("src/a/b.ts", "src/*.ts"), false)
  assert.equal(micromatch.isMatch("src/a/b.ts", "src/**", { noglobstar: true }), false)
  assert.equal(micromatch.isMatch("src/.hidden.ts", "src/*.ts"), false)
  assert.equal(micromatch.isMatch("src/.hidden.ts", "src/*.ts", { dot: true }), true)
  assert.equal(micromatch.isMatch("INDEX.TS", "*.ts"), false)
  assert.equal(micromatch.isMatch("INDEX.TS", "*.ts", { nocase: true }), true)
  assert.equal(micromatch.isMatch("foo*", "foo\\*"), true)
  assert.equal(micromatch.isMatch("before-foo-after", "foo", { contains: true }), true)
  assert.equal(micromatch.isMatch("a", "{a,b}", { nobrace: true }), false)
  assert.equal(micromatch.isMatch("a", "@(a|b)", { noext: true }), false)
})

test("Windows paths are normalized for matching and captures only when requested", () => {
  assert.equal(micromatch.isMatch("src\\news\\index.ts", "src/**/*.ts", { windows: true }), true)
  assert.equal(micromatch.isMatch("src\\news\\index.ts", "src/**/*.ts", { windows: false }), false)
  assert.deepEqual(micromatch.capture("src/*/*.ts", "src\\news\\index.ts", { windows: true }), [
    "news",
    "index",
  ])
  assert.equal(
    micromatch.capture("src/*/*.ts", "src\\news\\index.ts", { windows: false }),
    undefined
  )
})

test("makeRe forwards advanced arguments and capture options without mutating options", () => {
  const options = Object.freeze({ nocase: true, capture: false })
  const expression = micromatch.makeRe("src/*.ts", { capture: true })
  assert.deepEqual(expression.exec("src/index.ts").slice(1), ["index"])
  assert.equal(micromatch.makeRe("*.ts", options).flags, "i")
  assert.equal(typeof micromatch.makeRe("*.ts", {}, true), "string")
  assert.equal(micromatch.makeRe("*.ts", { fastpaths: false }, false, true).state.input, "*.ts")
  assert.deepEqual(micromatch.capture("*.ts", "INDEX.TS", options), ["INDEX"])
  assert.deepEqual(options, { nocase: true, capture: false })
})

test("invalid inputs retain errors and capture retains upstream string coercion", () => {
  for (const invalid of [undefined, null, 42, true, {}, ""]) {
    assert.throws(() => micromatch.makeRe(invalid), TypeError)
  }
  assert.throws(() => micromatch.isMatch(42, "*"), /Expected input to be a string/)
  assert.throws(() => micromatch.isMatch("a", {}), TypeError)
  assert.throws(() => micromatch.makeRe("[", { strictBrackets: true }), SyntaxError)
  assert.deepEqual(micromatch.capture(42, "42"), [])
  assert.deepEqual(micromatch.capture(undefined, "undefined"), [])
  assert.equal(micromatch.isMatch("", "*"), false)
})

test("deeply nested brace patterns stay out of recursive brace expansion", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--max-old-space-size=128",
      "-e",
      `const assert = require('node:assert/strict');
       const mm = require('micromatch');
       // 4,900 levels reproduce the original braces.expand stack overflow.
       for (const pattern of ['{'.repeat(4900) + 'a' + '}'.repeat(4900), '{'.repeat(4900) + 'a']) {
         assert.equal(mm.isMatch('other', pattern), false);
         assert.equal(mm.makeRe(pattern).test('other'), false);
         assert.equal(mm.capture(pattern, 'other'), undefined);
       }
       assert.throws(() => mm.braceExpand('{1..1000000000}'), TypeError);`,
    ],
    { cwd: new URL("..", import.meta.url), encoding: "utf8", timeout: 15000 }
  )
  assert.ifError(result.error)
  assert.equal(result.status, 0, result.stderr)
})
