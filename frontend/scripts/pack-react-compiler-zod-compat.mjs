import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs"
import { get } from "node:https"
import { dirname, isAbsolute, join, resolve } from "node:path"
import { pathToFileURL } from "node:url"
import { gunzipSync } from "node:zlib"
import {
  assertNpmCommand,
  npmCommand,
  validateRegistryMetadata,
  verifyArchiveBytes,
} from "./generate-zod-root-lock-candidate.mjs"
import {
  adapterManifest,
  assertImmutableCheckout,
} from "./generate-react-compiler-adapter-lock-candidate.mjs"

const NAMES = Object.freeze(["LICENSE", "README.md", "index.cjs", "package.json"])
const LOCAL = "scripts/react-compiler-zod-compat"
const NAME = "@university-ecosystem/react-compiler-zod-compat"
const FILENAME = "university-ecosystem-react-compiler-zod-compat-1.0.0.tgz"
const FILE_LIMIT = 64 * 1024
const SOURCE_LIMIT = 128 * 1024
const ARCHIVE_LIMIT = 64 * 1024
const TAR_LIMIT = 256 * 1024
const REPORT_LIMIT = 96 * 1024
const PACK_MTIME = Math.floor(Date.parse("1985-10-26T08:15:00Z") / 1000)
const digest = (bytes, algorithm = "sha256", encoding = "hex") =>
  createHash(algorithm).update(bytes).digest(encoding)

function assertCanonicalPath(path) {
  assert(typeof path === "string" && path.length > 0 && path.length <= 4096)
  assert(isAbsolute(path) && resolve(path) === path)
  assert(
    [...path].every((character) => {
      const code = character.charCodeAt(0)
      return code >= 32 && code !== 127
    })
  )
}

export function facadePackCommand(destination) {
  assertCanonicalPath(destination)
  return Object.freeze([
    "pack",
    "--ignore-scripts",
    "--offline",
    "--json",
    "--pack-destination=" + destination,
    "--no-audit",
    "--no-fund",
  ])
}

export function assertFacadePackCommand(args, destination) {
  assert.deepEqual(args, facadePackCommand(destination))
  return true
}

export function validateFacadeSources(files) {
  assert(files && typeof files === "object" && !Array.isArray(files))
  assert.deepEqual(Object.keys(files).sort(), NAMES)
  let total = 0
  for (const name of NAMES) {
    const bytes = files[name]
    assert(Buffer.isBuffer(bytes) && bytes.length > 0 && bytes.length <= FILE_LIMIT)
    assert.deepEqual(Buffer.from(bytes.toString("utf8"), "utf8"), bytes)
    total += bytes.length
  }
  assert(total <= SOURCE_LIMIT)
  assert(files.LICENSE.toString("utf8").startsWith("MIT License\n"))
  assert.deepEqual(JSON.parse(files["package.json"]), adapterManifest())
  return true
}

function regularBytes(path, limit) {
  assertCanonicalPath(path)
  assert.equal(realpathSync(path), path)
  const stat = lstatSync(path)
  assert(stat.isFile() && stat.size > 0 && stat.size <= limit)
  const bytes = readFileSync(path)
  assert.equal(bytes.length, stat.size)
  return bytes
}

export function readFacadeSources(directory) {
  assertCanonicalPath(directory)
  assert.equal(realpathSync(directory), directory)
  assert(lstatSync(directory).isDirectory())
  const files = Object.fromEntries(
    NAMES.map((name) => [name, regularBytes(join(directory, name), FILE_LIMIT)])
  )
  validateFacadeSources(files)
  return files
}

function sourceFiles(files) {
  return NAMES.map((path) => ({
    path,
    bytes: files[path].length,
    sha256: digest(files[path]),
  }))
}

function zeroBytes(bytes) {
  return bytes.every((byte) => byte === 0)
}

