"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const { execFileSync } = require("node:child_process");
const { after } = require("node:test");
const { createRequire } = require("node:module");
const { createHash } = require("node:crypto");
const { fileURLToPath, pathToFileURL } = require("node:url");
const { takeCoverage } = require("node:v8");

const coverageRoot = path.resolve(__dirname, "../../..");
const runtimePaths = [
  ".github/actions/dependency-review-capture/capture.cjs",
  ".github/actions/dependency-review-capture/index.cjs",
];
const controlPaths = [
  ...runtimePaths,
  ".github/actions/dependency-review-capture/action.yml",
  ".github/actions/node-actions-coverage/action.yml",
  ".github/actions/dependency-review-capture/capture.test.cjs",
  ".github/workflows/dependency-review.yml",
  ".github/workflows/ci.yml",
  "frontend/package.json",
  "frontend/package-lock.json",
  "quality/ownership-mapping.json",
  "quality/quality-contract.json",
];
const sourceBefore = new Map(controlPaths.map((relative) => [
  relative, fs.readFileSync(path.join(coverageRoot, relative)),
]));
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");


const capture = require("./capture.cjs");
const DELIMITER = "ghadelimiter_00000000-0000-4000-8000-000000000001";
const frame = (name, value) => Buffer.from(name + "<<" + DELIMITER + "\n" +
  value + "\n" + DELIMITER + "\n");
const output = (value = "[]") => frame("dependency-changes", value);
const row = '[{"change_type":"added","manifest":"fixture/go.mod","ecosystem":"gomod",' +
  '"name":"fixture.test/module","version":"1","package_url":"pkg:golang/fixture.test/module@1",' +
  '"license":null,"source_repository_url":null,"vulnerabilities":[]}]';

function temporary(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "dependency-capture-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function fixture(t, body = "") {
  const directory = temporary(t);
  const workspace = path.join(directory, "workspace");
  const source = path.join(workspace, ".dependency-review-upstream");
  fs.mkdirSync(path.join(source, "dist"), { recursive: true });
  const files = {};
  for (const relative of Object.keys(capture.UPSTREAM.files)) {
    const bytes = Buffer.from(relative === "dist/index.js" ? body :
      relative === "package.json" ? '{"type":"commonjs"}\n' : "fixture\n");
    fs.writeFileSync(path.join(source, relative), bytes);
    files[relative] = capture.gitBlob(bytes);
  }
  const manifest = { commit: "a".repeat(40), files };
  const commandFile = path.join(directory, "runner-output");
  fs.writeFileSync(commandFile, "");
  return { directory, workspace, source, manifest, commandFile,
    destination: path.join(directory, "dependency-review-changes.json"),
    env: { RUNNER_TEMP: directory, GITHUB_WORKSPACE: workspace, GITHUB_OUTPUT: commandFile,
      "INPUT_UPSTREAM-DIRECTORY": source, "INPUT_UPSTREAM-COMMIT": manifest.commit } };
}

function start(value) {
  const before = new Set(process.listeners("exit"));
  capture.install(value.env, value.manifest);
  const added = process.listeners("exit").filter((listener) => !before.has(listener));
  assert.equal(added.length, 1);
  process.removeListener("exit", added[0]);
  return added[0];
}

function finalize(t, callback, code) {
  const previous = process.exitCode;
  const messages = [];
  const original = fs.writeSync;
  // Node may route writeFileSync(descriptor) through fs.writeSync; only the
  // stdout/stderr status lines are recorded, data writes reach the file.
  const logger = t.mock.method(fs, "writeSync", (fd, message, ...rest) => {
    if (fd !== 1 && fd !== 2) return original.call(fs, fd, message, ...rest);
    messages.push([fd, message]);
    return Buffer.byteLength(message);
  });
  try {
    process.exitCode = code;
    callback(code);
    return { exit: process.exitCode, messages };
  } finally {
    logger.mock.restore();
    process.exitCode = previous;
  }
}

test("complete declared records preserve byte-exact comparison without other output", () => {
  const bytes = Buffer.concat([
    frame("vulnerable-changes", "[]"), frame("invalid-license-changes", "{}"),
    frame("denied-changes", "[]"), output(row),
    frame("comment-content", "original comment\nsecond line"),
  ]);
  assert.equal(capture.parseRecords(bytes).toString(), row);
  for (const payload of ["[]", "  [ ] ", "{invalid-json}", "null"]) {
    assert.equal(capture.parseRecords(output(payload)).toString(), payload);
  }
});

