import type {
  MfaChallengeOut,
  MfaFactorStatusOut,
  MfaMethodChallengeOut,
  MfaTotpEnrollmentOut,
  MfaVerifyIn,
  PendingMfaResponse,
  RequestStepUpApiV1AuthMfaStepUpPostResponse,
  TotpEnrollmentConfirmIn,
  TotpEnrollmentStartIn,
  TotpEnrollmentStartOut,
  WebAuthnAuthenticationOptionsOut,
  WebAuthnRegistrationOptionsOut,
  WebAuthnRegistrationVerifyIn,
} from "@/api/generated"

export type { PendingMfaResponse }

export type MfaMethod = "totp" | "webauthn" | "recovery_code"

export type MfaStepUpStatus = PendingMfaResponse

export type MfaEnrollment = MfaTotpEnrollmentOut
export type MfaTotpEnrollment = MfaTotpEnrollmentOut

export type MfaChallenge = MfaChallengeOut

export type TotpEnrollmentStart = TotpEnrollmentStartOut

export type TotpEnrollmentStartPayload = TotpEnrollmentStartIn

export type TotpEnrollmentConfirmPayload = TotpEnrollmentConfirmIn

export type MfaVerifyPayload = MfaVerifyIn

export type StepUpResponse = RequestStepUpApiV1AuthMfaStepUpPostResponse

export type MfaFactorStatus = MfaFactorStatusOut

export type WebAuthnCredential = {
  id: string
  label: string
  created_at: string
  last_used_at: string | null
  credential_id: string
}

export type WebAuthnRegistrationOptions = WebAuthnRegistrationOptionsOut

export type WebAuthnRegistrationVerifyPayload = WebAuthnRegistrationVerifyIn

export type MfaMethodChallenge = MfaMethodChallengeOut

export type WebAuthnAuthenticationOptions = WebAuthnAuthenticationOptionsOut
