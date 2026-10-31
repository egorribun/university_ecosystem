import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { gunzipSync, gzipSync } from "node:zlib"
import {
  assertFacadePackCommand,
  assertFacadePackPostflight,
  facadeArchiveEvidence,
  facadePackCommand,
  inspectFacadeArchive,
  readFacadeSources,
  validateFacadePackSummary,
  validateFacadeSources,
} from "./pack-react-compiler-zod-compat.mjs"

const NAMES = ["LICENSE", "README.md", "index.cjs", "package.json"]
const NAME = "@university-ecosystem/react-compiler-zod-compat"
const FILENAME = "university-ecosystem-react-compiler-zod-compat-1.0.0.tgz"
const SOURCE = "1".repeat(40)
const TREE = "2".repeat(40)
const hash = (bytes, algorithm = "sha256", encoding = "hex") =>
  createHash(algorithm).update(bytes).digest(encoding)

function sources() {
  return {
    LICENSE: Buffer.from("MIT License\n\nCopyright (c) 2026 fixture\n"),
    "README.md": Buffer.from("A synthetic packaging fixture, never executed.\n"),
    "index.cjs": Buffer.from("module.exports = Object.freeze({})\n"),
    "package.json": Buffer.from(
      JSON.stringify(
        {
          name: NAME,
          version: "1.0.0",
          private: true,
          description: "The legacy schema API used only by the pinned React Compiler ESLint gate",
          main: "index.cjs",
          files: ["index.cjs", "LICENSE", "README.md"],
          license: "MIT",
          dependencies: { "patched-zod": "npm:zod@4.6.7" },
        },
        null,
        2
      ) + "\n"
    ),
  }
}

