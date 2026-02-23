import {
  confirmTotpEnrollmentApiV1AuthMfaTotpConfirmPost,
  confirmWebauthnRegistrationApiV1AuthMfaWebauthnRegisterConfirmPost,
  deletePendingTotpEnrollmentApiV1AuthMfaTotpPendingEnrollmentIdDelete,
  deleteTotpEnrollmentApiV1AuthMfaTotpEnrollmentIdDelete,
  deleteWebauthnCredentialApiV1AuthMfaWebauthnCredentialIdDelete,
  generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost,
  listTotpEnrollmentsApiV1AuthMfaTotpGet,
  listWebauthnCredentialsApiV1AuthMfaWebauthnGet,
  requestStepUpApiV1AuthMfaStepUpPost,
  startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost,
  startWebauthnRegistrationApiV1AuthMfaWebauthnRegisterStartPost,
  verifyMfaChallengeApiV1AuthMfaVerifyPost,
} from "@/api/generated"
import type {
  MfaFactorStatus,
  MfaTotpEnrollment,
  TotpEnrollmentConfirmPayload,
  TotpEnrollmentStartPayload,
  TotpEnrollmentStart,
  MfaVerifyPayload,
  StepUpResponse,
} from "@/types/Mfa"

export const startTotpEnrollment = async (payload?: TotpEnrollmentStartPayload) => {
  const { data } = await startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost({ body: payload })
  return data as TotpEnrollmentStart
}

export const confirmTotpEnrollment = async (payload: TotpEnrollmentConfirmPayload) => {
  const { data } = await confirmTotpEnrollmentApiV1AuthMfaTotpConfirmPost({ body: payload })
  return data as MfaTotpEnrollment
}

export const listTotpEnrollments = async () => {
  const { data } = await listTotpEnrollmentsApiV1AuthMfaTotpGet()
  return data as MfaTotpEnrollment[]
}

export const deleteTotpEnrollment = async (enrollmentId: string) => {
  const { data } = await deleteTotpEnrollmentApiV1AuthMfaTotpEnrollmentIdDelete({
    path: { enrollment_id: enrollmentId },
  })
  return data as MfaFactorStatus
}

export const deletePendingTotpEnrollment = async (enrollmentId: string) => {
  await deletePendingTotpEnrollmentApiV1AuthMfaTotpPendingEnrollmentIdDelete({
    path: { enrollment_id: enrollmentId },
  })
}

export const verifyMfaChallenge = async (payload: MfaVerifyPayload) => {
  const { data } = await verifyMfaChallengeApiV1AuthMfaVerifyPost({ body: payload })
  return data as { access_token: string; token_type: string }
}

export const requestStepUpChallenge = async () => {
  const { data } = await requestStepUpApiV1AuthMfaStepUpPost()
  return data as StepUpResponse
}

export const startWebAuthnRegistration = async () => {
  const { data } = await startWebauthnRegistrationApiV1AuthMfaWebauthnRegisterStartPost()
  return data as { publicKey: unknown; challenge_token: string }
}

export const confirmWebAuthnRegistration = async (payload: {
  challenge: string
  response: unknown
  label?: string
}) => {
  const { data } = await confirmWebauthnRegistrationApiV1AuthMfaWebauthnRegisterConfirmPost({
    body: payload as any,
  })
  return data as MfaFactorStatus
}

export const listWebAuthnCredentials = async () => {
  const { data } = await listWebauthnCredentialsApiV1AuthMfaWebauthnGet()
  return data as unknown[]
}

export const deleteWebAuthnCredential = async (credentialId: string) => {
  const { data } = await deleteWebauthnCredentialApiV1AuthMfaWebauthnCredentialIdDelete({
    path: { credential_id: credentialId },
  })
  return data as MfaFactorStatus
}

export const generateRecoveryCodes = async () => {
  const { data } = await generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost()
  return data as { codes: string[] }
}
