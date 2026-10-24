import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
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
      `import assert from "node:assert/strict";\nimport * as liveUiDiagnostics from ${JSON.stringify(helperUrl.href)};\nimport { ${helperExports} } from ${JSON.stringify(helperUrl.href)};\n${calls}`,
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

function assertNoPrivateDiagnosticInspection(source) {
  const inspectionSource = source
    .replaceAll('"arm-response"', '""')
    .replaceAll('"await-response"', '""')
  assert.doesNotMatch(
    inspectionSource,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\.(?:message|stack|json|text|screenshot|storageState|attach)\s*\(|\b(?:page|browser|context|response|request|URL)\b/u
  )
}

test("UI diagnostic helper cannot inspect the browser, environment, errors, or response bodies", async () => {
  const source = await readFile(helperUrl, "utf8")
  assertNoPrivateDiagnosticInspection(source)
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 1)
})

test("privacy source guard exempts only the two exact finite step literals", () => {
  assert.doesNotThrow(() =>
    assertNoPrivateDiagnosticInspection('const steps = ["arm-response", "await-response"]')
  )
  for (const source of [
    "const response = null",
    "request.method()",
    "browser.newPage()",
    'const step = "other-response"',
    'const step = "await-response-extra"',
    "const step = 'arm-response'",
    '"arm-response"; response.json()',
    '"await-response"; process.env.PRIVATE',
    '"arm-response"; console.log("private")',
    '"await-response"; error.stack()',
  ]) {
    assert.throws(() => assertNoPrivateDiagnosticInspection(source), {
      code: "ERR_ASSERTION",
    })
  }
})

test("reset registration diagnostics expose only finite project-step pairs", async () => {
  const diagnostics = await import(helperUrl.href)
  assert.equal(typeof diagnostics.reportLivePasswordResetRegistrationFailure, "function")
  const output = reportInChild(`
    const report = liveUiDiagnostics.reportLivePasswordResetRegistrationFailure;
    assert.equal(typeof report, "function");
    for (const project of ["desktop", "mobile"]) {
      for (const step of ["arm-response", "click", "await-response"]) {
        report(project, step);
        report(project, step);
      }
    }
  `)
  assert.equal(
    output,
    ["desktop", "mobile"]
      .flatMap((project) =>
        ["arm-response", "click", "await-response"].map(
          (step) => `UE_LIVE_RESET_REGISTRATION_V1 project=${project} step=${step}\n`
        )
      )
      .join("")
  )
})

test("reset registration diagnostics reject malformed values without coercion", async () => {
  const diagnostics = await import(helperUrl.href)
  assert.equal(typeof diagnostics.reportLivePasswordResetRegistrationFailure, "function")
  const output = reportInChild(`
    const report = liveUiDiagnostics.reportLivePasswordResetRegistrationFailure;
    assert.equal(typeof report, "function");
    const privateValue = {
      toString() { throw new Error("private-value-must-not-be-read"); },
      [Symbol.toPrimitive]() { throw new Error("private-coercion"); }
    };
    for (const value of [
      "private-account@example.invalid",
      "click\\nprivate", "await-response\\r",
      "", null, undefined, 17, privateValue
    ]) {
      report(value, "click");
      report("desktop", value);
    }
  `)
  assert.equal(output, "")
})

test("reset registration diagnostic sink failure never escapes", async () => {
  const diagnostics = await import(helperUrl.href)
  assert.equal(typeof diagnostics.reportLivePasswordResetRegistrationFailure, "function")
  const output = reportInChild(`
    const report = liveUiDiagnostics.reportLivePasswordResetRegistrationFailure;
    assert.equal(typeof report, "function");
    const originalWrite = process.stdout.write;
    process.stdout.write = () => { throw new Error("private-sink-error"); };
    try {
      assert.doesNotThrow(() => report("desktop", "click"));
    } finally {
      process.stdout.write = originalWrite;
    }
  `)
  assert.equal(output, "")
})

const registrationActionUrl = new URL("./password-reset-registration-action.ts", import.meta.url)

function registrationActionInChild(calls) {
  assert.ok(existsSync(registrationActionUrl), "the registration action helper must exist")
  return reportInChild(`
    const actionModule = await import(${JSON.stringify(registrationActionUrl.href)});
    const run = actionModule.runPasswordResetRegistrationAction;
    const report = liveUiDiagnostics.reportLivePasswordResetRegistrationFailure;
    assert.equal(typeof run, "function");
    assert.equal(typeof report, "function");
    ${calls}
  `)
}

