import assert from "node:assert/strict"
import { readFileSync, realpathSync } from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"

const require = createRequire(import.meta.url)
const clone = require("@university-ecosystem/node-resolve-defaults-clone-compat")
const defaults = () => ({
  dedupe: [],
  extensions: [".mjs", ".js", ".json", ".node"],
  resolveOnly: [],
  moduleDirectories: ["node_modules"],
  modulePaths: [],
  ignoreSideEffectsForRoot: false,
  allowExportsFolderMapping: true,
})

test("clones exact defaults with independent mutable arrays", () => {
  const original = defaults()
  const first = clone({}, original)
  const second = clone({}, original)
  assert.deepEqual(first, original)
  assert.notEqual(first, original)
  for (const key of ["dedupe", "extensions", "resolveOnly", "moduleDirectories", "modulePaths"]) {
    assert.notEqual(first[key], original[key])
    assert.notEqual(first[key], second[key])
    Object.freeze(first[key])
  }
  Object.freeze(first)
  assert.throws(() => first.extensions.push(".invalid"), TypeError)
  assert.deepEqual(original, defaults())
  assert.deepEqual(second, defaults())
})

test("rejects general merge behavior, options and shape drift", () => {
  const invalid = [null, [], Object.create(null), { ...defaults(), extra: true }]
  for (const source of invalid) assert.throws(() => clone({}, source), TypeError)
  assert.throws(() => clone({ existing: true }, defaults()), TypeError)
  assert.throws(() => clone({}, defaults(), {}), TypeError)
  assert.throws(() => clone({}, { ...defaults(), allowExportsFolderMapping: false }), TypeError)
  const cyclic = defaults()
  cyclic.dedupe.push(cyclic)
  assert.throws(() => clone({}, cyclic), TypeError)
})

test("rejects accessors and prototype poisoning without invoking getters", () => {
  let accessed = false
  const accessor = defaults()
  Object.defineProperty(accessor, "extensions", {
    enumerable: true,
    get() {
      accessed = true
      return []
    },
  })
  assert.throws(() => clone({}, accessor), TypeError)
  assert.equal(accessed, false)
  const before = Reflect.ownKeys(Object.prototype)
  for (const key of ["__proto__", "constructor", "prototype"]) {
    const source = defaults()
    Object.defineProperty(source, key, { value: { polluted: true }, enumerable: true })
    assert.throws(() => clone({}, source), TypeError)
  }
  assert.deepEqual(Reflect.ownKeys(Object.prototype), before)
  assert.equal(Object.hasOwn(Object.prototype, "polluted"), false)
})

test("actual CJS and ESM consumers retain the scoped clone contract", async () => {
  const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"))
  const packages = lock.packages
  assert.equal(packages["node_modules/@rollup/plugin-node-resolve"].version, "16.0.3")
  const consumerPath = "node_modules/@rollup/plugin-node-resolve"
  assert.deepEqual(
    Object.keys(packages).filter(
      (path) => path === consumerPath || path.endsWith(`/${consumerPath}`)
    ),
    [consumerPath]
  )
  assert.deepEqual(
    Object.entries(packages)
      .filter(([, pkg]) =>
        ["dependencies", "optionalDependencies", "peerDependencies"].some((field) =>
          Object.hasOwn(pkg[field] ?? {}, "deepmerge")
        )
      )
      .map(([path]) => path),
    [consumerPath]
  )
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"))
  assert.equal(manifest.devDependencies["@rollup/plugin-node-resolve"], "16.0.3")
  assert.equal(packages[""].devDependencies["@rollup/plugin-node-resolve"], "16.0.3")
  assert.equal(manifest.overrides.deepmerge, undefined)
  assert.deepEqual(manifest.overrides["@rollup/plugin-node-resolve@16.0.3"], {
    deepmerge: "file:./scripts/node-resolve-defaults-clone-compat",
  })
  const target = "scripts/node-resolve-defaults-clone-compat"
  const edge = packages["node_modules/deepmerge"]
  assert.equal(edge.link, true)
  assert.equal(edge.resolved, target)
  assert.equal(packages[target].name, "@university-ecosystem/node-resolve-defaults-clone-compat")
  const scopedName = "@university-ecosystem/node-resolve-defaults-clone-compat"
  assert.deepEqual(packages[`node_modules/${scopedName}`], edge)
  const expectedEntry = realpathSync(
    new URL("./node-resolve-defaults-clone-compat/index.cjs", import.meta.url)
  )
  assert.equal(realpathSync(require.resolve(scopedName)), expectedEntry)
  assert.equal(clone, require(expectedEntry))
  assert.equal(realpathSync(require.resolve("deepmerge")), expectedEntry)
  const entry = require.resolve("@rollup/plugin-node-resolve")
  const source = readFileSync(entry, "utf8")
  assert.equal((source.match(/deepMerge\(/g) ?? []).length, 1)
  assert.ok(source.includes("deepFreeze(deepMerge({}, defaults))"))
  assert.ok(source.includes("const options = { ...defaults, ...opts };"))
  const fromResolver = createRequire(entry)
  assert.equal(realpathSync(fromResolver.resolve("deepmerge")), expectedEntry)
  const esmEntry = import.meta.resolve("@rollup/plugin-node-resolve")
  assert.ok(esmEntry.endsWith("/dist/es/index.js"))
  const esmSource = readFileSync(new URL(esmEntry), "utf8")
  assert.equal((esmSource.match(/deepMerge\(/g) ?? []).length, 1)
  assert.ok(esmSource.includes("deepFreeze(deepMerge({}, defaults))"))
  assert.ok(esmSource.includes("const options = { ...defaults, ...opts };"))
  assert.equal(realpathSync(createRequire(esmEntry).resolve("deepmerge")), expectedEntry)
  const esm = await import("@rollup/plugin-node-resolve")
  const adapter = fromResolver("deepmerge/package.json")
  assert.equal(adapter.name, "@university-ecosystem/node-resolve-defaults-clone-compat")
  assert.equal(adapter.version, "1.0.0")
  assert.equal(adapter.dependencies, undefined)
  assert.equal(adapter.scripts, undefined)
  for (const { DEFAULTS, nodeResolve } of [require("@rollup/plugin-node-resolve"), esm]) {
    assert.deepEqual(DEFAULTS, defaults())
    assert.ok(Object.isFrozen(DEFAULTS))
    for (const value of Object.values(DEFAULTS)) {
      if (Array.isArray(value)) assert.ok(Object.isFrozen(value))
    }
    assert.equal(nodeResolve({ extensions: [".custom"] }).name, "node-resolve")
    assert.deepEqual(DEFAULTS, defaults())
  }
})
