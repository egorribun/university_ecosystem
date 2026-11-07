import assert from "node:assert/strict"
import { readFileSync, realpathSync } from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"

const require = createRequire(import.meta.url)
const adapterPath = realpathSync(new URL("./minimatch-3-compat/index.cjs", import.meta.url))
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"))
const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"))
const adapterName = "@university-ecosystem/minimatch-3-compat"

test("the consumers' minimatch edges resolve to the repository-owned adapter", () => {
  assert.equal(manifest.overrides["minimatch@3.1.5"], "file:./scripts/minimatch-3-compat")
  assert.equal(manifest.devDependencies[adapterName], "file:./scripts/minimatch-3-compat")
  assert.equal(manifest.devDependencies.minimatch, "11.0.2")
  assert.equal(lock.packages[""].devDependencies.minimatch, "11.0.2")
  for (const consumer of ["eslint-plugin-react", "eslint-plugin-jsx-a11y"]) {
    const consumerRequire = createRequire(require.resolve(consumer))
    assert.equal(realpathSync(consumerRequire.resolve("minimatch")), adapterPath)
  }
})

test("the adapter exposes the minimatch 3 call shape over the patched minimatch 11 engine", () => {
  // Imported by package name: this resolves the installed link, not a source-path shortcut.
  const minimatch = require("@university-ecosystem/minimatch-3-compat")
  assert.equal(typeof minimatch, "function")
  assert.equal(realpathSync(require.resolve(adapterName)), adapterPath)
  // The engine (root minimatch 11.0.2) is the behavioural reference for the adapter.
  const engine = require("minimatch").minimatch
  assert.equal(require("minimatch/package.json").version, "11.0.2")
  const cases = [
    ["Button", "Button", undefined],
    ["ButtonGroup", "Button*", undefined],
    ["Foo.Bar", "Foo*", { noglobstar: true }],
    ["Button", "Input", undefined],
    ["src/a/b", "src/**", { noglobstar: true }],
    ["src/a/b", "src/**", undefined],
  ]
  for (const [p, pattern, options] of cases) {
    assert.equal(minimatch(p, pattern, options), engine(p, pattern, options), `${p} ${pattern}`)
  }
  assert.equal(minimatch("Button", "Button"), true)
  assert.throws(() => minimatch("x", 42), TypeError)
})

test("the lockfile has no vulnerable minimatch record outside the adapter", () => {
  for (const [location, metadata] of Object.entries(lock.packages)) {
    if (!/(?:^|\/)node_modules\/minimatch$/.test(location)) continue
    if (metadata.link === true) {
      assert.equal(metadata.resolved, "scripts/minimatch-3-compat", location)
      continue
    }
    const [major, minor, patch] = metadata.version.split(".").map(Number)
    const fixed = major > 11 || (major === 11 && (minor > 0 || patch >= 1))
    assert.equal(fixed, true, `${location} ${metadata.version} is below 11.0.1`)
  }
  assert.equal(lock.packages[`scripts/minimatch-3-compat`].name, adapterName)
})