// Accept canonical octal forms emitted by npm's tar and the POSIX fixture.
// Never accept base-256, signs, whitespace prefixes or parseInt suffixes.
function tarNumber(bytes, allowBlank = false) {
  if (allowBlank && zeroBytes(bytes)) return 0
  let digits
  if (bytes.at(-1) === 0) {
    digits = bytes.subarray(0, bytes.length - (bytes.at(-2) === 32 ? 2 : 1))
  } else {
    assert(bytes.at(-1) === 32 && bytes.at(-2) === 0)
    digits = bytes.subarray(0, bytes.length - 2)
  }
  assert(digits.length > 0 && digits.every((byte) => byte >= 48 && byte <= 55))
  const value = Number.parseInt(digits.toString("ascii"), 8)
  assert(Number.isSafeInteger(value) && value >= 0)
  return value
}

export function inspectFacadeArchive(bytes, files) {
  validateFacadeSources(files)
  assert(Buffer.isBuffer(bytes) && bytes.length > 18 && bytes.length <= ARCHIVE_LIMIT)
  assert.deepEqual(bytes.subarray(0, 4), Buffer.from([31, 139, 8, 0]))
  // Node 24.21 rejects additional gzip members and trailing input explicitly.
  const tar = gunzipSync(bytes, {
    maxOutputLength: TAR_LIMIT,
    rejectGarbageAfterEnd: true,
  })
  assert(tar.length >= 1024 && tar.length <= TAR_LIMIT && tar.length % 512 === 0)
  const seen = new Set()
  let offset = 0
  let terminated = false
  while (offset < tar.length) {
    const header = tar.subarray(offset, offset + 512)
    if (zeroBytes(header)) {
      assert.equal(tar.length - offset, 1024)
      assert(zeroBytes(tar.subarray(offset)))
      terminated = true
      break
    }
    assert(seen.size < NAMES.length)
    const nameField = header.subarray(0, 100)
    const end = nameField.indexOf(0)
    assert(end > 0 && zeroBytes(nameField.subarray(end)))
    const path = nameField.subarray(0, end).toString("utf8")
    const name = NAMES.find((candidate) => path === "package/" + candidate)
    assert(name && !seen.has(name))
    assert.deepEqual(nameField.subarray(0, end), Buffer.from("package/" + name))
    assert.equal(tarNumber(header.subarray(100, 108)), 0o644)
    assert.equal(tarNumber(header.subarray(108, 116), true), 0)
    assert.equal(tarNumber(header.subarray(116, 124), true), 0)
    const size = tarNumber(header.subarray(124, 136))
    assert.equal(size, files[name].length)
    assert.equal(tarNumber(header.subarray(136, 148)), PACK_MTIME)
    let checksum = 8 * 32
    for (let index = 0; index < 512; index += 1) {
      if (index < 148 || index >= 156) checksum += header[index]
    }
    assert.equal(tarNumber(header.subarray(148, 156)), checksum)
    assert.equal(header[156], 48)
    assert(zeroBytes(header.subarray(157, 257)))
    assert.deepEqual(header.subarray(257, 265), Buffer.from("ustar\0" + "00"))
    assert(zeroBytes(header.subarray(265, 329)))
    assert.equal(tarNumber(header.subarray(329, 337), true), 0)
    assert.equal(tarNumber(header.subarray(337, 345), true), 0)
    assert(zeroBytes(header.subarray(345, 512)))
    const start = offset + 512
    const payloadEnd = start + size
    const next = start + Math.ceil(size / 512) * 512
    assert(next <= tar.length)
    assert.deepEqual(tar.subarray(start, payloadEnd), files[name])
    assert(zeroBytes(tar.subarray(payloadEnd, next)))
    seen.add(name)
    offset = next
  }
  assert(terminated)
  assert.deepEqual([...seen].sort(), NAMES)
  return { bytes: bytes.length, sha256: digest(bytes), files: sourceFiles(files) }
}

export function validateFacadePackSummary(output, bytes, files) {
  assert(typeof output === "string" && Buffer.byteLength(output) <= 8192)
  inspectFacadeArchive(bytes, files)
  const expected = {
    id: NAME + "@1.0.0",
    name: NAME,
    version: "1.0.0",
    size: bytes.length,
    unpackedSize: NAMES.reduce((sum, name) => sum + files[name].length, 0),
    shasum: digest(bytes, "sha1"),
    integrity: "sha512-" + digest(bytes, "sha512", "base64"),
    filename: FILENAME,
    files: NAMES.map((path) => ({ path, size: files[path].length, mode: 0o644 })),
    entryCount: 4,
    bundled: [],
  }
  assert.deepEqual(JSON.parse(output), [expected])
  return true
}

