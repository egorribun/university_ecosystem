import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { get } from "node:https"
import { createRequire } from "node:module"
import { dirname, isAbsolute, join, relative, resolve } from "node:path"
import { pathToFileURL } from "node:url"
import {
  NPM_TRANSPORT_ARGS,
  assertNpmCommand,
  npmCommand,
  validateRegistryMetadata,
  verifyArchiveBytes,
} from "./generate-zod-root-lock-candidate.mjs"
import {
  adapterManifest,
  assertImmutableCheckout,
  diagnoseLockScope,
} from "./generate-react-compiler-adapter-lock-candidate.mjs"

const LOCAL = "scripts/react-compiler-zod-compat"
const ALIAS = "node_modules/patched-zod"
const LINK = "node_modules/react-compiler-zod-compat"
const COMPILER = "node_modules/eslint-plugin-react-compiler"
const OLD_ENGINE = COMPILER + "/node_modules/zod"
const FORMATTER = "node_modules/zod-validation-error"
const HOOKS = "node_modules/eslint-plugin-react-hooks"
const HOOKS_FORMATTER = HOOKS + "/node_modules/zod-validation-error"
const ENGINE = "node_modules/zod"
const EXACT_CONSUMER = "eslint-plugin-react-compiler@19.1.0-rc.2"
const SINGLETON_RANGE = ">=19.1.0-rc.2 <=19.1.0-rc.2"
const CONSUMER = "eslint-plugin-react-compiler@" + SINGLETON_RANGE
const FINAL_OVERRIDE = Object.freeze({
  ".": "$eslint-plugin-react-compiler",
  zod: "file:../../scripts/react-compiler-zod-compat",
  "zod-validation-error": Object.freeze({ ".": "4.0.2", zod: "4.6.7" }),
})
const HOOKS_PEER = "^3.0.0 || ^4.0.0 || ^5.0.0 || ^6.0.0 || ^7.0.0 || ^8.0.0-0 || ^9.0.0 || ^10.0.0"
const FORMATTER_PEER = "^3.25.0 || ^4.0.0"
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex")

function assertSourceManifest(manifest) {
  assert.equal(manifest.private, true)
  assert.equal(manifest.packageManager, "npm@11.17.0")
  assert.equal(manifest.devDependencies?.eslint, "^10.12.0")
  assert.equal(manifest.devDependencies?.["eslint-plugin-react-compiler"], "^19.1.0-rc.2")
  assert.equal(manifest.devDependencies?.["eslint-plugin-react-hooks"], "^7.1.1")
  assert.equal(manifest.devDependencies?.["react-compiler-zod-compat"], "file:./" + LOCAL)
  for (const section of ["dependencies", "optionalDependencies", "peerDependencies"]) {
    assert(!Object.hasOwn(manifest[section] ?? {}, "react-compiler-zod-compat"))
  }
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    for (const name of ["zod", "patched-zod"]) {
      assert(!Object.hasOwn(manifest[section] ?? {}, name))
    }
  }
  assert.deepEqual(manifest.overrides?.["eslint-plugin-react-hooks"], {
    "zod-validation-error": "4.0.2",
  })
}

export function prepareFinalManifest(manifest) {
  assertSourceManifest(manifest)
  for (const name of Object.keys(manifest.overrides ?? {})) {
    assert(!/^(?:zod|eslint-plugin-react-compiler)(?:@|$)/.test(name))
  }
  const candidate = structuredClone(manifest)
  candidate.overrides[CONSUMER] = structuredClone(FINAL_OVERRIDE)
  return candidate
}

export function prepareStrictManifest(manifest) {
  assertSourceManifest(manifest)
  assert.deepEqual(manifest.overrides[CONSUMER], FINAL_OVERRIDE)
  return {
    name: "react-compiler-peer-proof",
    version: "1.0.0",
    private: true,
    packageManager: "npm@11.17.0",
    devDependencies: {
      eslint: "10.12.0",
      "eslint-plugin-react-compiler": "19.1.0-rc.2",
      "eslint-plugin-react-hooks": "7.1.1",
      "react-compiler-zod-compat": "file:./" + LOCAL,
      zod: "4.6.7",
    },
    overrides: {
      [CONSUMER]: structuredClone(FINAL_OVERRIDE),
      "eslint-plugin-react-hooks": { "zod-validation-error": "4.0.2" },
    },
  }
}

export function assertFinalSourcePrerequisites(lock) {
  assert.equal(lock.lockfileVersion, 3)
  for (const [path, version] of [
    ["node_modules/body-parser", "1.20.9"],
    ["node_modules/undici", "8.12.2"],
    [COMPILER, "19.1.0-rc.2"],
    [OLD_ENGINE, "3.25.76"],
    [FORMATTER, "3.5.4"],
    [HOOKS_FORMATTER, "4.0.2"],
    [HOOKS, "7.1.1"],
    ["node_modules/eslint", "10.12.0"],
    ["node_modules/@puppeteer/browsers", "3.2.4"],
    ["node_modules/chromium-bidi", "157.0.8090-0"],
    ["node_modules/puppeteer-core", "25.13.0"],
    ["node_modules/puppeteer-core/node_modules/devtools-protocol", "0.0.1696802"],
    ["node_modules/typed-query-selector", "2.12.3"],
    ["node_modules/webdriver-bidi-protocol", "1.0.1"],
  ]) {
    assert.equal(lock.packages[path]?.version, version)
    assert.equal(lock.packages[path].dev, true)
  }
  assert.equal(lock.packages[ENGINE].version, "4.6.7")
  assert(!Object.hasOwn(lock.packages[ENGINE], "dev"))
  assert.deepEqual(lock.packages[ALIAS], {
    name: "zod",
    ...lock.packages[ENGINE],
    dev: true,
  })
  assert.deepEqual(lock.packages[LINK], { resolved: LOCAL, link: true })
  assert.deepEqual(lock.packages[LOCAL], {
    name: adapterManifest().name,
    version: "1.0.0",
    dev: true,
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  })
  assert.equal(lock.packages[""].devDependencies["react-compiler-zod-compat"], "file:./" + LOCAL)
  assert.equal(lock.packages["node_modules/chromium-bidi"].dependencies.zod, "^4.6.5")
  assert.equal(lock.packages[COMPILER].dependencies.zod, "^3.22.4")
  assert.equal(lock.packages[COMPILER].dependencies["zod-validation-error"], "^3.0.3")
  assert.equal(lock.packages[COMPILER].peerDependencies.eslint, ">=7")
  assert.equal(lock.packages[HOOKS].peerDependencies.eslint, HOOKS_PEER)
  assert.equal(lock.packages[HOOKS_FORMATTER].peerDependencies.zod, FORMATTER_PEER)
  assert.deepEqual(
    Object.keys(lock.packages)
      .filter((path) => /(?:^|\/)node_modules\/zod$/.test(path))
      .sort(),
    [OLD_ENGINE, ENGINE]
  )
  assert(!Object.hasOwn(lock.packages, LOCAL + "/node_modules/patched-zod"))
  return true
}

