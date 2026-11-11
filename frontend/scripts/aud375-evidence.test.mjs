import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import path from "node:path"
import test, { after } from "node:test"
import { fileURLToPath } from "node:url"

const require = createRequire(import.meta.url)
const implementation = new URL("./aud375-evidence.mjs", import.meta.url)
const coverageFlags = [
  "--test-coverage-include=scripts/aud375-evidence.mjs",
  "--test-coverage-lines=100",
  "--test-coverage-branches=100",
  "--test-coverage-functions=100",
]
const helperDigest = createHash("sha256").update(readFileSync(implementation)).digest("hex")
after(() =>
  assert.equal(
    createHash("sha256").update(readFileSync(implementation)).digest("hex"),
    helperDigest
  )
)
test("coverage gate includes these exact helper bytes with all three strict thresholds", () => {
  assert.deepEqual(
    process.execArgv.filter((arg) => arg.startsWith("--test-coverage")).sort(),
    [...coverageFlags].sort()
  )
  assert.equal(typeof process.env.NODE_V8_COVERAGE, "string", "V8 coverage must be active")
  assert.ok(process.env.NODE_V8_COVERAGE.length > 0)
  assert.equal(path.resolve("scripts/aud375-evidence.mjs"), fileURLToPath(implementation))
})

const titles = [
  "forwards the cookie proof and deletes a terminal 403 while two active workers contend",
  "an abandoned worker's lease blocks its successor until forced expiry, then the successor drains the row",
]
const github = {
  GITHUB_REPOSITORY: "egorribun/university_ecosystem",
  GITHUB_RUN_ID: "123",
  GITHUB_RUN_ATTEMPT: "1",
  GITHUB_JOB: "e2e",
  GITHUB_WORKFLOW: "Nightly Full Quality Gate",
}

function git(root, ...args) {
  const result = spawnSync("git", args, { cwd: root, encoding: "utf8" })
  assert.equal(result.status, 0, result.stderr)
  return result.stdout.trim()
}