export function assertFacadePackPostflight(before, after, expectedSha) {
  assert.match(expectedSha ?? "", /^[0-9a-f]{40}$/)
  for (const state of [before, after]) {
    assert.equal(state.head, expectedSha)
    assert.match(state.tree ?? "", /^[0-9a-f]{40}$/)
    assert.equal(state.status, "")
    validateFacadeSources(state.files)
  }
  assert.equal(after.tree, before.tree)
  assert.deepEqual(after.files, before.files)
  return true
}

export function facadeArchiveEvidence(first, second, files, provenance) {
  const archive = inspectFacadeArchive(first, files)
  inspectFacadeArchive(second, files)
  assert.deepEqual(second, first)
  assert.match(provenance.sourceSha ?? "", /^[0-9a-f]{40}$/)
  assert.match(provenance.sourceTree ?? "", /^[0-9a-f]{40}$/)
  assert.equal(provenance.node, "v24.21.0")
  assert.equal(provenance.npm, "11.17.0")
  assert.equal(provenance.platform, "linux")
  assert.equal(provenance.arch, "x64")
  assert.equal(provenance.postflightVerified, true)
  assert.equal(provenance.cleanupComplete, true)
  const report = {
    kind: "react-compiler-facade-foundation-candidate",
    sourceSha: provenance.sourceSha,
    sourceTree: provenance.sourceTree,
    packageName: NAME,
    version: "1.0.0",
    license: "MIT",
    engineAlias: "npm:zod@4.6.7",
    recipe: "frontend/scripts/pack-react-compiler-zod-compat.mjs",
    artifactPath: "frontend/vendor/react-compiler-zod-compat-1.0.0.tgz",
    archive: {
      bytes: archive.bytes,
      sha256: archive.sha256,
      base64: first.toString("base64"),
    },
    sourceFiles: archive.files,
    node: provenance.node,
    npm: provenance.npm,
    platform: provenance.platform,
    arch: provenance.arch,
    reproduced: true,
    reproducibilityScope: "two packs in this pinned Linux Node/npm environment",
    sourceUnchanged: true,
    temporaryWorkspaceRemoved: true,
    packageGraphChanged: false,
    artifactPublished: false,
  }
  assert.deepEqual(Buffer.from(report.archive.base64, "base64"), first)
  assert(Buffer.byteLength(JSON.stringify(report)) <= REPORT_LIMIT)
  return report
}

