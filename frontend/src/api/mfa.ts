import {
  confirmTotpEnrollmentApiV1AuthMfaTotpConfirmPost,
  deletePendingTotpEnrollmentApiV1AuthMfaTotpPendingEnrollmentIdDelete,
  deleteTotpEnrollmentApiV1AuthMfaTotpEnrollmentIdDelete,
  disableEmailMfaEndpointApiV1AuthMfaEmailDelete,
  generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost,
  listTotpEnrollmentsApiV1AuthMfaTotpGet,
  resendEmailMfaChallengeApiV1AuthMfaEmailResendPost,
  requestStepUpApiV1AuthMfaStepUpPost,
  startEmailMfaEnablementApiV1AuthMfaEmailEnablePost,
  startEmailVerificationApiV1AuthMfaEmailVerificationStartPost,
  startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost,
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
  const { data } = await startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost({
    body: payload,
    throwOnError: true,
  })
  return data as TotpEnrollmentStart
}

export const confirmTotpEnrollment = async (payload: TotpEnrollmentConfirmPayload) => {
  const { data } = await confirmTotpEnrollmentApiV1AuthMfaTotpConfirmPost({
    body: payload,
    throwOnError: true,
  })
  return data as MfaTotpEnrollment
}

export const listTotpEnrollments = async () => {
  const { data } = await listTotpEnrollmentsApiV1AuthMfaTotpGet()
  return data as MfaTotpEnrollment[]
}

export const deleteTotpEnrollment = async (enrollmentId: string) => {
  const { data } = await deleteTotpEnrollmentApiV1AuthMfaTotpEnrollmentIdDelete({
    path: { enrollment_id: enrollmentId },
    throwOnError: true,
  })
  return data as MfaFactorStatus
}

export const deletePendingTotpEnrollment = async (enrollmentId: string) => {
  await deletePendingTotpEnrollmentApiV1AuthMfaTotpPendingEnrollmentIdDelete({
    path: { enrollment_id: enrollmentId },
    throwOnError: true,
  })
}

export const verifyMfaChallenge = async (payload: MfaVerifyPayload) => {
  const { data } = await verifyMfaChallengeApiV1AuthMfaVerifyPost({
    body: payload,
    throwOnError: true,
  })
  return data as { access_token: string; token_type: string }
}

export const requestStepUpChallenge = async () => {
  const { data } = await requestStepUpApiV1AuthMfaStepUpPost({ throwOnError: true })
  return data as StepUpResponse
}

export const startEmailVerification = async () => {
  const { data } = await startEmailVerificationApiV1AuthMfaEmailVerificationStartPost({
    throwOnError: true,
  })
  return data
}

export const startEmailMfaEnablement = async () => {
  const { data } = await startEmailMfaEnablementApiV1AuthMfaEmailEnablePost({
    throwOnError: true,
  })
  return data
}

export const resendEmailMfaChallenge = async (challengeToken: string) => {
  const { data } = await resendEmailMfaChallengeApiV1AuthMfaEmailResendPost({
    body: { challenge_token: challengeToken },
    throwOnError: true,
  })
  return data
}

export const disableEmailMfa = async () => {
  const { data } = await disableEmailMfaEndpointApiV1AuthMfaEmailDelete({
    throwOnError: true,
  })
  return data as MfaFactorStatus
}

export const generateRecoveryCodes = async () => {
  const { data } = await generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost({
    throwOnError: true,
  })
  return data as { codes: string[] }
}
