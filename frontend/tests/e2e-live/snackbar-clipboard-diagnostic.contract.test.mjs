import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import test from "node:test"

const helper = new URL("./snackbar-clipboard-diagnostic.ts", import.meta.url)
const base = {
  project: "desktop",
  permission: "prompt",
  secure: true,
  focused: false,
  clipboard: true,
  hydrated: true,
  enabled: true,
  alerts: 0,
}

function report(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { reportSnackbarClipboardFailure } from ${JSON.stringify(helper.href)};
const base = ${JSON.stringify(base)};
${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0, result.stderr)
  assert.equal(result.stderr, "")
  return result.stdout
}

test("clipboard diagnostic emits only finite fields", () => {
  assert.equal(
    report("reportSnackbarClipboardFailure(base)"),
    "UE_LIVE_SNACKBAR_CLIPBOARD_V1 project=desktop permission=prompt " +
      "secure=true focused=false clipboard=true hydrated=true enabled=true alerts=0\n"
  )
  const output = report(`reportSnackbarClipboardFailure({
    ...base, permission: "private", secure: "private", alerts: 10000,
    payload: "private", error: new Error("private")
  })`)
  assert.match(output, /permission=unavailable secure=unknown/u)
  assert.match(output, /alerts=999\n$/u)
  assert.doesNotMatch(output, /private/u)
})

test("clipboard diagnostic ignores invalid identity and throwing getters", () => {
  assert.equal(
    report(`reportSnackbarClipboardFailure({ ...base, project: "private" });
reportSnackbarClipboardFailure({ get project() { throw Error("private") } });
reportSnackbarClipboardFailure(null);`),
    ""
  )
})

test("clipboard diagnostic deduplicates and bounds records", () => {
  const output = report(`for (let alerts = 0; alerts < 8; alerts++) {
    reportSnackbarClipboardFailure({ ...base, alerts });
    reportSnackbarClipboardFailure({ ...base, alerts });
  }`)
  assert.equal(output.trim().split("\n").length, 4)
  assert.match(output, /alerts=3\n$/u)
})

test("diagnostic output failure cannot replace the assertion", () => {
  assert.equal(
    report(`process.stdout.write = () => { throw Error("private") };
reportSnackbarClipboardFailure(base);`),
    ""
  )
})

test("sampling is bounded and never invokes clipboard or changes permissions", async () => {
  const source = await readFile(helper, "utf8")
  assert.match(source, /permissions\.query/u)
  assert.doesNotMatch(source, /\.(?:readText|writeText|read|write|grantPermissions|clearPermissions)\(/u)
  assert.match(source, /setTimeout/u)
  const spec = await readFile(new URL("./settings-radio-focus.live.spec.ts", import.meta.url), "utf8")
  assert.equal(
    spec.split("\n")[443],
    'test("Settings Snackbar content receives a real pointer click on Profile", async ({ page }) => {'
  )
  assert.match(spec, /catch \(error\) \{[\s\S]*sampleSnackbarClipboardFailure[\s\S]*throw error/u)
  assert.match(spec, /await expect\(alert\)\.toHaveCount\(1\)/u)
})

test("sampling reports unavailable observations without leaking errors", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { sampleSnackbarClipboardFailure } from ${JSON.stringify(helper.href)};
await sampleSnackbarClipboardFailure(
  { evaluate: async () => { throw Error("private") } },
  { isEnabled: async () => { throw Error("private") } },
  { count: async () => { throw Error("private") } },
  "mobile"
);`,
    ],
    { encoding: "utf8", timeout: 3000 }
  )
  assert.equal(result.status, 0, result.stderr)
  assert.equal(result.stderr, "")
  assert.equal(
    result.stdout,
    "UE_LIVE_SNACKBAR_CLIPBOARD_V1 project=mobile permission=unavailable " +
      "secure=unknown focused=unknown clipboard=unknown hydrated=unknown " +
      "enabled=unknown alerts=unknown\n"
  )
})

test("sampling deadline does not wait for hung browser observations", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { sampleSnackbarClipboardFailure } from ${JSON.stringify(helper.href)};
await sampleSnackbarClipboardFailure(
  { evaluate: () => new Promise(() => {}) },
  { isEnabled: () => new Promise(() => {}) },
  { count: () => new Promise(() => {}) },
  "desktop"
);`,
    ],
    { encoding: "utf8", timeout: 3000 }
  )
  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /permission=unavailable/u)
  assert.match(result.stdout, /alerts=unknown\n$/u)
})
