import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { createHash } from "node:crypto"
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import * as yaml from "js-yaml"

const frontend = fileURLToPath(new URL("../", import.meta.url))
const cli = fileURLToPath(import.meta.resolve("@playwright/test/cli"))
const playwright = import.meta.resolve("@playwright/test")
const workflow = yaml.load(
  await readFile(new URL("../../.github/workflows/reusable-e2e-tests.yml", import.meta.url), "utf8")
)
const steps = Object.values(workflow.jobs).flatMap((job) => job.steps ?? [])
// Consume the workflow's actual reporter and output arguments. Do not execute
// its shell: these fixtures must never start a browser, build, or service.
const invocations = steps.flatMap((step) =>
  [
    ...(step.run ?? "")
      .replaceAll(/\\\r?\n\s*/gu, " ")
      .matchAll(/^(?:\s*)(?:PLAYWRIGHT_HTML_OUTPUT_DIR=(\S+)\s+)?npx playwright test ([^\n]+)/gmu),
  ].map((match) => ({
    step,
    html: match[1] ?? step.env?.PLAYWRIGHT_HTML_OUTPUT_DIR ?? "playwright-report",
    output: match[2].match(/--output=(\S+)/u)?.[1] ?? "test-results",
    reporter: match[2].match(/--reporter=(\S+)/u)?.[1],
    config: match[2].includes("--config=playwright.ssr.config.ts")
      ? "playwright.ssr.config.ts"
      : "playwright.config.ts",
  }))
)

async function snapshot(directory) {
  const files = {}
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const filename = path.join(dir, entry.name)
      if (entry.isDirectory()) await walk(filename)
      else
        files[path.relative(directory, filename)] = createHash("sha256")
          .update(await readFile(filename))
          .digest("hex")
    }
  }
  await walk(directory)
  return files
}

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), "playwright-preservation-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  await writeFile(path.join(root, "package.json"), JSON.stringify({ type: "module" }))
  await mkdir(path.join(root, "specs"))
  await writeFile(
    path.join(root, "specs", "evidence.spec.mjs"),
    `import { test } from ${JSON.stringify(playwright)};
import { writeFile } from 'node:fs/promises';
test('browserless evidence', async ({}, testInfo) => {
  const artifact = testInfo.outputPath('evidence.txt');
  await writeFile(artifact, process.env.PRESERVATION_MARKER);
  await testInfo.attach('evidence', { path: artifact, contentType: 'text/plain' });
});`
  )
  return {
    root,
    async run(invocation, marker) {
      const config = path.join(root, "playwright.config.ts")
      await writeFile(
        config,
        `import base from ${JSON.stringify(path.join(frontend, invocation.config))};
export default { ...base, webServer: undefined, testDir: './specs',
  outputDir: './test-results', retries: 0, workers: 1 };`
      )
      const env = { ...process.env }
      for (const key of Object.keys(env)) {
        if (/^(PLAYWRIGHT_|PW_|URL_STATE_E2E|PRODUCTION_SERVER_E2E|SKIP_WEBSERVER)/u.test(key)) {
          delete env[key]
        }
      }
      const result = spawnSync(
        process.execPath,
        [
          cli,
          "test",
          `--config=${config}`,
          "--project=chromium",
          `--output=${invocation.output}`,
          `--reporter=${invocation.reporter}`,
        ],
        {
          cwd: root,
          env: {
            ...env,
            CI: "true",
            PRODUCTION_SERVER_E2E: "true",
            PLAYWRIGHT_HTML_OPEN: "never",
            PLAYWRIGHT_HTML_OUTPUT_DIR: invocation.html,
            PRESERVATION_MARKER: marker,
          },
          encoding: "utf8",
          timeout: 30_000,
        }
      )
      assert.equal(result.error, undefined, result.error?.message)
      assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`)
      const report = path.join(root, invocation.html)
      const reportFiles = await snapshot(report)
      assert.ok(reportFiles["index.html"], "real HTML report exists")
      const data = Object.keys(reportFiles).filter((name) => name.startsWith(`data${path.sep}`))
      assert.ok(data.length > 0, "report includes real copied attachment")
      assert.ok(
        (await Promise.all(data.map((name) => readFile(path.join(report, name), "utf8")))).includes(
          marker
        ),
        "report attachment contains this invocation's evidence"
      )
      const output = path.join(root, invocation.output)
      const outputFiles = await snapshot(output)
      assert.ok(Object.keys(outputFiles).some((name) => name.endsWith("evidence.txt")))
      return { report, reportFiles, output, outputFiles }
    },
  }
}

test("workflow preserves all six HTML reports and test artifacts through the final upload", async (t) => {
  assert.equal(invocations.length, 6, "exercise main plus every auxiliary invocation")
  const f = await fixture(t)
  const saved = []
  for (const [index, invocation] of invocations.entries()) {
    saved.push(await f.run(invocation, `workflow-evidence-${index}`))
  }
  for (const evidence of saved) {
    assert.deepEqual(
      await snapshot(evidence.report),
      evidence.reportFiles,
      "a later invocation must not overwrite an earlier HTML report"
    )
    assert.deepEqual(
      await snapshot(evidence.output),
      evidence.outputFiles,
      "a later invocation must not erase an earlier test artifact"
    )
  }
  assert.equal(new Set(invocations.map((entry) => entry.html)).size, 6)
  assert.equal(new Set(invocations.map((entry) => entry.output)).size, 6)
  for (const invocation of invocations) {
    assert.match(invocation.html, /^playwright-report\/[a-z-]+$/u)
    assert.match(invocation.output, /^test-results\/[a-z-]+$/u)
  }
  const upload = steps.find((step) => step.name === "Upload Playwright report")
  assert.equal(upload.with.path, "frontend/playwright-report/")
  assert.equal(upload.if, "always()")
  assert.equal(upload["continue-on-error"], true)
  assert.equal(
    upload.with.name,
    "playwright-report-${{ inputs.browser }}-shard-${{ inputs.shard-index }}-of-${{ inputs.shard-total }}"
  )
  assert.equal(upload.with["retention-days"], 14)
})

test("negative control: legacy shared HTML directory clobbers prior evidence despite distinct --output", async (t) => {
  const f = await fixture(t)
  const base = { config: "playwright.config.ts", reporter: "html", html: "playwright-report" }
  const first = await f.run({ ...base, output: "test-results/main" }, "original-main")
  await f.run({ ...base, output: "test-results/auxiliary" }, "replacement-auxiliary")
  assert.notDeepEqual(await snapshot(first.report), first.reportFiles)
  assert.deepEqual(await snapshot(first.output), first.outputFiles)
})

test("negative control: using either parent root erases previously preserved children", async (t) => {
  const f = await fixture(t)
  const base = { config: "playwright.config.ts", reporter: "html" }
  const first = await f.run(
    { ...base, html: "playwright-report/main", output: "test-results/main" },
    "child-evidence"
  )
  await f.run({ ...base, html: "playwright-report", output: "test-results" }, "parent-cleanup")
  await assert.rejects(snapshot(first.report), { code: "ENOENT" })
  await assert.rejects(snapshot(first.output), { code: "ENOENT" })
})
