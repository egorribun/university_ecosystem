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
import { dirname, join, resolve } from "node:path"
import { pathToFileURL } from "node:url"

import {
  assertImmutableCheckout,
  diagnoseLockScope,
  stagedNpmCommand,
} from "./generate-react-compiler-adapter-lock-candidate.mjs"
import {
  NPM_TRANSPORT_ARGS,
  npmCommand,
  validateRegistryMetadata,
  verifyArchiveBytes,
} from "./generate-zod-root-lock-candidate.mjs"

const TARGETS = Object.freeze(
  [
    ["puppeteer-core", "25.11.0", "25.13.0", "node_modules/puppeteer-core"],
    ["@puppeteer/browsers", "3.2.2", "3.2.4", "node_modules/@puppeteer/browsers"],
    ["chromium-bidi", "17.0.2", "157.0.8090-0", "node_modules/chromium-bidi"],
    [
      "devtools-protocol",
      "0.0.1680125",
      "0.0.1696802",
      "node_modules/puppeteer-core/node_modules/devtools-protocol",
    ],
    ["typed-query-selector", "2.12.2", "2.12.3", "node_modules/typed-query-selector"],
    ["webdriver-bidi-protocol", "0.4.3", "1.0.1", "node_modules/webdriver-bidi-protocol"],
  ].map(([name, from, to, path]) => Object.freeze({ name, from, to, path }))
)
const REMOVED = "node_modules/chromium-bidi/node_modules/zod"
const DAY = 86_400_000
const INSTALL_FIELDS = [
  "dependencies",
  "bin",
  "engines",
  "peerDependencies",
  "peerDependenciesMeta",
]
const EXPECTED_GRAPH = {
  "puppeteer-core": {
    license: "Apache-2.0",
    dependencies: {
      "@puppeteer/browsers": "3.2.4",
      "chromium-bidi": "157.0.8090-0",
      "devtools-protocol": "0.0.1696802",
      "typed-query-selector": "^2.12.3",
      "webdriver-bidi-protocol": "1.0.1",
      ws: "^8.21.3",
    },
    engines: { node: ">=22.12.0" },
  },
  "@puppeteer/browsers": {
    license: "Apache-2.0",
    dependencies: { "modern-tar": "^0.8.5", yargs: "^18.0.0" },
    bin: { browsers: "lib/main-cli.js" },
    engines: { node: ">=22.12.0" },
    peerDependencies: { "proxy-agent": ">=8.0.1", yauzl: "^2.10.0 || ^3.4.0" },
    peerDependenciesMeta: { "proxy-agent": { optional: true }, yauzl: { optional: true } },
  },
  "chromium-bidi": {
    license: "Apache-2.0",
    dependencies: { mitt: "^3.0.1", zod: "^4.6.5" },
    engines: { node: ">=20.19.0 <22.0.0 || >=22.12.0" },
    peerDependencies: { "devtools-protocol": "*" },
  },
  "devtools-protocol": { license: "BSD-3-Clause" },
  "typed-query-selector": { license: "MIT" },
  "webdriver-bidi-protocol": { license: "Apache-2.0" },
}

export function puppeteerTargets() {
  return TARGETS
}

function assertTarget(target) {
  const expected = TARGETS.find((item) => item.name === target?.name)
  assert(expected)
  assert.deepEqual(target, expected)
}

function assertReleaseGraph(data, target) {
  assertTarget(target)
  assert.equal(data.name, target.name)
  assert.equal(data.version, target.to)
  const expected = EXPECTED_GRAPH[target.name]
  assert.equal(data.license, expected.license)
  for (const field of INSTALL_FIELDS) {
    const value =
      field === "bin" && typeof data.bin === "string"
        ? { [target.name.split("/").at(-1)]: data.bin }
        : data[field]
    assert.deepEqual(value, expected[field])
  }
  for (const field of ["optionalDependencies", "bundleDependencies", "bundledDependencies"]) {
    assert(data[field] === undefined)
  }
  for (const field of ["os", "cpu", "libc", "funding"]) assert(data[field] === undefined)
}

