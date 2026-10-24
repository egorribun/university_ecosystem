import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { spawnSync } from "node:child_process"
import { get } from "node:https"
import { createRequire } from "node:module"
import { dirname, join, relative, resolve } from "node:path"
import { pathToFileURL } from "node:url"
import { isDeepStrictEqual } from "node:util"
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
import {
  NPM_TRANSPORT_ARGS,
  assertNpmCommand,
  npmCommand,
  validateRegistryMetadata,
  verifyArchiveBytes,
} from "./generate-zod-root-lock-candidate.mjs"

const LOCAL = "scripts/react-compiler-zod-compat"
const ALIAS = LOCAL + "/node_modules/patched-zod"
const LINK = "node_modules/react-compiler-zod-compat"

export function adapterManifest() {
  return {
    name: "@university-ecosystem/react-compiler-zod-compat",
    version: "1.0.0",
    private: true,
    description: "The legacy schema API used only by the pinned React Compiler ESLint gate",
    main: "index.cjs",
    files: ["index.cjs", "LICENSE", "README.md"],
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  }
}

export function prepareStagedManifest(manifest) {
  assert.equal(manifest.packageManager, "npm@11.17.0")
  assert.equal(manifest.devDependencies?.["eslint-plugin-react-compiler"], "^19.1.0-rc.2")
  for (const section of [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
  ]) {
    for (const name of ["zod", "patched-zod", "react-compiler-zod-compat"]) {
      assert(!Object.hasOwn(manifest[section] ?? {}, name))
    }
  }
  for (const name of Object.keys(manifest.overrides ?? {})) {
    assert(!/^(?:zod|eslint-plugin-react-compiler)(?:@|$)/.test(name))
  }
  const staged = structuredClone(manifest)
  staged.devDependencies["react-compiler-zod-compat"] = "file:./" + LOCAL
  return staged
}

export function assertStagedSourcePrerequisites(lock) {
  assert.equal(lock.lockfileVersion, 3)
  for (const [path, version] of [
    ["node_modules/body-parser", "1.20.9"],
    ["node_modules/undici", "8.12.2"],
    ["node_modules/eslint-plugin-react-compiler", "19.1.0-rc.2"],
    ["node_modules/chromium-bidi/node_modules/zod", "3.25.76"],
    ["node_modules/eslint-plugin-react-compiler/node_modules/zod", "3.25.76"],
  ]) {
    assert.equal(lock.packages[path].version, version)
    assert.equal(lock.packages[path].dev, true)
  }
  assert.equal(lock.packages["node_modules/zod"].version, "4.6.7")
  assert(!Object.hasOwn(lock.packages["node_modules/zod"], "dev"))
  assert.deepEqual(
    Object.keys(lock.packages)
      .filter((path) => /(?:^|\/)node_modules\/zod$/.test(path))
      .sort(),
    [
      "node_modules/chromium-bidi/node_modules/zod",
      "node_modules/eslint-plugin-react-compiler/node_modules/zod",
      "node_modules/zod",
    ]
  )
  for (const path of [LINK, LOCAL, ALIAS, "node_modules/patched-zod"]) {
    assert(!Object.hasOwn(lock.packages, path))
  }
}

export function assertStagedLockScope(original, candidate, release) {
  assertStagedSourcePrerequisites(original)
  const root = original.packages["node_modules/zod"]
  assert.equal(release.name, "zod")
  assert.equal(release.version, "4.6.7")
  assert.equal(root.resolved, release.dist.tarball)
  assert.equal(root.integrity, release.dist.integrity)
  assert.equal(root.license, release.license)
  assert.deepEqual(root.engines, release.engines)
  assert.deepEqual(root.dependencies ?? {}, {})
  assert.deepEqual(release.dependencies ?? {}, {})
  const funding = typeof release.funding === "string" ? { url: release.funding } : release.funding
  assert.deepEqual(root.funding, funding)
  const expected = structuredClone(original)
  assert(!Object.hasOwn(expected.packages[""].devDependencies, "react-compiler-zod-compat"))
  expected.packages[""].devDependencies["react-compiler-zod-compat"] = "file:./" + LOCAL
  expected.packages[LINK] = { resolved: LOCAL, link: true }
  expected.packages[LOCAL] = {
    name: adapterManifest().name,
    version: "1.0.0",
    dev: true,
    license: "MIT",
    dependencies: { "patched-zod": "npm:zod@4.6.7" },
  }
  expected.packages[ALIAS] = { name: "zod", ...root, dev: true }
  assert.deepEqual(candidate, expected)
}

