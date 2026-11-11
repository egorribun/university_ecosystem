import assert from "node:assert/strict"
import { execFileSync, spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  writeFileSync,
} from "node:fs"
import { createRequire } from "node:module"
import path from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

const specFile = "audit375-service-worker.spec.ts"
const suiteTitle = "AUD-375 real service-worker replay"
const titles = Object.freeze([
  "forwards the cookie proof and deletes a terminal 403 while two active workers contend",
  "an abandoned worker's lease blocks its successor until forced expiry, then the successor drains the row",
])
export const sourcePaths = Object.freeze([
  "frontend/tests/e2e/audit375-service-worker.spec.ts",
  "frontend/src/sw.ts",
  "frontend/src/sw/offline.ts",
  "frontend/src/sw/replayPolicy.ts",
  "frontend/src/sw/replayCredentialResponder.ts",
  "frontend/src/stores/sessionEpoch.ts",
  "frontend/playwright.config.ts",
  "frontend/package.json",
  "frontend/package-lock.json",
  "frontend/scripts/aud375-evidence.mjs",
  ".github/workflows/reusable-e2e-tests.yml",
  ".github/workflows/nightly-full-gate.yml",
])
const toPosix = (value) => value.replaceAll("\\", "/")
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex")

export function captureSource(root, expectedSha) {
  assert.match(expectedSha, /^[a-f0-9]{40}$/u, "expected source SHA is required")
  const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim()
  const commit = git("rev-parse", "HEAD")
  assert.equal(commit, expectedSha, "checkout must match the event source")
  assert.equal(
    git("status", "--porcelain", "--untracked-files=no"),
    "",
    "tracked source must be clean"
  )
  const tree = git("rev-parse", "HEAD^{tree}")
  const bindings = Object.fromEntries(
    sourcePaths.map((file) => {
      const blob = git("rev-parse", `HEAD:${file}`)
      const actual = git("hash-object", "--no-filters", "--", file)
      assert.equal(actual, blob, `source bytes changed: ${file}`)
      return [file, { blob, sha256: sha256(readFileSync(path.join(root, file))) }]
    })
  )
  return { commit, tree, trackedClean: true, bindings }
}

export function createReceipt({ raw, exitCode, before, after, root, environment }) {
  assert.equal(exitCode, 0, "Playwright must exit successfully")
  assert.equal(before.trackedClean, true)
  assert.deepEqual(after, before, "source must remain unchanged through execution")
  assert.match(before.commit, /^[a-f0-9]{40}$/u)
  assert.match(before.tree, /^[a-f0-9]{40}$/u)
  assert.deepEqual(Object.keys(before.bindings), [...sourcePaths])
  for (const binding of Object.values(before.bindings)) {
    assert.match(binding.blob, /^[a-f0-9]{40}$/u)
    assert.match(binding.sha256, /^[a-f0-9]{64}$/u)
  }
  const report = JSON.parse(raw.toString("utf8"))
  assert.deepEqual(report.errors, [], "global errors are not accepted")
  assert.equal(report.stats.expected, 2)
  for (const key of ["skipped", "unexpected", "flaky"]) assert.equal(report.stats[key], 0)
  const frontend = path.join(root, "frontend")
  assert.equal(report.config.rootDir, toPosix(path.join(frontend, "tests/e2e")))
  assert.equal(report.config.configFile, toPosix(path.join(frontend, "playwright.config.ts")))
  assert.equal(report.config.workers, 1)
  assert.equal(report.config.shard, null)
  const projects = report.config.projects.filter(({ name }) => name === "chromium")
  assert.equal(projects.length, 1)
  assert.equal(projects[0].retries, 0)
  assert.equal(projects[0].repeatEach, 1)
  assert.equal(projects[0].testDir, report.config.rootDir)
  assert.equal(report.suites.length, 1)
  const fileSuite = report.suites[0]
  assert.equal(fileSuite.file, specFile)
  assert.deepEqual(fileSuite.specs, [])
  assert.equal(fileSuite.suites.length, 1)
  const suite = fileSuite.suites[0]
  assert.equal(suite.title, suiteTitle)
  assert.equal(suite.file, specFile)
  assert.equal(suite.suites?.length ?? 0, 0)
  assert.deepEqual(
    suite.specs.map(({ title }) => title),
    [...titles]
  )
  const cases = suite.specs.map((spec) => {
    assert.equal(spec.file, specFile)
    assert.equal(spec.ok, true)
    assert.equal(spec.tests.length, 1)
    const test = spec.tests[0]
    assert.equal(test.projectName, "chromium")
    assert.equal(test.projectId, projects[0].id)
    assert.equal(test.expectedStatus, "passed")
    assert.equal(test.status, "expected")
    assert.deepEqual(test.annotations, [])
    assert.equal(test.results.length, 1)
    const result = test.results[0]
    assert.equal(result.status, "passed")
    assert.equal(result.retry, 0)
    assert.deepEqual(result.errors, [])
    assert.equal(result.error, undefined)
    assert.deepEqual(result.annotations, [])
    assert.ok(Number.isFinite(result.duration) && result.duration >= 0)
    assert.ok(Number.isFinite(Date.parse(result.startTime)))
    return {
      title: spec.title,
      file: spec.file,
      project: test.projectName,
      status: result.status,
      retry: result.retry,
      startTime: result.startTime,
      duration: result.duration,
    }
  })
  const provenance = {}
  for (const key of [
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_JOB",
    "GITHUB_WORKFLOW",
  ]) {
    assert.equal(typeof environment[key], "string", `missing ${key}`)
    assert.ok(environment[key].length > 0 && environment[key].length <= 256)
    provenance[key] = environment[key]
  }
  assert.match(provenance.GITHUB_RUN_ID, /^[1-9][0-9]*$/u)
  assert.match(provenance.GITHUB_RUN_ATTEMPT, /^[1-9][0-9]*$/u)
  return {
    schemaVersion: 1,
    finding: "AUD-375",
    status: "passed",
    source: before,
    sourceAfter: after,
    exitCode,
    reportSha256: sha256(raw),
    cases,
    provenance,
    nodeVersion: process.version,
    playwrightVersion: report.config.version,
  }
}