export function validateFormatterMetadata(data, record, now = Date.now()) {
  assert.equal(data.name, "zod-validation-error")
  assert.equal(data.version, "4.0.2")
  assert.equal(data.license, "MIT")
  assert.equal(data.repository?.type, "git")
  assert.equal(data.repository?.url, "git://github.com/causaly/zod-validation-error.git")
  assert.equal(
    data.dist.tarball,
    "https://registry.npmjs.org/zod-validation-error/-/zod-validation-error-4.0.2.tgz"
  )
  assert.match(data.dist.integrity, /^sha512-[A-Za-z0-9+/]{86}==$/)
  assert.match(data.dist.shasum, /^[0-9a-f]{40}$/)
  assert.equal(record.version, data.version)
  assert.equal(record.resolved, data.dist.tarball)
  assert.equal(record.integrity, data.dist.integrity)
  assert.equal(record.license, data.license)
  assert.deepEqual(data.dependencies ?? {}, {})
  assert.deepEqual(data.engines, record.engines)
  assert.deepEqual(data.peerDependencies, { zod: FORMATTER_PEER })
  assert.deepEqual(data.peerDependencies, record.peerDependencies)
  assert(!data.deprecated)
  for (const phase of ["preinstall", "install", "postinstall"]) {
    assert(!data.scripts?.[phase])
  }
  const published = data.time?.["4.0.2"]
  assert.match(published ?? "", /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/)
  const timestamp = Date.parse(published)
  assert(Number.isFinite(now) && Number.isFinite(timestamp))
  assert(timestamp <= now - 7 * 86400000)
  return { data, published, timestamp }
}

export function assertFinalLockScope(original, candidate, formatter) {
  assertFinalSourcePrerequisites(original)
  validateFormatterMetadata(formatter, original.packages[HOOKS_FORMATTER])
  const expected = structuredClone(original)
  expected.packages[OLD_ENGINE] = { resolved: LOCAL, link: true }
  expected.packages[FORMATTER] = structuredClone(original.packages[HOOKS_FORMATTER])
  delete expected.packages[HOOKS_FORMATTER]
  assert.deepEqual(candidate, expected)
  return true
}

function assertConfigPaths(paths) {
  for (const name of ["userconfig", "globalconfig"]) {
    assert(typeof paths[name] === "string")
    assert(isAbsolute(paths[name]) && resolve(paths[name]) === paths[name])
  }
  assert.equal(dirname(paths.userconfig), dirname(paths.globalconfig))
  assert.notEqual(paths.userconfig, paths.globalconfig)
}

export function finalNpmCommand(operation, paths = {}) {
  const operations = {
    generateLock: ["update", "zod", "zod-validation-error", "--package-lock-only"],
    fullGraph: ["ci", "--include=dev"],
    productionGraph: ["ci", "--omit=dev"],
    strictGenerate: ["install", "--package-lock-only"],
    strictInstall: ["ci", "--include=dev"],
    strictList: ["ls", "--all", "--json", "--long"],
  }
  assert(Object.hasOwn(operations, operation))
  const strict = []
  if (operation.startsWith("strict")) {
    assertConfigPaths(paths)
    strict.push(
      "--legacy-peer-deps=false",
      "--strict-peer-deps",
      "--userconfig=" + paths.userconfig,
      "--globalconfig=" + paths.globalconfig
    )
  }
  return Object.freeze([
    ...operations[operation],
    ...strict,
    "--no-audit",
    "--no-fund",
    ...NPM_TRANSPORT_ARGS,
  ])
}

export function assertFinalNpmCommand(operation, args, paths = {}) {
  assert.deepEqual(args, finalNpmCommand(operation, paths))
  return true
}

export function strictPeerEnvironment(original, paths) {
  assertConfigPaths(paths)
  for (const name of ["home", "cache"]) {
    assert(typeof paths[name] === "string")
    assert(isAbsolute(paths[name]) && resolve(paths[name]) === paths[name])
    assert.equal(dirname(paths[name]), dirname(paths.userconfig))
  }
  assert(typeof original.PATH === "string" && original.PATH.length > 0)
  return {
    PATH: original.PATH,
    HOME: paths.home,
    npm_config_cache: paths.cache,
    npm_config_userconfig: paths.userconfig,
    npm_config_globalconfig: paths.globalconfig,
    npm_config_legacy_peer_deps: "false",
    npm_config_strict_peer_deps: "true",
    npm_config_ignore_scripts: "true",
  }
}

function artifactIdentity(record) {
  assert(record && typeof record === "object")
  const identity = { ...record }
  for (const field of ["dev", "devOptional", "optional", "peer"]) delete identity[field]
  return identity
}