export function stagedNpmCommand(operation) {
  const commands = {
    generateLock: ["install", "--package-lock-only"],
    fullGraph: ["ci", "--include=dev"],
    productionGraph: ["ci", "--omit=dev"],
  }
  assert(Object.hasOwn(commands, operation))
  return Object.freeze([...commands[operation], "--no-audit", "--no-fund", ...NPM_TRANSPORT_ARGS])
}

export function assertStagedNpmCommand(operation, args) {
  assert.deepEqual(args, stagedNpmCommand(operation))
}

export function assertImmutableCheckout(state) {
  assert.match(state.expectedSha ?? "", /^[0-9a-f]{40}$/)
  assert.equal(state.head, state.expectedSha)
  assert.equal(state.status, "")
  assert.equal(state.node, "v24.21.0")
  assert.equal(state.repository, "egorribun/university_ecosystem")
  assert.equal(state.hasNodeModules, false)
}

export function assertInstalledGraph(frontend, mode) {
  assert(mode === "full" || mode === "production")
  assert.equal(realpathSync(frontend), frontend)
  const root = JSON.parse(readFileSync(join(frontend, "node_modules/zod/package.json")))
  assert.equal(root.name, "zod")
  assert.equal(root.version, "4.6.7")
  assert(!existsSync(join(frontend, "node_modules/patched-zod")))
  if (mode === "production") {
    for (const path of [LINK, ALIAS, "node_modules/eslint-plugin-react-compiler"]) {
      assert(!existsSync(join(frontend, path)))
    }
    return
  }
  const local = join(frontend, LOCAL)
  assert.equal(realpathSync(join(frontend, LINK)), local)
  assert.equal(realpathSync(local), local)
  assert.deepEqual(JSON.parse(readFileSync(join(local, "package.json"))), adapterManifest())
  const adapterRequire = createRequire(join(local, "package.json"))
  const enginePath = adapterRequire.resolve("patched-zod/package.json")
  assert.equal(realpathSync(enginePath), join(frontend, ALIAS, "package.json"))
  const engine = JSON.parse(readFileSync(enginePath))
  assert.equal(engine.name, "zod")
  assert.equal(engine.version, "4.6.7")
  const compiler = join(frontend, "node_modules/eslint-plugin-react-compiler")
  const compilerManifest = JSON.parse(readFileSync(join(compiler, "package.json")))
  assert.equal(compilerManifest.name, "eslint-plugin-react-compiler")
  assert.equal(compilerManifest.version, "19.1.0-rc.2")
  const compilerRequire = createRequire(join(compiler, "package.json"))
  const oldEnginePath = compilerRequire.resolve("zod/package.json")
  assert.equal(realpathSync(oldEnginePath), join(compiler, "node_modules/zod/package.json"))
  const oldEngine = JSON.parse(readFileSync(oldEnginePath))
  assert.equal(oldEngine.name, "zod")
  assert.equal(oldEngine.version, "3.25.76")
}

