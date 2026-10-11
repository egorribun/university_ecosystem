export type AuthDiagnosticProject = "desktop" | "mobile"
export type AuthUiScenario = "password_current_invalid" | "totp_recovery_replay"
export type AuthUiDetailClass = "expected" | "other-string" | "non-string" | "missing"

export type AuthHttpOperation =
  | "profile_read"
  | "profile_identity_read"
  | "push_topics_read"
  | "push_subscribe"
  | "push_topics_initial"
  | "push_topics_optout"
  | "push_unsubscribe"
  | "push_rebind"
  | "profile_update_enable"
  | "profile_update_start"
  | "profile_update_end"
  | "profile_update_midnight_start"
  | "profile_update_midnight_end"
  | "profile_update_disable"
  | "student_admin_read"
  | "admin_topics_read"
  | "admin_account_search"
  | "admin_account_delete"
  | "password_change_invalid"
  | "password_change_save"
  | "totp_recovery_accept"
  | "totp_recovery_replay"
  | "password_settings_register"
  | "totp_register"

const PASSWORD_EXPECTED_DETAIL = "Текущий пароль указан неверно"
const MAX_ALERT_COUNT = 8
const MAX_DIAGNOSTIC_RECORDS = 16
const emittedUiRecords = new Set<string>()
const emittedHttpRecords = new Set<string>()
const emittedRegistrationRecords = new Set<string>()
const MAX_REGISTRATION_DIAGNOSTIC_RECORDS = 4

const EXPECTED_STATUS: Readonly<Record<AuthHttpOperation, 200 | 400 | 403>> = {
  profile_read: 200,
  profile_identity_read: 200,
  push_topics_read: 200,
  push_subscribe: 200,
  push_topics_initial: 200,
  push_topics_optout: 200,
  push_unsubscribe: 200,
  push_rebind: 200,
  profile_update_enable: 200,
  profile_update_start: 200,
  profile_update_end: 200,
  profile_update_midnight_start: 200,
  profile_update_midnight_end: 200,
  profile_update_disable: 200,
  student_admin_read: 403,
  admin_topics_read: 200,
  admin_account_search: 200,
  admin_account_delete: 200,
  password_change_invalid: 400,
  password_change_save: 200,
  totp_recovery_accept: 200,
  totp_recovery_replay: 400,
  password_settings_register: 200,
  totp_register: 200,
}

function classifyDetail(scenario: AuthUiScenario, detail: unknown): AuthUiDetailClass {
  if (detail === undefined) return "missing"
  if (typeof detail !== "string") return "non-string"
  if (scenario === "password_current_invalid") {
    return detail === PASSWORD_EXPECTED_DETAIL ? "expected" : "other-string"
  }
  return detail.length > 0 ? "expected" : "other-string"
}

export interface AuthUiFailureDiagnostic {
  project: AuthDiagnosticProject
  scenario: AuthUiScenario
  status: number
  detail: unknown
  alertCount: number
  alertCountCapped: boolean
  alertVisible: boolean
  currentFieldInvalid: boolean | null
  loginChallenge: boolean | null
  pageError: boolean
}

export function reportAuthUiFailure(value: unknown): void {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return
  const input = value as AuthUiFailureDiagnostic
  const scenarioIsValid =
    input.scenario === "password_current_invalid" || input.scenario === "totp_recovery_replay"
  if (
    (input.project !== "desktop" && input.project !== "mobile") ||
    !scenarioIsValid ||
    !Number.isInteger(input.status) ||
    input.status < 100 ||
    input.status > 599 ||
    !Number.isInteger(input.alertCount) ||
    input.alertCount < 0 ||
    input.alertCount > MAX_ALERT_COUNT ||
    typeof input.alertCountCapped !== "boolean" ||
    (input.alertCountCapped && input.alertCount !== MAX_ALERT_COUNT) ||
    typeof input.alertVisible !== "boolean" ||
    typeof input.pageError !== "boolean" ||
    (input.scenario === "password_current_invalid" &&
      (typeof input.currentFieldInvalid !== "boolean" || input.loginChallenge !== null)) ||
    (input.scenario === "totp_recovery_replay" &&
      (input.currentFieldInvalid !== null || typeof input.loginChallenge !== "boolean"))
  ) {
    return
  }

  const record =
    "AUTH_UI_DIAG " +
    JSON.stringify({
      schema: 1,
      project: input.project,
      scenario: input.scenario,
      status: input.status,
      detailClass: classifyDetail(input.scenario, input.detail),
      alertCount: input.alertCount,
      alertCountCapped: input.alertCountCapped,
      alertVisible: input.alertVisible,
      currentFieldInvalid: input.currentFieldInvalid,
      loginChallenge: input.loginChallenge,
      pageError: input.pageError,
    }) +
    "\n"
  if (emittedUiRecords.has(record) || emittedUiRecords.size >= MAX_DIAGNOSTIC_RECORDS) return
  emittedUiRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // Diagnostics must never replace the live assertion result.
  }
}