test("unknown, duplicate, missing, malformed, oversized and invalid UTF-8 records block", () => {
  for (const bytes of [
    Buffer.alloc(0), Buffer.from("unfinished"), Buffer.from([0xff]),
    Buffer.concat([output(), output()]), frame("unknown", "[]"),
    Buffer.from("dependency-changes=[]\n"), output(""),
    Buffer.from("dependency-changes<<" + DELIMITER + "\n[]\n"),
    Buffer.from("dependency-changes<<invalid\n[]\ninvalid\n"),
    Buffer.from("\ufeff" + output().toString()), Buffer.alloc(capture.LIMIT + 1), "[]",
  ]) assert.throws(() => capture.parseRecords(bytes));
});

test("bounded regular-file reader checks exact boundary and preserves bytes", (t) => {
  const root = temporary(t);
  const filename = path.join(root, "file");
  fs.writeFileSync(filename, Buffer.alloc(capture.LIMIT, 65));
  const first = capture.readBounded(filename);
  assert.equal(first.bytes.length, capture.LIMIT);
  assert.deepEqual(capture.readBounded(filename, capture.LIMIT, first.identity).bytes,
    first.bytes);
  fs.appendFileSync(filename, "x");
  assert.throws(() => capture.readBounded(filename));
});

test("source and output readers reject links, inode substitution and non-files", (t) => {
  const root = temporary(t);
  const filename = path.join(root, "file");
  fs.writeFileSync(filename, "a");
  const { identity } = capture.readBounded(filename);
  const hardlink = path.join(root, "hardlink");
  fs.linkSync(filename, hardlink);
  assert.throws(() => capture.readBounded(filename));
  fs.unlinkSync(hardlink);
  const link = path.join(root, "link");
  fs.symlinkSync(filename, link);
  assert.throws(() => capture.readBounded(link));
  assert.throws(() => capture.readBounded(root));
  assert.throws(() => capture.readBounded(filename, capture.LIMIT,
    { ...identity, ino: identity.ino + 1n }));
});

test("reader rejects source mutation between open and final snapshot", (t) => {
  const root = temporary(t);
  const filename = path.join(root, "file");
  fs.writeFileSync(filename, "before");
  const original = fs.readSync;
  let changed = false;
  const mocked = t.mock.method(fs, "readSync", (...args) => {
    const count = original(...args);
    if (!changed) { changed = true; fs.appendFileSync(filename, "after"); }
    return count;
  });
  assert.throws(() => capture.readBounded(filename));
  mocked.mock.restore();
});

test("directory identity rejects relative and symlinked roots", (t) => {
  const root = temporary(t);
  assert.equal(capture.realDirectory(root), root);
  const link = path.join(root, "link");
  fs.symlinkSync(root, link);
  for (const value of [undefined, ".", link]) {
    assert.throws(() => capture.realDirectory(value));
  }
});

test("exact finite source manifest produces private read-only byte-identical files", (t) => {
  const value = fixture(t, "module.exports = {};");
  const target = fs.mkdtempSync(path.join(value.directory, "stage-"));
  const entry = capture.stageDistribution(value.source, target, value.manifest);
  assert.equal(entry, path.join(target, "dist", "index.js"));
  for (const [relative, oid] of Object.entries(value.manifest.files)) {
    const copied = path.join(target, relative);
    assert.equal(capture.gitBlob(capture.readBounded(copied).bytes), oid);
    assert.equal(fs.statSync(copied).mode & 0o777, 0o400);
  }
});

test("source hash, file-set, file-type and total-size violations block staging", (t) => {
  for (const mutate of [
    (value) => { value.manifest.files.LICENSE = "0".repeat(40); },
    (value) => { value.manifest.files.LICENSE = "invalid"; },
    (value) => { delete value.manifest.files.LICENSE; },
    (value) => { value.manifest.files["../outside"] = "a".repeat(40); },
    (value) => { fs.unlinkSync(path.join(value.source, "LICENSE")); },
    (value) => {
      fs.unlinkSync(path.join(value.source, "LICENSE"));
      fs.symlinkSync("/outside", path.join(value.source, "LICENSE"));
    },
  ]) {
    const value = fixture(t);
    mutate(value);
    const target = fs.mkdtempSync(path.join(value.directory, "stage-"));
    assert.throws(() => capture.stageDistribution(value.source, target, value.manifest));
  }
  const value = fixture(t);
  for (const relative of Object.keys(value.manifest.files)) {
    const bytes = Buffer.alloc(3 * 1024 * 1024, 65);
    fs.writeFileSync(path.join(value.source, relative), bytes);
    value.manifest.files[relative] = capture.gitBlob(bytes);
  }
  const target = fs.mkdtempSync(path.join(value.directory, "stage-"));
  assert.throws(() => capture.stageDistribution(value.source, target, value.manifest));
});

