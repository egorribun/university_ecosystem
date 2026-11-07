"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const LIMIT = 8 * 1024 * 1024;
const SOURCE_TOTAL_LIMIT = 16 * 1024 * 1024;
// Public immutable upstream Git identities, not secret or policy dispositions.
const UPSTREAM = Object.freeze({
  commit: "a1d282b36b6f3519aa1f3fc636f609c47dddb294",
  files: Object.freeze({
    "LICENSE": "cdfebd4e4322284fde560f21808182055976d9bf",
    "action.yml": "5f6cf73d694f70892899c2768fa9814a9218dd0d",
    "dist/index.js": "2da57a506bca32ba8fc714566f3561f962df53fb",
    "dist/index.js.map": "87e80840130481412bf48172ccb2130d40d00324",
    "dist/licenses.txt": "8f8164bf89809ecc11490daa411f3dcd783187d3",
    "dist/sourcemap-register.js": "cb1fb13627f07ab9250566c7069e0756f882663a",
    "package.json": "e5e5ca95bdc41ba23fd208a2aebd75e001db0450",
  }),
});
const OUTPUT_NAMES = new Set([
  "comment-content", "dependency-changes", "vulnerable-changes",
  "invalid-license-changes", "denied-changes",
]);

function fail() {
  throw new Error("Dependency Review capture integrity check failed");
}

function gitBlob(bytes) {
  return crypto.createHash("sha1").update("blob " + bytes.length + "\0")
    .update(bytes).digest("hex");
}

function realDirectory(directory) {
  if (typeof directory !== "string" || !path.isAbsolute(directory) ||
      !fs.lstatSync(directory).isDirectory() ||
      fs.realpathSync(directory) !== path.resolve(directory)) fail();
  return path.resolve(directory);
}

function sameFile(left, right) {
  return left.dev === right.dev && left.ino === right.ino;
}

function sameSnapshot(left, right) {
  return sameFile(left, right) && left.size === right.size &&
    left.mode === right.mode && left.nlink === right.nlink &&
    left.mtimeNs === right.mtimeNs && left.ctimeNs === right.ctimeNs;
}

// Only the new reader is bounded. Upstream's original file writes are unchanged.
function readBounded(filename, limit = LIMIT, expectedIdentity) {
  const named = fs.lstatSync(filename, { bigint: true });
  if (!named.isFile() || named.nlink !== 1n || named.size > BigInt(limit) ||
      fs.realpathSync(filename) !== path.resolve(filename) ||
      (expectedIdentity && !sameFile(named, expectedIdentity))) fail();
  const descriptor = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const before = fs.fstatSync(descriptor, { bigint: true });
    if (!sameSnapshot(before, named)) fail();
    const bytes = Buffer.alloc(Number(before.size) + 1);
    let length = 0;
    while (length < bytes.length) {
      const count = fs.readSync(descriptor, bytes, length, bytes.length - length, null);
      if (count === 0) break;
      length += count;
    }
    const after = fs.fstatSync(descriptor, { bigint: true });
    const finalName = fs.lstatSync(filename, { bigint: true });
    if (length !== Number(before.size) || !sameSnapshot(before, after) ||
        !sameSnapshot(after, finalName)) fail();
    return { bytes: bytes.subarray(0, length), identity: after };
  } finally {
    fs.closeSync(descriptor);
  }
}

