import type { components, paths } from "@/api/generated/schema"

export type MfaMethod = components["schemas"]["MfaMethodChallengeOut"]["method"]
export type MfaMethodChallenge = components["schemas"]["MfaMethodChallengeOut"]
export type PendingMfaResponse = components["schemas"]["PendingMfaResponse"]
export type MfaTotpEnrollment = components["schemas"]["MfaTotpEnrollmentOut"]
export type MfaWebAuthnCredential = components["schemas"]["MfaWebAuthnCredentialOut"]
export type MfaRecoveryCode = components["schemas"]["MfaRecoveryCodeOut"]
export type MfaChallenge = components["schemas"]["MfaChallengeOut"]
export type TotpEnrollmentStartResponse = components["schemas"]["TotpEnrollmentStartOut"]
export type TotpEnrollmentStartPayload = components["schemas"]["TotpEnrollmentStartIn"]
export type TotpEnrollmentConfirmPayload = components["schemas"]["TotpEnrollmentConfirmIn"]
export type WebAuthnAttestationStartResponse = components["schemas"]["WebAuthnAttestationStartOut"]
export type WebAuthnAttestationFinishPayload = components["schemas"]["WebAuthnAttestationFinishIn"]
export type WebAuthnAssertionStartResponse = components["schemas"]["WebAuthnAssertionStartOut"]
export type MfaVerifyPayload = components["schemas"]["MfaVerifyIn"]

type StepUpPath = paths["/auth/mfa/step-up"]["post"]

export type StepUpResponse = StepUpPath["responses"]["200"]["content"]["application/json"]