test("exclusive comparison publication is private and never overwrites stale data", (t) => {
  const root = temporary(t);
  const filename = path.join(root, "comparison");
  capture.writeComparison(filename, Buffer.from(row));
  assert.equal(fs.readFileSync(filename, "utf8"), row);
  assert.equal(fs.statSync(filename).mode & 0o777, 0o600);
  assert.throws(() => capture.writeComparison(filename, Buffer.from("[]")));
  assert.equal(fs.readFileSync(filename, "utf8"), row);
});

test("failed publication removes its own incomplete file", (t) => {
  const filename = path.join(temporary(t), "comparison");
  const mocked = t.mock.method(fs, "fsyncSync", () => { throw new Error("fixture"); });
  assert.throws(() => capture.writeComparison(filename, Buffer.from(row)));
  mocked.mock.restore();
  assert.equal(fs.existsSync(filename), false);
});

test("capture waits for original asynchronous work and preserves original output file", async (t) => {
  const value = fixture(t, "module.exports = {};");
  const callback = start(value);
  assert.equal(fs.existsSync(value.destination), false);
  await new Promise((resolve) => setTimeout(resolve, 10));
  fs.appendFileSync(value.commandFile, output(row));
  const originalBytes = fs.readFileSync(value.commandFile);
  const result = finalize(t, callback, 0);
  assert.equal(result.exit, 0);
  assert.equal(fs.readFileSync(value.destination, "utf8"), row);
  assert.deepEqual(fs.readFileSync(value.commandFile), originalBytes);
  assert.equal(result.messages.some(([, message]) => message.includes("fixture.test")), false);
  assert.equal(fs.readdirSync(value.directory).some((name) =>
    name.startsWith("dependency-review-capture-")), false);
});

test("valid capture never masks original nonzero exits", (t) => {
  for (const code of [1, 7]) {
    const value = fixture(t);
    const callback = start(value);
    fs.appendFileSync(value.commandFile, output());
    assert.equal(finalize(t, callback, code).exit, code);
    assert.equal(fs.readFileSync(value.destination, "utf8"), "[]");
  }
});

test("missing, truncated, duplicate and replaced invocation output fail closed", (t) => {
  for (const change of [
    () => {},
    (value) => fs.appendFileSync(value.commandFile, "unfinished"),
    (value) => fs.appendFileSync(value.commandFile, Buffer.concat([output(), output()])),
    (value) => { fs.unlinkSync(value.commandFile); },
    (value) => {
      fs.renameSync(value.commandFile, value.commandFile + ".old");
      fs.writeFileSync(value.commandFile, output());
    },
  ]) {
    for (const code of [0, 1, 7]) {
      const value = fixture(t);
      const callback = start(value);
      change(value);
      const result = finalize(t, callback, code);
      assert.equal(result.exit, code || 1);
      assert.equal(fs.existsSync(value.destination), false);
      assert.match(result.messages[0][1], /capture failed/);
    }
  }
});

test("callback cleanup and fixed-log exceptions never create a success result", (t) => {
  const value = fixture(t);
  const callback = start(value);
  fs.appendFileSync(value.commandFile, output());
  const cleanup = t.mock.method(fs, "rmSync", () => { throw new Error("fixture"); });
  assert.equal(finalize(t, callback, 0).exit, 1);
  cleanup.mock.restore();

  const next = fixture(t);
  const nextCallback = start(next);
  fs.appendFileSync(next.commandFile, output());
  const previous = process.exitCode;
  const logger = t.mock.method(fs, "writeSync", () => { throw new Error("fixture"); });
  try {
    process.exitCode = 7;
    assert.doesNotThrow(() => nextCallback(7));
    assert.equal(process.exitCode, 7);
  } finally {
    logger.mock.restore();
    process.exitCode = previous;
  }
});

test("initial nonempty output, stale capture, invalid pin and outside paths block before load", (t) => {
  for (const mutate of [
    (value) => { value.env["INPUT_UPSTREAM-COMMIT"] = "b".repeat(40); },
    (value) => { value.env["INPUT_UPSTREAM-DIRECTORY"] = "/outside"; },
    (value) => { value.env.GITHUB_OUTPUT = "relative"; },
    (value) => { value.env.GITHUB_OUTPUT = value.directory; },
    (value) => { value.env.GITHUB_OUTPUT = path.dirname(value.directory); },
    (value) => { value.env.GITHUB_OUTPUT = undefined; },
    (value) => { fs.writeFileSync(value.commandFile, output()); },
    (value) => { fs.writeFileSync(value.destination, "stale"); },
    (value) => { fs.writeFileSync(path.join(value.source, "LICENSE"), "tampered"); },
  ]) {
    const value = fixture(t);
    mutate(value);
    assert.throws(() => capture.install(value.env, value.manifest));
    assert.equal(fs.readdirSync(value.directory).some((name) =>
      name.startsWith("dependency-review-capture-")), false);
  }
});

