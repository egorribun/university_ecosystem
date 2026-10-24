import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { spawnSync } from "node:child_process"
import { get } from "node:https"
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path"
import { pathToFileURL } from "node:url"
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

// Independently verified official v4.6.7 source commit; registry metadata must match.
const EXPECTED_ZOD_SOURCE_SHA = "b500a2ee95134f81d74da7911d7378dd2853d042"

export const NPM_TRANSPORT_ARGS = Object.freeze([
  "--registry=https://registry.npmjs.org/",
  "--fetch-retries=0",
  "--fetch-timeout=30000",
  "--ignore-scripts",
  "--min-release-age=7",
])

const commands = Object.freeze({
  version: Object.freeze(["--version"]),
  toolMetadata: Object.freeze(["view", "npm@11.17.0", "--json", ...NPM_TRANSPORT_ARGS]),
  targetMetadata: Object.freeze(["view", "zod@4.6.7", "--json", ...NPM_TRANSPORT_ARGS]),
  targetUpdate: Object.freeze([
    "update",
    "zod",
    "--package-lock-only",
    "--no-audit",
    "--no-fund",
    ...NPM_TRANSPORT_ARGS,
  ]),
})

export function npmCommand(operation, paths = {}) {
  if (operation === "toolInstall") {
    const { prefix, archive } = paths
    assert(typeof prefix === "string" && isAbsolute(prefix) && resolve(prefix) === prefix)
    assert(typeof archive === "string" && isAbsolute(archive) && resolve(archive) === archive)
    assert.equal(dirname(prefix), dirname(archive))
    assert.equal(basename(prefix), "tool")
    assert.equal(basename(archive), "npm-11.17.0.tgz")
    return Object.freeze([
      "install",
      "--prefix",
      prefix,
      "--no-audit",
      "--no-fund",
      "--package-lock=false",
      "--save=false",
      ...NPM_TRANSPORT_ARGS,
      archive,
    ])
  }
  assert(Object.hasOwn(commands, operation))
  return commands[operation]
}

export function assertNpmCommand(operation, args, paths = {}) {
  assert.deepEqual(args, npmCommand(operation, paths))
}

export function validateRegistryMetadata(
  data,
  name,
  version,
  now = Date.now(),
  expectedSourceGitHead = EXPECTED_ZOD_SOURCE_SHA
) {
  assert((name === "npm" && version === "11.17.0") || (name === "zod" && version === "4.6.7"))
  assert.equal(data.name, name)
  assert.equal(data.version, version)
  assert.equal(
    data.dist.tarball,
    "https://registry.npmjs.org/" + name + "/-/" + name + "-" + version + ".tgz"
  )
  assert.match(data.dist.integrity, /^sha512-[A-Za-z0-9+/]{86}==$/)
  assert.match(data.dist.shasum, /^[0-9a-f]{40}$/)
  const published = data.time?.[version]
  assert.match(published ?? "", /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/)
  const timestamp = Date.parse(published)
  assert(Number.isFinite(now) && Number.isFinite(timestamp))
  assert(timestamp <= now - 7 * 86400000)
  assert(!data.deprecated)
  if (name === "zod") {
    for (const phase of ["preinstall", "install", "postinstall", "prepare"]) {
      assert(!data.scripts?.[phase])
    }
    assert.equal(data.repository?.type, "git")
    assert.equal(data.repository?.url, "git+https://github.com/colinhacks/zod.git")
    assert.match(expectedSourceGitHead ?? "", /^[0-9a-f]{40}$/)
    assert.match(data.gitHead ?? "", /^[0-9a-f]{40}$/)
    assert.equal(data.gitHead, expectedSourceGitHead)
  }
  return { data, published, timestamp }
}

export function verifyArchiveBytes(meta, bytes, limit) {
  assert(Number.isSafeInteger(limit) && limit > 0 && limit <= 16 * 1024 * 1024)
  assert(Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length <= limit)
  assert.equal(
    "sha512-" + createHash("sha512").update(bytes).digest("base64"),
    meta.dist.integrity
  )
  assert.equal(createHash("sha1").update(bytes).digest("hex"), meta.dist.shasum)
}