export type AuthRegistrationScenario = "password-settings" | "totp"
export type AuthRegistrationPhase =
  "before-submit" | "response-wait" | "response-received" | "navigation"

export interface AuthRegistrationObservation {
  phase: AuthRegistrationPhase
  formValid: boolean
  submitEnabled: boolean
  requestObserved: boolean
  status: number | null
}

export function reportAuthRegistrationFailure(
  project: AuthDiagnosticProject,
  scenario: AuthRegistrationScenario,
  observation: AuthRegistrationObservation
): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    (scenario !== "password-settings" && scenario !== "totp") ||
    observation === null ||
    typeof observation !== "object" ||
    (observation.phase !== "before-submit" &&
      observation.phase !== "response-wait" &&
      observation.phase !== "response-received" &&
      observation.phase !== "navigation") ||
    typeof observation.formValid !== "boolean" ||
    typeof observation.submitEnabled !== "boolean" ||
    typeof observation.requestObserved !== "boolean" ||
    (observation.status !== null &&
      (!Number.isInteger(observation.status) ||
        observation.status < 100 ||
        observation.status > 599)) ||
    (observation.phase === "before-submit" &&
      (observation.requestObserved || observation.status !== null)) ||
    (observation.phase === "response-wait" && observation.status !== null) ||
    ((observation.phase === "response-received" || observation.phase === "navigation") &&
      (!observation.requestObserved ||
        observation.status === null ||
        (observation.phase === "navigation" &&
          (observation.status < 200 || observation.status > 299))))
  ) {
    return
  }

  const record =
    "AUTH_REGISTRATION_DIAG " +
    JSON.stringify({
      schema: 1,
      project,
      scenario,
      phase: observation.phase,
      formValid: observation.formValid,
      submitEnabled: observation.submitEnabled,
      requestObserved: observation.requestObserved,
      status: observation.status,
    }) +
    "\n"
  if (
    record.length > 512 ||
    emittedRegistrationRecords.has(record) ||
    emittedRegistrationRecords.size >= MAX_REGISTRATION_DIAGNOSTIC_RECORDS
  ) {
    return
  }
  emittedRegistrationRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // Registration diagnostics must never replace the live assertion result.
  }
}
export function reportAuthHttpStatus(
  project: string,
  operation: AuthHttpOperation,
  status: number
): void {
  if (
    typeof project !== "string" ||
    (project !== "desktop" && project !== "mobile") ||
    typeof operation !== "string" ||
    !Object.prototype.hasOwnProperty.call(EXPECTED_STATUS, operation) ||
    !Number.isInteger(status) ||
    status < 100 ||
    status > 599
  ) {
    return
  }

  const expectedStatus = EXPECTED_STATUS[operation]
  if (status === expectedStatus) return
  const record =
    "AUTH_HTTP_DIAG " +
    JSON.stringify({ schema: 1, project, operation, expectedStatus, status }) +
    "\n"
  if (emittedHttpRecords.has(record) || emittedHttpRecords.size >= MAX_DIAGNOSTIC_RECORDS) return
  emittedHttpRecords.add(record)
  try {
    process.stdout.write(record)
  } catch {
    // Diagnostics must never replace the live assertion result.
  }
}
