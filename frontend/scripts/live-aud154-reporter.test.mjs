import assert from "node:assert/strict"
import { fileURLToPath } from "node:url"
import test from "node:test"
import { execFileSync } from "node:child_process"
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const module = await import("./live-aud154-reporter.mjs").catch(() => null)
const title = "a message is delivered, edited, and tombstoned in the other authenticated session"
const enterTitle = "shows sent confirmation after the server accepts the message"
const file = fileURLToPath(
  new URL("../tests/e2e-live/messenger-realtime.live.spec.ts", import.meta.url)
)

function subject(project = "desktop", changes = {}) {
  return {
    title,
    location: { file },
    parent: { title: "live messenger delivery", project: () => ({ name: project }) },
    expectedStatus: "passed",
    results: [
      { status: "passed", retry: 0, stdout: ["private-message"], attachments: ["private-token"] },
    ],
    outcome: () => "expected",
    ...changes,
  }
}

function collect(tests) {
  assert.ok(module, "the privacy-preserving AUD-154 reporter must exist")
  const output = []
  const reporter = new module.default({}, (line) => output.push(line))
  reporter.onBegin({}, { allTests: () => tests })
  reporter.onEnd({ status: "passed" })
  return output
}

test("retains the exact named case's final results without runtime content", () => {
  const output = collect([subject(), subject("mobile"), subject("desktop", { title: "other" })])
  assert.equal(output.length, 2)
  const records = output.map((line) => JSON.parse(line.slice("UE_LIVE_AUD154_V1 ".length)))
  assert.deepEqual(records[0], {
    schema: 1,
    case_id: "aud154-sent-confirmation",
    project: "desktop",
    final_status: "passed",
    expected_status: "passed",
    outcome: "expected",
    attempts: ["passed"],
    retry: 0,
    skipped: false,
  })
  assert.equal(records[1].project, "mobile")
  assert.doesNotMatch(output.join(""), /private|ticket|token|https?:/u)
})

test("reads results only at run end, after teardown and retries", () => {
  assert.ok(module)
  const output = []
  const row = subject()
  const reporter = new module.default({}, (line) => output.push(line))
  reporter.onBegin({}, { allTests: () => [row] })
  row.results = [
    { status: "failed", retry: 0 },
    { status: "passed", retry: 1 },
  ]
  row.outcome = () => "flaky"
  reporter.onEnd({ status: "passed" })
  const result = JSON.parse(output[0].slice("UE_LIVE_AUD154_V1 ".length))
  assert.deepEqual(result.attempts, ["failed", "passed"])
  assert.equal(result.retry, 1)
  assert.equal(result.outcome, "flaky")
})

test("never recognizes a different file, suite, title, or project", () => {
  for (const change of [
    { location: { file: file.replace("e2e-live", "private") } },
    { title: title + " private" },
    { parent: { title: "private", project: () => ({ name: "desktop" }) } },
    { parent: { title: "live messenger delivery", project: () => ({ name: "private" }) } },
  ])
    assert.deepEqual(collect([subject("desktop", change)]), [])
})

test("invalid result shapes and duplicate cases cannot mint passing records", () => {
  for (const change of [
    { results: [] },
    { results: [{ status: "private", retry: 0 }] },
    { results: [{ status: "passed", retry: 1 }] },
    { expectedStatus: "private" },
    { outcome: () => "private" },
  ])
    assert.deepEqual(collect([subject("desktop", change)]), ["UE_LIVE_AUD154_V1 invalid\n"])
  assert.deepEqual(collect([subject(), subject()]), ["UE_LIVE_AUD154_V1 invalid\n"])
})

test("retains skipped and failed outcomes instead of recasting them as passes", () => {
  for (const status of ["skipped", "failed", "timedOut", "interrupted"]) {
    const line = collect([
      subject("desktop", {
        results: [{ status, retry: 0 }],
        outcome: () => (status === "skipped" ? "skipped" : "unexpected"),
      }),
    ])[0]
    const record = JSON.parse(line.slice("UE_LIVE_AUD154_V1 ".length))
    assert.equal(record.final_status, status)
    assert.equal(record.skipped, status === "skipped")
  }
})

