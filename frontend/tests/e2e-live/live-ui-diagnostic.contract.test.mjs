import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import process from "node:process"
import test from "node:test"
import { URL } from "node:url"

const helperUrl = new URL("./live-ui-diagnostic.ts", import.meta.url)

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { reportLiveActivityGeometry, reportLiveAdminQueueState, reportLiveAxeColorContrast } from ${JSON.stringify(helperUrl.href)};\n${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0, "the diagnostic helper must not throw")
  assert.equal(result.stderr, "", "the helper writes only its bounded stdout protocol")
  return result.stdout
}

test("UI diagnostics emit only fixed live project/period labels and bounded measurements", () => {
  const output = reportInChild(`
    reportLiveAdminQueueState("desktop", 200, true, 1005, true, false, true, true, 1001);
    reportLiveActivityGeometry("mobile", "30-day", true, true, -1000000, 25, -12, 1000001);
  `)

  assert.equal(
    output,
    "UE_LIVE_ADMIN_QUEUE_V1 project=desktop status=200 items_array=true items_count=999 total_valid=true table_visible=false progressbar_visible=true alert_visible=true row_count=999\n" +
      "UE_LIVE_ACTIVITY_GEOMETRY_V1 project=mobile period=30-day indicator_present=true radio_present=true dx_milli=-999999 dy_milli=25 dw_milli=-12 dh_milli=999999\n"
  )
})

test("UI contrast diagnostics emit only bounded route-bound RGB and milli-ratio values", () => {
  assert.equal(
    reportInChild(`
      reportLiveAxeColorContrast("desktop", "settings", "#AABBCC", "#000000", 2.85);
      reportLiveAxeColorContrast("mobile", "dashboard", "#ffffff", "#000000", 21);
    `),
    "UE_LIVE_A11Y_CONTRAST_V1 project=desktop route=settings fg=#aabbcc bg=#000000 ratio_milli=2850\n" +
      "UE_LIVE_A11Y_CONTRAST_V1 project=mobile route=dashboard fg=#ffffff bg=#000000 ratio_milli=21000\n"
  )
})

test("UI contrast diagnostics reject untrusted labels, malformed colors, and private values", () => {
  assert.equal(
    reportInChild(`
      const privateValue = { toString() { throw new Error("private-value") } };
      reportLiveAxeColorContrast("desktop\\nprivate", "settings", "#ffffff", "#000000", 4.5);
      reportLiveAxeColorContrast("desktop", "private-route", "#ffffff", "#000000", 4.5);
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff\\nprivate", "#000000", 4.5);
      reportLiveAxeColorContrast("desktop", "settings", "ffffff", "#000000", 4.5);
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", "4.5");
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", privateValue);
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", NaN);
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", Infinity);
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", 21.001);
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", -0.001);
    `),
    ""
  )
})

test("UI contrast diagnostics deduplicate and cap at four findings per project-route", () => {
  const output = reportInChild(`
    for (let ratio = 0; ratio < 8; ratio += 1) {
      reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", ratio);
    }
    reportLiveAxeColorContrast("desktop", "settings", "#ffffff", "#000000", 0);
    reportLiveAxeColorContrast("desktop", "dashboard", "#ffffff", "#000000", 1);
    reportLiveAxeColorContrast("mobile", "settings", "#ffffff", "#000000", 1);
  `)
  const lines = output.trimEnd().split("\n")
  assert.equal(lines.length, 6)
  assert.equal(
    lines
      .slice(0, 4)
      .map((line) => line.match(/ratio_milli=(\d+)/u)?.[1])
      .join(","),
    "0,1000,2000,3000"
  )
  assert.match(lines[4], /project=desktop route=dashboard/u)
  assert.match(lines[5], /project=mobile route=settings/u)
})

test("UI diagnostics reject untrusted labels, noninteger values, and private objects without coercion", () => {
  assert.equal(
    reportInChild(`
      const privateValue = { toString() { throw new Error("private-value") } };
      reportLiveAdminQueueState("desktop\\nprivate", 200, true, 1, true, true, false, false, 1);
      reportLiveAdminQueueState("desktop", "200\\nprivate", true, 1, true, true, false, false, 1);
      reportLiveAdminQueueState("desktop", 200, true, privateValue, true, true, false, false, 1);
      reportLiveAdminQueueState("desktop", 200, true, 1, true, true, false, false, -1);
      reportLiveActivityGeometry("desktop", "30-day\\nprivate", true, true, 0, 0, 0, 0);
      reportLiveActivityGeometry("desktop", "30-day", true, true, NaN, 0, 0, 0);
      reportLiveActivityGeometry("desktop", "30-day", true, true, 0.5, 0, 0, 0);
      reportLiveActivityGeometry(privateValue, "30-day", true, true, 0, 0, 0, 0);
    `),
    ""
  )
})

test("UI diagnostic records are deduplicated and capped per worker process", () => {
  const output = reportInChild(`
    for (let status = 100; status < 200; status += 1) {
      reportLiveAdminQueueState("desktop", status, true, status, true, true, false, false, status);
    }
    reportLiveActivityGeometry("mobile", "90-day", true, true, 1, 2, 3, 4);
    reportLiveActivityGeometry("mobile", "90-day", true, true, 1, 2, 3, 4);
  `)
  const lines = output.trimEnd().split("\n")
  assert.equal(lines.length, 16)
  assert.equal(
    lines[0],
    "UE_LIVE_ADMIN_QUEUE_V1 project=desktop status=100 items_array=true items_count=100 total_valid=true table_visible=true progressbar_visible=false alert_visible=false row_count=100"
  )
  assert.equal(
    lines.at(-1),
    "UE_LIVE_ADMIN_QUEUE_V1 project=desktop status=115 items_array=true items_count=115 total_valid=true table_visible=true progressbar_visible=false alert_visible=false row_count=115"
  )
})

test("UI diagnostic helper cannot inspect the browser, environment, errors, or response bodies", async () => {
  const source = await readFile(helperUrl, "utf8")
  assert.doesNotMatch(
    source,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\.(?:message|stack|json|text|screenshot|storageState|attach)\s*\(|\b(?:page|browser|context|response|request|URL)\b/u
  )
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 1)
})