function parseRecords(bytes) {
  if (!Buffer.isBuffer(bytes) || bytes.length > LIMIT) fail();
  const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
  const records = new Map();
  let offset = 0;
  while (offset < text.length) {
    const newline = text.indexOf("\n", offset);
    if (newline === -1) fail();
    const match = /^([a-z-]+)<<(ghadelimiter_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/
      .exec(text.slice(offset, newline));
    if (!match || !OUTPUT_NAMES.has(match[1]) || records.has(match[1])) fail();
    const marker = "\n" + match[2] + "\n";
    const end = text.indexOf(marker, newline + 1);
    if (end === -1) fail();
    records.set(match[1], text.slice(newline + 1, end));
    offset = end + marker.length;
  }
  const comparison = records.get("dependency-changes");
  if (comparison === undefined || comparison === "") fail();
  // No normalization or duplicate policy implementation: Python validates rows.
  return Buffer.from(comparison, "utf8");
}

function stageDistribution(source, directory, manifest = UPSTREAM) {
  realDirectory(source);
  realDirectory(directory);
  let total = 0;
  fs.mkdirSync(path.join(directory, "dist"), { mode: 0o700 });
  for (const [relative, oid] of Object.entries(manifest.files)) {
    // Manifest is reviewed source, not a workflow/user input.
    if (!Object.hasOwn(UPSTREAM.files, relative) || !/^[0-9a-f]{40}$/.test(oid)) fail();
    const { bytes } = readBounded(path.join(source, relative));
    total += bytes.length;
    if (total > SOURCE_TOTAL_LIMIT || gitBlob(bytes) !== oid) fail();
    const destination = path.join(directory, relative);
    fs.writeFileSync(destination, bytes, { mode: 0o400, flag: "wx" });
    if (gitBlob(readBounded(destination).bytes) !== oid) fail();
  }
  if (Object.keys(manifest.files).length !== Object.keys(UPSTREAM.files).length) fail();
  return path.join(directory, "dist", "index.js");
}

function writeComparison(destination, bytes) {
  const descriptor = fs.openSync(destination,
    fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL |
      fs.constants.O_NOFOLLOW, 0o600);
  let complete = false;
  try {
    fs.writeFileSync(descriptor, bytes);
    fs.fsyncSync(descriptor);
    complete = true;
  } finally {
    try { fs.closeSync(descriptor); }
    finally { if (!complete) fs.unlinkSync(destination); }
  }
}

function install(env = process.env, manifest = UPSTREAM) {
  if (process.versions.node.split(".")[0] !== "24") fail();
  const temporary = realDirectory(env.RUNNER_TEMP);
  const workspace = realDirectory(env.GITHUB_WORKSPACE);
  const source = path.join(workspace, ".dependency-review-upstream");
  if (env["INPUT_UPSTREAM-COMMIT"] !== manifest.commit ||
      env["INPUT_UPSTREAM-DIRECTORY"] !== source) fail();
  const commandFile = env.GITHUB_OUTPUT;
  if (typeof commandFile !== "string" || !path.isAbsolute(commandFile)) fail();
  const commandRelative = path.relative(temporary, commandFile);
  if (!commandRelative || commandRelative === ".." ||
      commandRelative.startsWith(".." + path.sep) || path.isAbsolute(commandRelative)) fail();
  const original = readBounded(commandFile, 0);
  const destination = path.join(temporary, "dependency-review-changes.json");
  if (fs.existsSync(destination)) fail();
  const directory = fs.mkdtempSync(path.join(temporary, "dependency-review-capture-"));
  fs.chmodSync(directory, 0o700);
  let executable;
  try {
    executable = stageDistribution(source, directory, manifest);
  } catch (error) {
    fs.rmSync(directory, { recursive: true, force: true });
    throw error;
  }
  // No signal handler: cancellation remains the runner's responsibility.
  // Every operation in this callback must remain synchronous.
  process.once("exit", (code) => {
    let failed = false;
    try {
      const output = readBounded(commandFile, LIMIT, original.identity).bytes;
      const comparison = parseRecords(output);
      writeComparison(destination, comparison);
    } catch {
      failed = true;
    } finally {
      try { fs.rmSync(directory, { recursive: true, force: true }); }
      catch { failed = true; }
    }
    // Never mask an original policy failure or explicit nonzero exit.
    if (failed && code === 0) process.exitCode = 1;
    try {
      fs.writeSync(failed ? 2 : 1, failed
        ? "Dependency Review capture failed; strict scope verification remains required.\n"
        : "Captured the original Dependency Review comparison; strict scope verification remains required.\n");
    } catch {
      if (code === 0) process.exitCode = 1;
    }
  });
  // This CommonJS bundle starts its own asynchronous run. Do not exit or await
  // require's return value: natural process exit follows the original work.
  require(executable);
}

module.exports = {
  LIMIT, SOURCE_TOTAL_LIMIT, UPSTREAM, gitBlob, realDirectory, sameFile,
  sameSnapshot, readBounded, parseRecords, stageDistribution, writeComparison, install,
};