test("the default reporter writes only the closed protocol to stdout", (context) => {
  const lines = []
  context.mock.method(process.stdout, "write", (line) => {
    lines.push(line)
    return true
  })
  const reporter = new module.default()
  reporter.onBegin({}, { allTests: () => [subject()] })
  reporter.onEnd()
  assert.equal(lines.length, 1)
  assert.equal(JSON.parse(lines[0].slice("UE_LIVE_AUD154_V1 ".length)).final_status, "passed")
})

test("actual browser-free Playwright reports final teardown, skip, and retry outcomes", () => {
  const root = mkdtempSync(join(tmpdir(), "aud154-reporter-"))
  try {
    mkdirSync(join(root, "scripts"))
    mkdirSync(join(root, "tests", "e2e-live"), { recursive: true })
    copyFileSync(
      new URL("./live-aud154-reporter.mjs", import.meta.url),
      join(root, "scripts", "live-aud154-reporter.mjs")
    )
    symlinkSync(
      fileURLToPath(new URL("../node_modules", import.meta.url)),
      join(root, "node_modules"),
      "dir"
    )
    writeFileSync(
      join(root, "playwright.config.cjs"),
      `module.exports = {
      testDir: './tests/e2e-live', workers: 1, retries: 1,
      reporter: './scripts/live-aud154-reporter.mjs',
      projects: [{name:'desktop'}, {name:'mobile'}]
    }`
    )
    for (const scenario of ["passed", "skipped", "teardown", "retry"]) {
      writeFileSync(
        join(root, "tests", "e2e-live", "messenger-realtime.live.spec.ts"),
        `
        import { test, expect } from '@playwright/test';
        test.describe('live messenger delivery', () => {
          test.afterEach(() => { if ('${scenario}' === 'teardown') throw new Error('private-teardown'); });
          for (const title of ${JSON.stringify([title, "shows sent confirmation after the server accepts the message"])}) test(title, async ({}, info) => {
            test.skip('${scenario}' === 'skipped');
            if ('${scenario}' === 'retry' && info.retry === 0) throw new Error('private-first-attempt');
            expect(true).toBe(true);
          });
        });
      `
      )
      let output
      try {
        output = execFileSync(
          process.execPath,
          [
            fileURLToPath(new URL("../node_modules/@playwright/test/cli.js", import.meta.url)),
            "test",
            "-c",
            join(root, "playwright.config.cjs"),
          ],
          { cwd: root, encoding: "utf8", timeout: 30000, stdio: ["ignore", "pipe", "pipe"] }
        )
      } catch (error) {
        assert.equal(scenario, "teardown")
        assert.equal(error.status, 1)
        output = error.stdout
      }
      const lines = output.trim().split("\n")
      assert.equal(lines.length, 4)
      assert.doesNotMatch(output, /private/u)
      for (const line of lines) {
        const row = JSON.parse(line.slice("UE_LIVE_AUD154_V1 ".length))
        assert.equal(
          row.final_status,
          scenario === "skipped" ? "skipped" : scenario === "teardown" ? "failed" : "passed"
        )
        assert.equal(row.retry, ["retry", "teardown"].includes(scenario) ? 1 : 0)
        assert.equal(
          row.outcome,
          { passed: "expected", skipped: "skipped", teardown: "unexpected", retry: "flaky" }[
            scenario
          ]
        )
      }
    }
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("retains Enter and button identities independently in both projects", () => {
  const rows = collect([
    subject(),
    subject("mobile"),
    subject("desktop", { title: enterTitle }),
    subject("mobile", { title: enterTitle }),
  ])
  assert.equal(rows.length, 4)
  assert.deepEqual(
    rows.map((line) => JSON.parse(line.slice("UE_LIVE_AUD154_V1 ".length)).case_id),
    [
      "aud154-sent-confirmation",
      "aud154-sent-confirmation",
      "aud154-enter-sent-confirmation",
      "aud154-enter-sent-confirmation",
    ]
  )
  assert.deepEqual(
    collect([subject("desktop", { title: enterTitle }), subject("desktop", { title: enterTitle })]),
    ["UE_LIVE_AUD154_V1 invalid\n"]
  )
})