test("file snapshot comparison checks every integrity field", () => {
  const base = { dev: 1n, ino: 2n, size: 3n, mode: 4n, nlink: 1n,
    mtimeNs: 5n, ctimeNs: 6n };
  assert.equal(capture.sameSnapshot(base, { ...base }), true);
  for (const name of Object.keys(base)) {
    assert.equal(capture.sameSnapshot(base, { ...base, [name]: base[name] + 1n }), false);
  }
});

test("workflow retains exact upstream pin, always-run guard, and no comparison refetch", () => {
  const workflow = fs.readFileSync(path.resolve(__dirname,
    "../../workflows/dependency-review.yml"), "utf8");
  assert.equal(workflow.includes(" fetch --root "), false);
  assert.match(workflow, new RegExp("DEPENDENCY_REVIEW_ACTION_REF: " + capture.UPSTREAM.commit));
  assert.match(workflow, /if: \$\{\{ always\(\) \}\}/);
  assert.match(workflow, /changes --root \. --base-sha "\$BASE_SHA" --changes-file "\$DEPENDENCY_CHANGES_FILE"/);
  assert.equal(workflow.includes("continue-on-error"), false);
});

function processFixture(value, body) {
  const executable = path.join(value.source, "dist", "index.js");
  fs.writeFileSync(executable, body);
  value.manifest.files["dist/index.js"] = capture.gitBlob(Buffer.from(body));
  const driver = path.join(value.directory, "driver.cjs");
  fs.writeFileSync(driver,
    "require(" + JSON.stringify(path.join(__dirname, "capture.cjs")) +
    ").install(process.env, " + JSON.stringify(value.manifest) + ");");
  const options = { env: { ...process.env, ...value.env },
    cwd: value.workspace, encoding: "utf8", timeout: 5000, killSignal: "SIGKILL",
    maxBuffer: 65536, stdio: ["ignore", "pipe", "pipe"] };
  try {
    return { status: 0, stdout: execFileSync(process.execPath, [driver], options),
      stderr: "", signal: null };
  } catch (error) {
    return { status: error.status, stdout: error.stdout, stderr: error.stderr,
      signal: error.signal };
  }
}

function asyncWriter(value, status = 0) {
  return 'const fs = require("node:fs"); setTimeout(() => { ' +
    "fs.appendFileSync(process.env.GITHUB_OUTPUT, " + JSON.stringify(output(row).toString()) + "); " +
    "fs.writeFileSync(" + JSON.stringify(path.join(value.directory, "summary")) +
    ', "original summary"); console.log("original action diagnostic"); ' +
    "process.exitCode = " + status + "; }, 20);";
}

test("natural process exit captures only after the original asynchronous bundle finishes", (t) => {
  for (const code of [0, 1, 7]) {
    const value = fixture(t);
    const result = processFixture(value, asyncWriter(value, code));
    assert.equal(result.status, code);
    assert.equal(fs.readFileSync(value.destination, "utf8"), row);
    assert.equal(fs.readFileSync(path.join(value.directory, "summary"), "utf8"),
      "original summary");
    assert.match(result.stdout, /original action diagnostic/);
    assert.equal(result.stdout.includes("fixture.test/module"), false);
  }
});

test("explicit exits and original import exceptions retain their failure outcomes", (t) => {
  const explicit = fixture(t);
  const result = processFixture(explicit,
    'require("node:fs").appendFileSync(process.env.GITHUB_OUTPUT, ' +
    JSON.stringify(output().toString()) + "); process.exit(7);");
  assert.equal(result.status, 7);
  assert.equal(fs.readFileSync(explicit.destination, "utf8"), "[]");
  const failed = fixture(t);
  const thrown = processFixture(failed, 'throw new Error("synthetic original failure");');
  assert.equal(thrown.status, 1);
  assert.match(thrown.stderr, /synthetic original failure/);
  assert.equal(fs.existsSync(failed.destination), false);
  assert.equal(fs.readdirSync(failed.directory).some((name) =>
    name.startsWith("dependency-review-capture-")), false);
});

test("runner-style process termination is not intercepted or changed to success", (t) => {
  const value = fixture(t);
  const result = processFixture(value, 'process.kill(process.pid, "SIGTERM");');
  assert.equal(result.signal, "SIGTERM");
  assert.equal(result.status, null);
  assert.equal(fs.existsSync(value.destination), false);
});

test("capture startup does not rewrite GitHub environment values", (t) => {
  const value = fixture(t);
  const snapshot = { ...process.env };
  const callback = start(value);
  assert.deepEqual({ ...process.env }, snapshot);
  fs.appendFileSync(value.commandFile, output());
  finalize(t, callback, 0);
});