export function assertZodLockScope(originalLock, candidateLock, release) {
  assertSourceLockPrerequisites(originalLock)
  const key = "node_modules/zod"
  const oldRecord = originalLock.packages[key]
  assert.equal(release.name, "zod")
  assert.equal(release.version, "4.6.7")
  assert.deepEqual(release.dependencies ?? {}, {})
  assert.deepEqual(oldRecord.dependencies ?? {}, {})
  assert.deepEqual(release.engines, oldRecord.engines)
  assert.equal(release.license, oldRecord.license)
  const funding = typeof release.funding === "string" ? { url: release.funding } : release.funding
  assert.deepEqual(funding, oldRecord.funding)
  const expected = structuredClone(originalLock)
  expected.packages[key] = {
    ...oldRecord,
    version: "4.6.7",
    resolved: release.dist.tarball,
    integrity: release.dist.integrity,
  }
  assert.deepEqual(candidateLock, expected)
}

export function assertSourceLockPrerequisites(lock) {
  assert.equal(lock.lockfileVersion, 3)
  assert.equal(lock.packages["node_modules/body-parser"].version, "1.20.9")
  assert.equal(lock.packages["node_modules/body-parser"].dev, true)
  assert.equal(lock.packages["node_modules/undici"].version, "8.12.2")
  assert.equal(lock.packages["node_modules/undici"].dev, true)
  assert.equal(lock.packages["node_modules/zod"].version, "4.6.5")
  assert(!Object.hasOwn(lock.packages["node_modules/zod"], "dev"))
  const nested = [
    "node_modules/chromium-bidi/node_modules/zod",
    "node_modules/eslint-plugin-react-compiler/node_modules/zod",
  ]
  assert.deepEqual(
    Object.keys(lock.packages)
      .filter((path) => /(?:^|\/)node_modules\/zod$/.test(path))
      .sort(),
    [...nested, "node_modules/zod"]
  )
  for (const path of nested) {
    assert.equal(lock.packages[path].version, "3.25.76")
    assert.equal(lock.packages[path].dev, true)
  }
}

export function prepareTemporaryManifest(manifest) {
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    assert(!Object.hasOwn(manifest[section] ?? {}, "zod"))
  }
  assert(
    !Object.keys(manifest.overrides ?? {}).some((name) => name === "zod" || name.startsWith("zod@"))
  )
  const temporary = structuredClone(manifest)
  temporary.overrides = { ...temporary.overrides, "zod@4.6.5": "4.6.7" }
  return temporary
}

