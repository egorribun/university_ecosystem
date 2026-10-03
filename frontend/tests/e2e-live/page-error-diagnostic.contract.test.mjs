import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { randomUUID } from "node:crypto"
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import process from "node:process"
import test from "node:test"
import { fileURLToPath, URL } from "node:url"

const helperUrl = new URL("./page-error-diagnostic.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const specUrl = new URL("./password-reset.live.spec.ts", import.meta.url)
const resetTitle =
  "a student resets with the Mailpit link without retaining tokens or following hostile redirects"
function freshPassword() {
  return `Aa1!${randomUUID()}`
}
const types = [
  ["Error", "error"],
  ["TypeError", "type-error"],
  ["ReferenceError", "reference-error"],
  ["SyntaxError", "syntax-error"],
  ["RangeError", "range-error"],
  ["URIError", "uri-error"],
  ["EvalError", "eval-error"],
  ["AggregateError", "aggregate-error"],
  ["AbortError", "abort-error"],
  ["SecurityError", "security-error"],
  ["InvalidStateError", "invalid-state-error"],
  ["private-name", "other"],
]

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { createLivePageErrorDiagnostics } from ${JSON.stringify(helperUrl.href)};
      function reportLivePageErrors(project, check, errors, pathname = "/reset-password") {
        const diagnostics = createLivePageErrorDiagnostics();
        for (const error of errors) diagnostics.record(error, pathname);
        diagnostics.report(project, check);
      }
      ${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0, "the diagnostic helper must not throw")
  assert.equal(result.stderr, "", "the helper writes only its bounded stdout protocol")
  return result.stdout
}

test("page error diagnostics classify exact standard names and emit counts only", () => {
  const expected = []
  const calls = []
  for (const project of ["desktop", "mobile"]) {
    calls.push(`reportLivePageErrors(${JSON.stringify(project)}, "password-reset", [
      ${types.map(([name]) => `{ name: ${JSON.stringify(name)}, get message() { throw new Error("private-message") }, get stack() { throw new Error("private-stack") }, get code() { throw new Error("private-code") } }`).join(",\n")}
    ])`)
    for (const [, type] of types) {
      expected.push(
        `UE_LIVE_PAGE_ERROR_V1 project=${project} check=password-reset page=reset-password type=${type} count=1\n`
      )
    }
  }
  assert.equal(reportInChild(calls.join("\n")), expected.join(""))
})

test("page error diagnostics never coerce private names and unknown values count as other", () => {
  const output = reportInChild(`
    const privateValue = { toString() { throw new Error("private-coercion") } };
    reportLivePageErrors("desktop", "password-reset", [
      { name: "TypeError\\nprivate-token" }, { name: "Error\\r" }, { name: "error" },
      { name: "constructor" }, { name: "__proto__" }, { name: privateValue },
      { get name() { throw new Error("private-name-getter") } },
      null, undefined, "private-message"
    ]);
  `)
  assert.equal(
    output,
    "UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=reset-password type=other count=10\n"
  )
})

test("page classification retains only exact public paths", () => {
  for (const [pathname, page] of [
    ["/register", "register"],
    ["/login", "login"],
    ["/forgot-password", "forgot-password"],
    ["/reset-password", "reset-password"],
    ["/dashboard", "dashboard"],
    ["/private-token", "other"],
    ["/reset-password?token=private-token", "other"],
    ["/login#private-fragment", "other"],
    ["/login/", "other"],
    [null, "other"],
    [1, "other"],
  ]) {
    assert.equal(
      reportInChild(
        `reportLivePageErrors("desktop", "password-reset", [new Error("private-message")], ${JSON.stringify(pathname)})`
      ),
      `UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=${page} type=error count=1\n`
    )
  }
  assert.equal(
    reportInChild(`
    const diagnostics = createLivePageErrorDiagnostics();
    diagnostics.record(new Error("private-message"), { toString() { throw new Error("private-path") } });
    diagnostics.record(new Error("private-message"), undefined);
    diagnostics.report("desktop", "password-reset");
  `),
    "UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=other type=error count=2\n"
  )
})

test("page error diagnostics reject unrelated labels without output", () => {
  assert.equal(
    reportInChild(`
      const privateValue = { toString() { throw new Error("private-value") } };
      for (const project of ["", "Desktop", "private-project", "desktop\\n", "desktop\\r", null, undefined, 1, privateValue]) {
        reportLivePageErrors(project, "password-reset", [new Error("private-message")]);
      }
      for (const check of ["", "private-check", "password-reset\\n", null, undefined, 1, privateValue]) {
        reportLivePageErrors("desktop", check, [new Error("private-message")]);
      }
      reportLivePageErrors("desktop", "password-reset", []);
    `),
    ""
  )
})