// Exercise the installed JSON reporter without requesting any browser fixture.
// These synthetic cases validate receipt parsing only, never AUD-375 behavior.
test("receipt accepts real JSON reporter output and rejects altered evidence", async (t) => {
  const { captureSource, createReceipt, sourcePaths, runEvidence } = await import(
    implementation.href
  )
  const root = mkdtempSync(path.join(tmpdir(), "aud375-receipt-contract-"))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  for (const file of sourcePaths) {
    mkdirSync(path.dirname(path.join(root, file)), { recursive: true })
    writeFileSync(path.join(root, file), "fixture\n")
  }
  writeFileSync(path.join(root, "frontend/package.json"), '{"type":"module"}\n')
  const spec = path.join(root, "frontend/tests/e2e/audit375-service-worker.spec.ts")
  const imported = JSON.stringify(import.meta.resolve("@playwright/test"))
  writeFileSync(
    spec,
    `import { test, expect } from ${imported};\ntest.describe("AUD-375 real service-worker replay", () => {\n${titles.map((title) => `test(${JSON.stringify(title)}, () => { expect(true).toBe(true) });`).join("\n")}\n});\n`
  )
  writeFileSync(
    path.join(root, "frontend/playwright.config.ts"),
    'export default { testDir: "./tests/e2e", workers: 1, retries: 0, projects: [{ name: "chromium", use: { browserName: "chromium" } }] };\n'
  )
  writeFileSync(
    path.join(root, "frontend/scripts/aud375-evidence.mjs"),
    readFileSync(implementation)
  )
  git(root, "init", "--quiet")
  git(root, "add", ".")
  git(
    root,
    "-c",
    "user.name=Receipt contract",
    "-c",
    "user.email=contract@example.invalid",
    "-c",
    "core.hooksPath=/dev/null",
    "commit",
    "--quiet",
    "-m",
    "test fixture"
  )
  const sha = git(root, "rev-parse", "HEAD")
  const before = captureSource(root, sha)
  const output = path.join(root, "report.json")
  const cli = path.join(path.dirname(require.resolve("playwright/package.json")), "cli.js")
  const result = spawnSync(
    process.execPath,
    [
      cli,
      "test",
      "tests/e2e/audit375-service-worker.spec.ts",
      "--config=playwright.config.ts",
      "--project=chromium",
      "--workers=1",
      "--retries=0",
      "--reporter=json",
    ],
    {
      cwd: path.join(root, "frontend"),
      env: {
        PATH: process.env.PATH,
        HOME: root,
        CI: "true",
        PLAYWRIGHT_JSON_OUTPUT_FILE: output,
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1",
      },
      encoding: "utf8",
      timeout: 60_000,
    }
  )
  assert.equal(result.status, 0, result.stderr + result.stdout)
  symlinkSync(
    path.dirname(path.dirname(require.resolve("playwright/package.json"))),
    path.join(root, "frontend/node_modules"),
    "junction"
  )
  const run = (expectedSha = sha) => {
    try {
      runEvidence(root, {
        PATH: process.env.PATH,
        HOME: root,
        CI: "true",
        ...github,
        GITHUB_SHA: expectedSha,
      })
      return { status: 0, stdout: "", stderr: "" }
    } catch (error) {
      return { status: 1, stdout: "", stderr: String(error) }
    }
  }
  const executed = run()
  assert.equal(executed.status, 0, executed.stderr + executed.stdout)
  const archived = path.join(root, "frontend/playwright-report/aud375")
  const artifactReceipt = JSON.parse(readFileSync(path.join(archived, "receipt.json")))
  assert.equal(
    artifactReceipt.reportSha256,
    createHash("sha256")
      .update(readFileSync(path.join(archived, "report.json")))
      .digest("hex")
  )
  assert.equal(artifactReceipt.source.commit, sha)
  assert.equal(run().status, 1, "stale receipt directories must not be reused")
  await t.test(
    "runner rejects a symlinked report parent without issuing an outside receipt",
    () => {
      const parent = path.dirname(archived)
      const outside = path.join(root, "outside-artifact-root")
      rmSync(parent, { recursive: true })
      mkdirSync(outside)
      symlinkSync(outside, parent, "junction")
      const linked = run()
      rmSync(parent)
      mkdirSync(parent)
      mkdirSync(archived)
      assert.notEqual(linked.status, 0)
      assert.equal(existsSync(path.join(outside, "aud375/receipt.json")), false)
    }
  )
  await t.test("runner rejects a linked output root and a non-directory report parent", () => {
    const outside = path.join(root, "outside-artifact-root")
    rmSync(archived, { recursive: true })
    symlinkSync(outside, archived, "junction")
    assert.equal(run().status, 1)
    rmSync(archived)
    rmSync(path.dirname(archived), { recursive: true })
    writeFileSync(path.dirname(archived), "not a directory")
    assert.equal(run().status, 1)
    rmSync(path.dirname(archived))
    mkdirSync(path.dirname(archived))
    mkdirSync(archived)
  })
  await t.test("runner rejects a symlinked source root", () => {
    const linkedRoot = `${root}-link`
    symlinkSync(root, linkedRoot, "junction")
    try {
      assert.throws(
        () => runEvidence(linkedRoot, { ...github, GITHUB_SHA: sha }),
        /source root must be canonical/u
      )
    } finally {
      rmSync(linkedRoot)
    }
  })
  const raw = readFileSync(output)
  const after = captureSource(root, sha)
  const options = { raw, exitCode: 0, before, after, root, environment: github }
  const receipt = createReceipt(options)
  assert.equal(receipt.status, "passed")
  assert.equal(receipt.source.commit, sha)
  assert.deepEqual(receipt.source, before)
  assert.equal(receipt.reportSha256, createHash("sha256").update(raw).digest("hex"))
  assert.deepEqual(
    receipt.cases.map((entry) => entry.title),
    titles
  )

  function altered(mutator) {
    const report = JSON.parse(raw)
    const specs = report.suites[0].suites[0].specs
    mutator(report, specs)
    return Buffer.from(JSON.stringify(report))
  }
  const negatives = [
    [
      "extra nested suite",
      (r) => {
        r.suites[0].suites[0].suites = [{ title: "unexpected", specs: [] }]
      },
    ],
    [
      "empty suite",
      (r) => {
        r.suites = []
      },
    ],
    ["missing case", (_r, specs) => specs.pop()],
    ["extra case", (_r, specs) => specs.push(structuredClone(specs[0]))],
    [
      "wrong title",
      (_r, specs) => {
        specs[0].title = "different"
      },
    ],
    [
      "wrong file",
      (_r, specs) => {
        specs[0].file = "other.spec.ts"
      },
    ],
    [
      "wrong suite",
      (r) => {
        r.suites[0].suites[0].title = "other"
      },
    ],
    [
      "wrong project",
      (_r, specs) => {
        specs[0].tests[0].projectName = "firefox"
      },
    ],
    ["multiple tests", (_r, specs) => specs[0].tests.push(structuredClone(specs[0].tests[0]))],
    [
      "unexpected outcome",
      (_r, specs) => {
        specs[0].tests[0].status = "unexpected"
      },
    ],
    [
      "flaky outcome",
      (_r, specs) => {
        specs[0].tests[0].status = "flaky"
      },
    ],
    [
      "skipped attempt",
      (_r, specs) => {
        specs[0].tests[0].results[0].status = "skipped"
      },
    ],
    [
      "failed attempt",
      (_r, specs) => {
        specs[0].tests[0].results[0].status = "failed"
      },
    ],
    [
      "interrupted attempt",
      (_r, specs) => {
        specs[0].tests[0].results[0].status = "interrupted"
      },
    ],
    [
      "retry",
      (_r, specs) => {
        specs[0].tests[0].results[0].retry = 1
      },
    ],
    [
      "two attempts",
      (_r, specs) => specs[0].tests[0].results.push(structuredClone(specs[0].tests[0].results[0])),
    ],
    [
      "expected failure",
      (_r, specs) => {
        specs[0].tests[0].expectedStatus = "failed"
      },
    ],
    ["annotation", (_r, specs) => specs[0].tests[0].annotations.push({ type: "skip" })],
    [
      "result error",
      (_r, specs) => {
        specs[0].tests[0].results[0].error = { message: "error" }
      },
    ],
    [
      "result errors",
      (_r, specs) => specs[0].tests[0].results[0].errors.push({ message: "error" }),
    ],
    ["global error", (r) => r.errors.push({ message: "error" })],
    [
      "summary skip",
      (r) => {
        r.stats.skipped = 1
      },
    ],
    [
      "summary flaky",
      (r) => {
        r.stats.flaky = 1
      },
    ],
    [
      "summary failure",
      (r) => {
        r.stats.unexpected = 1
      },
    ],
    [
      "wrong count",
      (r) => {
        r.stats.expected = 3
      },
    ],
    [
      "wrong root",
      (r) => {
        r.config.rootDir = "/wrong"
      },
    ],
    [
      "wrong config",
      (r) => {
        r.config.configFile = "/wrong/config.ts"
      },
    ],
    [
      "retry configuration",
      (r) => {
        r.config.projects[0].retries = 1
      },
    ],
    [
      "repeat configuration",
      (r) => {
        r.config.projects[0].repeatEach = 2
      },
    ],
  ]
  for (const [name, mutate] of negatives) {
    await t.test(name, () =>
      assert.throws(() => createReceipt({ ...options, raw: altered(mutate) }))
    )
  }
  for (const exitCode of [1, null, undefined]) {
    assert.throws(() => createReceipt({ ...options, exitCode }))
  }
  assert.throws(() => createReceipt({ ...options, raw: Buffer.from("{}") }))
  assert.throws(() => createReceipt({ ...options, raw: Buffer.from("not json") }))
  assert.throws(() => createReceipt({ ...options, environment: {} }))
  assert.throws(() => createReceipt({ ...options, after: { ...after, tree: "a".repeat(40) } }))
  assert.throws(() => createReceipt({ ...options, before: { ...before, trackedClean: false } }))
  assert.throws(() => captureSource(root, "a".repeat(40)))
  writeFileSync(spec, "changed\n")
  assert.throws(() => captureSource(root, sha))
  git(root, "add", "frontend/tests/e2e/audit375-service-worker.spec.ts")
  assert.throws(() => captureSource(root, sha))
  git(
    root,
    "restore",
    "--staged",
    "--worktree",
    "frontend/tests/e2e/audit375-service-worker.spec.ts"
  )
  const originalSpec = readFileSync(spec, "utf8")
  await t.test("runner retains failed raw output without issuing a pass receipt", () => {
    rmSync(archived, { recursive: true })
    writeFileSync(spec, originalSpec.replace("expect(true).toBe(true)", "expect(false).toBe(true)"))
    git(root, "add", "frontend/tests/e2e/audit375-service-worker.spec.ts")
    git(
      root,
      "-c",
      "user.name=Receipt contract",
      "-c",
      "user.email=contract@example.invalid",
      "-c",
      "core.hooksPath=/dev/null",
      "commit",
      "--quiet",
      "-m",
      "failing fixture"
    )
    const failed = run(git(root, "rev-parse", "HEAD"))
    assert.equal(failed.status, 1)
    assert.equal(existsSync(path.join(archived, "receipt.json")), false)
    assert.equal(existsSync(path.join(archived, "report.json")), true)
    assert.equal(JSON.parse(readFileSync(path.join(archived, "process.json"))).exitCode, 1)
  })
  await t.test("runner rejects a tracked source mutation during execution", () => {
    rmSync(archived, { recursive: true })
    const mutation = `writeFileSync(${JSON.stringify(path.join(root, "frontend/src/sw/replayPolicy.ts"))}, "changed during execution"); expect(true).toBe(true)`
    writeFileSync(
      spec,
      `import { writeFileSync } from "node:fs";\n` +
        originalSpec.replace("expect(true).toBe(true)", mutation)
    )
    git(root, "add", "frontend/tests/e2e/audit375-service-worker.spec.ts")
    git(
      root,
      "-c",
      "user.name=Receipt contract",
      "-c",
      "user.email=contract@example.invalid",
      "-c",
      "core.hooksPath=/dev/null",
      "commit",
      "--quiet",
      "-m",
      "mutating fixture"
    )
    const changed = run(git(root, "rev-parse", "HEAD"))
    assert.equal(changed.status, 1)
    assert.match(changed.stderr, /tracked source must be clean/u)
    assert.equal(existsSync(path.join(archived, "receipt.json")), false)
  })
  for (const entry of ["report.json", "receipt.json"]) {
    await t.test(`runner rejects a child-created symlink ${entry}`, () => {
      git(root, "restore", "frontend/src/sw/replayPolicy.ts")
      rmSync(archived, { recursive: true })
      writeFileSync(spec, originalSpec)
      const outside = path.join(root, `outside-${entry}`)
      writeFileSync(outside, "untouched")
      // The teardown module is constant code; the paths it links travel as JSON
      // data, so no fixture value is ever spliced into executable source.
      writeFileSync(
        path.join(root, "frontend/teardown-target.json"),
        JSON.stringify({ target: outside, link: path.join(archived, entry) })
      )
      writeFileSync(
        path.join(root, "frontend/teardown.mjs"),
        'import { readFileSync, symlinkSync } from "node:fs"\n' +
          "export default () => {\n" +
          '  const source = new URL("./teardown-target.json", import.meta.url)\n' +
          '  const { target, link } = JSON.parse(readFileSync(source, "utf8"))\n' +
          '  symlinkSync(target, link, "file")\n' +
          "}\n"
      )
      writeFileSync(
        path.join(root, "frontend/playwright.config.ts"),
        'export default { testDir: "./tests/e2e", workers: 1, retries: 0, globalTeardown: "./teardown.mjs", projects: [{ name: "chromium", use: { browserName: "chromium" } }] };\n'
      )
      git(
        root,
        "add",
        "frontend/tests/e2e/audit375-service-worker.spec.ts",
        "frontend/playwright.config.ts",
        "frontend/teardown.mjs",
        "frontend/teardown-target.json"
      )
      git(
        root,
        "-c",
        "user.name=Receipt contract",
        "-c",
        "user.email=contract@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "--quiet",
        "-m",
        "symlink fixture"
      )
      const linked = run(git(root, "rev-parse", "HEAD"))
      assert.equal(linked.status, 1)
      assert.match(linked.stderr, /artifact entries must not be symlinks/u)
      if (entry === "receipt.json") assert.equal(readFileSync(outside, "utf8"), "untouched")
      else assert.equal(existsSync(path.join(archived, "receipt.json")), false)
    })
  }
})

