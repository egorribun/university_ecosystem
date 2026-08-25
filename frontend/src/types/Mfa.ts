import type {
  MfaFactorStatusOut,
  MfaMethodChallengeOut,
  MfaTotpEnrollmentOut,
  MfaVerifyIn,
  PendingMfaResponse,
  RequestStepUpApiV1AuthMfaStepUpPostResponse,
  TotpEnrollmentConfirmIn,
  TotpEnrollmentStartIn,
  TotpEnrollmentStartOut,
} from "@/api/generated"

export type { PendingMfaResponse }

export type MfaMethod = "totp" | "email_otp" | "recovery_code"

export type MfaStepUpStatus = PendingMfaResponse

export type MfaEnrollment = MfaTotpEnrollmentOut
export type MfaTotpEnrollment = MfaTotpEnrollmentOut

export type TotpEnrollmentStart = TotpEnrollmentStartOut

export type TotpEnrollmentStartPayload = TotpEnrollmentStartIn

export type TotpEnrollmentConfirmPayload = TotpEnrollmentConfirmIn

export type MfaVerifyPayload = MfaVerifyIn

export type StepUpResponse = RequestStepUpApiV1AuthMfaStepUpPostResponse

export type MfaFactorStatus = MfaFactorStatusOut

export type MfaMethodChallenge = MfaMethodChallengeOut