export async function runFacadePack() {
  let stage = "preflight"
  let scratch
  let before
  let snapshots
  let sourceDirectory
  let git
  let archives
  let failed = false
  let postflightVerified = false
  let cleanupComplete = false
  const sourceSha = process.env.SOURCE_SHA
  const deadline = performance.now() + 2 * 60_000
  const remaining = (cap) => {
    const budget = Math.floor(deadline - performance.now())
    assert(budget > 0)
    return Math.min(cap, budget)
  }
  const reject = () => {
    failed = true
    console.error("Facade archive rejected at stage: " + stage)
  }
  try {
    assert.equal(process.version, "v24.21.0")
    assert.equal(process.platform, "linux")
    assert.equal(process.arch, "x64")
    assert.match(sourceSha ?? "", /^[0-9a-f]{40}$/)
    const workspace = realpathSync(process.env.GITHUB_WORKSPACE)
    assertCanonicalPath(workspace)
    const frontend = join(workspace, "frontend")
    assert.equal(realpathSync(process.cwd()), frontend)
    sourceDirectory = join(frontend, LOCAL)
    const files = readFacadeSources(sourceDirectory)
    snapshots = [
      ["frontend/package.json", 64 * 1024],
      ["frontend/package-lock.json", 4 * 1024 * 1024],
      ["frontend/.npmrc", 4096],
      ["LICENSE", FILE_LIMIT],
    ].map(([name, limit]) => ({
      name,
      path: join(workspace, name),
      limit,
      bytes: regularBytes(join(workspace, name), limit),
    }))
    assert.equal(JSON.parse(snapshots[0].bytes).packageManager, "npm@11.17.0")
    assert.equal(
      snapshots[2].bytes.toString(),
      "legacy-peer-deps=true\nengine-strict=true\nmin-release-age=7\nstrict-allow-scripts=true\n"
    )
    assert.deepEqual(files.LICENSE, snapshots[3].bytes)
    const temporaryRoot = realpathSync(process.env.RUNNER_TEMP)
    assertCanonicalPath(temporaryRoot)
    assert(temporaryRoot !== workspace && !temporaryRoot.startsWith(workspace + "/"))
    scratch = realpathSync(mkdtempSync(join(temporaryRoot, "compiler-facade-pack-")))
    const userConfig = join(scratch, "empty-user.npmrc")
    const globalConfig = join(scratch, "empty-global.npmrc")
    for (const path of [userConfig, globalConfig]) {
      writeFileSync(path, "", { flag: "wx", mode: 0o400 })
    }
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
      NPM_CONFIG_IGNORE_SCRIPTS: "true",
    }
    function command(executable, args, cwd, options = {}) {
      const result = spawnSync(executable, args, {
        cwd,
        env: npmEnv,
        encoding: "utf8",
        shell: false,
        timeout: options.postflight ? 10_000 : remaining(options.timeout ?? 60_000),
        maxBuffer: options.maxBuffer ?? 2 * 1024 * 1024,
      })
      assert(!result.error && !result.signal && result.status === 0)
      assert.equal(result.stderr, "")
      return result.stdout
    }
    git = (args, postflight = false) =>
      command("/usr/bin/git", args, workspace, {
        timeout: 10_000,
        maxBuffer: 5 * 1024 * 1024,
        postflight,
      })
    before = {
      head: git(["rev-parse", "HEAD"]).trim(),
      tree: git(["rev-parse", "HEAD^{tree}"]).trim(),
      status: git(["status", "--porcelain=v1", "--untracked-files=all"]),
      files,
    }
    assertImmutableCheckout({
      expectedSha: sourceSha,
      head: before.head,
      status: before.status,
      node: process.version,
      repository: process.env.GITHUB_REPOSITORY,
      hasNodeModules: existsSync(join(frontend, "node_modules")),
    })
    assertFacadePackPostflight(before, before, sourceSha)
    // Compare the four payloads and configuration snapshots with Git itself.
    // A clean-looking checkout alone is not the source-byte authority.
    const tracked = [
      ...snapshots.map(({ name, bytes }) => ({ name, bytes })),
      ...NAMES.map((name) => ({ name: "frontend/" + LOCAL + "/" + name, bytes: files[name] })),
    ]
    for (const item of tracked) {
      const index = git(["ls-files", "--stage", "--", item.name]).trim()
      assert.match(index, /^100644 [0-9a-f]{40} 0\t/)
      assert.equal(index.split("\t")[1], item.name)
      assert.deepEqual(Buffer.from(git(["show", sourceSha + ":" + item.name])), item.bytes)
    }

    stage = "isolated four-file mirrors"
    const mirrors = ["first", "second"].map((name) => {
      const directory = join(scratch, name)
      const destination = join(scratch, name + "-output")
      mkdirSync(directory)
      mkdirSync(destination)
      for (const path of NAMES) {
        writeFileSync(join(directory, path), files[path], { flag: "wx", mode: 0o644 })
      }
      assert.deepEqual(readdirSync(directory).sort(), NAMES)
      assert.deepEqual(readFacadeSources(directory), files)
      assert.equal(realpathSync(destination), destination)
      return { directory, destination }
    })
    const bootstrap = realpathSync(join(dirname(process.execPath), "npm"))
    assert.equal(
      bootstrap,
      join(dirname(dirname(process.execPath)), "lib/node_modules/npm/bin/npm-cli.js")
    )
    function npm(cli, operation, cwd, paths = {}) {
      const args = npmCommand(operation, paths)
      assertNpmCommand(operation, args, paths)
      return command(process.execPath, [cli, ...args], cwd)
    }
    assert.equal(npm(bootstrap, "version", scratch).trim(), "11.19.0")

    stage = "npm tool metadata and archive verification"
    const tool = validateRegistryMetadata(
      JSON.parse(npm(bootstrap, "toolMetadata", scratch)),
      "npm",
      "11.17.0"
    )
    assert.equal(tool.data.repository?.type, "git")
    assert.equal(tool.data.repository?.url, "git+https://github.com/npm/cli.git")
    const toolArchive = join(scratch, "npm-11.17.0.tgz")
    const timeout = remaining(30_000)
    const toolBytes = await new Promise((resolveBytes, rejectArchive) => {
      const chunks = []
      let size = 0
      const request = get(
        tool.data.dist.tarball,
        { headers: { Accept: "application/octet-stream" } },
        (response) => {
          if (response.statusCode !== 200) {
            response.destroy()
            rejectArchive(new Error("Non-200 archive response"))
            return
          }
          response.on("data", (chunk) => {
            size += chunk.length
            if (size > 16 * 1024 * 1024) request.destroy(new Error("Archive size exceeded"))
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
    verifyArchiveBytes(tool.data, toolBytes, 16 * 1024 * 1024)
    writeFileSync(toolArchive, toolBytes, { flag: "wx", mode: 0o600 })
    stage = "isolated npm tool installation"
    const prefix = join(scratch, "tool")
    mkdirSync(prefix)
    npm(bootstrap, "toolInstall", scratch, { prefix, archive: toolArchive })
    const cli = realpathSync(join(prefix, "node_modules/npm/bin/npm-cli.js"))
    assert(cli.startsWith(prefix + "/"))
    assert.equal(npm(cli, "version", scratch).trim(), "11.17.0")

    archives = []
    for (const [index, mirror] of mirrors.entries()) {
      stage = index === 0 ? "first offline pack" : "second offline pack"
      const args = facadePackCommand(mirror.destination)
      assertFacadePackCommand(args, mirror.destination)
      const summary = command(process.execPath, [cli, ...args], mirror.directory, {
        maxBuffer: 8192,
      })
      assert.deepEqual(readdirSync(mirror.destination), [FILENAME])
      const bytes = regularBytes(join(mirror.destination, FILENAME), ARCHIVE_LIMIT)
      validateFacadePackSummary(summary, bytes, files)
      assert.deepEqual(readdirSync(mirror.directory).sort(), NAMES)
      assert.deepEqual(readFacadeSources(mirror.directory), files)
      archives.push(bytes)
    }
    stage = "archive reproducibility and configuration verification"
    assert.deepEqual(archives[0], archives[1])
    for (const path of [userConfig, globalConfig]) {
      assert.equal(realpathSync(path), path)
      assert(lstatSync(path).isFile())
      assert.equal(readFileSync(path).length, 0)
    }
  } catch {
    reject()
  } finally {
    try {
      stage = "original source verification"
      if (snapshots) {
        for (const item of snapshots) {
          assert.deepEqual(regularBytes(item.path, item.limit), item.bytes)
        }
      }
      if (before && git) {
        const after = {
          head: git(["rev-parse", "HEAD"], true).trim(),
          tree: git(["rev-parse", "HEAD^{tree}"], true).trim(),
          status: git(["status", "--porcelain=v1", "--untracked-files=all"], true),
          files: readFacadeSources(sourceDirectory),
        }
        assertFacadePackPostflight(before, after, sourceSha)
        postflightVerified = true
      }
    } catch {
      reject()
    } finally {
      stage = "temporary workspace cleanup"
      try {
        if (scratch) {
          rmSync(scratch, { recursive: true, force: true })
          assert(!existsSync(scratch))
          cleanupComplete = true
        }
      } catch {
        reject()
      }
    }
  }
  if (failed) return 1
  stage = "bounded foundation evidence"
  try {
    const report = facadeArchiveEvidence(archives[0], archives[1], before.files, {
      sourceSha,
      sourceTree: before.tree,
      node: process.version,
      npm: "11.17.0",
      platform: process.platform,
      arch: process.arch,
      postflightVerified,
      cleanupComplete,
    })
    console.log("REACT_COMPILER_FACADE_FOUNDATION_CANDIDATE " + JSON.stringify(report))
    return 0
  } catch {
    reject()
    return 1
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  process.exitCode = await runFacadePack()
}