export function assertStrictLock(strict, project) {
  assert.equal(strict.lockfileVersion, 3)
  assert.equal(strict.name, "react-compiler-peer-proof")
  assert.equal(strict.version, "1.0.0")
  assert.deepEqual(strict.packages[""].devDependencies, {
    eslint: "10.12.0",
    "eslint-plugin-react-compiler": "19.1.0-rc.2",
    "eslint-plugin-react-hooks": "7.1.1",
    "react-compiler-zod-compat": "file:./" + LOCAL,
    zod: "4.6.7",
  })
  for (const path of [
    COMPILER,
    FORMATTER,
    HOOKS,
    "node_modules/eslint",
    ENGINE,
    ALIAS,
    LINK,
    LOCAL,
    OLD_ENGINE,
  ]) {
    assert.deepEqual(
      artifactIdentity(strict.packages[path]),
      artifactIdentity(project.packages[path])
    )
  }
  assert.equal(strict.packages["node_modules/eslint"].version, "10.12.0")
  assert.equal(strict.packages[COMPILER].version, "19.1.0-rc.2")
  assert.equal(strict.packages[COMPILER].peerDependencies.eslint, ">=7")
  assert.equal(strict.packages[HOOKS].version, "7.1.1")
  assert.equal(strict.packages[HOOKS].peerDependencies.eslint, HOOKS_PEER)
  assert.equal(strict.packages[FORMATTER].version, "4.0.2")
  assert.equal(strict.packages[FORMATTER].peerDependencies.zod, FORMATTER_PEER)
  assert.equal(strict.packages[LOCAL].version, "1.0.0")
  assert.equal(strict.packages[LOCAL].dependencies["patched-zod"], "npm:zod@4.6.7")
  assert.deepEqual(strict.packages[OLD_ENGINE], { resolved: LOCAL, link: true })
  assert(!Object.hasOwn(strict.packages, HOOKS_FORMATTER))
  assert.deepEqual(
    Object.keys(strict.packages)
      .filter((path) => /(?:^|\/)node_modules\/zod$/.test(path))
      .sort(),
    [OLD_ENGINE, ENGINE]
  )
  return true
}

function regularBytes(path, limit) {
  const stat = lstatSync(path, { throwIfNoEntry: false })
  assert(stat?.isFile() && !stat.isSymbolicLink())
  assert(stat.size > 0 && stat.size <= limit)
  assert.equal(realpathSync(path), path)
  const bytes = readFileSync(path)
  assert.equal(bytes.length, stat.size)
  return bytes
}

function packageMetadata(path) {
  return JSON.parse(regularBytes(path, 32768))
}

export function inspectInstalledEngineLicense(frontend) {
  assert.equal(realpathSync(frontend), frontend)
  const directory = join(frontend, ALIAS)
  const stat = lstatSync(directory, { throwIfNoEntry: false })
  assert(stat?.isDirectory() && !stat.isSymbolicLink())
  assert.equal(realpathSync(directory), directory)
  const manifest = packageMetadata(join(directory, "package.json"))
  assert.equal(manifest.name, "zod")
  assert.equal(manifest.version, "4.6.7")
  assert.equal(manifest.license, "MIT")
  const license = regularBytes(join(directory, "LICENSE"), 8192)
  return {
    packageName: manifest.name,
    version: manifest.version,
    declaredLicense: manifest.license,
    licenseFile: { bytes: license.length, sha256: digest(license) },
  }
}

export function assertLocalOverrideTarget(frontend, consumer, target) {
  assert.equal(realpathSync(frontend), frontend)
  assert.equal(consumer, join(frontend, COMPILER))
  assert.equal(target, join(frontend, LOCAL))
  assert.equal(realpathSync(target), target)
  assert.deepEqual(packageMetadata(join(target, "package.json")), adapterManifest())
  return true
}

