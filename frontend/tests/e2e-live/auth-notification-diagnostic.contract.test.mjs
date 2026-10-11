import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { readFile } from "node:fs/promises"
import process from "node:process"
import test from "node:test"
import { URL } from "node:url"

const helperUrl = new URL("./auth-notification-diagnostic.ts", import.meta.url)

function reportInChild(calls) {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { reportAuthHttpStatus, reportAuthUiFailure, reportAuthRegistrationFailure } from ${JSON.stringify(helperUrl.href)};\n${calls}`,
    ],
    { encoding: "utf8" }
  )
  assert.equal(result.status, 0, "diagnostics must not throw")
  assert.equal(result.stderr, "", "diagnostics must write only bounded stdout records")
  return result.stdout
}

test("auth UI failure diagnostics emit only fixed categories and bounded state", () => {
  const output = reportInChild(`
    const passwordFailure = { project: "desktop", scenario: "password_current_invalid", status: 400, detail: "Текущий пароль указан неверно", alertCount: 1, alertCountCapped: false, alertVisible: true, currentFieldInvalid: true, loginChallenge: null, pageError: false };
    reportAuthUiFailure(passwordFailure);
    reportAuthUiFailure(passwordFailure);
    reportAuthUiFailure({ project: "desktop", scenario: "password_current_invalid", status: 422, detail: "private detail", alertCount: 0, alertCountCapped: false, alertVisible: false, currentFieldInvalid: false, loginChallenge: null, pageError: false });
    reportAuthUiFailure({ project: "mobile", scenario: "totp_recovery_replay", status: 400, detail: { private: "object" }, alertCount: 8, alertCountCapped: true, alertVisible: true, currentFieldInvalid: null, loginChallenge: true, pageError: true });
    reportAuthUiFailure({ project: "mobile", scenario: "totp_recovery_replay", status: 401, detail: undefined, alertCount: 0, alertCountCapped: false, alertVisible: false, currentFieldInvalid: null, loginChallenge: false, pageError: false });
  `)
  const rows = output
    .trim()
    .split(/\r?\n/u)
    .map((line) => JSON.parse(line.slice("AUTH_UI_DIAG ".length)))
  assert.deepEqual(rows, [
    {
      schema: 1,
      project: "desktop",
      scenario: "password_current_invalid",
      status: 400,
      detailClass: "expected",
      alertCount: 1,
      alertCountCapped: false,
      alertVisible: true,
      currentFieldInvalid: true,
      loginChallenge: null,
      pageError: false,
    },
    {
      schema: 1,
      project: "desktop",
      scenario: "password_current_invalid",
      status: 422,
      detailClass: "other-string",
      alertCount: 0,
      alertCountCapped: false,
      alertVisible: false,
      currentFieldInvalid: false,
      loginChallenge: null,
      pageError: false,
    },
    {
      schema: 1,
      project: "mobile",
      scenario: "totp_recovery_replay",
      status: 400,
      detailClass: "non-string",
      alertCount: 8,
      alertCountCapped: true,
      alertVisible: true,
      currentFieldInvalid: null,
      loginChallenge: true,
      pageError: true,
    },
    {
      schema: 1,
      project: "mobile",
      scenario: "totp_recovery_replay",
      status: 401,
      detailClass: "missing",
      alertCount: 0,
      alertCountCapped: false,
      alertVisible: false,
      currentFieldInvalid: null,
      loginChallenge: false,
      pageError: false,
    },
  ])
  assert.doesNotMatch(output, /private detail|private|Текущий пароль/u)
})

test("auth UI diagnostics reject malformed state without coercion", () => {
  assert.equal(
    reportInChild(`
      const privateValue = { toString() { throw new Error("private") } };
      reportAuthUiFailure(null);
      reportAuthUiFailure({ project: privateValue, scenario: "password_current_invalid", status: 400, detail: privateValue, alertCount: 0, alertCountCapped: false, alertVisible: false, currentFieldInvalid: true, loginChallenge: null, pageError: false });
      reportAuthUiFailure({ project: "desktop", scenario: "password_current_invalid", status: 99, detail: "private", alertCount: 0, alertCountCapped: false, alertVisible: false, currentFieldInvalid: true, loginChallenge: null, pageError: false });
      reportAuthUiFailure({ project: "desktop", scenario: "password_current_invalid", status: 400, detail: "private", alertCount: 9, alertCountCapped: false, alertVisible: false, currentFieldInvalid: true, loginChallenge: null, pageError: false });
      reportAuthUiFailure({ project: "desktop", scenario: "totp_recovery_replay", status: 400, detail: "private", alertCount: 9, alertCountCapped: true, alertVisible: false, currentFieldInvalid: false, loginChallenge: true, pageError: false });
    `),
    ""
  )
})

test("auth HTTP diagnostics emit only failures with a finite operation and status", () => {
  const output = reportInChild(`
    reportAuthHttpStatus("desktop", "push_subscribe", 200);
    reportAuthHttpStatus("desktop", "student_admin_read", 403);
    reportAuthHttpStatus("desktop", "push_subscribe", 500);
    reportAuthHttpStatus("mobile", "password_change_invalid", 503);
    reportAuthHttpStatus("mobile", "totp_recovery_replay", 400);
  `)
  const rows = output
    .trim()
    .split(/\r?\n/u)
    .map((line) => JSON.parse(line.slice("AUTH_HTTP_DIAG ".length)))
  assert.deepEqual(rows, [
    {
      schema: 1,
      project: "desktop",
      operation: "push_subscribe",
      expectedStatus: 200,
      status: 500,
    },
    {
      schema: 1,
      project: "mobile",
      operation: "password_change_invalid",
      expectedStatus: 400,
      status: 503,
    },
  ])
})

test("auth HTTP diagnostics reject private labels, invalid statuses, and cap unique records", () => {
  const output = reportInChild(`
    const privateValue = { toString() { throw new Error("private") } };
    reportAuthHttpStatus("desktop", privateValue, 500);
    reportAuthHttpStatus("desktop", "push_subscribe", 99);
    for (let status = 100; status < 125; status += 1) {
      reportAuthHttpStatus("desktop", "push_subscribe", status);
      if (status === 100) reportAuthHttpStatus("desktop", "push_subscribe", status);
    }
  `)
  const rows = output
    .trim()
    .split(/\r?\n/u)
    .map((line) => JSON.parse(line.slice("AUTH_HTTP_DIAG ".length)))
  assert.equal(rows.length, 16)
  assert.deepEqual(rows[0], {
    schema: 1,
    project: "desktop",
    operation: "push_subscribe",
    expectedStatus: 200,
    status: 100,
  })
  assert.deepEqual(rows.at(-1), {
    schema: 1,
    project: "desktop",
    operation: "push_subscribe",
    expectedStatus: 200,
    status: 115,
  })
  assert.doesNotMatch(output, /private/u)
})

test("registration failure diagnostics emit only bounded closed state", () => {
  const calls = [
    'reportAuthRegistrationFailure("desktop", "password-settings", { phase: "response-wait", formValid: true, submitEnabled: true, requestObserved: false, status: null })',
    'reportAuthRegistrationFailure("mobile", "totp", { phase: "response-received", formValid: true, submitEnabled: true, requestObserved: true, status: 422 })',
    'reportAuthRegistrationFailure("desktop", "password-settings", { phase: "navigation", formValid: true, submitEnabled: true, requestObserved: true, status: 200 })',
    'reportAuthRegistrationFailure("mobile", "totp", { phase: "before-submit", formValid: false, submitEnabled: false, requestObserved: false, status: null })',
    'reportAuthRegistrationFailure("mobile", "other", { phase: "response-received", formValid: true, submitEnabled: true, requestObserved: true, status: 500 })',
  ]
  const output = reportInChild(calls.join("\n"))
  const rows = output.trim().split(/\r?\n/u)
  assert.equal(rows.length, 4)
  assert.ok(rows.every((line) => line.length <= 512))
  assert.deepEqual(
    rows.map((line) => JSON.parse(line.slice("AUTH_REGISTRATION_DIAG ".length))),
    [
      {
        schema: 1,
        project: "desktop",
        scenario: "password-settings",
        phase: "response-wait",
        formValid: true,
        submitEnabled: true,
        requestObserved: false,
        status: null,
      },
      {
        schema: 1,
        project: "mobile",
        scenario: "totp",
        phase: "response-received",
        formValid: true,
        submitEnabled: true,
        requestObserved: true,
        status: 422,
      },
      {
        schema: 1,
        project: "desktop",
        scenario: "password-settings",
        phase: "navigation",
        formValid: true,
        submitEnabled: true,
        requestObserved: true,
        status: 200,
      },
      {
        schema: 1,
        project: "mobile",
        scenario: "totp",
        phase: "before-submit",
        formValid: false,
        submitEnabled: false,
        requestObserved: false,
        status: null,
      },
    ]
  )
  assert.doesNotMatch(output, /other|private|credential|https?:/iu)
})

test("registration diagnostics reject inconsistent phases and cap distinct records", () => {
  const calls = [
    'reportAuthRegistrationFailure("desktop", "password-settings", { phase: "before-submit", formValid: true, submitEnabled: true, requestObserved: true, status: null })',
    'reportAuthRegistrationFailure("desktop", "totp", { phase: "response-wait", formValid: true, submitEnabled: true, requestObserved: true, status: 500 })',
  ]
  for (const scenario of ["password-settings", "totp"]) {
    for (const project of ["desktop", "mobile"]) {
      calls.push(
        'reportAuthRegistrationFailure("' +
          project +
          '", "' +
          scenario +
          '", { phase: "response-wait", formValid: true, submitEnabled: true, requestObserved: false, status: null })'
      )
    }
  }
  calls.push(
    'reportAuthRegistrationFailure("desktop", "totp", { phase: "response-wait", formValid: false, submitEnabled: false, requestObserved: false, status: null })'
  )
  const output = reportInChild(calls.join("\n"))
  const rows = output.trim().split(/\r?\n/u)
  assert.equal(rows.length, 4)
  assert.equal(new Set(rows).size, 4)
})

test("auth diagnostic helper is browser-independent and cannot replace a failure", async () => {
  const source = await readFile(helperUrl, "utf8")
  const sourceWithoutClosedRegistrationPhases = source
    .replaceAll('"response-wait"', "")
    .replaceAll('"response-received"', "")
  assert.doesNotMatch(
    sourceWithoutClosedRegistrationPhases,
    /\bimport\b|\brequire\s*\(|process\.(?:env|stderr)|console\.|\b(?:page|browser|context|response|request|URL)\b|\.(?:json|text|screenshot|storageState|attach)\s*\(/u
  )
  assert.equal((source.match(/process\.stdout\.write\(/gu) ?? []).length, 3)
  assert.equal(
    reportInChild(`
      process.stdout.write = () => { throw new Error("synthetic-write-failure") };
      reportAuthHttpStatus("desktop", "push_subscribe", 500);
      reportAuthUiFailure({ project: "desktop", scenario: "password_current_invalid", status: 400, detail: "private", alertCount: 0, alertCountCapped: false, alertVisible: false, currentFieldInvalid: true, loginChallenge: null, pageError: false });
    `),
    ""
  )
})