test("default production manifest cannot be substituted by a fixture commit", (t) => {
  const value = fixture(t);
  assert.throws(() => capture.install(value.env));
  const target = fs.mkdtempSync(path.join(value.directory, "stage-"));
  assert.throws(() => capture.stageDistribution(value.source, target));
});

test("wrapper metadata retains the exact pinned upstream inputs, defaults and outputs", () => {
  const upstream = fs.readFileSync(path.resolve(__dirname,
    "../../../.dependency-review-upstream/action.yml"));
  assert.equal(capture.gitBlob(upstream), capture.UPSTREAM.files["action.yml"]);
  const original = upstream.toString();
  const local = fs.readFileSync(path.join(__dirname, "action.yml"), "utf8");
  const originalInputs = original.split("\ninputs:\n")[1].split("\noutputs:\n")[0].trim();
  const localInputs = local.split("\ninputs:\n")[1].split("\n  mode:\n")[0].trim();
  assert.equal(localInputs, originalInputs);
  assert.equal(local.split("\noutputs:\n")[1].split("\nruns:\n")[0].trim(),
    original.split("\noutputs:\n")[1].split("\nruns:\n")[0].trim());
});

test("production source provenance pin binds every copied executable/support file", (t) => {
  const source = path.resolve(__dirname, "../../../.dependency-review-upstream");
  const target = temporary(t);
  const entry = capture.stageDistribution(source, target);
  assert.equal(entry, path.join(target, "dist", "index.js"));
  assert.equal(fs.readdirSync(target).sort().join(","),
    "LICENSE,action.yml,dist,package.json");
  assert.equal(fs.readdirSync(path.join(target, "dist")).sort().join(","),
    "index.js,index.js.map,licenses.txt,sourcemap-register.js");
});

test("reader rejects a source swapped or changed immediately after open", (t) => {
  const filename = path.join(temporary(t), "source");
  fs.writeFileSync(filename, "before");
  const original = fs.openSync;
  let modified = false;
  const opened = t.mock.method(fs, "openSync", (...args) => {
    const descriptor = original(...args);
    if (!modified) {
      modified = true;
      fs.appendFileSync(filename, "changed");
    }
    return descriptor;
  });
  assert.throws(() => capture.readBounded(filename));
  opened.mock.restore();
});

test("reader supports short reads but never accepts premature EOF", (t) => {
  const filename = path.join(temporary(t), "source");
  fs.writeFileSync(filename, "complete");
  const original = fs.readSync;
  const short = t.mock.method(fs, "readSync", (fd, buffer, offset, length, position) =>
    original(fd, buffer, offset, Math.min(length, 1), position));
  assert.equal(capture.readBounded(filename).bytes.toString(), "complete");
  short.mock.restore();
  const eof = t.mock.method(fs, "readSync", () => 0);
  assert.throws(() => capture.readBounded(filename));
  eof.mock.restore();
});

test("copied-source readback detects substitution before require", (t) => {
  const value = fixture(t);
  const target = fs.mkdtempSync(path.join(value.directory, "stage-"));
  const original = fs.writeFileSync;
  const changed = t.mock.method(fs, "writeFileSync", (...args) => {
    original(...args);
    if (typeof args[0] === "string" && args[0].startsWith(target + path.sep)) {
      fs.chmodSync(args[0], 0o600);
      original(args[0], "tamper", { flag: "a" });
    }
  });
  assert.throws(() => capture.stageDistribution(value.source, target, value.manifest));
  changed.mock.restore();
});

test("capture publication collision after startup remains an original nonzero failure", (t) => {
  const value = fixture(t);
  const callback = start(value);
  fs.appendFileSync(value.commandFile, output());
  fs.writeFileSync(value.destination, "unrelated");
  assert.equal(finalize(t, callback, 7).exit, 7);
  assert.equal(fs.readFileSync(value.destination, "utf8"), "unrelated");
});

test("callback fixed-log failure changes success to failure without throwing", (t) => {
  const value = fixture(t);
  const callback = start(value);
  fs.appendFileSync(value.commandFile, output());
  const previous = process.exitCode;
  const logger = t.mock.method(fs, "writeSync", () => { throw new Error("fixture"); });
  try {
    process.exitCode = 0;
    assert.doesNotThrow(() => callback(0));
    assert.equal(process.exitCode, 1);
  } finally {
    logger.mock.restore();
    process.exitCode = previous;
  }
});