for (const failedStep of ["arm-response", "click", "await-response"]) {
  test(`reset registration preserves the original ${failedStep} failure`, () => {
    const output = registrationActionInChild(`
      const failedStep = ${JSON.stringify(failedStep)};
      const original = new Error("private-message private-token private-account");
      Object.defineProperty(original, "stack", {
        get() { throw new Error("private-stack-must-not-be-read"); }
      });
      const events = [];
      const result = run(
        () => {
          events.push("arm");
          if (failedStep === "arm-response") throw original;
          return failedStep === "await-response"
            ? Promise.reject(original)
            : Promise.resolve({ status: 200 });
        },
        async () => {
          events.push("click");
          if (failedStep === "click") throw original;
        },
        (...args) => {
          assert.deepEqual(args, [failedStep]);
          events.push("report");
          report("desktop", ...args);
        }
      );
      await assert.rejects(result, (error) => error === original);
      assert.deepEqual(events, failedStep === "arm-response"
        ? ["arm", "report"] : ["arm", "click", "report"]);
    `)
    assert.equal(
      output,
      `UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=${failedStep}\n`
    )
  })
}

test("reset registration handles the abandoned waiter after click rejection", () => {
  const output = registrationActionInChild(`
    const clickError = new Error("private-click");
    const lateError = new Error("private-late-response");
    let rejectWaiter;
    const waiter = new Promise((_resolve, reject) => { rejectWaiter = reject; });
    const unhandled = [];
    const onUnhandled = (error) => { unhandled.push(error); };
    process.on("unhandledRejection", onUnhandled);
    try {
      await assert.rejects(
        run(() => waiter, async () => { throw clickError; },
          (step) => report("mobile", step)),
        (error) => error === clickError
      );
      rejectWaiter(lateError);
      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual(unhandled, []);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  `)
  assert.equal(output, "UE_LIVE_RESET_REGISTRATION_V1 project=mobile step=click\n")
})

test("reset registration handles early waiter rejection during a pending click", () => {
  const output = registrationActionInChild(`
    const original = new Error("private-early-response");
    let finishClick;
    let rejectWaiter;
    const waiter = new Promise((_resolve, reject) => { rejectWaiter = reject; });
    const click = new Promise((resolve) => { finishClick = resolve; });
    const unhandled = [];
    const onUnhandled = (error) => { unhandled.push(error); };
    process.on("unhandledRejection", onUnhandled);
    try {
      const result = run(() => waiter, () => click,
        (step) => report("desktop", step));
      const rejection = assert.rejects(result, (error) => error === original);
      rejectWaiter(original);
      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual(unhandled, []);
      finishClick();
      await rejection;
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  `)
  assert.equal(output, "UE_LIVE_RESET_REGISTRATION_V1 project=desktop step=await-response\n")
})

test("reset registration keeps success identity and waits for click completion", () => {
  const output = registrationActionInChild(`
    const response = { status: 200 };
    const events = [];
    let finishClick;
    let finished = false;
    let reports = 0;
    const pending = run(
      () => { events.push("arm"); return Promise.resolve(response); },
      () => {
        events.push("click");
        return new Promise((resolve) => { finishClick = resolve; });
      },
      () => { reports += 1; }
    ).then((value) => { finished = true; return value; });
    await Promise.resolve();
    assert.equal(finished, false);
    assert.deepEqual(events, ["arm", "click"]);
    finishClick();
    assert.equal(await pending, response);
    assert.equal(reports, 0);
  `)
  assert.equal(output, "")
})

test("reset registration reporter failure cannot replace the original error", () => {
  const output = registrationActionInChild(`
    const original = new Error("private-original");
    await assert.rejects(
      run(
        () => Promise.resolve({ status: 200 }),
        async () => { throw original; },
        () => { throw new Error("private-reporter"); }
      ),
      (error) => error === original
    );
  `)
  assert.equal(output, "")
})