test("page error diagnostics saturate counts and deduplicate bounded worker output", () => {
  assert.equal(
    reportInChild(`
      const errors = Array.from({ length: 1200 }, () => new TypeError("private-message"));
      for (let i = 0; i < 3; i += 1) reportLivePageErrors("desktop", "password-reset", errors);
    `),
    "UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=reset-password type=type-error count=999\n"
  )
  assert.equal(
    reportInChild(`
      for (let count = 1; count < 200; count += 1) {
        reportLivePageErrors("desktop", "password-reset", Array.from({ length: count }, () => new Error("private-message")));
      }
    `),
    Array.from(
      { length: 144 },
      (_, i) =>
        `UE_LIVE_PAGE_ERROR_V1 project=desktop check=password-reset page=reset-password type=error count=${i + 1}\n`
    ).join("")
  )
})

test("page error diagnostics have no browser, private error field, or artifact access", async () => {
  const source = await readFile(helperUrl, "utf8")
  assert.doesNotMatch(
    source,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\.(?:message|stack|code)\b|\b(?:page|browser|context|response|request)\.|\bURL\b|\.(?:json|text|screenshot|storageState|attach)\s*\(/u
  )
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 1)
})

test("reset diagnostic wiring preserves the hard page error and replay assertions", async () => {
  const fixtures = await readFile(fixtureUrl, "utf8")
  const spec = await readFile(specUrl, "utf8")
  assert.match(
    fixtures,
    /await use\(errors\)[\s\S]*pageErrorDiagnostics\.report\([\s\S]*expect\(errors, errors\.map\(\(error\) => error\.message\)\.join\("\\n"\)\)\.toEqual\(\[\]\)/u
  )
  assert.match(fixtures, /testInfo\.title ===/u)
  assert.ok(fixtures.includes(resetTitle))
  assert.match(fixtures, /\.endsWith\("\/tests\/e2e-live\/password-reset\.live\.spec\.ts"\)/u)
  assert.match(
    spec,
    /reportLiveHttpStatus\(testInfo\.project\.name, "password-reset-replay", replayResult\.status\(\)\)\s*expect\(replayResult\.status\(\), "a consumed reset token must be rejected by the API"\)\.toBe\(400\)/u
  )
})

test("the actual automatic fixture emits only reset counts and still fails uncaught errors without a browser", async (t) => {
  const temporaryRoot = await mkdtemp(path.join(tmpdir(), "ue-reset-diagnostic-"))
  t.after(() => rm(temporaryRoot, { recursive: true, force: true }))
  const testDir = path.join(temporaryRoot, "tests", "e2e-live")
  await mkdir(testDir, { recursive: true })
  const cliPath = fileURLToPath(
    new URL("../../node_modules/@playwright/test/cli.js", import.meta.url)
  )
  const configPath = path.join(temporaryRoot, "playwright.config.mjs")
  const outputPath = path.join(temporaryRoot, "output")
  await writeFile(
    configPath,
    `export default {
    testDir: ${JSON.stringify(testDir)}, testMatch: "*.live.spec.ts", reporter: "list",
    workers: 1, retries: 0, preserveOutput: "never", outputDir: ${JSON.stringify(outputPath)},
    use: { trace: "off", screenshot: "off", video: "off" },
    projects: [{ name: "desktop" }, { name: "mobile" }, { name: "private-project" }]
  }`
  )
  const fixtureImport = `
    import { EventEmitter } from "node:events";
    import { test as base } from ${JSON.stringify(fileURLToPath(fixtureUrl))};
    import { reportLiveHttpStatus } from ${JSON.stringify(fileURLToPath(new URL("./http-status-diagnostic.ts", import.meta.url)))};
    const test = base.extend({ page: async ({}, use) => { const page = new EventEmitter(); page.currentUrl = "https://private.invalid/reset-password?token=private-token#private-fragment"; page.url = () => page.currentUrl; await use(page); } });
  `
  await writeFile(
    path.join(testDir, "password-reset.live.spec.ts"),
    `${fixtureImport}
    test(${JSON.stringify(resetTitle)}, async ({ page }, testInfo) => {
      process.stdout.write("private-body https://private.invalid/?token=private-token\\n");
      process.stderr.write("private-credential private-browser-state\\n");
      reportLiveHttpStatus(testInfo.project.name, "password-reset-replay", 429);
      page.emit("pageerror", new TypeError("private-message"));
      page.emit("pageerror", new TypeError("private-message"));
      page.currentUrl = "https://private.invalid/dashboard?token=private-token";
      page.emit("pageerror", Object.assign(new Error("private-message"), { name: "SecurityError" }));
      page.currentUrl = "private-invalid-url";
      page.emit("pageerror", Object.assign(new Error("private-message"), { name: "private-name" }));
    });
    test("private-title", async ({ page }) => { page.emit("pageerror", new RangeError("private-message")); });
    test("no page errors", async () => {});
  `
  )
  await writeFile(
    path.join(testDir, "other.live.spec.ts"),
    `${fixtureImport}
    test(${JSON.stringify(resetTitle)}, async ({ page }) => { page.emit("pageerror", new RangeError("private-message")); });
  `
  )
  const result = spawnSync(process.execPath, [cliPath, "test", "--config", configPath], {
    encoding: "utf8",
    timeout: 30_000,
    env: {
      ...process.env,
      FORCE_COLOR: "0",
      TEST_PASSWORD: freshPassword(),
      LIVE_MAILPIT_URL: "http://127.0.0.1:25000",
    },
  })
  assert.equal(result.status, 1, "the real fixture must retain its hard assertion")
  assert.match(result.stdout, /9 failed/u)
  assert.match(result.stdout, /3 passed/u)
  const records = result.stdout.split("\n").filter((line) => line.startsWith("UE_LIVE_"))
  assert.deepEqual(
    records,
    ["desktop", "mobile"].flatMap((project) => [
      `UE_LIVE_HTTP_STATUS_V1 project=${project} check=password-reset-replay status=429`,
      `UE_LIVE_PAGE_ERROR_V1 project=${project} check=password-reset page=reset-password type=type-error count=2`,
      `UE_LIVE_PAGE_ERROR_V1 project=${project} check=password-reset page=dashboard type=security-error count=1`,
      `UE_LIVE_PAGE_ERROR_V1 project=${project} check=password-reset page=other type=other count=1`,
    ])
  )
  assert.match(result.stdout, /private-message|private-body/u)
  assert.match(result.stderr, /private-credential/u)
  assert.doesNotMatch(result.stderr, /UE_LIVE_/u)
  assert.deepEqual(await readdir(outputPath), [".last-run.json"])

  // Both new diagnostic call sites must preserve their original hard assertions.
  await rm(path.join(testDir, "other.live.spec.ts"))
  await writeFile(
    path.join(testDir, "password-reset.live.spec.ts"),
    `${fixtureImport}
    import { expect } from ${JSON.stringify(fileURLToPath(fixtureUrl))};
    test(${JSON.stringify(resetTitle)}, async ({ page }, testInfo) => {
      const write = process.stdout.write.bind(process.stdout);
      process.stdout.write = (chunk, ...args) => {
        if (typeof chunk === "string" && chunk.startsWith("UE_LIVE_")) throw new Error("synthetic-write-failure");
        return write(chunk, ...args);
      };
      page.emit("pageerror", new Error("private-assertion-canary"));
      reportLiveHttpStatus(testInfo.project.name, "password-reset-replay", 429);
      expect(429, "public replay assertion").toBe(400);
    });
  `
  )
  const writeFailure = spawnSync(process.execPath, [cliPath, "test", "--config", configPath], {
    encoding: "utf8",
    timeout: 30_000,
    env: {
      ...process.env,
      FORCE_COLOR: "0",
      TEST_PASSWORD: freshPassword(),
      LIVE_MAILPIT_URL: "http://127.0.0.1:25000",
    },
  })
  assert.equal(writeFailure.status, 1)
  assert.match(writeFailure.stdout, /3 failed/u)
  assert.match(writeFailure.stdout, /public replay assertion/u)
  assert.match(writeFailure.stdout, /private-assertion-canary/u)
  assert.doesNotMatch(writeFailure.stdout + writeFailure.stderr, /Error: synthetic-write-failure/u)
})

test("page error diagnostics cannot replace an assertion when stdout writing fails", () => {
  assert.equal(
    reportInChild(`
    process.stdout.write = () => { throw new Error("synthetic-write-failure") };
    reportLivePageErrors("desktop", "password-reset", [new Error("private-message")]);
  `),
    ""
  )
})