export function inspectOverrideSelector(toolRoot, manifest, frontend) {
  assert.equal(realpathSync(toolRoot), toolRoot)
  assertSourceManifest(manifest)
  assert.deepEqual(manifest.overrides[CONSUMER], FINAL_OVERRIDE)
  const npmPath = join(toolRoot, "package.json")
  const npmMetadata = packageMetadata(npmPath)
  assert.equal(npmMetadata.name, "npm")
  assert.equal(npmMetadata.version, "11.17.0")
  const toolRequire = createRequire(npmPath)
  const packages = {}
  for (const [name, version] of [
    ["semver", "7.8.4"],
    ["@npmcli/arborist", "9.8.0"],
    ["npm-package-arg", "13.0.2"],
  ]) {
    const packagePath = toolRequire.resolve(name + "/package.json")
    assert.equal(packagePath, join(toolRoot, "node_modules", name, "package.json"))
    const metadata = packageMetadata(packagePath)
    assert.equal(metadata.name, name)
    assert.equal(metadata.version, version)
    packages[name] = { path: dirname(packagePath), version: metadata.version }
  }
  assert.equal(realpathSync(frontend), frontend)
  const npaPath = toolRequire.resolve("npm-package-arg")
  assert(npaPath.startsWith(packages["npm-package-arg"].path + "/"))
  regularBytes(npaPath, 128 * 1024)
  const buildPath = join(packages["@npmcli/arborist"].path, "lib/arborist/build-ideal-tree.js")
  regularBytes(buildPath, 128 * 1024)
  const arboristRequire = createRequire(buildPath)
  assert.equal(arboristRequire.resolve("npm-package-arg"), npaPath)
  assert.equal(
    arboristRequire.resolve("npm-package-arg/package.json"),
    join(packages["npm-package-arg"].path, "package.json")
  )
  const semverPath = toolRequire.resolve("semver")
  assert(semverPath.startsWith(packages.semver.path + "/"))
  regularBytes(semverPath, 128 * 1024)
  const overridePath = join(packages["@npmcli/arborist"].path, "lib/override-set.js")
  regularBytes(overridePath, 128 * 1024)
  const nodePath = join(packages["@npmcli/arborist"].path, "lib/node.js")
  const edgePath = join(packages["@npmcli/arborist"].path, "lib/edge.js")
  regularBytes(nodePath, 128 * 1024)
  regularBytes(edgePath, 128 * 1024)
  // Only the already verified npm tool's own resolver is inspected. No project
  // package entrypoint or npm install/update operation is invoked here.
  const npa = toolRequire(npaPath)
  const semver = toolRequire(semverPath)
  const OverrideSet = toolRequire(overridePath)
  const Node = toolRequire(nodePath)
  const Edge = toolRequire(edgePath)
  // Retain the previously observed exact-selector failure as a separate control.
  const baselineOverrides = structuredClone(manifest.overrides)
  delete baselineOverrides[CONSUMER]
  baselineOverrides[EXACT_CONSUMER] = structuredClone(FINAL_OVERRIDE)
  delete baselineOverrides[EXACT_CONSUMER]["."]
  baselineOverrides[EXACT_CONSUMER].zod = "$react-compiler-zod-compat"
  const baseline = new OverrideSet({ overrides: baselineOverrides })
  const selected = new OverrideSet({ overrides: structuredClone(manifest.overrides) })
  const name = "eslint-plugin-react-compiler"
  const version = "19.1.0-rc.2"
  const range = manifest.devDependencies[name]
  const edge = { name, rawSpec: range, spec: range }
  const node = { name, version }
  const identity = (root, rule, key) => {
    if (rule === root) return null
    assert.equal(rule?.key, key)
    return rule.key
  }
  const boolean = (value) => {
    assert.equal(typeof value, "boolean")
    return value
  }
  const selectedIdentity = (rule) => identity(selected, rule, CONSUMER)
  // Node and Edge model this one direct dependency in memory; no tree is loaded
  // from disk and no installer runs. The reference must preserve its raw spec.
  const directRoot = (override) =>
    new Node({
      path: frontend,
      loadOverrides: true,
      pkg: {
        name: "react-compiler-selector-control",
        version: "1.0.0",
        devDependencies: {
          [name]: range,
          "react-compiler-zod-compat": manifest.devDependencies["react-compiler-zod-compat"],
        },
        overrides: { [CONSUMER]: structuredClone(override) },
      },
    })
  const direct = directRoot(FINAL_OVERRIDE)
  const directEdge = direct.edgesOut.get(name)
  assert(directEdge instanceof Edge)
  assert.equal(directEdge.overrides.key, CONSUMER)
  direct.assertRootOverrides()
  const withoutReference = structuredClone(FINAL_OVERRIDE)
  delete withoutReference["."]
  assert.throws(() => directRoot(withoutReference).assertRootOverrides(), {
    code: "EOVERRIDE",
  })
  const localDependency = (override) => {
    const consumer = new Node({
      parent: directRoot(override),
      pkg: { name, version, dependencies: { zod: "^3.22.4" } },
    })
    assert.equal(consumer.path, join(frontend, COMPILER))
    const dependency = consumer.edgesOut.get("zod")
    assert(dependency instanceof Edge)
    assert.equal(dependency.rawSpec, "^3.22.4")
    const parsed = npa.resolve(dependency.name, dependency.spec, dependency.from.path)
    assert.equal(parsed.type, "directory")
    return { consumer, dependency, target: parsed.fetchSpec }
  }
  const originalReference = structuredClone(FINAL_OVERRIDE)
  originalReference.zod = "$react-compiler-zod-compat"
  const misplaced = localDependency(originalReference)
  const corrected = localDependency(FINAL_OVERRIDE)
  assert.equal(misplaced.target, join(frontend, COMPILER, LOCAL))
  assertLocalOverrideTarget(frontend, corrected.consumer.path, corrected.target)
  const versionChecks = [
    "19.1.0-rc.1",
    "19.1.0-rc.2",
    "19.1.0-rc.2+fixture",
    "19.1.0-rc.3",
    "19.1.0",
    "19.1.1-rc.2",
    "20.0.0",
  ].map((candidate) => ({
    version: candidate,
    exact: boolean(semver.satisfies(candidate, version)),
    selected: boolean(semver.satisfies(candidate, SINGLETON_RANGE)),
    nodeAttached: selectedIdentity(selected.getNodeRule({ name, version: candidate })) !== null,
  }))
  const result = {
    kind: "react-compiler-override-selector-diagnostic",
    npm: npmMetadata.version,
    semver: packages.semver.version,
    arborist: packages["@npmcli/arborist"].version,
    packageName: name,
    declaredRange: range,
    installedVersion: version,
    selectorVersion: version,
    satisfiesRange: boolean(semver.satisfies(version, range)),
    satisfiesSelector: boolean(semver.satisfies(version, version)),
    intersectsSelector: boolean(semver.intersects(range, version)),
    edgeRule: identity(baseline, baseline.getEdgeRule(edge), EXACT_CONSUMER),
    nodeRule: identity(baseline, baseline.getNodeRule(node), EXACT_CONSUMER),
    selectedSelector: {
      range: SINGLETON_RANGE,
      satisfies: boolean(semver.satisfies(version, SINGLETON_RANGE)),
      intersects: boolean(semver.intersects(range, SINGLETON_RANGE)),
      edgeRule: selectedIdentity(selected.getEdgeRule(edge)),
      nodeRule: selectedIdentity(selected.getNodeRule(node)),
    },
    versionChecks,
    directDependency: {
      rawSpec: directEdge.rawSpec,
      effectiveSpec: directEdge.spec,
      rootOverrideAccepted: true,
      missingReferenceError: "EOVERRIDE",
    },
    localDependency: {
      parser: "npm-package-arg",
      parserVersion: packages["npm-package-arg"].version,
      rawSpec: corrected.dependency.rawSpec,
      baselineSpec: misplaced.dependency.spec,
      baselineTarget: relative(frontend, misplaced.target),
      selectedSpec: corrected.dependency.spec,
      selectedTarget: relative(frontend, corrected.target),
      targetCanonical: true,
    },
    candidateAccepted: false,
  }
  assert(Buffer.byteLength(JSON.stringify(result)) <= 2048)
  return result
}

export function assertOverrideSelectorControl(report) {
  const versionChecks = [
    ["19.1.0-rc.1", false],
    ["19.1.0-rc.2", true],
    ["19.1.0-rc.2+fixture", true],
    ["19.1.0-rc.3", false],
    ["19.1.0", false],
    ["19.1.1-rc.2", false],
    ["20.0.0", false],
  ].map(([version, accepted]) => ({
    version,
    exact: accepted,
    selected: accepted,
    nodeAttached: accepted,
  }))
  assert.deepEqual(report, {
    kind: "react-compiler-override-selector-diagnostic",
    npm: "11.17.0",
    semver: "7.8.4",
    arborist: "9.8.0",
    packageName: "eslint-plugin-react-compiler",
    declaredRange: "^19.1.0-rc.2",
    installedVersion: "19.1.0-rc.2",
    selectorVersion: "19.1.0-rc.2",
    satisfiesRange: true,
    satisfiesSelector: true,
    intersectsSelector: false,
    edgeRule: null,
    nodeRule: EXACT_CONSUMER,
    selectedSelector: {
      range: SINGLETON_RANGE,
      satisfies: true,
      intersects: true,
      edgeRule: CONSUMER,
      nodeRule: CONSUMER,
    },
    versionChecks,
    directDependency: {
      rawSpec: "^19.1.0-rc.2",
      effectiveSpec: "^19.1.0-rc.2",
      rootOverrideAccepted: true,
      missingReferenceError: "EOVERRIDE",
    },
    localDependency: {
      parser: "npm-package-arg",
      parserVersion: "13.0.2",
      rawSpec: "^3.22.4",
      baselineSpec: "file:./scripts/react-compiler-zod-compat",
      baselineTarget: COMPILER + "/" + LOCAL,
      selectedSpec: "file:../../scripts/react-compiler-zod-compat",
      selectedTarget: LOCAL,
      targetCanonical: true,
    },
    candidateAccepted: false,
  })
  return true
}