export function validatePuppeteerMetadata(data, target, now = Date.now()) {
  assertReleaseGraph(data, target)
  const basename = target.name.split("/").at(-1)
  assert.equal(
    data.dist.tarball,
    "https://registry.npmjs.org/" + target.name + "/-/" + basename + "-" + target.to + ".tgz"
  )
  assert.match(data.dist.integrity, /^sha512-[A-Za-z0-9+/]{86}==$/)
  const encoded = data.dist.integrity.slice(7)
  assert.equal(Buffer.from(encoded, "base64").toString("base64"), encoded)
  assert.match(data.dist.shasum, /^[0-9a-f]{40}$/)
  const published = data.time?.[target.to]
  assert.match(published ?? "", /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/)
  const timestamp = Date.parse(published)
  assert(Number.isFinite(timestamp) && Number.isFinite(now))
  const canonical = published.replace(/(?:\.(\d{1,3}))?Z$/, (_, fraction = "") => {
    return "." + fraction.padEnd(3, "0") + "Z"
  })
  assert.equal(new Date(timestamp).toISOString(), canonical)
  assert(timestamp <= now - 7 * DAY)
  assert(!data.deprecated)
  for (const phase of [
    "preinstall",
    "install",
    "postinstall",
    "prepublish",
    "preprepare",
    "prepare",
    "postprepare",
  ]) {
    assert(!data.scripts?.[phase])
  }
  return { data, published, timestamp }
}

export function verifyPuppeteerArchive(meta, bytes, limit) {
  verifyArchiveBytes(meta, bytes, limit)
  return true
}

export function assertPuppeteerSourceLock(lock) {
  assert.equal(lock.lockfileVersion, 3)
  for (const target of TARGETS) {
    assert.equal(lock.packages[target.path].version, target.from)
    assert.equal(lock.packages[target.path].dev, true)
  }
  for (const [path, version] of [
    ["node_modules/body-parser", "1.20.9"],
    ["node_modules/undici", "8.12.2"],
    ["node_modules/lighthouse", "13.5.0"],
    [REMOVED, "3.25.76"],
  ]) {
    assert.equal(lock.packages[path].version, version)
    assert.equal(lock.packages[path].dev, true)
  }
  assert.equal(lock.packages["node_modules/zod"].version, "4.6.7")
  assert(!Object.hasOwn(lock.packages["node_modules/zod"], "dev"))
  assert.equal(lock.packages["node_modules/lighthouse"].dependencies["puppeteer-core"], "^25.9.0")
  return true
}

export function preparePuppeteerManifest(manifest) {
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    assert(!Object.hasOwn(manifest[section] ?? {}, "puppeteer-core"))
  }
  function checkOverrides(overrides, depth = 0) {
    assert(depth <= 16)
    assert(overrides && typeof overrides === "object" && !Array.isArray(overrides))
    for (const [key, value] of Object.entries(overrides)) {
      assert(!/^puppeteer-core(?:@|$)/.test(key))
      if (value && typeof value === "object") checkOverrides(value, depth + 1)
    }
  }
  checkOverrides(manifest.overrides ?? {})
  const temporary = structuredClone(manifest)
  temporary.overrides = { ...temporary.overrides, "puppeteer-core@25.11.0": "25.13.0" }
  return temporary
}

export function assertPuppeteerLockScope(original, candidate, releases) {
  assertPuppeteerSourceLock(original)
  assert(Array.isArray(releases) && releases.length === TARGETS.length)
  const expected = structuredClone(original)
  const names = new Set()
  for (const data of releases) {
    const target = TARGETS.find((item) => item.name === data?.name)
    assert(target && !names.has(target.name))
    names.add(target.name)
    assertReleaseGraph(data, target)
    const record = {
      version: target.to,
      resolved: data.dist.tarball,
      integrity: data.dist.integrity,
      dev: true,
      license: data.license,
    }
    for (const field of INSTALL_FIELDS) {
      if (Object.hasOwn(EXPECTED_GRAPH[target.name], field)) {
        record[field] = structuredClone(EXPECTED_GRAPH[target.name][field])
      }
    }
    expected.packages[target.path] = record
  }
  delete expected.packages[REMOVED]
  assert.deepEqual(candidate, expected)
  return true
}

export function puppeteerNpmCommand(operation, target) {
  if (operation === "metadata") {
    assertTarget(target)
    return Object.freeze(["view", target.name + "@" + target.to, "--json", ...NPM_TRANSPORT_ARGS])
  }
  assert.equal(operation, "update")
  return Object.freeze([
    "update",
    "puppeteer-core",
    "--package-lock-only",
    "--no-audit",
    "--no-fund",
    ...NPM_TRANSPORT_ARGS,
  ])
}