test("entrypoint dispatch preserves test outcomes and delegates capture without wrapping errors", (t) => {
  const childProcess = require("node:child_process");
  const entry = require.resolve("./index.cjs");
  const previousMode = process.env.INPUT_MODE;
  const previousExit = process.exitCode;
  const dispatch = () => { delete require.cache[entry]; require(entry); };
  try {
    process.env.INPUT_MODE = "test";
    for (const status of [0, 1, 7, null]) {
      const mocked = t.mock.method(childProcess, "spawnSync", (executable, args, options) => {
        assert.equal(executable, process.execPath);
        assert.equal(args.includes("--test"), true);
        assert.equal(options.stdio, "inherit");
        return { status };
      });
      dispatch();
      assert.equal(process.exitCode, status ?? 1);
      mocked.mock.restore();
    }
    const failure = new Error("synthetic launch failure");
    const failed = t.mock.method(childProcess, "spawnSync", () => ({ error: failure }));
    assert.throws(dispatch, (error) => error === failure);
    failed.mock.restore();
    process.env.INPUT_MODE = "capture";
    let invoked = 0;
    const installed = t.mock.method(capture, "install", () => { invoked += 1; });
    dispatch();
    assert.equal(invoked, 1);
    installed.mock.restore();
    process.env.INPUT_MODE = "invalid";
    assert.throws(dispatch, /capture mode is invalid/);
  } finally {
    delete require.cache[entry];
    process.exitCode = previousExit;
    if (previousMode === undefined) delete process.env.INPUT_MODE;
    else process.env.INPUT_MODE = previousMode;
  }
});

test("unsupported Node major version blocks before source execution", (t) => {
  const value = fixture(t);
  const descriptor = Object.getOwnPropertyDescriptor(process.versions, "node");
  assert.equal(descriptor.configurable, true);
  try {
    Object.defineProperty(process.versions, "node", { ...descriptor, value: "22.0.0" });
    assert.throws(() => capture.install(value.env, value.manifest));
  } finally {
    Object.defineProperty(process.versions, "node", descriptor);
  }
  assert.equal(fs.existsSync(value.destination), false);
});

test("output under a sibling directory is outside RUNNER_TEMP", (t) => {
  const value = fixture(t);
  value.env.GITHUB_OUTPUT = path.join(path.dirname(value.directory),
    path.basename(value.directory) + "-sibling", "output");
  assert.throws(() => capture.install(value.env, value.manifest));
  const unexpected = t.mock.method(path, "relative", () => "/outside");
  assert.throws(() => capture.install(
    { ...value.env, GITHUB_OUTPUT: value.commandFile }, value.manifest));
  unexpected.mock.restore();
});

test("a final pathname substitution cannot reuse the originally opened source inode", (t) => {
  const filename = path.join(temporary(t), "source");
  fs.writeFileSync(filename, "before");
  const original = fs.readSync;
  let replaced = false;
  const reader = t.mock.method(fs, "readSync", (...args) => {
    const count = original(...args);
    if (!replaced) {
      replaced = true;
      fs.renameSync(filename, filename + ".old");
      fs.writeFileSync(filename, "before");
    }
    return count;
  });
  assert.throws(() => capture.readBounded(filename));
  reader.mock.restore();
});

test("bounded reader rejects a symlinked ancestor and reports close failures", (t) => {
  const root = temporary(t);
  const real = path.join(root, "real");
  fs.mkdirSync(real);
  fs.writeFileSync(path.join(real, "file"), "bytes");
  const link = path.join(root, "linked");
  fs.symlinkSync(real, link);
  assert.throws(() => capture.readBounded(path.join(link, "file")));
  assert.throws(() => capture.realDirectory(path.join(real, "file")));
  const close = fs.closeSync;
  const mocked = t.mock.method(fs, "closeSync", (descriptor) => {
    close(descriptor);
    throw new Error("synthetic close failure");
  });
  assert.throws(() => capture.readBounded(path.join(real, "file")),
    /synthetic close failure/);
  mocked.mock.restore();
});

test("failed writes remove incomplete capture even when descriptor close also fails", (t) => {
  const filename = path.join(temporary(t), "comparison");
  const write = t.mock.method(fs, "writeFileSync", () => {
    throw new Error("synthetic write failure");
  });
  const originalClose = fs.closeSync;
  const close = t.mock.method(fs, "closeSync", (descriptor) => {
    originalClose(descriptor);
    throw new Error("synthetic close failure");
  });
  assert.throws(() => capture.writeComparison(filename, Buffer.from(row)),
    /synthetic close failure/);
  write.mock.restore();
  close.mock.restore();
  assert.equal(fs.existsSync(filename), false);
});