function withDirectory(action) {
  const directory = realpathSync(mkdtempSync(join(tmpdir(), "compiler-facade-pack-test-")))
  try {
    return action(directory)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
}

function writeSources(directory, files) {
  mkdirSync(directory, { recursive: true })
  for (const name of NAMES) writeFileSync(join(directory, name), files[name])
}

function sourceFiles(files) {
  return NAMES.map((path) => ({
    path,
    bytes: files[path].length,
    sha256: hash(files[path]),
  }))
}

function checksum(header) {
  header.fill(32, 148, 156)
  const sum = header.reduce((total, byte) => total + byte, 0)
  header.write(sum.toString(8).padStart(6, "0") + "\0 ", 148, 8, "ascii")
}

function tarBytes(
  files,
  entries = NAMES.map((name) => ({ name: "package/" + name, nameKey: name }))
) {
  const blocks = []
  for (const entry of entries) {
    const bytes = entry.bytes ?? files[entry.nameKey] ?? Buffer.alloc(0)
    const header = Buffer.alloc(512)
    header.write(entry.name, 0, 100, "utf8")
    header.write("0000644\0", 100, 8, "ascii")
    header.write("0000000\0", 108, 8, "ascii")
    header.write("0000000\0", 116, 8, "ascii")
    header.write(bytes.length.toString(8).padStart(11, "0") + "\0", 124, 12, "ascii")
    const mtime = Math.floor(Date.parse("1985-10-26T08:15:00Z") / 1000)
    header.write(mtime.toString(8).padStart(11, "0") + "\0", 136, 12, "ascii")
    header.write(entry.type ?? "0", 156, 1, "ascii")
    header.write(entry.link ?? "", 157, 100, "utf8")
    header.write("ustar\0", 257, 6, "ascii")
    header.write("00", 263, 2, "ascii")
    header.write(entry.prefix ?? "", 345, 155, "utf8")
    checksum(header)
    blocks.push(header, bytes, Buffer.alloc((512 - (bytes.length % 512)) % 512))
  }
  return Buffer.concat([...blocks, Buffer.alloc(1024)])
}

function archive(files, entries) {
  return gzipSync(tarBytes(files, entries), { level: 9 })
}

function packSummary(bytes, files) {
  return JSON.stringify([
    {
      id: NAME + "@1.0.0",
      name: NAME,
      version: "1.0.0",
      size: bytes.length,
      unpackedSize: NAMES.reduce((sum, name) => sum + files[name].length, 0),
      shasum: hash(bytes, "sha1"),
      integrity: "sha512-" + hash(bytes, "sha512", "base64"),
      filename: FILENAME,
      files: NAMES.map((path) => ({ path, size: files[path].length, mode: 0o644 })),
      entryCount: 4,
      bundled: [],
    },
  ])
}

function provenance() {
  return {
    sourceSha: SOURCE,
    sourceTree: TREE,
    node: "v24.21.0",
    npm: "11.17.0",
    platform: "linux",
    arch: "x64",
    postflightVerified: true,
    cleanupComplete: true,
  }
}

test("pack command is offline, lifecycle-free and limited to the owned destination", () => {
  withDirectory((directory) => {
    const destination = join(directory, "output")
    const expected = [
      "pack",
      "--ignore-scripts",
      "--offline",
      "--json",
      "--pack-destination=" + destination,
      "--no-audit",
      "--no-fund",
    ]
    assert.deepEqual(facadePackCommand(destination), expected)
    assert.equal(assertFacadePackCommand(expected, destination), true)
  })
})

test("pack command rejects relative, noncanonical and control-bearing destinations", () => {
  for (const path of ["", ".", "output", "/owned/../outside", "/owned\noutside", null]) {
    assert.throws(() => facadePackCommand(path), { name: "AssertionError" })
  }
})

test("pack command guard rejects scripts, online mode and extra package arguments", () => {
  withDirectory((directory) => {
    const destination = join(directory, "output")
    const args = [
      "pack",
      "--ignore-scripts",
      "--offline",
      "--json",
      "--pack-destination=" + destination,
      "--no-audit",
      "--no-fund",
    ]
    for (const changed of [
      args.filter((value) => value !== "--ignore-scripts"),
      args.filter((value) => value !== "--offline"),
      [...args, "--ignore-scripts=false"],
      [...args, "private-package"],
      args.map((value) => (value.startsWith("--pack-destination=") ? "/outside" : value)),
    ]) {
      assert.throws(() => assertFacadePackCommand(changed, destination), {
        name: "AssertionError",
      })
    }
  })
})

test("source contract accepts only the honest four-file dev facade", () => {
  assert.equal(validateFacadeSources(sources()), true)
})

test("source manifest rejects identity, engine, license, scripts and scope changes", () => {
  for (const mutate of [
    (value) => (value.name = "zod"),
    (value) => (value.version = "4.6.7"),
    (value) => (value.private = false),
    (value) => (value.main = "other.cjs"),
    (value) => (value.license = "UNLICENSED"),
    (value) => (value.dependencies["patched-zod"] = "npm:zod@3.25.76"),
    (value) => (value.dependencies.zod = "4.6.7"),
    (value) => (value.scripts = { prepare: "node index.cjs" }),
    (value) => value.files.push("legacy-baseline.json"),
  ]) {
    const files = sources()
    const manifest = JSON.parse(files["package.json"])
    mutate(manifest)
    files["package.json"] = Buffer.from(JSON.stringify(manifest))
    assert.throws(() => validateFacadeSources(files), { name: "AssertionError" })
  }
})

test("source contract rejects missing, extra, empty, nonbuffer and invalid UTF-8", () => {
  for (const mutate of [
    (files) => delete files.LICENSE,
    (files) => (files["legacy-baseline.json"] = Buffer.from("{}")),
    (files) => (files["index.cjs"] = Buffer.alloc(0)),
    (files) => (files["index.cjs"] = "not a buffer"),
    (files) => (files["index.cjs"] = Buffer.from([255])),
    (files) => (files.LICENSE = Buffer.from("Not an MIT license\n")),
  ]) {
    const files = sources()
    mutate(files)
    assert.throws(() => validateFacadeSources(files), { name: "AssertionError" })
  }
})

test("source contract bounds each file and the total snapshot", () => {
  const oversized = sources()
  oversized["index.cjs"] = Buffer.alloc(65537, 32)
  assert.throws(() => validateFacadeSources(oversized), { name: "AssertionError" })
  const excessive = sources()
  excessive["index.cjs"] = Buffer.alloc(45000, 32)
  excessive["README.md"] = Buffer.alloc(45000, 32)
  excessive.LICENSE = Buffer.from("MIT License\n" + " ".repeat(45000))
  assert.throws(() => validateFacadeSources(excessive), { name: "AssertionError" })
})

test("source reader reads only four regular files without importing their code", () => {
  withDirectory((directory) => {
    const files = sources()
    files["index.cjs"] = Buffer.from("throw new Error('Source must never execute')\n")
    writeSources(directory, files)
    writeFileSync(join(directory, "legacy-baseline.json"), "excluded")
    assert.deepEqual(readFacadeSources(directory), files)
  })
})

test("source reader rejects linked files and linked source directories", () => {
  withDirectory((directory) => {
    const source = join(directory, "source")
    const files = sources()
    writeSources(source, files)
    const linked = join(directory, "linked")
    symlinkSync(source, linked, "dir")
    assert.throws(() => readFacadeSources(linked), { name: "AssertionError" })
    rmSync(join(source, "index.cjs"))
    writeFileSync(join(directory, "outside.cjs"), files["index.cjs"])
    symlinkSync(join(directory, "outside.cjs"), join(source, "index.cjs"))
    assert.throws(() => readFacadeSources(source), { name: "AssertionError" })
  })
})

test("source reader rejects missing, nonregular and oversized members", () => {
  for (const mutation of ["missing", "directory", "oversized"]) {
    withDirectory((directory) => {
      writeSources(directory, sources())
      const path = join(directory, "index.cjs")
      rmSync(path)
      if (mutation === "directory") mkdirSync(path)
      if (mutation === "oversized") writeFileSync(path, Buffer.alloc(65537, 32))
      assert.throws(() => readFacadeSources(directory))
    })
  }
})

test("archive inspector binds every payload byte and emits only finite hash metadata", () => {
  const files = sources()
  const bytes = archive(files)
  assert.deepEqual(inspectFacadeArchive(bytes, files), {
    bytes: bytes.length,
    sha256: hash(bytes),
    files: sourceFiles(files),
  })
})

test("archive inspector rejects invalid gzip and compressed or expanded overflow", () => {
  const files = sources()
  const corrupt = archive(files)
  corrupt[corrupt.length - 5] ^= 1
  for (const bytes of [
    Buffer.from("not gzip"),
    corrupt,
    Buffer.alloc(65537),
    gzipSync(Buffer.alloc(256 * 1024 + 1)),
  ]) {
    assert.throws(() => inspectFacadeArchive(bytes, files))
  }
})

test("archive inspector rejects checksum, size, padding and termination corruption", () => {
  const files = sources()
  for (const mutation of ["checksum", "size", "termination", "padding"]) {
    let tar = tarBytes(files)
    if (mutation === "checksum") tar[0] ^= 1
    if (mutation === "size") {
      tar[124] = 128
      checksum(tar.subarray(0, 512))
    }
    if (mutation === "termination") tar = tar.subarray(0, tar.length - 512)
    if (mutation === "padding") tar[512 + files.LICENSE.length] = 1
    assert.throws(() => inspectFacadeArchive(gzipSync(tar), files), {
      name: "AssertionError",
    })
  }
})

test("archive inspector rejects traversal, absolute, duplicate and unlisted paths", () => {
  const files = sources()
  const standard = NAMES.map((name) => ({ name: "package/" + name, nameKey: name }))
  for (const entries of [
    [{ name: "../index.cjs", nameKey: "index.cjs" }, ...standard],
    [{ name: "/outside", nameKey: "index.cjs" }, ...standard],
    [{ name: "package/./index.cjs", nameKey: "index.cjs" }, ...standard],
    [{ name: "package\\index.cjs", nameKey: "index.cjs" }, ...standard],
    [standard[0], ...standard],
    [...standard, { name: "package/legacy-baseline.json", bytes: Buffer.from("{}") }],
    standard.slice(1),
  ]) {
    assert.throws(() => inspectFacadeArchive(archive(files, entries), files), {
      name: "AssertionError",
    })
  }
})

test("archive inspector rejects links, PAX, directories and nonempty prefixes", () => {
  const files = sources()
  for (const extra of [
    { type: "1", link: "outside" },
    { type: "2", link: "outside" },
    { type: "5" },
    { type: "x" },
    { type: "g" },
    { type: "0", link: "outside" },
    { prefix: "../" },
  ]) {
    const entries = NAMES.map((name) => ({ name: "package/" + name, nameKey: name }))
    entries[0] = { ...entries[0], ...extra }
    assert.throws(() => inspectFacadeArchive(archive(files, entries), files), {
      name: "AssertionError",
    })
  }
})

test("archive inspector rejects payload changes despite valid gzip and tar checksums", () => {
  const files = sources()
  const changed = sources()
  changed["index.cjs"] = Buffer.from("module.exports = { changed: true }\n")
  assert.throws(() => inspectFacadeArchive(archive(changed), files), {
    name: "AssertionError",
  })
})

test("npm pack summary is bound to exact archive hashes, members and identity", () => {
  const files = sources()
  const bytes = archive(files)
  assert.equal(validateFacadePackSummary(packSummary(bytes, files), bytes, files), true)
})

test("npm pack summary rejects unlisted files, hashes, names and unbounded output", () => {
  const files = sources()
  const bytes = archive(files)
  for (const mutate of [
    (value) => (value[0].name = "zod"),
    (value) => (value[0].version = "4.6.7"),
    (value) => (value[0].filename = "../outside.tgz"),
    (value) => (value[0].size += 1),
    (value) => (value[0].unpackedSize += 1),
    (value) => (value[0].shasum = "0".repeat(40)),
    (value) => (value[0].integrity = "sha512-" + hash("other", "sha512", "base64")),
    (value) => (value[0].entryCount = 5),
    (value) => value[0].bundled.push("zod"),
    (value) => (value[0].files[0].mode = 0o755),
    (value) => value[0].files.push({ path: "legacy-baseline.json", size: 2, mode: 0o644 }),
    (value) => value.push(value[0]),
  ]) {
    const value = JSON.parse(packSummary(bytes, files))
    mutate(value)
    assert.throws(() => validateFacadePackSummary(JSON.stringify(value), bytes, files), {
      name: "AssertionError",
    })
  }
  for (const value of ["not json", "null", "{}", "[]", " ".repeat(8193)]) {
    assert.throws(() => validateFacadePackSummary(value, bytes, files))
  }
})

test("postflight requires identical clean Git identity and every source byte", () => {
  const before = { head: SOURCE, tree: TREE, status: "", files: sources() }
  const after = { head: SOURCE, tree: TREE, status: "", files: sources() }
  assert.equal(assertFacadePackPostflight(before, after, SOURCE), true)
})

test("postflight rejects source, tree, head and dirty checkout changes", () => {
  for (const mutate of [
    (value) => (value.head = "3".repeat(40)),
    (value) => (value.tree = "3".repeat(40)),
    (value) => (value.status = " M frontend/package-lock.json"),
    (value) => (value.files["index.cjs"] = Buffer.from("changed")),
    (value) => delete value.files.LICENSE,
  ]) {
    const before = { head: SOURCE, tree: TREE, status: "", files: sources() }
    const after = { head: SOURCE, tree: TREE, status: "", files: sources() }
    mutate(after)
    assert.throws(() => assertFacadePackPostflight(before, after, SOURCE), {
      name: "AssertionError",
    })
  }
  const snapshot = { head: SOURCE, tree: TREE, status: "", files: sources() }
  assert.throws(() => assertFacadePackPostflight(snapshot, snapshot, "3".repeat(40)), {
    name: "AssertionError",
  })
})

test("foundation evidence contains canonical bounded bytes and source provenance only", () => {
  const files = sources()
  const bytes = archive(files)
  const report = facadeArchiveEvidence(bytes, Buffer.from(bytes), files, provenance())
  assert.deepEqual(report, {
    kind: "react-compiler-facade-foundation-candidate",
    sourceSha: SOURCE,
    sourceTree: TREE,
    packageName: NAME,
    version: "1.0.0",
    license: "MIT",
    engineAlias: "npm:zod@4.6.7",
    recipe: "frontend/scripts/pack-react-compiler-zod-compat.mjs",
    artifactPath: "frontend/vendor/react-compiler-zod-compat-1.0.0.tgz",
    archive: { bytes: bytes.length, sha256: hash(bytes), base64: bytes.toString("base64") },
    sourceFiles: sourceFiles(files),
    node: "v24.21.0",
    npm: "11.17.0",
    platform: "linux",
    arch: "x64",
    reproduced: true,
    reproducibilityScope: "two packs in this pinned Linux Node/npm environment",
    sourceUnchanged: true,
    temporaryWorkspaceRemoved: true,
    packageGraphChanged: false,
    artifactPublished: false,
  })
  assert.deepEqual(Buffer.from(report.archive.base64, "base64"), bytes)
  assert.ok(Buffer.byteLength(JSON.stringify(report)) <= 96 * 1024)
})

test("foundation evidence rejects changed compression despite identical payloads", () => {
  const files = sources()
  const first = archive(files)
  const second = Buffer.from(first)
  second[4] ^= 1
  assert.deepEqual(gunzipSync(second), gunzipSync(first))
  assert.notDeepEqual(first, second)
  assert.throws(() => facadeArchiveEvidence(first, second, files, provenance()), {
    name: "AssertionError",
  })
})

test("foundation evidence refuses unverified cleanup, source or runtime provenance", () => {
  const files = sources()
  const bytes = archive(files)
  for (const mutate of [
    (value) => (value.sourceSha = "not a commit"),
    (value) => (value.sourceTree = "3".repeat(39)),
    (value) => (value.node = "v22.0.0"),
    (value) => (value.npm = "11.19.0"),
    (value) => (value.platform = "darwin"),
    (value) => (value.arch = "arm64"),
    (value) => (value.postflightVerified = false),
    (value) => (value.cleanupComplete = false),
    (value) => (value.cleanupComplete = "true"),
  ]) {
    const value = provenance()
    mutate(value)
    assert.throws(() => facadeArchiveEvidence(bytes, bytes, files, value), {
      name: "AssertionError",
    })
  }
})

test("foundation entrypoint fails closed without output and import remains inert", () => {
  const url = new URL("./pack-react-compiler-zod-compat.mjs", import.meta.url)
  const options = {
    env: { GITHUB_WORKSPACE: "/facade-pack-test-does-not-exist" },
    encoding: "utf8",
    timeout: 10000,
    maxBuffer: 4096,
  }
  const direct = spawnSync(process.execPath, [fileURLToPath(url)], options)
  assert.equal(direct.status, 1)
  assert.equal(direct.stdout, "")
  assert.equal(direct.stderr, "Facade archive rejected at stage: preflight\n")
  const imported = spawnSync(
    process.execPath,
    ["--input-type=module", "-e", "import " + JSON.stringify(url.href)],
    options
  )
  assert.equal(imported.status, 0)
  assert.equal(imported.stdout, "")
  assert.equal(imported.stderr, "")
})

test("archive inspector rejects an empty second gzip member despite identical payload", () => {
  const files = sources()
  const first = archive(files)
  const concatenated = Buffer.concat([first, gzipSync(Buffer.alloc(0))])
  assert.deepEqual(gunzipSync(concatenated), gunzipSync(first))
  assert.throws(() => inspectFacadeArchive(concatenated, files))
})

test("archive inspector rejects trailing garbage after the gzip member", () => {
  const files = sources()
  const first = archive(files)
  const padded = Buffer.concat([first, Buffer.alloc(8)])
  assert.deepEqual(gunzipSync(padded), gunzipSync(first))
  for (const trailing of [padded, Buffer.concat([first, Buffer.from("trailing garbage")])]) {
    assert.throws(() => inspectFacadeArchive(trailing, files))
  }
})
