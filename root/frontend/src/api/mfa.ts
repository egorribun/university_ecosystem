import api from "./client"
import type {
  MfaFactorStatus,
  MfaTotpEnrollment,
  MfaRecoveryCode,
  PendingMfaResponse,
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

export const deleteTotpEnrollment = (enrollmentId: number) =>
  api.delete<MfaFactorStatus>(`/auth/mfa/totp/${enrollmentId}`)

export const deletePendingTotpEnrollment = (enrollmentId: number) =>
  api.delete<void>(`/auth/mfa/totp/pending/${enrollmentId}`)

export const verifyMfaChallenge = (payload: MfaVerifyPayload) =>
  api.post<{ access_token: string; token_type: string }>("/auth/mfa/verify", payload)

export const requestStepUpChallenge = () => api.post<StepUpResponse>("/auth/mfa/step-up")

export const regenerateRecoveryCodes = () =>
  api.post<{ codes: string[]; generated_at: string | null }>("/auth/mfa/recovery/regenerate")

export const listRecoveryCodes = () => api.get<MfaRecoveryCode[]>("/auth/mfa/recovery")