function assertDirectory(directory) {
  const entry = lstatSync(directory)
  assert.equal(entry.isSymbolicLink(), false, "artifact ancestor must not be a symlink")
  assert.equal(entry.isDirectory(), true, "artifact ancestor must be a directory")
}

function assertArtifactPath(root, output) {
  assert.equal(realpathSync(root), path.resolve(root), "source root must be canonical")
  for (const directory of [root, path.join(root, "frontend"), path.dirname(output), output]) {
    assertDirectory(directory)
  }
}

function assertArtifactTree(directory) {
  for (const name of readdirSync(directory)) {
    const file = path.join(directory, name)
    const entry = lstatSync(file)
    assert.equal(entry.isSymbolicLink(), false, "artifact entries must not be symlinks")
    if (entry.isDirectory()) assertArtifactTree(file)
    else assert.equal(entry.isFile(), true, "artifact entries must be regular files")
  }
}

export function readEvidenceFile(file) {
  // The final component must never follow a link, including a dangling one.
  assert.equal(typeof constants.O_NOFOLLOW, "number")
  const descriptor = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW)
  try {
    assert.equal(fstatSync(descriptor).isFile(), true, "report must be a regular file")
    return readFileSync(descriptor)
  } finally {
    closeSync(descriptor)
  }
}

// CLI fixes its own root below. Tests call this same implementation with a
// synthetic repository, so coverage is for these bytes, not a fixture copy.
export function runEvidence(root, environment) {
  const frontend = path.join(root, "frontend")
  const before = captureSource(root, environment.GITHUB_SHA)
  assert.equal(realpathSync(root), path.resolve(root), "source root must be canonical")
  assertDirectory(frontend)
  const parent = path.join(frontend, "playwright-report")
  if (lstatSync(parent, { throwIfNoEntry: false }) === undefined) mkdirSync(parent)
  assertDirectory(parent)
  // Exclusive directory creation rejects old receipts and linked output roots.
  const output = path.join(parent, "aud375")
  mkdirSync(output)
  const save = (name, value) => {
    assertArtifactPath(root, output)
    writeFileSync(path.join(output, name), `${JSON.stringify(value, null, 2)}\n`, { flag: "wx" })
  }
  save("source-before.json", before)
  const require = createRequire(import.meta.url)
  const cli = path.join(path.dirname(require.resolve("playwright/package.json")), "cli.js")
  const result = spawnSync(
    process.execPath,
    [
      cli,
      "test",
      `tests/e2e/${specFile}`,
      "--config=playwright.config.ts",
      "--project=chromium",
      "--workers=1",
      "--retries=0",
      "--reporter=list,json,html",
      "--output=test-results/aud375",
    ],
    {
      cwd: frontend,
      env: {
        ...environment,
        SKIP_WEBSERVER: "true",
        PLAYWRIGHT_JSON_OUTPUT_FILE: path.join(output, "report.json"),
        PLAYWRIGHT_HTML_OUTPUT_DIR: path.join(output, "html"),
        PLAYWRIGHT_HTML_OPEN: "never",
      },
      stdio: "inherit",
      timeout: 300_000,
    }
  )
  // Recheck ancestry and every report entry after the child, before any reads
  // or writes. In particular, an escaped report is never accepted as evidence.
  assertArtifactPath(root, output)
  assertArtifactTree(output)
  save("process.json", { exitCode: result.status, signal: result.signal })
  const after = captureSource(root, environment.GITHUB_SHA)
  save("source-after.json", after)
  const raw = readEvidenceFile(path.join(output, "report.json"))
  const receipt = createReceipt({ raw, exitCode: result.status, before, after, root, environment })
  save("receipt.json", receipt)
  console.log("AUD-375 source-bound receipt prepared; artifact upload is still required.")
  return receipt
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  runEvidence(path.resolve(fileURLToPath(new URL("../../", import.meta.url))), process.env)
}