export function assertFinalInstalledGraph(frontend, mode, controls) {
  assert(mode === "full" || mode === "production")
  assert.equal(realpathSync(frontend), frontend)
  const rootPath = join(frontend, ENGINE, "package.json")
  const root = packageMetadata(rootPath)
  assert.equal(root.name, "zod")
  assert.equal(root.version, "4.6.7")
  assert(!existsSync(join(frontend, LOCAL, "node_modules/patched-zod")))
  if (mode === "production") {
    for (const path of [ALIAS, LINK, COMPILER, FORMATTER, HOOKS]) {
      assert(!lstatSync(join(frontend, path), { throwIfNoEntry: false }))
    }
    return true
  }
  const local = join(frontend, LOCAL)
  assert.equal(realpathSync(local), local)
  assert.equal(realpathSync(join(frontend, LINK)), local)
  assert.equal(realpathSync(join(frontend, OLD_ENGINE)), local)
  const localPath = join(local, "package.json")
  assert.deepEqual(packageMetadata(localPath), adapterManifest())
  const enginePath = createRequire(localPath).resolve("patched-zod/package.json")
  assert.equal(enginePath, join(frontend, ALIAS, "package.json"))
  const engine = packageMetadata(enginePath)
  assert.equal(engine.name, "zod")
  assert.equal(engine.version, "4.6.7")
  const compilerPath = join(frontend, COMPILER, "package.json")
  const compiler = packageMetadata(compilerPath)
  assert.equal(compiler.name, "eslint-plugin-react-compiler")
  assert.equal(compiler.version, "19.1.0-rc.2")
  assert.deepEqual(compiler.dependencies, controls.compilerDependencies)
  assert.equal(compiler.peerDependencies.eslint, ">=7")
  const compilerRequire = createRequire(compilerPath)
  assert.equal(realpathSync(compilerRequire.resolve("zod/package.json")), localPath)
  const compilerEntry = compilerRequire.resolve("./")
  assert(compilerEntry.startsWith(join(frontend, COMPILER) + "/"))
  assert.match(controls.compilerBundleSha256 ?? "", /^[0-9a-f]{64}$/)
  assert.equal(digest(regularBytes(compilerEntry, 8 * 1024 * 1024)), controls.compilerBundleSha256)
  const formatterPath = join(frontend, FORMATTER, "package.json")
  const formatter = packageMetadata(formatterPath)
  const formatterEntry = compilerRequire.resolve("zod-validation-error")
  assert.equal(formatterEntry, resolve(frontend, FORMATTER, formatter.main))
  regularBytes(formatterEntry, 1024 * 1024)
  assert.equal(formatter.name, "zod-validation-error")
  assert.equal(formatter.version, "4.0.2")
  assert.equal(formatter.peerDependencies.zod, FORMATTER_PEER)
  assert.equal(createRequire(formatterPath).resolve("zod/package.json"), rootPath)
  for (const [name, version] of [
    ["eslint", "10.12.0"],
    ["eslint-plugin-react-hooks", "7.1.1"],
  ]) {
    const installed = packageMetadata(join(frontend, "node_modules", name, "package.json"))
    assert.equal(installed.name, name)
    assert.equal(installed.version, version)
    if (name === "eslint-plugin-react-hooks") {
      assert.equal(installed.peerDependencies.eslint, HOOKS_PEER)
    }
  }
  return true
}

