import api from "./client"
import type {
  MfaTotpEnrollment,
  MfaWebAuthnCredential,
  MfaRecoveryCode,
  PendingMfaResponse,
  TotpEnrollmentConfirmPayload,
  TotpEnrollmentStartPayload,
  TotpEnrollmentStartResponse,
  WebAuthnAssertionStartResponse,
  WebAuthnAttestationFinishPayload,
  WebAuthnAttestationStartResponse,
  MfaVerifyPayload,
} from "@/types/Mfa"

export const startTotpEnrollment = (payload?: TotpEnrollmentStartPayload) =>
  api.post<TotpEnrollmentStartResponse>("/auth/mfa/totp/start", payload)

export const confirmTotpEnrollment = (payload: TotpEnrollmentConfirmPayload) =>
  api.post<MfaTotpEnrollment>("/auth/mfa/totp/confirm", payload)

export const listTotpEnrollments = () => api.get<MfaTotpEnrollment[]>("/auth/mfa/totp")

export const deleteTotpEnrollment = (enrollmentId: number) =>
  api.delete<{ disabled: boolean }>(`/auth/mfa/totp/${enrollmentId}`)

export const listWebAuthnCredentials = () => api.get<MfaWebAuthnCredential[]>("/auth/mfa/webauthn")

export const deleteWebAuthnCredential = (credentialId: string) =>
  api.delete<{ disabled: boolean }>(`/auth/mfa/webauthn/${credentialId}`)

export const startWebAuthnAttestation = () =>
  api.post<WebAuthnAttestationStartResponse>("/auth/mfa/webauthn/attestation/start")

export const finishWebAuthnAttestation = (payload: WebAuthnAttestationFinishPayload) =>
  api.post<MfaWebAuthnCredential>("/auth/mfa/webauthn/attestation/finish", payload)

export const startWebAuthnAssertion = () =>
  api.post<WebAuthnAssertionStartResponse>("/auth/mfa/webauthn/assertion/start")

export const verifyMfaChallenge = (payload: MfaVerifyPayload) =>
  api.post<{ access_token: string; token_type: string }>("/auth/mfa/verify", payload)

export const requestStepUpChallenge = () => api.post<PendingMfaResponse>("/auth/mfa/step-up")

export const regenerateRecoveryCodes = () =>
  api.post<{ codes: string[]; generated_at: string | null }>("/auth/mfa/recovery/regenerate")

export const listRecoveryCodes = () => api.get<MfaRecoveryCode[]>("/auth/mfa/recovery")
