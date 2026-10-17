import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import process from "node:process"
import test from "node:test"
import { URL } from "node:url"

const helperUrl = new URL("./live-ui-diagnostic.ts", import.meta.url)
const helperExports = [
  "reportLiveActivityGeometry",
  "reportLiveAdminQueueState",
  "reportLiveAxeColorContrast",
  "reportLiveAxePaintState",
  "reportLiveA11yPhaseState",
  "reportLiveFooterGeometry",
].join(", ")

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { ${helperExports} } from ${JSON.stringify(helperUrl.href)};\n${calls}`,
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

test("UI phase diagnostics emit one bounded before and after page state per route", () => {
  const output = reportInChild(
    'reportLiveA11yPhaseState("desktop", "settings", "before_axe", true, 0.9, 1, 0.8, "opacity", 2);' +
      'reportLiveA11yPhaseState("desktop", "settings", "before_axe", true, 0.7, 0.8, 0.6, "mixed", 3);' +
      'reportLiveA11yPhaseState("desktop", "settings", "after_axe", true, 1, 1, 1, "none", 0);'
  )
  assert.equal(
    output,
    "UE_LIVE_A11Y_PHASE_V1 project=desktop route=settings phase=before_axe " +
      "page_ready=true page_opacity_milli=900 root_opacity_milli=1000 " +
      "layout_opacity_milli=800 animation=opacity active_animations=2\n" +
      "UE_LIVE_A11Y_PHASE_V1 project=desktop route=settings phase=after_axe " +
      "page_ready=true page_opacity_milli=1000 root_opacity_milli=1000 " +
      "layout_opacity_milli=1000 animation=none active_animations=0\n"
  )
})
test("UI paint diagnostics emit bounded opacity, text-color, and animation tags", () => {
  const output = reportInChild(`
    reportLiveAxePaintState(
      "desktop", "settings", "#8691a3", "#f8fafc", 3.04, "#8691a3", "opaque", 1,
      0.8, 0.75, "multiple", true, 0.9, 0.8, "opacity", 2
    );
  `)
  assert.equal(
    output,
    "UE_LIVE_A11Y_PAINT_V1 project=desktop route=settings axe_fg=#8691a3 " +
      "axe_bg=#f8fafc ratio_milli=3040 css_fg=#8691a3 text_color=opaque " +
      "css_alpha_milli=1000 node_opacity_milli=800 " +
      "ancestor_opacity_milli=750 opacity_tag=multiple page_ready=true page_opacity_milli=900 " +
      "layout_opacity_milli=800 animation=opacity active_animations=2\n"
  )
})

test("UI paint diagnostics reject private labels, tags, and out-of-range measurements", () => {
  assert.equal(
    reportInChild(`
      const privateValue = { toString() { throw new Error("private-value") } };
      reportLiveAxePaintState(
        "private", "settings", "#ffffff", "#000000", 4.5, "#ffffff", "opaque", 1,
        1, 1, "none", true, 1, 1, "none", 0
      );
      reportLiveAxePaintState(
        "desktop", "private", "#ffffff", "#000000", 4.5, "#ffffff", "opaque", 1,
        1, 1, "none", true, 1, 1, "none", 0
      );
      reportLiveAxePaintState(
        "desktop", "settings", "#ffffff", "#000000", 4.5, "#ffffff", "private-tag", 1,
        1, 1, "none", true, 1, 1, "none", 0
      );
      reportLiveAxePaintState(
        "desktop", "settings", "#ffffff", "#000000", 4.5, "#ffffff", "opaque", 1.001,
        1, 1, "none", true, 1, 1, "none", 0
      );
      reportLiveAxePaintState(
        "desktop", "settings", "#ffffff", "#000000", 4.5, "#ffffff", "opaque", 1,
        1, 1, "none", true, 1, 1, privateValue, 0
      );
      reportLiveA11yPhaseState("private", "settings", "before_axe", true, 1, 1, 1, "none", 0);
      reportLiveA11yPhaseState("desktop", "settings", "private", true, 1, 1, 1, "none", 0);
      reportLiveA11yPhaseState("desktop", "settings", "after_axe", true, 1.001, 1, 1, "none", 0);
      reportLiveFooterGeometry(
        "desktop", 390, 844, 0, 844, 390, 390, 0, 390, 780, 844, 390, false, 0, 0,
        false, 0, 0, 0, 0, 0
      );
      reportLiveFooterGeometry(
        "desktop", 390, 844, 390, 844, 390, 390, 0, 390, 780, 844, 390, false, 0, 0,
        false, 0, 1, 0, 0, 0
      );
      reportLiveFooterGeometry(
        "desktop", 390, 844, 390, 844, 390, 390, 0, 390, 780, 844, 390, false, 0, 0,
        false, 0, 9000, 0, 0, 0
      );
    `),
    ""
  )
})

test("UI footer diagnostics emit bounded geometry", () => {
  assert.equal(
    reportInChild(`
      reportLiveFooterGeometry(
        "mobile", 390, 844, 390, 844, 390, 390, 0, 390, 780, 844, 390, false, 0, 0,
        false, 0, 0, 0, 0, 0
      );
      reportLiveFooterGeometry(
        "desktop", 390, 844, 390, 844, 390, 412, -11.25, 400, 780, 844, 411.25,
        true, -11.25, 0, true, 2, -12, 412, 0, 800
      );
    `),
    "UE_LIVE_FOOTER_GEOM_V1 project=mobile req_w_milli=390000 req_h_milli=844000 " +
      "inner_w_milli=390000 inner_h_milli=844000 client_w_milli=390000 scroll_w_milli=390000 " +
      "nav_left_milli=0 nav_right_milli=390000 nav_top_milli=780000 nav_bottom_milli=844000 " +
      "nav_width_milli=390000 nav_transform_present=false nav_tx_milli=0 nav_ty_milli=0 " +
      "fixed_cb_found=false fixed_cb_depth=0 " +
      "cb_left_milli=0 cb_right_milli=0 cb_top_milli=0 cb_bottom_milli=0\n" +
      "UE_LIVE_FOOTER_GEOM_V1 project=desktop req_w_milli=390000 req_h_milli=844000 " +
      "inner_w_milli=390000 inner_h_milli=844000 client_w_milli=390000 scroll_w_milli=412000 " +
      "nav_left_milli=-11250 nav_right_milli=400000 nav_top_milli=780000 nav_bottom_milli=844000 " +
      "nav_width_milli=411250 nav_transform_present=true nav_tx_milli=-11250 nav_ty_milli=0 " +
      "fixed_cb_found=true fixed_cb_depth=2 " +
      "cb_left_milli=-12000 cb_right_milli=412000 cb_top_milli=0 cb_bottom_milli=800000\n"
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