export async function runZodGenerator() {
  let stage = "preflight"
  let scratch
  let sourcePaths
  let original
  let git
  let report
  let patch
  let failure = false
  const deadline = performance.now() + 6 * 60_000
  const remaining = (cap) => {
    const budget = Math.floor(deadline - performance.now())
    assert(budget > 0, "Generation deadline exceeded")
    return Math.min(cap, budget)
  }
  const reject = () => {
    failure = true
    process.exitCode = 1
    console.error("Zod candidate rejected at stage: " + stage)
  }
  try {
    const workspace = realpathSync(process.env.GITHUB_WORKSPACE)
    const frontend = join(workspace, "frontend")
    assert.equal(realpathSync(process.cwd()), frontend)
    assert.equal(process.version, "v24.21.0")
    assert.match(process.env.SOURCE_SHA ?? "", /^[0-9a-f]{40}$/)
    sourcePaths = ["package.json", "package-lock.json", ".npmrc"].map((path) =>
      join(frontend, path)
    )
    original = sourcePaths.map((path) => readFileSync(path))
    const manifest = JSON.parse(original[0])
    const lock = JSON.parse(original[1])
    const key = "node_modules/zod"
    const oldRecord = lock.packages[key]
    const digest = (value) => createHash("sha256").update(value).digest("hex")
    scratch = mkdtempSync(join(realpathSync(process.env.RUNNER_TEMP), "zod-lock-"))
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
    git = (args, postflight = false) =>
      command("/usr/bin/git", args, workspace, 10_000, postflight)
    assert.equal(git(["rev-parse", "HEAD"]).trim(), process.env.SOURCE_SHA)
    assert.equal(git(["status", "--porcelain=v1", "--untracked-files=all"]), "")
    assert(!existsSync(join(frontend, "node_modules")), "Run before npm ci")
    assert.equal(manifest.packageManager, "npm@11.17.0")
    assert.equal(
      original[2].toString(),
      "legacy-peer-deps=true\nengine-strict=true\nmin-release-age=7\nstrict-allow-scripts=true\n"
    )
    const temporary = prepareTemporaryManifest(manifest)
    // The clean immutable source checkout is the baseline; its bytes are retained
    // and hashed in the report, rather than maintaining a second digest authority.
    assertSourceLockPrerequisites(lock)
    const localDirectories = []
    for (const section of ["dependencies", "devDependencies", "optionalDependencies"]) {
      assert(!manifest[section]?.["zod"])
      for (const value of Object.values(manifest[section] ?? {})) {
        if (typeof value === "string" && value.startsWith("file:")) {
          localDirectories.push(value.slice(5).replace(/^\.\//, ""))
        }
      }
    }
    assert.deepEqual(localDirectories.sort(), [
      "scripts/boundary-micromatch-compat",
      "wasm-sanitizer/pkg",
    ])

    stage = "isolated source mirror"
    const mirror = join(scratch, "frontend")
    mkdirSync(mirror)
    for (const [index, name] of ["package.json", "package-lock.json", ".npmrc"].entries()) {
      writeFileSync(join(mirror, name), original[index], { flag: "wx" })
    }
    let copiedBytes = 0
    let copiedFiles = 0
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
        const source = join(workspace, name)
        assert.equal(realpathSync(source), source)
        const stat = lstatSync(source)
        assert(stat.isFile() && stat.size <= 16 * 1024 * 1024)
        copiedBytes += stat.size
        copiedFiles += 1
        assert(copiedBytes <= 64 * 1024 * 1024 && copiedFiles <= 1024)
        const rel = relative(frontend, source)
        assert(!rel.startsWith("../") && !rel.startsWith("/") && !rel.includes("\\"))
        const destination = join(mirror, rel)
        mkdirSync(dirname(destination), { recursive: true })
        writeFileSync(destination, readFileSync(source), { flag: "wx" })
      }
    }
    const bootstrap = realpathSync(join(dirname(process.execPath), "npm"))
    assert.equal(
      bootstrap,
      join(dirname(dirname(process.execPath)), "lib/node_modules/npm/bin/npm-cli.js")
    )
    function npm(cli, operation, paths = {}, cwd = mirror) {
      const args = npmCommand(operation, paths)
      assertNpmCommand(operation, args, paths)
      return command(process.execPath, [cli, ...args], cwd)
    }
    assert.equal(npm(bootstrap, "version").trim(), "11.19.0")

    function metadata(cli, name, version) {
      const operation = name === "npm" ? "toolMetadata" : "targetMetadata"
      const data = JSON.parse(npm(cli, operation))
      if (name === "zod") {
        const scalar = (value) => (typeof value === "string" ? value.slice(0, 256) : null)
        console.log(
          "ZOD_REGISTRY_SOURCE_METADATA " +
            JSON.stringify({
              name: scalar(data.name),
              version: scalar(data.version),
              repositoryType: scalar(data.repository?.type),
              repositoryUrl: scalar(data.repository?.url),
              registryGitHead: scalar(data.gitHead),
              expectedGitHead: EXPECTED_ZOD_SOURCE_SHA,
              published: scalar(data.time?.[version]),
            })
        )
      }
      return validateRegistryMetadata(data, name, version)
    }
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
    const toolMetadata = metadata(bootstrap, "npm", "11.17.0")
    const toolArchive = join(scratch, "npm-11.17.0.tgz")
    await verifiedArchive(toolMetadata.data, toolArchive, 16 * 1024 * 1024)
    stage = "isolated npm tool installation"
    const toolPrefix = join(scratch, "tool")
    mkdirSync(toolPrefix)
    npm(bootstrap, "toolInstall", { prefix: toolPrefix, archive: toolArchive }, scratch)
    const cli = realpathSync(join(toolPrefix, "node_modules/npm/bin/npm-cli.js"))
    assert(cli.startsWith(toolPrefix + "/"))
    assert.equal(npm(cli, "version").trim(), "11.17.0")

    stage = "mature zod metadata and archive verification"
    const release = metadata(cli, "zod", "4.6.7")
    assert.deepEqual(release.data.dependencies ?? {}, {})
    assert.deepEqual(oldRecord.dependencies ?? {}, {})
    assert.deepEqual(release.data.engines, oldRecord.engines)
    assert.equal(release.data.license, oldRecord.license)
    await verifiedArchive(release.data, join(scratch, "zod-4.6.7.tgz"), 4 * 1024 * 1024)

    stage = "isolated targeted lock generation"
    writeFileSync(join(mirror, "package.json"), JSON.stringify(temporary, null, 2) + "\n")
    npm(cli, "targetUpdate")
    stage = "whole-lock scope verification"
    const candidatePath = join(mirror, "package-lock.json")
    const candidate = readFileSync(candidatePath)
    assertZodLockScope(lock, JSON.parse(candidate), release.data)
    assert.deepEqual(readFileSync(join(mirror, ".npmrc")), original[2])
    assert.deepEqual(JSON.parse(readFileSync(join(mirror, "package.json"))), temporary)
    assert(!existsSync(join(mirror, "node_modules")))
    assert.equal(readFileSync(userConfig).length, 0)
    assert.equal(readFileSync(globalConfig).length, 0)

    stage = "bounded candidate diff"
    const diff = spawnSync(
      "/usr/bin/git",
      ["diff", "--no-index", "--no-ext-diff", "--no-color", "--", sourcePaths[1], candidatePath],
      {
        cwd: workspace,
        env: npmEnv,
        encoding: "utf8",
        shell: false,
        timeout: remaining(10_000),
        maxBuffer: 16 * 1024,
      }
    )
    assert(!diff.error && !diff.signal && diff.status === 1)
    patch = diff.stdout
      .replace(
        /^diff --git .*$/m,
        "diff --git a/frontend/package-lock.json b/frontend/package-lock.json"
      )
      .replace(/^--- .*$/m, "--- a/frontend/package-lock.json")
      .replace(/^\+\+\+ .*$/m, "+++ b/frontend/package-lock.json")
    assert(Buffer.byteLength(patch) > 0 && Buffer.byteLength(patch) <= 8192)
    assert.equal(
      patch.split("\n").filter((line) => line.startsWith("+") && !line.startsWith("+++")).length,
      3
    )
    assert.equal(
      patch.split("\n").filter((line) => line.startsWith("-") && !line.startsWith("---")).length,
      3
    )
    report = {
      kind: "zod-root-lock-candidate",
      sourceSha: process.env.SOURCE_SHA,
      node: process.version,
      npm: "11.17.0",
      bootstrapNpm: "11.19.0",
      package: "zod",
      from: "4.6.5",
      to: "4.6.7",
      advisories: ["GHSA-mrhx-c7xc-m3w5", "CVE-2023-54404"],
      registryGitHead: release.data.gitHead,
      expectedSourceGitHead: EXPECTED_ZOD_SOURCE_SHA,
      repository: release.data.repository.url,
      registrySourceMetadataMatched: true,
      cryptographicPublishProvenanceVerified: false,
      preservedNestedVersions: {
        chromiumBidi: "3.25.76",
        eslintPluginReactCompiler: "3.25.76",
      },
      published: release.published,
      cooldownException: false,
      cooldownMatures: new Date(release.timestamp + 7 * 86400000).toISOString(),
      registry: "https://registry.npmjs.org/",
      tarball: release.data.dist.tarball,
      integrity: release.data.dist.integrity,
      shasum: release.data.dist.shasum,
      tarballVerified: true,
      lifecycleScriptsExecuted: false,
      checkoutModified: false,
      changedFields: ["version", "resolved", "integrity"],
      originalLockSha256: digest(original[1]),
      candidateLockSha256: digest(candidate),
      npmToolPublished: toolMetadata.published,
      npmToolIntegrity: toolMetadata.data.dist.integrity,
    }
  } catch {
    reject()
  } finally {
    try {
      stage = "original source verification"
      if (original) {
        sourcePaths.forEach((path, index) => assert.deepEqual(readFileSync(path), original[index]))
      }
      if (git) {
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
    console.log("ZOD_CANDIDATE_METADATA " + JSON.stringify(report))
    console.log("ZOD_CANDIDATE_PATCH_BEGIN\n" + patch + "ZOD_CANDIDATE_PATCH_END")
    console.log(
      "Checked-in source unchanged; candidate generation does not establish a passing audit."
    )
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await runZodGenerator()
}