test("a completed write with a close failure is still reported as failure", (t) => {
  const filename = path.join(temporary(t), "comparison");
  const originalClose = fs.closeSync;
  const close = t.mock.method(fs, "closeSync", (descriptor) => {
    originalClose(descriptor);
    throw new Error("synthetic close failure");
  });
  assert.throws(() => capture.writeComparison(filename, Buffer.from(row)),
    /synthetic close failure/);
  close.mock.restore();
  assert.equal(fs.readFileSync(filename, "utf8"), row);
});

test("test entrypoint requires exact production files and all native metrics at 100", () => {
  const source = fs.readFileSync(path.join(__dirname, "index.cjs"), "utf8");
  for (const metric of ["lines", "branches", "functions"]) {
    assert.equal(source.includes("--test-coverage-" + metric + "=100"), true);
  }
  assert.equal(source.includes('path.join(__dirname, "capture.cjs")'), true);
  assert.equal(source.includes('path.join(__dirname, "index.cjs")'), true);
  assert.equal(source.includes("--test-coverage-exclude"), false);
});

test("default environment path remains the real process environment without rewriting it", (t) => {
  const value = fixture(t);
  const previous = Object.fromEntries(Object.keys(value.env).map((key) => [key, process.env[key]]));
  try {
    Object.assign(process.env, value.env);
    // The default manifest is production-pinned and refuses this fixture commit.
    assert.throws(() => capture.install());
    for (const [key, expected] of Object.entries(value.env)) {
      assert.equal(process.env[key], expected);
    }
  } finally {
    for (const [key, old] of Object.entries(previous)) {
      if (old === undefined) delete process.env[key];
      else process.env[key] = old;
    }
  }
});

test("same-length source metadata changes during a read fail the final descriptor snapshot", (t) => {
  const filename = path.join(temporary(t), "source");
  fs.writeFileSync(filename, "before", { mode: 0o600 });
  const original = fs.readSync;
  let changed = false;
  const reader = t.mock.method(fs, "readSync", (...args) => {
    const count = original(...args);
    if (!changed) {
      changed = true;
      fs.chmodSync(filename, 0o400);
    }
    return count;
  });
  assert.throws(() => capture.readBounded(filename));
  reader.mock.restore();
});

test("one same-run producer is reused without new jobs, events or permission grants", () => {
  const root = path.resolve(__dirname, "../../..");
  const helper = fs.readFileSync(path.join(root,
    ".github/actions/node-actions-coverage/action.yml"), "utf8");
  const review = fs.readFileSync(path.join(root,
    ".github/workflows/dependency-review.yml"), "utf8");
  const ci = fs.readFileSync(path.join(root, ".github/workflows/ci.yml"), "utf8");
  assert.equal(helper.includes("using: composite"), true);
  assert.equal(helper.includes("package-manager-cache: false"), true);
  assert.equal(helper.includes("npm ci --ignore-scripts --no-audit --no-fund"), true);
  assert.equal(helper.includes("node-actions-node="), true);
  assert.equal(helper.includes("coverage-source-snapshot.json"), true);
  assert.equal(helper.includes('node=$(node --version)'), false);
  assert.equal(helper.includes("permissions:"), false);
  assert.equal(helper.includes("continue-on-error"), false);
  for (const workflow of [review, ci]) {
    assert.equal(workflow.split("uses: ./.github/actions/node-actions-coverage").length, 2);
  }
  assert.equal(review.includes("workflow_run:"), false);
  assert.equal(review.includes("push:"), false);
});

