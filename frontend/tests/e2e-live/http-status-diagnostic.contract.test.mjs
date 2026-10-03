import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import process from "node:process"
import test from "node:test"
import { fileURLToPath, URL } from "node:url"

const helperUrl = new URL("./http-status-diagnostic.ts", import.meta.url)

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { reportLiveHttpStatus } from ${JSON.stringify(helperUrl.href)};\n${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0, "the diagnostic helper must not throw")
  assert.equal(result.stderr, "", "the helper writes only its bounded stdout protocol")
  return result.stdout
}

test("HTTP diagnostics emit only fixed project/check labels and integer status boundaries", () => {
  for (const status of [100, 599]) {
    const calls = []
    const expected = []
    for (const project of ["desktop", "mobile"]) {
      for (const check of ["admin-users", "admin-feature-flags", "admin-feature-flags-ui"]) {
        calls.push(
          `reportLiveHttpStatus(${JSON.stringify(project)}, ${JSON.stringify(check)}, ${status})`
        )
        expected.push(`UE_LIVE_HTTP_STATUS_V1 project=${project} check=${check} status=${status}\n`)
      }
    }
    assert.equal(reportInChild(calls.join("\n")), expected.join(""))
  }
})

test("HTTP diagnostics silently reject out-of-domain runtime values without coercion", () => {
  assert.equal(
    reportInChild(`
      const privateValue = { toString() { throw new Error("private-value") } };
      for (const project of ["", "Desktop", "private-project", "desktop\\n", "desktop\\r", "desktop\\u202e", null, undefined, 1, privateValue]) {
        reportLiveHttpStatus(project, "admin-users", 200);
      }
      for (const check of ["", "admin", "private-check", "admin-users\\n", "admin-users status=401", null, undefined, 1, privateValue]) {
        reportLiveHttpStatus("desktop", check, 200);
      }
      for (const status of [99, 600, -1, 200.5, NaN, Infinity, -Infinity, "200", "200\\nprivate", null, undefined, true, 200n, privateValue]) {
        reportLiveHttpStatus("desktop", "admin-users", status);
      }
    `),
    ""
  )
})

test("HTTP diagnostics deduplicate records and stop at eight records per worker process", () => {
  const output = reportInChild(`
    for (let status = 100; status < 600; status += 1) {
      for (let duplicate = 0; duplicate < 10; duplicate += 1) {
        reportLiveHttpStatus("desktop", "admin-users", status);
      }
    }
  `)
  assert.equal(
    output,
    Array.from(
      { length: 8 },
      (_, index) =>
        `UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=${100 + index}\n`
    ).join("")
  )
})

test("HTTP diagnostic helper has no browser, response, environment, or artifact access", async () => {
  const source = await readFile(helperUrl, "utf8")
  assert.doesNotMatch(
    source,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\b(?:page|browser|context|response|request|URL)\b|\.(?:json|text|screenshot|storageState|attach)\s*\(/u
  )
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 1)
})

test("the real Playwright list reporter preserves stdout protocol without browser fixtures", async (t) => {
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), "ue-http-diagnostic-"))
  t.after(() => rm(temporaryRoot, { recursive: true, force: true }))
  const playwrightUrl = new URL("../../node_modules/@playwright/test/index.mjs", import.meta.url)
  const cliPath = fileURLToPath(
    new URL("../../node_modules/@playwright/test/cli.js", import.meta.url)
  )
  const configPath = path.join(temporaryRoot, "playwright.config.mjs")
  const outputPath = path.join(temporaryRoot, "output")
  await writeFile(
    configPath,
    `export default {
      testDir: ${JSON.stringify(temporaryRoot)}, testMatch: "diagnostic.spec.mjs",
      reporter: "list", workers: 1, retries: 0, preserveOutput: "never",
      outputDir: ${JSON.stringify(outputPath)},
      use: { trace: "off", screenshot: "off", video: "off" },
      projects: [{ name: "desktop" }, { name: "mobile" }]
    }`
  )
  await writeFile(
    path.join(temporaryRoot, "diagnostic.spec.mjs"),
    `import { test } from ${JSON.stringify(playwrightUrl.href)};
    import { reportLiveHttpStatus } from ${JSON.stringify(helperUrl.href)};
    test("private-title", async ({}, testInfo) => {
      process.stdout.write("private-body https://private.invalid/?token=private-token\\n");
      process.stderr.write("private-credential private-browser-state\\n");
      reportLiveHttpStatus(testInfo.project.name, "admin-users", 403);
      reportLiveHttpStatus(testInfo.project.name, "admin-feature-flags", 503);
      reportLiveHttpStatus(testInfo.project.name, "admin-feature-flags-ui", 502);
      throw new Error("private-error");
    });`
  )
  const result = spawnSync(process.execPath, [cliPath, "test", "--config", configPath], {
    encoding: "utf8",
    timeout: 30_000,
    env: { ...process.env, FORCE_COLOR: "0" },
  })
  assert.equal(result.status, 1, "the fixture must execute and fail its intentional assertion")
  const records = result.stdout
    .split("\n")
    .filter((line) => line.startsWith("UE_LIVE_HTTP_STATUS_V1 "))
  assert.deepEqual(records, [
    "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-users status=403",
    "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-feature-flags status=503",
    "UE_LIVE_HTTP_STATUS_V1 project=desktop check=admin-feature-flags-ui status=502",
    "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-users status=403",
    "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-feature-flags status=503",
    "UE_LIVE_HTTP_STATUS_V1 project=mobile check=admin-feature-flags-ui status=502",
  ])
  assert.match(result.stdout, /private-title|private-body/u)
  assert.match(result.stderr, /private-credential/u)
  assert.doesNotMatch(result.stderr, /UE_LIVE_HTTP_STATUS_V1/u)
  assert.deepEqual(await readdir(outputPath), [".last-run.json"])
})
