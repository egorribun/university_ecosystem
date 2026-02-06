import type { components, paths } from "@/api/generated/schema"

export type MfaMethod = components["schemas"]["MfaMethodChallengeOut"]["method"]
export type MfaMethodChallenge = components["schemas"]["MfaMethodChallengeOut"]
export type PendingMfaResponse = components["schemas"]["PendingMfaResponse"] & {
  challenges: MfaMethodChallenge[]
}
export type MfaTotpEnrollment = components["schemas"]["MfaTotpEnrollmentOut"]
export type MfaChallenge = components["schemas"]["MfaChallengeOut"]
export type TotpEnrollmentStartResponse = components["schemas"]["TotpEnrollmentStartOut"]
export type TotpEnrollmentStartPayload = components["schemas"]["TotpEnrollmentStartIn"]
export type TotpEnrollmentConfirmPayload = components["schemas"]["TotpEnrollmentConfirmIn"]
export type MfaVerifyPayload = {
  method: "totp" | "webauthn"
  challenge_token: string
  code?: string
  webauthn_response?: any
  trust_device?: boolean
}

type StepUpPath = paths["/api/v1/auth/mfa/step-up"]["post"]

export type StepUpResponse = StepUpPath["responses"]["202"]["content"]["application/json"]

export type MfaFactorStatus = {
  disabled: boolean
  mfa_default_method: MfaMethod | null
  mfa_required: boolean
}

export type WebAuthnCredential = {
  id: string
  label: string
  created_at: string
  last_used_at: string | null
  credential_id: string
}

export type WebAuthnRegistrationOptionsOut = {
  publicKey: any
}

export type WebAuthnRegistrationVerifyIn = {
  challenge: string
  response: any
  label?: string
}