const resetV2Prefix = "UE_LIVE_RESET_REGISTRATION_V2 "
const resetV2Expected = {
  project: "mobile",
  step: "await-response",
  errorCategory: "timeout",
  snapshot: "available",
  hydrated: true,
  formPresent: true,
  formInvalid: false,
  formError: false,
  submitPresent: true,
  submitDisabled: false,
  submitBusy: false,
  csrfRequested: true,
  csrfResponse: "success",
  csrfFailed: false,
}
function resetV2Records(output) {
  return output
    .trimEnd()
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      assert.ok(line.startsWith(resetV2Prefix), "only closed V2 frames may be emitted")
      return JSON.parse(line.slice(resetV2Prefix.length))
    })
}
function resetV2InChild(calls) {
  return registrationActionInChild(`
    const create = actionModule.createPasswordResetRegistrationDiagnostics;
    assert.equal(typeof create, "function", "bounded registration V2 factory is missing");
    const { EventEmitter } = await import("node:events");
    const { JSDOM } = await import("jsdom");
    class ObservationPage extends EventEmitter {
      constructor() {
        super();
        this.dom = new JSDOM(
          '<form><input required value="present"><button id="register-submit" type="submit">Submit</button></form>',
          { url: "https://owned.invalid/register", runScripts: "outside-only" }
        );
        this.dom.window.__APP_HYDRATED = true;
        this.evaluations = 0;
      }
      async evaluate(callback) {
        this.evaluations += 1;
        return this.dom.window.eval("(" + callback.toString() + ")()");
      }
    }
    function request(url = "https://owned.invalid/api/v1/auth/csrf-cookie", method = "GET") {
      return {
        url: () => url, method: () => method,
        postData() { throw new Error("private-body-must-not-be-read"); },
        headers() { throw new Error("private-cookie-must-not-be-read"); },
      };
    }
    function response(req, status = 204) {
      return {
        request: () => req, status: () => status,
        url() { throw new Error("private-response-url-must-not-be-read"); },
        body() { throw new Error("private-body-must-not-be-read"); },
        headers() { throw new Error("private-cookie-must-not-be-read"); },
      };
    }
    function privateError(name = "TimeoutError") {
      return {
        name,
        get message() { throw new Error("private-message-must-not-be-read"); },
        get stack() { throw new Error("private-stack-must-not-be-read"); },
        get constructor() { throw new Error("private-constructor-must-not-be-read"); },
        toString() { throw new Error("private-error-must-not-be-coerced"); },
      };
    }
    ${calls}
  `)
}
test("reset V2 optional observer preserves failure identity and closes on every path", () => {
  const output = registrationActionInChild(`
    for (const outcome of ["success", "arm-response", "click", "await-response"]) {
      const original = new Error("private-original");
      const value = { status: 200 };
      const events = [];
      const diagnostic = {
        async reportFailure(step, error) {
          assert.equal(step, outcome);
          assert.equal(error, original);
          events.push("v2");
          throw new Error("private-diagnostic-error");
        },
        dispose() { events.push("dispose"); throw new Error("private-dispose-error"); },
      };
      const result = run(
        () => {
          if (outcome === "arm-response") throw original;
          return outcome === "await-response" ? Promise.reject(original) : Promise.resolve(value);
        },
        async () => { if (outcome === "click") throw original; },
        (...args) => {
          assert.deepEqual(args, [outcome]);
          events.push("v1");
          throw new Error("private-v1-error");
        },
        diagnostic
      );
      if (outcome === "success") assert.equal(await result, value);
      else await assert.rejects(result, error => error === original);
      assert.deepEqual(events, outcome === "success" ? ["dispose"] : ["v1", "v2", "dispose"]);
    }
  `)
  assert.equal(output, "")
})
test("reset V2 reports fixed failure state and owned CSRF observation without private data", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    const diagnostic = create(page, "mobile", "https://owned.invalid", performance.now() + 1000);
    const req = request();
    page.emit("request", req);
    page.emit("response", response(req));
    const original = privateError();
    await assert.rejects(
      run(() => Promise.reject(original), async () => {}, () => {}, diagnostic),
      error => error === original
    );
    assert.equal(page.evaluations, 1);
    for (const event of ["request", "response", "requestfailed"]) assert.equal(page.listenerCount(event), 0);
    page.dom.window.close();
  `)
  assert.deepEqual(resetV2Records(output), [resetV2Expected])
  assert.doesNotMatch(output, /private|https?:|cookie|present|Submit/u)
})
test("reset V2 distinguishes form state and aggregates only matching CSRF response classes", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    page.dom.window.__APP_HYDRATED = false;
    page.dom.window.document.querySelector("input").value = "";
    page.dom.window.document.querySelector("form").insertAdjacentHTML("beforeend", '<div role="alert">private-form-error</div>');
    const button = page.dom.window.document.getElementById("register-submit");
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    const diagnostic = create(page, "desktop", "https://owned.invalid", performance.now() + 1000);
    const first = request();
    const second = request();
    page.emit("request", first);
    page.emit("response", response(first, 200));
    page.emit("request", second);
    page.emit("response", response(second, 503));
    page.emit("requestfailed", second);
    await assert.rejects(run(() => Promise.reject(privateError("TypeError")), async () => {}, () => {}, diagnostic));
    page.dom.window.close();
  `)
  assert.deepEqual(resetV2Records(output), [
    {
      ...resetV2Expected,
      project: "desktop",
      errorCategory: "type-error",
      hydrated: false,
      formInvalid: true,
      formError: true,
      submitDisabled: true,
      submitBusy: true,
      csrfResponse: "mixed",
      csrfFailed: true,
    },
  ])
  assert.doesNotMatch(output, /private-form-error|503/u)
})
test("reset V2 ignores foreign, malformed and untracked CSRF events", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    const diagnostic = create(page, "mobile", "https://owned.invalid", performance.now() + 1000);
    const candidates = [
      request("https://foreign.invalid/api/v1/auth/csrf-cookie"),
      request("https://owned.invalid/api/v1/auth/csrf-cookie?private"),
      request("https://owned.invalid/api/v1/auth/csrf-cookie#private"),
      request("https://owned.invalid/api/v1/auth/csrf-cookie", "POST"),
      request("https://owned.invalid/api/v1/auth/csrf-cookie-extra"),
      request("https://owned.invalid/api/v1/auth/register"),
      request({ toString() { throw new Error("private-url-coercion"); } }),
      { url() { throw new Error("private-url"); }, method: () => "GET" },
    ];
    for (const req of candidates) {
      assert.doesNotThrow(() => page.emit("request", req));
      assert.doesNotThrow(() => page.emit("response", response(req)));
      assert.doesNotThrow(() => page.emit("requestfailed", req));
    }
    page.emit("response", response(request()));
    page.emit("requestfailed", request());
    const original = privateError("private-name");
    Object.defineProperty(original, "name", { get() { throw new Error("private-name"); } });
    await assert.rejects(run(() => Promise.reject(original), async () => {}, () => {}, diagnostic),
      error => error === original);
    page.dom.window.close();
  `)
  assert.deepEqual(resetV2Records(output), [
    {
      ...resetV2Expected,
      errorCategory: "other",
      csrfRequested: false,
      csrfResponse: "not-observed",
    },
  ])
})
test("reset V2 has no success snapshot and removes listeners after success", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    const diagnostic = create(page, "desktop", "https://owned.invalid", performance.now() + 1000);
    const value = { status: 201 };
    assert.equal(await run(() => Promise.resolve(value), async () => {}, () => {}, diagnostic), value);
    assert.equal(page.evaluations, 0);
    for (const event of ["request", "response", "requestfailed"]) assert.equal(page.listenerCount(event), 0);
    page.dom.window.close();
  `)
  assert.equal(output, "")
})
test("reset V2 expired snapshot budget never evaluates the page or replaces the error", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    const diagnostic = create(page, "mobile", "https://owned.invalid", performance.now() - 1);
    const original = privateError("AbortError");
    await assert.rejects(run(() => Promise.reject(original), async () => {}, () => {}, diagnostic),
      error => error === original);
    assert.equal(page.evaluations, 0);
    page.dom.window.close();
  `)
  assert.deepEqual(resetV2Records(output), [
    {
      ...resetV2Expected,
      errorCategory: "abort",
      snapshot: "unavailable",
      hydrated: false,
      formPresent: false,
      submitPresent: false,
      csrfRequested: false,
      csrfResponse: "not-observed",
    },
  ])
})
test("reset V2 pending snapshot stays bounded and owns late rejection", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    let rejectSnapshot;
    page.evaluate = () => new Promise((_resolve, reject) => { rejectSnapshot = reject; });
    const diagnostic = create(page, "mobile", "https://owned.invalid", performance.now() + 10);
    const original = privateError();
    const unhandled = [];
    const onUnhandled = error => unhandled.push(error);
    process.on("unhandledRejection", onUnhandled);
    let guard;
    try {
      await Promise.race([
        assert.rejects(run(() => Promise.reject(original), async () => {}, () => {}, diagnostic),
          error => error === original),
        new Promise((_resolve, reject) => { guard = setTimeout(() => reject(new Error("diagnostic exceeded original budget")), 1000); }),
      ]);
      if (rejectSnapshot) rejectSnapshot(new Error("private-late-snapshot"));
      await new Promise(resolve => setImmediate(resolve));
      assert.deepEqual(unhandled, []);
      for (const event of ["request", "response", "requestfailed"]) assert.equal(page.listenerCount(event), 0);
    } finally {
      clearTimeout(guard);
      process.off("unhandledRejection", onUnhandled);
      page.dom.window.close();
    }
  `)
  assert.deepEqual(resetV2Records(output), [
    {
      ...resetV2Expected,
      snapshot: "unavailable",
      hydrated: false,
      formPresent: false,
      submitPresent: false,
      csrfRequested: false,
      csrfResponse: "not-observed",
    },
  ])
})
test("reset V2 rejects untrusted project and step values without coercion", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    const poison = { toString() { throw new Error("private-coercion"); } };
    for (const project of ["private-project", "mobile\\nprivate", poison, null, 1]) {
      const diagnostic = create(page, project, "https://owned.invalid", performance.now() + 1000);
      await diagnostic.reportFailure("await-response", privateError());
      diagnostic.dispose();
    }
    const diagnostic = create(page, "desktop", "https://owned.invalid", performance.now() + 1000);
    for (const step of ["private-step", "click\\nprivate", poison, null, 1]) {
      await diagnostic.reportFailure(step, privateError());
    }
    diagnostic.dispose();
    assert.equal(page.evaluations, 0);
    page.dom.window.close();
  `)
  assert.equal(output, "")
})

test("reset V2 rejects private DOM snapshots and contains sink failure", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    page.evaluate = async () => ({
      hydrated: true, formPresent: true, formInvalid: false, formError: false,
      submitPresent: true, submitDisabled: false, submitBusy: false,
      privateField: "private-input",
    });
    const diagnostic = create(page, "mobile", "https://owned.invalid", performance.now() + 1000);
    const original = privateError();
    await assert.rejects(run(() => Promise.reject(original), async () => {}, () => {}, diagnostic),
      error => error === original);
    const next = create(page, "desktop", "https://owned.invalid", performance.now() + 1000);
    const originalWrite = process.stdout.write;
    process.stdout.write = () => { throw new Error("private-sink"); };
    try {
      await assert.rejects(run(() => Promise.reject(original), async () => {}, () => {}, next),
        error => error === original);
    } finally {
      process.stdout.write = originalWrite;
    }
    for (const event of ["request", "response", "requestfailed"]) assert.equal(page.listenerCount(event), 0);
    page.dom.window.close();
  `)
  assert.deepEqual(resetV2Records(output), [
    {
      ...resetV2Expected,
      snapshot: "unavailable",
      hydrated: false,
      formPresent: false,
      submitPresent: false,
      csrfRequested: false,
      csrfResponse: "not-observed",
    },
  ])
})
test("reset V2 diagnostic frames are deduplicated and capped", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    const diagnostic = create(page, "mobile", "https://owned.invalid", performance.now() + 1000);
    for (const name of ["TimeoutError", "AbortError", "TypeError", "TargetClosedError", "Error", "Other"]) {
      await diagnostic.reportFailure("await-response", privateError(name));
      await diagnostic.reportFailure("await-response", privateError(name));
    }
    await diagnostic.reportFailure("click", privateError());
    diagnostic.dispose();
    page.dom.window.close();
  `)
  assert.deepEqual(
    resetV2Records(output).map((record) => record.errorCategory),
    ["timeout", "abort", "type-error", "target-closed", "error", "other"]
  )
})

test("reset V2 caps snapshot scheduling at 250ms with a long remaining deadline", () => {
  const output = resetV2InChild(`
    const page = new ObservationPage();
    page.evaluate = () => new Promise(() => {});
    const diagnostic = create(page, "mobile", "https://owned.invalid", performance.now() + 60_000);
    const original = privateError();
    const requested = [];
    const cleared = [];
    const handle = {};
    let expire;
    const originalSetTimeout = globalThis.setTimeout;
    const originalClearTimeout = globalThis.clearTimeout;
    globalThis.setTimeout = (callback, delay) => {
      requested.push(delay);
      expire = callback;
      return handle;
    };
    globalThis.clearTimeout = timer => { cleared.push(timer); };
    try {
      const rejected = assert.rejects(
        run(() => Promise.reject(original), async () => {}, () => {}, diagnostic),
        error => error === original
      );
      // Drain pending microtasks without advancing a real timeout clock.
      await new Promise(resolve => setImmediate(resolve));
      assert.deepEqual(requested, [250]);
      assert.equal(typeof expire, "function");
      expire();
      await rejected;
      assert.deepEqual(cleared, [handle]);
      for (const event of ["request", "response", "requestfailed"]) {
        assert.equal(page.listenerCount(event), 0);
      }
    } finally {
      globalThis.setTimeout = originalSetTimeout;
      globalThis.clearTimeout = originalClearTimeout;
      page.dom.window.close();
    }
  `)
  assert.deepEqual(resetV2Records(output), [
    {
      ...resetV2Expected,
      snapshot: "unavailable",
      hydrated: false,
      formPresent: false,
      submitPresent: false,
      csrfRequested: false,
      csrfResponse: "not-observed",
    },
  ])
})