test("hosted receipt uses the existing lane and requires an immutable archive", async () => {
  const yaml = await import("js-yaml")
  const workflow = yaml.load(
    readFileSync(new URL("../../.github/workflows/reusable-e2e-tests.yml", import.meta.url), "utf8")
  )
  const steps = workflow.jobs.e2e.steps
  const run = steps.find((step) => step.id === "aud375-receipt")
  assert.ok(run, "the receipt runner must have a real hosted invocation")
  assert.equal(run.if, "inputs.browser == 'chromium' && inputs.shard-index == 1")
  assert.equal(run["working-directory"], "frontend")
  assert.equal(run.run, "node scripts/aud375-evidence.mjs")
  const archive = steps.find((step) => step.id === "aud375-archive")
  assert.equal(archive.if, "${{ always() && steps.aud375-receipt.outcome == 'success' }}")
  assert.match(archive.uses, /^actions\/upload-artifact@[0-9a-f]{40}$/u)
  assert.equal(archive["continue-on-error"], undefined)
  assert.equal(archive.with["if-no-files-found"], "error")
  assert.equal(archive.with.path, "frontend/playwright-report/aud375/")
  for (const binding of ["github.sha", "github.run_id", "github.run_attempt"]) {
    assert.ok(archive.with.name.includes(binding))
  }
  const nightly = yaml.load(
    readFileSync(new URL("../../.github/workflows/nightly-full-gate.yml", import.meta.url), "utf8")
  )
  assert.equal(nightly.jobs["browser-matrix"].if, "${{ github.ref == 'refs/heads/main' }}")
  assert.equal(nightly.jobs["browser-matrix"].uses, "./.github/workflows/reusable-e2e-tests.yml")
  const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url)))
  assert.ok(packageJson.scripts["test:wasm"].includes("scripts/aud375-evidence.test.mjs"))
  assert.ok(
    packageJson.scripts["test:wasm"].includes("scripts/playwright-report-preservation.test.mjs")
  )
})