export async function runPuppeteerGenerator() {
  let stage = "preflight"
  let scratch
  let snapshots
  let git
  let sourceTree
  let report
  let patch
  let failure = false
  const deadline = performance.now() + 7 * 60_000
  const remaining = (cap) => {
    const budget = Math.floor(deadline - performance.now())
    assert(budget > 0, "Generation deadline exceeded")
    return Math.min(cap, budget)
  }
  const reject = () => {
    failure = true
    process.exitCode = 1
    console.error("Puppeteer candidate rejected at stage: " + stage)
  }
  try {
    const workspace = realpathSync(process.env.GITHUB_WORKSPACE)
    const frontend = join(workspace, "frontend")
    assert.equal(realpathSync(process.cwd()), frontend)
    snapshots = []
    const snapshot = (path, limit = 4 * 1024 * 1024) => {
      assert.equal(realpathSync(path), path)
      const stat = lstatSync(path)
      assert(stat.isFile() && stat.size > 0 && stat.size <= limit)
      const item = { path, bytes: readFileSync(path) }
      snapshots.push(item)
      return item.bytes
    }
    const manifestBytes = snapshot(join(frontend, "package.json"))
    const lockBytes = snapshot(join(frontend, "package-lock.json"))
    const configBytes = snapshot(join(frontend, ".npmrc"))
    const manifest = JSON.parse(manifestBytes)
    const lock = JSON.parse(lockBytes)
    const digest = (value) => createHash("sha256").update(value).digest("hex")
    scratch = mkdtempSync(join(realpathSync(process.env.RUNNER_TEMP), "puppeteer-lock-"))
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
    function command(executable, args, cwd, timeout = 120_000, postflight = false) {
      const result = spawnSync(executable, args, {
        cwd,
        env: npmEnv,
        encoding: "utf8",
        shell: false,
        timeout: postflight ? timeout : remaining(timeout),
        maxBuffer: 2 * 1024 * 1024,
      })
      assert(!result.error && !result.signal && result.status === 0)
      return result.stdout
    }
    git = (args, postflight = false) => command("/usr/bin/git", args, workspace, 10_000, postflight)
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
    assert.equal(manifest.packageManager, "npm@11.17.0")
    assert.equal(
      configBytes.toString(),
      "legacy-peer-deps=true\nengine-strict=true\nmin-release-age=7\nstrict-allow-scripts=true\n"
    )
    assertPuppeteerSourceLock(lock)
    const temporary = preparePuppeteerManifest(manifest)
    const temporaryBytes = Buffer.from(JSON.stringify(temporary, null, 2) + "\n")
    const allowedLocal = {
      "scripts/boundary-micromatch-compat": true,
      "wasm-sanitizer/pkg": true,
      "scripts/react-compiler-zod-compat": false,
    }
    const localInputs = []
    const directories = []
    for (const section of ["dependencies", "devDependencies", "optionalDependencies"]) {
      for (const value of Object.values(manifest[section] ?? {})) {
        if (typeof value !== "string" || !value.startsWith("file:")) continue
        const directory = value.slice(5).replace(/^\.\//, "")
        assert(Object.hasOwn(allowedLocal, directory) && !directories.includes(directory))
        directories.push(directory)
        const tracked = "frontend/" + directory + "/package.json"
        assert.equal(git(["ls-files", "--error-unmatch", "--", tracked]).trim(), tracked)
        const source = join(frontend, directory, "package.json")
        const bytes = snapshot(source, 64 * 1024)
        const local = JSON.parse(bytes)
        for (const field of ["dependencies", "devDependencies", "optionalDependencies"]) {
          for (const spec of Object.values(local[field] ?? {})) {
            assert(typeof spec === "string" && !/^(?:file|link|workspace|portal):/.test(spec))
          }
        }
        localInputs.push({ path: directory + "/package.json", bytes })
      }
    }
    for (const [directory, required] of Object.entries(allowedLocal)) {
      if (required) assert(directories.includes(directory))
    }

    stage = "isolated metadata-only source mirror"
    function mirror(name, rootManifest, rootLock) {
      const target = join(scratch, name)
      mkdirSync(target)
      for (const item of [
        { path: "package.json", bytes: rootManifest },
        { path: "package-lock.json", bytes: rootLock },
        { path: ".npmrc", bytes: configBytes },
        ...localInputs,
      ]) {
        const destination = join(target, item.path)
        mkdirSync(dirname(destination), { recursive: true })
        writeFileSync(destination, item.bytes, { flag: "wx" })
      }
      return target
    }
    const generation = mirror("generation", temporaryBytes, lockBytes)
    const bootstrap = realpathSync(join(dirname(process.execPath), "npm"))
    assert.equal(
      bootstrap,
      join(dirname(dirname(process.execPath)), "lib/node_modules/npm/bin/npm-cli.js")
    )
    const invoke = (cli, args, cwd = generation) => command(process.execPath, [cli, ...args], cwd)
    assert.equal(invoke(bootstrap, npmCommand("version")).trim(), "11.19.0")

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
      verifyPuppeteerArchive(meta, bytes, limit)
      writeFileSync(destination, bytes, { flag: "wx", mode: 0o600 })
    }

    stage = "npm tool metadata and archive verification"
    const toolData = JSON.parse(invoke(bootstrap, npmCommand("toolMetadata")))
    const tool = validateRegistryMetadata(toolData, "npm", "11.17.0")
    const toolArchive = join(scratch, "npm-11.17.0.tgz")
    await verifiedArchive(tool.data, toolArchive, 16 * 1024 * 1024)
    stage = "isolated npm tool installation"
    const prefix = join(scratch, "tool")
    mkdirSync(prefix)
    invoke(bootstrap, npmCommand("toolInstall", { prefix, archive: toolArchive }), scratch)
    const cli = realpathSync(join(prefix, "node_modules/npm/bin/npm-cli.js"))
    assert(cli.startsWith(prefix + "/"))
    assert.equal(invoke(cli, npmCommand("version")).trim(), "11.17.0")

    const releases = []
    for (const [index, target] of puppeteerTargets().entries()) {
      stage = target.name + " registry metadata verification"
      const data = JSON.parse(invoke(cli, puppeteerNpmCommand("metadata", target)))
      const release = validatePuppeteerMetadata(data, target)
      stage = target.name + " archive verification"
      await verifiedArchive(data, join(scratch, "target-" + index + ".tgz"), 16 * 1024 * 1024)
      releases.push(release)
    }

    stage = "isolated targeted lock generation"
    invoke(cli, puppeteerNpmCommand("update"))
    const candidatePath = join(generation, "package-lock.json")
    const candidate = readFileSync(candidatePath)
    const parsed = JSON.parse(candidate)
    stage = "whole-lock scope verification"
    try {
      assertPuppeteerLockScope(lock, parsed, releases.map((item) => item.data))
    } catch {
      const diagnostic = JSON.stringify(diagnoseLockScope(lock, parsed))
      assert(Buffer.byteLength(diagnostic) <= 16384)
      console.error("PUPPETEER_REJECTED_SCOPE " + diagnostic)
      throw new Error("Rejected generated lock scope")
    }
    assert(!existsSync(join(generation, "node_modules")))
    assert.deepEqual(readFileSync(join(generation, "package.json")), temporaryBytes)
    assert.deepEqual(readFileSync(join(generation, ".npmrc")), configBytes)

    for (const [name, operation] of [
      ["full", "fullGraph"],
      ["production", "productionGraph"],
    ]) {
      stage = name + " project-configured graph installation"
      const target = mirror(name, manifestBytes, candidate)
      invoke(cli, stagedNpmCommand(operation), target)
      stage = name + " project-configured graph verification"
      for (const release of TARGETS) {
        const directory = join(target, release.path)
        if (name === "production") {
          assert(!existsSync(directory))
          continue
        }
        const path = join(directory, "package.json")
        assert.equal(realpathSync(path), path)
        assert(lstatSync(path).isFile() && lstatSync(path).size <= 1024 * 1024)
        const installed = JSON.parse(readFileSync(path))
        assertReleaseGraph(installed, release)
      }
      assert(!existsSync(join(target, REMOVED)))
      const rootEnginePath = join(target, "node_modules/zod/package.json")
      assert.equal(realpathSync(rootEnginePath), rootEnginePath)
      const rootEngine = JSON.parse(readFileSync(rootEnginePath))
      assert.equal(rootEngine.name, "zod")
      assert.equal(rootEngine.version, "4.6.7")
      if (name === "full") {
        const bidi = createRequire(join(target, "node_modules/chromium-bidi/package.json"))
        assert.equal(realpathSync(bidi.resolve("zod/package.json")), rootEnginePath)
      }
      assert.deepEqual(readFileSync(join(target, "package.json")), manifestBytes)
      assert.deepEqual(readFileSync(join(target, "package-lock.json")), candidate)
      assert.deepEqual(readFileSync(join(target, ".npmrc")), configBytes)
      for (const item of localInputs) {
        assert.deepEqual(readFileSync(join(target, item.path)), item.bytes)
      }
    }
    assert.equal(readFileSync(userConfig).length, 0)
    assert.equal(readFileSync(globalConfig).length, 0)

    stage = "bounded generated lock diff"
    const result = spawnSync(
      "/usr/bin/git",
      ["diff", "--no-index", "--no-ext-diff", "--no-color", "--", snapshots[1].path, candidatePath],
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
    patch = result.stdout
      .replace(
        /^diff --git .*$/m,
        "diff --git a/frontend/package-lock.json b/frontend/package-lock.json"
      )
      .replace(/^--- .*$/m, "--- a/frontend/package-lock.json")
      .replace(/^\+\+\+ .*$/m, "+++ b/frontend/package-lock.json")
    assert(Buffer.byteLength(patch) > 0 && Buffer.byteLength(patch) <= 16384)
    const sourceMetadata = (data) => {
      const gitHead = /^[0-9a-f]{40}$/.test(data.gitHead ?? "") ? data.gitHead : null
      const value = typeof data.repository === "string" ? data.repository : data.repository?.url
      const repository =
        typeof value === "string" &&
        value.length <= 256 &&
        /^(?:git\+)?https:\/\/(?:github\.com|chromium\.googlesource\.com)\/[A-Za-z0-9._/-]+$/.test(
          value
        )
          ? value
          : null
      return { gitHead, repository, sourceBindingVerified: false }
    }
    report = {
      kind: "puppeteer-lock-candidate",
      sourceSha: process.env.SOURCE_SHA,
      sourceTree,
      node: process.version,
      npm: "11.17.0",
      bootstrapNpm: "11.19.0",
      registry: "https://registry.npmjs.org/",
      releases: releases.map(({ data, published, timestamp }) => ({
        name: data.name,
        version: data.version,
        published,
        cooldownMatures: new Date(timestamp + 7 * DAY).toISOString(),
        cooldownException: false,
        tarball: data.dist.tarball,
        integrity: data.dist.integrity,
        shasum: data.dist.shasum,
        tarballVerified: true,
        ...sourceMetadata(data),
      })),
      updatedPackagePaths: TARGETS.map((target) => target.path),
      removedPackagePaths: [REMOVED],
      addedPackagePaths: [],
      originalManifestPreserved: true,
      unrelatedRecordsPreserved: true,
      preservedRootZod: "4.6.7",
      preservedBodyParser: "1.20.9",
      preservedUndici: "8.12.2",
      fullGraphInstallVerified: true,
      productionGraphInstallVerified: true,
      graphInstallPolicy: "project-configured legacy-peer-deps=true; ignore-scripts",
      graphResolutionScope: "package identities and bidi-to-root-Zod resolution only",
      strictPeerCompatibilityVerified: false,
      normalLifecycleOrBuildVerified: false,
      localPackageContentsVerified: false,
      cryptographicPublishProvenanceVerified: false,
      libraryCodeExecuted: false,
      lifecycleScriptsExecuted: false,
      checkoutModified: false,
      originalManifestSha256: digest(manifestBytes),
      originalLockSha256: digest(lockBytes),
      candidateLockSha256: digest(candidate),
      projectNpmrcSha256: digest(configBytes),
      npmToolPublished: tool.published,
      npmToolIntegrity: tool.data.dist.integrity,
    }
  } catch {
    reject()
  } finally {
    try {
      stage = "original source verification"
      if (snapshots) {
        for (const item of snapshots) assert.deepEqual(readFileSync(item.path), item.bytes)
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
  if (!failure) {
    console.log("PUPPETEER_CANDIDATE_METADATA " + JSON.stringify(report))
    console.log("PUPPETEER_CANDIDATE_PATCH_BEGIN\n" + patch + "PUPPETEER_CANDIDATE_PATCH_END")
    console.log("Source unchanged; candidate evidence is not a passing audit or normal CI.")
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await runPuppeteerGenerator()
}