export function diagnoseLockScope(original, candidate) {
  const record = (value) => value && typeof value === "object" && !Array.isArray(value)
  if (
    !record(original) ||
    !record(candidate) ||
    !record(original.packages) ||
    !record(candidate.packages)
  ) {
    return { unavailable: true }
  }
  let omitted = 0
  const packageChanges = []
  const fields = (before, after) => {
    const changed = []
    for (const key of [...new Set([...Object.keys(before), ...Object.keys(after)])].sort()) {
      if (isDeepStrictEqual(before[key], after[key])) continue
      if (!/^[A-Za-z][A-Za-z0-9]{0,47}$/.test(key) || changed.length >= 16) omitted += 1
      else changed.push(key)
    }
    return changed
  }
  const paths = [
    ...new Set([...Object.keys(original.packages), ...Object.keys(candidate.packages)]),
  ]
  for (const path of paths.sort()) {
    const before = original.packages[path]
    const after = candidate.packages[path]
    if (isDeepStrictEqual(before, after)) continue
    const safe =
      path === "" ||
      (path.length <= 180 &&
        /^(?:node_modules|scripts|wasm-sanitizer)\/[a-zA-Z0-9@._~/-]+$/.test(path) &&
        !path.split("/").some((part) => part === ".." || part === "." || part === ""))
    if (!safe || packageChanges.length >= 16) {
      omitted += 1
      continue
    }
    const kind = before === undefined ? "added" : after === undefined ? "removed" : "changed"
    const names = kind === "changed" && record(before) && record(after) ? fields(before, after) : []
    packageChanges.push({ path, kind, fields: names })
  }
  const before = { ...original }
  const after = { ...candidate }
  delete before.packages
  delete after.packages
  return { packageChanges, topLevelFields: fields(before, after), omitted }
}