export async function runFinalCompilerGenerator() {
  let stage = "preflight"
  let scratch
  let snapshots
  const copied = []
  let git
  let sourceTree
  let report
  let patch
  let candidateManifestBytes
  let failed = false
  const deadline = performance.now() + 7 * 60_000
  const remaining = (cap) => {
    const budget = Math.floor(deadline - performance.now())
    assert(budget > 0, "Generation deadline exceeded")
    return Math.min(cap, budget)
  }
  const reject = () => {
    failed = true
    console.error("Final compiler candidate rejected at stage: " + stage)
  }
  try {
    const workspace = realpathSync(process.env.GITHUB_WORKSPACE)
    const frontend = join(workspace, "frontend")
    assert.equal(realpathSync(process.cwd()), frontend)
    const sourceNames = [
      "frontend/package.json",
      "frontend/package-lock.json",
      "frontend/.npmrc",
      "frontend/" + LOCAL + "/package.json",
      "frontend/" + LOCAL + "/legacy-baseline.json",
    ]
    snapshots = sourceNames.map((name) => {
      const path = join(workspace, name)
      return { path, bytes: regularBytes(path, 4 * 1024 * 1024) }
    })
    const [manifestBytes, lockBytes, configBytes, localManifestBytes, goldenBytes] = snapshots.map(
      (item) => item.bytes
    )
    const manifest = JSON.parse(manifestBytes)
    const lock = JSON.parse(lockBytes)
    const golden = JSON.parse(goldenBytes)
    assert.equal(golden.kind, "react-compiler-legacy-baseline")
    assert.equal(golden.schemaVersion, 1)
    assert.equal(golden.compilerVersion, "19.1.0-rc.2")
    assert.equal(golden.compilerIntegrity, lock.packages[COMPILER].integrity)
    assert.match(golden.compilerBundleSha256, /^[0-9a-f]{64}$/)
    const controls = {
      compilerBundleSha256: golden.compilerBundleSha256,
      compilerDependencies: lock.packages[COMPILER].dependencies,
    }
    assert.deepEqual(JSON.parse(localManifestBytes), adapterManifest())
    scratch = mkdtempSync(join(realpathSync(process.env.RUNNER_TEMP), "compiler-final-lock-"))
    const userConfig = join(scratch, "empty-user.npmrc")
    const globalConfig = join(scratch, "empty-global.npmrc")
    writeFileSync(userConfig, "", { flag: "wx", mode: 0o400 })
    writeFileSync(globalConfig, "", { flag: "wx", mode: 0o400 })
    const npmEnv = {
      PATH: dirname(process.execPath) + ":/usr/bin:/bin",
      HOME: scratch,
      TMPDIR: scratch,
      CI: "true",
      NO_COLOR: "1",
      NPM_CONFIG_USERCONFIG: userConfig,
      NPM_CONFIG_GLOBALCONFIG: globalConfig,
      NPM_CONFIG_CACHE: join(scratch, "cache"),
      NPM_CONFIG_REGISTRY: "https://registry.npmjs.org/",
    }
    function command(executable, args, cwd, options = {}) {
      const result = spawnSync(executable, args, {
        cwd,
        env: options.env ?? npmEnv,
        encoding: "utf8",
        shell: false,
        timeout: options.postflight ? 10_000 : remaining(options.timeout ?? 120_000),
        maxBuffer: 4 * 1024 * 1024,
      })
      assert(!result.error && !result.signal && result.status === 0)
      return result.stdout
    }
    git = (args, postflight = false) =>
      command("/usr/bin/git", args, workspace, { timeout: 10_000, postflight })
    assertImmutableCheckout({
      expectedSha: process.env.SOURCE_SHA,
      head: git(["rev-parse", "HEAD"]).trim(),
      status: git(["status", "--porcelain=v1", "--untracked-files=all"]),
      node: process.version,
      repository: process.env.GITHUB_REPOSITORY,
      hasNodeModules: existsSync(join(frontend, "node_modules")),
    })
    sourceTree = git(["rev-parse", "HEAD^{tree}"]).trim()
    assert.match(sourceTree, /^[0-9a-f]{40}$/)
    assert.equal(
      configBytes.toString(),
      "legacy-peer-deps=true\nengine-strict=true\nmin-release-age=7\nstrict-allow-scripts=true\n"
    )
    assertFinalSourcePrerequisites(lock)
    const candidateManifest = prepareFinalManifest(manifest)
    candidateManifestBytes = Buffer.from(JSON.stringify(candidateManifest, null, 2) + "\n")
    const localDirectories = []
    for (const section of ["dependencies", "devDependencies", "optionalDependencies"]) {
      for (const value of Object.values(manifest[section] ?? {})) {
        if (typeof value === "string" && value.startsWith("file:")) {
          localDirectories.push(value.slice(5).replace(/^\.\//, ""))
        }
      }
    }
    assert.deepEqual(localDirectories.sort(), [
      "scripts/boundary-micromatch-compat",
      LOCAL,
      "wasm-sanitizer/pkg",
    ])
    stage = "bounded isolated source inputs"
    let copiedBytes = 0
    for (const directory of localDirectories) {
      const sourceDirectory = join(frontend, directory)
      assert.equal(realpathSync(sourceDirectory), sourceDirectory)
      assert(lstatSync(sourceDirectory).isDirectory())
      const names = git(["ls-files", "-z", "--", "frontend/" + directory])
        .split("\0")
        .filter(Boolean)
      assert(names.includes("frontend/" + directory + "/package.json"))
      for (const name of names) {
        remaining(1)
        assert(name.startsWith("frontend/" + directory + "/"))
        const path = join(workspace, name)
        const bytes = regularBytes(path, 16 * 1024 * 1024)
        const rel = relative(frontend, path)
        assert(!rel.startsWith("../") && !rel.startsWith("/") && !rel.includes("\\"))
        assert(!rel.split("/").includes("node_modules"))
        copiedBytes += bytes.length
        assert(copiedBytes <= 64 * 1024 * 1024 && copied.length < 1024)
        copied.push({ path, rel, bytes })
      }
    }
    function mirror(name, rootManifest, rootLock, strict = false) {
      const target = join(scratch, name)
      mkdirSync(target)
      const files = [
        ["package.json", rootManifest],
        ...copied
          .filter((item) => !strict || item.rel.startsWith(LOCAL + "/"))
          .map((item) => [item.rel, item.bytes]),
      ]
      if (rootLock) files.push(["package-lock.json", rootLock])
      if (!strict) files.push([".npmrc", configBytes])
      for (const [path, bytes] of files) {
        const destination = join(target, path)
        mkdirSync(dirname(destination), { recursive: true })
        writeFileSync(destination, bytes, { flag: "wx" })
      }
      return target
    }
    const generation = mirror("generation", candidateManifestBytes, lockBytes)
    const bootstrap = realpathSync(join(dirname(process.execPath), "npm"))
    assert.equal(
      bootstrap,
      join(dirname(dirname(process.execPath)), "lib/node_modules/npm/bin/npm-cli.js")
    )
    function npm(cli, operation, cwd, paths = {}, env = npmEnv) {
      const helper = ["version", "toolMetadata", "targetMetadata", "toolInstall"].includes(
        operation
      )
      const args = helper ? npmCommand(operation, paths) : finalNpmCommand(operation, paths)
      if (helper) assertNpmCommand(operation, args, paths)
      else assertFinalNpmCommand(operation, args, paths)
      return command(process.execPath, [cli, ...args], cwd, { env })
    }
    assert.equal(npm(bootstrap, "version", generation).trim(), "11.19.0")
    async function verifiedArchive(meta, destination, limit) {
      const timeout = remaining(30000)
      const bytes = await new Promise((resolveBytes, rejectArchive) => {
        const chunks = []
        let size = 0
        const request = get(
          meta.dist.tarball,
          { headers: { Accept: "application/octet-stream" } },
          (response) => {
            if (response.statusCode !== 200) {
              response.destroy()
              rejectArchive(new Error("Non-200 archive response"))
              return
            }
            response.on("data", (chunk) => {
              size += chunk.length
              if (size > limit) request.destroy(new Error("Archive size exceeded"))
              else chunks.push(chunk)
            })
            response.on("error", rejectArchive)
            response.on("end", () => resolveBytes(Buffer.concat(chunks)))
          }
        )
        const timer = setTimeout(() => request.destroy(new Error("Archive timeout")), timeout)
        request.on("close", () => clearTimeout(timer))
        request.on("error", rejectArchive)
      })
      verifyArchiveBytes(meta, bytes, limit)
      writeFileSync(destination, bytes, { flag: "wx", mode: 0o600 })
    }

    stage = "npm tool metadata and archive verification"
    const toolMetadata = validateRegistryMetadata(
      JSON.parse(npm(bootstrap, "toolMetadata", generation)),
      "npm",
      "11.17.0"
    )
    const toolArchive = join(scratch, "npm-11.17.0.tgz")
    await verifiedArchive(toolMetadata.data, toolArchive, 16 * 1024 * 1024)
    stage = "isolated npm tool installation"
    const toolPrefix = join(scratch, "tool")
    mkdirSync(toolPrefix)
    npm(bootstrap, "toolInstall", scratch, { prefix: toolPrefix, archive: toolArchive })
    const cli = realpathSync(join(toolPrefix, "node_modules/npm/bin/npm-cli.js"))
    assert(cli.startsWith(toolPrefix + "/"))
    assert.equal(npm(cli, "version", generation).trim(), "11.17.0")

    stage = "mature patched engine metadata and archive verification"
    const engine = validateRegistryMetadata(
      JSON.parse(npm(cli, "targetMetadata", generation)),
      "zod",
      "4.6.7"
    )
    assert.equal(engine.data.dist.tarball, lock.packages[ENGINE].resolved)
    assert.equal(engine.data.dist.integrity, lock.packages[ENGINE].integrity)
    assert.equal(engine.data.license, lock.packages[ENGINE].license)
    assert.deepEqual(engine.data.dependencies ?? {}, {})
    await verifiedArchive(engine.data, join(scratch, "zod-4.6.7.tgz"), 4 * 1024 * 1024)
    stage = "mature formatter metadata and archive verification"
    const formatter = validateFormatterMetadata(
      JSON.parse(
        command(
          process.execPath,
          [cli, "view", "zod-validation-error@4.0.2", "--json", ...NPM_TRANSPORT_ARGS],
          generation
        )
      ),
      lock.packages[HOOKS_FORMATTER]
    )
    await verifiedArchive(
      formatter.data,
      join(scratch, "zod-validation-error-4.0.2.tgz"),
      4 * 1024 * 1024
    )

    stage = "pinned npm override selector diagnostic"
    const selectorDiagnostic = inspectOverrideSelector(
      dirname(dirname(cli)),
      candidateManifest,
      generation
    )
    console.log("FINAL_COMPILER_OVERRIDE_DIAGNOSTIC " + JSON.stringify(selectorDiagnostic))
    assertOverrideSelectorControl(selectorDiagnostic)

    stage = "isolated final consumer lock generation"
    npm(cli, "generateLock", generation)
    const candidatePath = join(generation, "package-lock.json")
    const candidateBytes = regularBytes(candidatePath, 4 * 1024 * 1024)
    const candidate = JSON.parse(candidateBytes)
    stage = "whole-lock scope verification"
    try {
      assertFinalLockScope(lock, candidate, formatter.data)
    } catch {
      const diagnostic = JSON.stringify(diagnoseLockScope(lock, candidate))
      assert(Buffer.byteLength(diagnostic) <= 16384)
      console.error("FINAL_COMPILER_REJECTED_SCOPE " + diagnostic)
      throw new Error("Rejected generated lock scope")
    }
    assert(!existsSync(join(generation, "node_modules")))
    assert.deepEqual(readFileSync(join(generation, "package.json")), candidateManifestBytes)
    assert.deepEqual(readFileSync(join(generation, ".npmrc")), configBytes)
    assert.deepEqual(readFileSync(join(generation, LOCAL, "package.json")), localManifestBytes)

    let licenseEvidence
    for (const [name, operation, mode] of [
      ["full", "fullGraph", "full"],
      ["production", "productionGraph", "production"],
    ]) {
      stage = name + " project-configured graph installation"
      const target = mirror(name, candidateManifestBytes, candidateBytes)
      npm(cli, operation, target)
      stage = name + " project-configured physical graph verification"
      assertFinalInstalledGraph(target, mode, controls)
      if (mode === "full") licenseEvidence = inspectInstalledEngineLicense(target)
      assert.deepEqual(readFileSync(join(target, "package.json")), candidateManifestBytes)
      assert.deepEqual(readFileSync(join(target, "package-lock.json")), candidateBytes)
      assert.deepEqual(readFileSync(join(target, ".npmrc")), configBytes)
      assert.deepEqual(readFileSync(join(target, LOCAL, "package.json")), localManifestBytes)
    }

    stage = "isolated strict peer fixture preparation"
    const strictPaths = {
      home: join(scratch, "strict-home"),
      cache: join(scratch, "strict-cache"),
      userconfig: join(scratch, "strict-user.npmrc"),
      globalconfig: join(scratch, "strict-global.npmrc"),
    }
    mkdirSync(strictPaths.home)
    mkdirSync(strictPaths.cache)
    for (const path of [strictPaths.userconfig, strictPaths.globalconfig]) {
      writeFileSync(path, "", { flag: "wx", mode: 0o400 })
    }
    const strictEnvironment = strictPeerEnvironment(npmEnv, strictPaths)
    const strictManifest = Buffer.from(
      JSON.stringify(prepareStrictManifest(candidateManifest), null, 2) + "\n"
    )
    const strict = mirror("strict", strictManifest, null, true)
    assert(!existsSync(join(strict, ".npmrc")))
    stage = "isolated strict peer lock generation"
    npm(cli, "strictGenerate", strict, strictPaths, strictEnvironment)
    const strictLockBytes = regularBytes(join(strict, "package-lock.json"), 4 * 1024 * 1024)
    assertStrictLock(JSON.parse(strictLockBytes), candidate)
    stage = "isolated strict peer installation"
    npm(cli, "strictInstall", strict, strictPaths, strictEnvironment)
    stage = "isolated strict peer physical graph and npm ls verification"
    assertFinalInstalledGraph(strict, "full", controls)
    assert.deepEqual(inspectInstalledEngineLicense(strict), licenseEvidence)
    const strictListing = JSON.parse(npm(cli, "strictList", strict, strictPaths, strictEnvironment))
    assert.equal(strictListing.name, "react-compiler-peer-proof")
    assert.equal(strictListing.version, "1.0.0")
    assert.deepEqual(strictListing.problems ?? [], [])
    assert.deepEqual(readFileSync(join(strict, "package.json")), strictManifest)
    assert.deepEqual(readFileSync(join(strict, "package-lock.json")), strictLockBytes)
    assert(!existsSync(join(strict, ".npmrc")))
    for (const path of [
      userConfig,
      globalConfig,
      strictPaths.userconfig,
      strictPaths.globalconfig,
    ]) {
      assert.equal(readFileSync(path).length, 0)
    }
    for (const item of copied) assert.deepEqual(readFileSync(item.path), item.bytes)

    stage = "bounded generated candidate diff"
    function diff(before, after, path) {
      const result = spawnSync(
        "/usr/bin/git",
        ["diff", "--no-index", "--no-ext-diff", "--no-color", "--", before, after],
        {
          cwd: workspace,
          env: npmEnv,
          encoding: "utf8",
          shell: false,
          timeout: remaining(10_000),
          maxBuffer: 32 * 1024,
        }
      )
      assert(!result.error && !result.signal && result.status === 1)
      return result.stdout
        .replace(/^diff --git .*$/m, "diff --git a/" + path + " b/" + path)
        .replace(/^--- .*$/m, "--- a/" + path)
        .replace(/^\+\+\+ .*$/m, "+++ b/" + path)
    }
    patch =
      diff(snapshots[0].path, join(generation, "package.json"), "frontend/package.json") +
      diff(snapshots[1].path, candidatePath, "frontend/package-lock.json")
    assert(Buffer.byteLength(patch) > 0 && Buffer.byteLength(patch) <= 16384)
    report = {
      kind: "react-compiler-final-lock-candidate",
      sourceSha: process.env.SOURCE_SHA,
      sourceTree,
      node: process.version,
      npm: "11.17.0",
      bootstrapNpm: "11.19.0",
      registry: "https://registry.npmjs.org/",
      compiler: {
        version: "19.1.0-rc.2",
        integrity: golden.compilerIntegrity,
        bundleSha256: golden.compilerBundleSha256,
        originalArtifactPreserved: true,
      },
      patchedEngine: {
        name: engine.data.name,
        version: engine.data.version,
        published: engine.published,
        integrity: engine.data.dist.integrity,
        registryGitHead: engine.data.gitHead,
        tarballVerified: true,
      },
      formatter: {
        name: formatter.data.name,
        version: formatter.data.version,
        published: formatter.published,
        integrity: formatter.data.dist.integrity,
        peerDependencies: formatter.data.peerDependencies,
        tarballVerified: true,
      },
      engineLicense: licenseEvidence,
      licenseEvidenceScope: "physical package metadata and LICENSE bytes; not scanner disposition",
      changedPackagePaths: [OLD_ENGINE, FORMATTER],
      removedPackagePaths: [HOOKS_FORMATTER],
      consumerOverrideAdded: true,
      globalZodOverrideAdded: false,
      fullGraphInstallVerified: true,
      productionGraphInstallVerified: true,
      graphInstallPolicy: "project-configured legacy-peer-deps=true; ignore-scripts",
      strictPeerCompatibilityVerified: true,
      strictPeerScope: "isolated exact-version dev-tool fixture, not the entire project",
      strictPeerVersions: {
        eslint: "10.12.0",
        compiler: "19.1.0-rc.2",
        hooks: "7.1.1",
        formatter: "4.0.2",
        facade: "1.0.0",
        zod: "4.6.7",
      },
      strictPeerDeclarations: {
        compilerEslint: ">=7",
        hooksEslint: HOOKS_PEER,
        formatterZod: FORMATTER_PEER,
      },
      strictNpmLsVerified: true,
      strictLegacyPeerDeps: false,
      cooldownException: false,
      compilerDiagnosticParityVerified: false,
      normalLifecycleOrBuildVerified: false,
      cryptographicPublishProvenanceVerified: false,
      projectLibraryCodeExecuted: false,
      lifecycleScriptsExecuted: false,
      checkoutModified: false,
      originalManifestSha256: digest(manifestBytes),
      candidateManifestSha256: digest(candidateManifestBytes),
      originalLockSha256: digest(lockBytes),
      candidateLockSha256: digest(candidateBytes),
      strictLockSha256: digest(strictLockBytes),
      projectNpmrcSha256: digest(configBytes),
      npmToolPublished: toolMetadata.published,
      npmToolIntegrity: toolMetadata.data.dist.integrity,
    }
  } catch {
    reject()
  } finally {
    try {
      stage = "original source verification"
      for (const item of [...(snapshots ?? []), ...copied]) {
        assert.deepEqual(readFileSync(item.path), item.bytes)
      }
      if (git) {
        assert.equal(git(["rev-parse", "HEAD"], true).trim(), process.env.SOURCE_SHA)
        if (sourceTree) assert.equal(git(["rev-parse", "HEAD^{tree}"], true).trim(), sourceTree)
        assert.equal(git(["status", "--porcelain=v1", "--untracked-files=all"], true), "")
      }
    } catch {
      reject()
    } finally {
      stage = "temporary workspace cleanup"
      try {
        if (scratch) rmSync(scratch, { recursive: true, force: true })
      } catch {
        reject()
      }
    }
  }
  if (failed) return 1
  console.log("FINAL_COMPILER_CANDIDATE_METADATA " + JSON.stringify(report))
  console.log(
    "FINAL_COMPILER_CANDIDATE_PATCH_BEGIN\n" + patch + "FINAL_COMPILER_CANDIDATE_PATCH_END"
  )
  console.log(
    "Source unchanged; isolated graph proof does not establish compiler parity, a passing audit or normal CI."
  )
  return 0
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  process.exitCode = await runFinalCompilerGenerator()
}