test("report reads reject symbolic links and non-regular files", async (t) => {
  const { readEvidenceFile } = await import(implementation.href)
  const directory = mkdtempSync(path.join(tmpdir(), "aud375-nofollow-"))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  const target = path.join(directory, "raw.json")
  const link = path.join(directory, "linked.json")
  writeFileSync(target, "{}")
  assert.deepEqual(readEvidenceFile(target), Buffer.from("{}"))
  symlinkSync(target, link, "file")
  assert.throws(() => readEvidenceFile(link))
  assert.throws(() => readEvidenceFile(directory), /regular file/u)
})

test("canonical CLI preflight fails without producing a receipt and contributes real-source coverage", () => {
  const cliEnvironment = {
    PATH: process.env.PATH,
    HOME: process.env.HOME,
    NODE_V8_COVERAGE: process.env.NODE_V8_COVERAGE,
    GITHUB_SHA: "0".repeat(40),
  }
  const executed = spawnSync(process.execPath, [fileURLToPath(implementation)], {
    env: cliEnvironment,
    encoding: "utf8",
    timeout: 30_000,
  })
  assert.notEqual(executed.status, 0)
  const imported = spawnSync(
    process.execPath,
    ["--input-type=module", "--eval", `await import(${JSON.stringify(implementation.href)})`],
    { env: cliEnvironment, encoding: "utf8", timeout: 30_000 }
  )
  assert.equal(imported.status, 0, imported.stderr)
})