export async function runStagedAdapterGenerator() {
  let stage = "preflight"
  let scratch
  let snapshots
  let git
  let sourceTree
  let report
  let patch
  let packageBytes
  let failure = false
  const started = performance.now()
  const deadline = started + 7 * 60_000
  const remaining = (cap) => {
    const budget = Math.floor(deadline - performance.now())
    assert(budget > 0, "Generation deadline exceeded")
    return Math.min(cap, budget)
  }
  const reject = () => {
    failure = true
    process.exitCode = 1
    console.error("Staged adapter candidate rejected at stage: " + stage)
    if (stage !== "preflight") {
      console.error("STAGED_ADAPTER_FAILURE_ELAPSED_MS " + Math.floor(performance.now() - started))
    }
  }
  try {
    const workspace = realpathSync(process.env.GITHUB_WORKSPACE)
    const frontend = join(workspace, "frontend")
    assert.equal(realpathSync(process.cwd()), frontend)
    const sourceNames = [
      "frontend/package.json",
      "frontend/package-lock.json",
      "frontend/.npmrc",
      "frontend/" + LOCAL + "/index.cjs",
      "LICENSE",
    ]
    snapshots = sourceNames.map((name) => {
      const path = join(workspace, name)
      assert.equal(realpathSync(path), path)
      assert(lstatSync(path).isFile() && lstatSync(path).size <= 4 * 1024 * 1024)
      return { path, bytes: readFileSync(path) }
    })
    const [manifestBytes, lockBytes, configBytes] = snapshots.map((item) => item.bytes)
    const manifest = JSON.parse(manifestBytes)
    const lock = JSON.parse(lockBytes)
    const digest = (value) => createHash("sha256").update(value).digest("hex")
    scratch = mkdtempSync(join(realpathSync(process.env.RUNNER_TEMP), "compiler-adapter-lock-"))
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
    assert.equal(
      configBytes.toString(),
      "legacy-peer-deps=true\nengine-strict=true\nmin-release-age=7\nstrict-allow-scripts=true\n"
    )
    const staged = prepareStagedManifest(manifest)
    assertStagedSourcePrerequisites(lock)
    assert(!existsSync(join(frontend, LOCAL, "package.json")))
    const stagedBytes = Buffer.from(JSON.stringify(staged, null, 2) + "\n")
    packageBytes = Buffer.from(JSON.stringify(adapterManifest(), null, 2) + "\n")
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
      "wasm-sanitizer/pkg",
    ])

    stage = "isolated source inputs"
    const copied = []
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
        const source = join(workspace, name)
        assert.equal(realpathSync(source), source)
        const stat = lstatSync(source)
        assert(stat.isFile() && stat.size <= 16 * 1024 * 1024)
        const rel = relative(frontend, source)
        assert(!rel.startsWith("../") && !rel.startsWith("/") && !rel.includes("\\"))
        assert(!rel.split("/").includes("node_modules"))
        copiedBytes += stat.size
        assert(copiedBytes <= 64 * 1024 * 1024 && copied.length < 1024)
        copied.push({ source, rel, bytes: readFileSync(source) })
      }
    }
    function mirror(name, rootManifest, rootLock) {
      const target = join(scratch, name)
      mkdirSync(target)
      for (const [path, bytes] of [
        ["package.json", rootManifest],
        ["package-lock.json", rootLock],
        [".npmrc", configBytes],
        [LOCAL + "/package.json", packageBytes],
        [LOCAL + "/index.cjs", snapshots[3].bytes],
        [LOCAL + "/LICENSE", snapshots[4].bytes],
        ...copied.map((item) => [item.rel, item.bytes]),
      ]) {
        const destination = join(target, path)
        mkdirSync(dirname(destination), { recursive: true })
        writeFileSync(destination, bytes, { flag: "wx" })
      }
      return target
    }
    const generation = mirror("generation", stagedBytes, lockBytes)
    const bootstrap = realpathSync(join(dirname(process.execPath), "npm"))
    assert.equal(
      bootstrap,
      join(dirname(dirname(process.execPath)), "lib/node_modules/npm/bin/npm-cli.js")
    )
    function npm(cli, operation, cwd, paths = {}) {
      const isStaged = ["generateLock", "fullGraph", "productionGraph"].includes(operation)
      const args = isStaged ? stagedNpmCommand(operation) : npmCommand(operation, paths)
      if (isStaged) assertStagedNpmCommand(operation, args)
      else assertNpmCommand(operation, args, paths)
      return command(process.execPath, [cli, ...args], cwd)
    }
    assert.equal(npm(bootstrap, "version", generation).trim(), "11.19.0")

    function metadata(cli, name, version) {
      const operation = name === "npm" ? "toolMetadata" : "targetMetadata"
      const data = JSON.parse(npm(cli, operation, generation))
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
    npm(bootstrap, "toolInstall", scratch, { prefix: toolPrefix, archive: toolArchive })
    const cli = realpathSync(join(toolPrefix, "node_modules/npm/bin/npm-cli.js"))
    assert(cli.startsWith(toolPrefix + "/"))
    assert.equal(npm(cli, "version", generation).trim(), "11.17.0")

    stage = "mature zod metadata and archive verification"
    const release = metadata(cli, "zod", "4.6.7")
    await verifiedArchive(release.data, join(scratch, "zod-4.6.7.tgz"), 4 * 1024 * 1024)

    stage = "isolated staged lock generation"
    npm(cli, "generateLock", generation)
    const candidatePath = join(generation, "package-lock.json")
    const candidate = readFileSync(candidatePath)
    stage = "whole-lock scope verification"
    try {
      assertStagedLockScope(lock, JSON.parse(candidate), release.data)
    } catch {
      const diagnostic = JSON.stringify(diagnoseLockScope(lock, JSON.parse(candidate)))
      assert(Buffer.byteLength(diagnostic) <= 16384)
      console.error("STAGED_ADAPTER_REJECTED_SCOPE " + diagnostic)
      throw new Error("Rejected generated lock scope")
    }
    assert(!existsSync(join(generation, "node_modules")))
    assert.deepEqual(readFileSync(join(generation, "package.json")), stagedBytes)
    assert.deepEqual(readFileSync(join(generation, ".npmrc")), configBytes)
    assert.deepEqual(readFileSync(join(generation, LOCAL, "package.json")), packageBytes)

    for (const [name, operation, mode] of [
      ["full", "fullGraph", "full"],
      ["production", "productionGraph", "production"],
    ]) {
      stage = name + " project-configured graph installation"
      const target = mirror(name, stagedBytes, candidate)
      npm(cli, operation, target)
      stage = name + " project-configured graph verification"
      assertInstalledGraph(target, mode)
      assert.deepEqual(readFileSync(join(target, "package.json")), stagedBytes)
      assert.deepEqual(readFileSync(join(target, "package-lock.json")), candidate)
      assert.deepEqual(readFileSync(join(target, ".npmrc")), configBytes)
      assert.deepEqual(readFileSync(join(target, LOCAL, "package.json")), packageBytes)
    }
    assert.equal(readFileSync(userConfig).length, 0)
    assert.equal(readFileSync(globalConfig).length, 0)
    for (const item of copied) assert.deepEqual(readFileSync(item.source), item.bytes)

    stage = "bounded generated candidate diff"
    function diff(before, after, path, added = false) {
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
        .replace(/^--- .*$/m, added ? "--- /dev/null" : "--- a/" + path)
        .replace(/^\+\+\+ .*$/m, "+++ b/" + path)
    }
    patch =
      diff(snapshots[0].path, join(generation, "package.json"), "frontend/package.json") +
      diff(snapshots[1].path, candidatePath, "frontend/package-lock.json") +
      diff(
        "/dev/null",
        join(generation, LOCAL, "package.json"),
        "frontend/" + LOCAL + "/package.json",
        true
      )
    assert(Buffer.byteLength(patch) > 0 && Buffer.byteLength(patch) <= 16384)
    report = {
      kind: "react-compiler-adapter-staged-lock-candidate",
      sourceSha: process.env.SOURCE_SHA,
      sourceTree,
      node: process.version,
      npm: "11.17.0",
      bootstrapNpm: "11.19.0",
      registry: "https://registry.npmjs.org/",
      package: release.data.name,
      version: release.data.version,
      registryGitHead: release.data.gitHead,
      sourceRevisionValidator: "generate-zod-root-lock-candidate.mjs#validateRegistryMetadata",
      repository: release.data.repository.url,
      registrySourceMetadataMatched: true,
      cryptographicPublishProvenanceVerified: false,
      published: release.published,
      cooldownMatures: new Date(release.timestamp + 7 * 86400000).toISOString(),
      cooldownException: false,
      tarball: release.data.dist.tarball,
      integrity: release.data.dist.integrity,
      shasum: release.data.dist.shasum,
      tarballVerified: true,
      preservedRootZod: "4.6.7",
      preservedNestedZod: "3.25.76",
      preservedBodyParser: "1.20.9",
      preservedUndici: "8.12.2",
      addedPackagePaths: [LINK, LOCAL, ALIAS],
      consumerOverrideAdded: false,
      formatterChanged: false,
      fullGraphInstallVerified: true,
      productionGraphInstallVerified: true,
      graphInstallPolicy: "project-configured legacy-peer-deps=true; ignore-scripts",
      graphResolutionScope: "package-metadata paths and identities only; no library entrypoints",
      strictPeerCompatibilityVerified: false,
      normalLifecycleOrBuildVerified: false,
      packageContentsVerified: false,
      localReadmeStaged: false,
      sourceAdapterIndexSha256: digest(snapshots[3].bytes),
      stagedLicenseSha256: digest(snapshots[4].bytes),
      libraryCodeExecuted: false,
      lifecycleScriptsExecuted: false,
      checkoutModified: false,
      originalManifestSha256: digest(manifestBytes),
      candidateManifestSha256: digest(stagedBytes),
      localManifestSha256: digest(packageBytes),
      originalLockSha256: digest(lockBytes),
      candidateLockSha256: digest(candidate),
      projectNpmrcSha256: digest(configBytes),
      npmToolPublished: toolMetadata.published,
      npmToolIntegrity: toolMetadata.data.dist.integrity,
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
    console.log("STAGED_ADAPTER_CANDIDATE_METADATA " + JSON.stringify(report))
    console.log(
      "STAGED_ADAPTER_PACKAGE_MANIFEST_BEGIN\n" +
        packageBytes +
        "STAGED_ADAPTER_PACKAGE_MANIFEST_END"
    )
    console.log(
      "STAGED_ADAPTER_CANDIDATE_PATCH_BEGIN\n" + patch + "STAGED_ADAPTER_CANDIDATE_PATCH_END"
    )
    console.log(
      "Source unchanged; graph-only candidate evidence is not a passing audit or normal CI."
    )
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await runStagedAdapterGenerator()
}
