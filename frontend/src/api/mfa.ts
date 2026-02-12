import api from "./client"
import type {
  MfaFactorStatus,
  MfaTotpEnrollment,
  TotpEnrollmentConfirmPayload,
  TotpEnrollmentStartPayload,
  TotpEnrollmentStartResponse,
  MfaVerifyPayload,
  StepUpResponse,
} from "@/types/Mfa"

export const startTotpEnrollment = (payload?: TotpEnrollmentStartPayload) =>
  api.post<TotpEnrollmentStartResponse>("/auth/mfa/totp/start", payload)

export const confirmTotpEnrollment = (payload: TotpEnrollmentConfirmPayload) =>
  api.post<MfaTotpEnrollment>("/auth/mfa/totp/confirm", payload)

export const listTotpEnrollments = () => api.get<MfaTotpEnrollment[]>("/auth/mfa/totp")

export const deleteTotpEnrollment = (enrollmentId: string) =>
  api.delete<MfaFactorStatus>(`/auth/mfa/totp/${enrollmentId}`)

export const deletePendingTotpEnrollment = (enrollmentId: string) =>
  api.delete<void>(`/auth/mfa/totp/pending/${enrollmentId}`)

export const verifyMfaChallenge = (payload: MfaVerifyPayload) =>
  api.post<{ access_token: string; token_type: string }>("/auth/mfa/verify", payload)

export const requestStepUpChallenge = () => api.post<StepUpResponse>("/auth/mfa/step-up")

export const startWebAuthnRegistration = () =>
  api.post<{ publicKey: unknown; challenge_token: string }>("/auth/mfa/webauthn/register/start")

export const confirmWebAuthnRegistration = (payload: {
  challenge: string
  response: unknown
  label?: string
}) => api.post<MfaFactorStatus>("/auth/mfa/webauthn/register/confirm", payload)

export const listWebAuthnCredentials = () => api.get<unknown[]>("/auth/mfa/webauthn")

export const deleteWebAuthnCredential = (credentialId: string) =>
  api.delete<MfaFactorStatus>(`/auth/mfa/webauthn/${credentialId}`)
