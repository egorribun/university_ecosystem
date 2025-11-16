import type { components, paths } from "@/api/generated/schema"

export type MfaMethod = components["schemas"]["MfaMethodChallengeOut"]["method"]
export type MfaMethodChallenge = components["schemas"]["MfaMethodChallengeOut"]
export type PendingMfaResponse = components["schemas"]["PendingMfaResponse"]
export type MfaTotpEnrollment = components["schemas"]["MfaTotpEnrollmentOut"]
export type MfaRecoveryCode = components["schemas"]["MfaRecoveryCodeOut"]
export type MfaChallenge = components["schemas"]["MfaChallengeOut"]
export type TotpEnrollmentStartResponse = components["schemas"]["TotpEnrollmentStartOut"]
export type TotpEnrollmentStartPayload = components["schemas"]["TotpEnrollmentStartIn"]
export type TotpEnrollmentConfirmPayload = components["schemas"]["TotpEnrollmentConfirmIn"]
export type MfaVerifyPayload = components["schemas"]["MfaVerifyIn"]

type StepUpPath = paths["/auth/mfa/step-up"]["post"]

export type StepUpResponse = StepUpPath["responses"]["200"]["content"]["application/json"]

export type MfaFactorStatus = {
  disabled: boolean
  mfa_default_method: MfaMethod | null
  mfa_required: boolean
}