after(async () => {
  const coverageDirectory = process.env.NODE_V8_COVERAGE;
  assert.ok(coverageDirectory && path.isAbsolute(coverageDirectory),
    "native coverage collection must be enabled");
  assert.match(process.env.GITHUB_SHA || "", /^[0-9a-f]{40}$/);

  const toolRequire = createRequire(path.join(coverageRoot, "frontend/package.json"));
  const lock = JSON.parse(sourceBefore.get("frontend/package-lock.json").toString("utf8"));
  const packages = [
    "@babel/parser", "@bcoe/v8-coverage", "ast-v8-to-istanbul",
    "istanbul-lib-coverage", "istanbul-lib-report", "istanbul-reports",
  ];
  const toolVersions = {};
  for (const name of packages) {
    const installed = JSON.parse(fs.readFileSync(
      path.join(coverageRoot, "frontend/node_modules", name, "package.json"), "utf8"));
    assert.equal(installed.version, lock.packages["node_modules/" + name].version);
    toolVersions[name] = installed.version;
  }
  const { mergeScriptCovs } = toolRequire("@bcoe/v8-coverage");
  const { parse } = await import(pathToFileURL(toolRequire.resolve("@babel/parser")).href);
  const { convert } = await import(pathToFileURL(toolRequire.resolve("ast-v8-to-istanbul")).href);
  const { createCoverageMap } = toolRequire("istanbul-lib-coverage");
  const { createContext } = toolRequire("istanbul-lib-report");
  const { create: createReport } = toolRequire("istanbul-reports");

  const expected = new Map(runtimePaths.map((relative) => [
    path.join(coverageRoot, relative), sourceBefore.get(relative).toString("utf8"),
  ]));
  const merged = new Map();
  takeCoverage();
  const rawFiles = fs.readdirSync(coverageDirectory)
    .filter((name) => /^coverage-[0-9]+-[0-9]{13}-[0-9]+\.json$/.test(name)).sort();
  assert.ok(rawFiles.length > 0, "native coverage reports are missing");
  for (const name of rawFiles) {
    const filename = path.join(coverageDirectory, name);
    const info = fs.lstatSync(filename);
    assert.ok(info.isFile() && info.size <= 64 * 1024 * 1024);
    const document = JSON.parse(fs.readFileSync(filename, "utf8"));
    assert.ok(Array.isArray(document.result));
    for (const script of document.result) {
      assert.equal(typeof script.url, "string");
      if (!script.url.startsWith("file:")) continue;
      const filename = fileURLToPath(script.url);
      if (!expected.has(filename)) continue;
      assert.ok(Array.isArray(script.functions) && script.functions.length > 0);
      const codeLength = expected.get(filename).length;
      for (const fn of script.functions) {
        assert.equal(typeof fn.functionName, "string");
        assert.equal(typeof fn.isBlockCoverage, "boolean");
        assert.ok(Array.isArray(fn.ranges) && fn.ranges.length > 0);
        for (const range of fn.ranges) {
          for (const field of ["startOffset", "endOffset", "count"]) {
            assert.ok(Number.isSafeInteger(range[field]) && range[field] >= 0);
          }
          assert.ok(range.startOffset <= range.endOffset && range.endOffset <= codeLength);
        }
      }
      const previous = merged.get(filename);
      merged.set(filename, mergeScriptCovs(previous ? [previous, script] : [script]));
    }
  }
  assert.deepEqual([...merged.keys()].sort(), [...expected.keys()].sort());

  const map = createCoverageMap({});
  for (const [filename, code] of expected) {
    assert.doesNotMatch(code, /(?:istanbul|v8|c8|node:coverage)\s+(?:ignore|disable)/);
    assert.doesNotMatch(code, /sourceMappingURL\s*=/);
    map.merge(await convert({
      code,
      ast: parse(code, { sourceType: "commonjs", plugins: ["estree"], ranges: true }).program,
      coverage: merged.get(filename),
      wrapperLength: 0,
      sourceMap: undefined,
    }));
  }
  assert.deepEqual(map.files().sort(), [...expected.keys()].sort());

  const controls = [];
  for (const [relative, bytes] of sourceBefore) {
    assert.deepEqual(fs.readFileSync(path.join(coverageRoot, relative)), bytes,
      "coverage source/control changed during tests: " + relative);
    // Additional exact commit binding must be supplied by the canonical
    // coverage_provenance writer/selector; this snapshot alone is not it.
    controls.push({ path: relative, sha256: digest(bytes), size_bytes: bytes.length });
  }
  const out = path.join(coverageRoot, "artifacts/coverage/node-actions");
  fs.mkdirSync(out, { recursive: true });
  const context = createContext({ dir: out, coverageMap: map });
  createReport("json").execute(context);
  createReport("lcovonly").execute(context);
  const summaries = Object.fromEntries(map.files().map((file) => [
    path.relative(coverageRoot, file).split(path.sep).join("/"),
    map.fileCoverageFor(file).toSummary().toJSON(),
  ]));
  fs.writeFileSync(path.join(out, "coverage-source-snapshot.json"), JSON.stringify({
    schema_version: 1,
    status: "supplemental snapshot; canonical commit/run provenance is separately required",
    tested_commit_sha: process.env.GITHUB_SHA,
    run_id: process.env.GITHUB_RUN_ID,
    run_attempt: process.env.GITHUB_RUN_ATTEMPT,
    node: process.versions.node,
    tool_versions: toolVersions,
    source_controls: controls,
    files: summaries,
  }, null, 2) + "\n", { flag: "wx", mode: 0o600 });

  for (const [file, summary] of Object.entries(summaries)) {
    assert.ok(summary.statements.total > 0, "empty runtime-file evidence: " + file);
    for (const metric of ["lines", "statements", "branches", "functions"]) {
      const value = summary[metric];
      for (const field of ["covered", "total", "skipped"]) {
        assert.ok(Number.isSafeInteger(value[field]) && value[field] >= 0);
      }
      assert.equal(value.skipped, 0, file + " has skipped " + metric);
      assert.equal(value.covered, value.total, file + " requires 100% " + metric);
    }
  }
});
