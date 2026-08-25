import { beforeEach, describe, expect, it, vi } from "vitest"

// Mock the generated SDK so the api/mfa wrappers run against canned responses
// (no MSW / contract validator needed — per the api-logic batch guidance).
vi.mock("@/api/generated", () => ({
  confirmTotpEnrollmentApiV1AuthMfaTotpConfirmPost: vi.fn(),
  deletePendingTotpEnrollmentApiV1AuthMfaTotpPendingEnrollmentIdDelete: vi.fn(),
  deleteTotpEnrollmentApiV1AuthMfaTotpEnrollmentIdDelete: vi.fn(),
  disableEmailMfaEndpointApiV1AuthMfaEmailDelete: vi.fn(),
  generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost: vi.fn(),
  listTotpEnrollmentsApiV1AuthMfaTotpGet: vi.fn(),
  resendEmailMfaChallengeApiV1AuthMfaEmailResendPost: vi.fn(),
  requestStepUpApiV1AuthMfaStepUpPost: vi.fn(),
  startEmailMfaEnablementApiV1AuthMfaEmailEnablePost: vi.fn(),
  startEmailVerificationApiV1AuthMfaEmailVerificationStartPost: vi.fn(),
  startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost: vi.fn(),
  verifyMfaChallengeApiV1AuthMfaVerifyPost: vi.fn(),
}))

import * as gen from "@/api/generated"
import {
  confirmTotpEnrollment,
  deletePendingTotpEnrollment,
  deleteTotpEnrollment,
  disableEmailMfa,
  generateRecoveryCodes,
  listTotpEnrollments,
  resendEmailMfaChallenge,
  requestStepUpChallenge,
  startEmailMfaEnablement,
  startEmailVerification,
  startTotpEnrollment,
  verifyMfaChallenge,
} from "@/api/mfa"

const ok = (data: unknown) => ({ data })

beforeEach(() => {
  vi.clearAllMocks()
})

describe("api/mfa — TOTP enrollment wrappers", () => {
  it("startTotpEnrollment posts the payload with throwOnError and returns data", async () => {
    const payload = { label: "My phone" }
    const result = { secret: "S3CR3T", otpauth_uri: "otpauth://x" } // pragma: allowlist secret
    vi.mocked(gen.startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost).mockResolvedValue(
      ok(result) as never
    )

    await expect(startTotpEnrollment(payload)).resolves.toEqual(result)
    expect(gen.startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost).toHaveBeenCalledWith({
      body: payload,
      throwOnError: true,
    })
  })

  it("startTotpEnrollment passes undefined body when called with no args", async () => {
    vi.mocked(gen.startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost).mockResolvedValue(
      ok({}) as never
    )
    await startTotpEnrollment()
    expect(gen.startTotpEnrollmentEndpointApiV1AuthMfaTotpStartPost).toHaveBeenCalledWith({
      body: undefined,
      throwOnError: true,
    })
  })

  it("confirmTotpEnrollment posts the confirm payload and returns the factor", async () => {
    const payload = { enrollment_id: "e1", code: "123456" } as never
    const factor = { id: "e1", verified: true }
    vi.mocked(gen.confirmTotpEnrollmentApiV1AuthMfaTotpConfirmPost).mockResolvedValue(
      ok(factor) as never
    )

    await expect(confirmTotpEnrollment(payload)).resolves.toEqual(factor)
    expect(gen.confirmTotpEnrollmentApiV1AuthMfaTotpConfirmPost).toHaveBeenCalledWith({
      body: payload,
      throwOnError: true,
    })
  })

  it("listTotpEnrollments returns the enrollment list (no args forwarded)", async () => {
    const list = [{ id: "e1" }, { id: "e2" }]
    vi.mocked(gen.listTotpEnrollmentsApiV1AuthMfaTotpGet).mockResolvedValue(ok(list) as never)

    await expect(listTotpEnrollments()).resolves.toEqual(list)
    expect(gen.listTotpEnrollmentsApiV1AuthMfaTotpGet).toHaveBeenCalledTimes(1)
  })

  it("deleteTotpEnrollment sends the enrollment id as a path param", async () => {
    vi.mocked(gen.deleteTotpEnrollmentApiV1AuthMfaTotpEnrollmentIdDelete).mockResolvedValue(
      ok({ status: "deleted" }) as never
    )

    await deleteTotpEnrollment("enroll-99")
    expect(gen.deleteTotpEnrollmentApiV1AuthMfaTotpEnrollmentIdDelete).toHaveBeenCalledWith({
      path: { enrollment_id: "enroll-99" },
      throwOnError: true,
    })
  })

  it("deletePendingTotpEnrollment sends the path param and resolves void", async () => {
    vi.mocked(
      gen.deletePendingTotpEnrollmentApiV1AuthMfaTotpPendingEnrollmentIdDelete
    ).mockResolvedValue(ok(undefined) as never)

    await expect(deletePendingTotpEnrollment("pending-1")).resolves.toBeUndefined()
    expect(
      gen.deletePendingTotpEnrollmentApiV1AuthMfaTotpPendingEnrollmentIdDelete
    ).toHaveBeenCalledWith({
      path: { enrollment_id: "pending-1" },
      throwOnError: true,
    })
  })
})

describe("api/mfa — verify + step-up wrappers", () => {
  it("verifyMfaChallenge posts the payload and returns the token bundle", async () => {
    const payload = { challenge_id: "c1", code: "654321" } as never
    const token = { access_token: "jwt", token_type: "bearer" }
    vi.mocked(gen.verifyMfaChallengeApiV1AuthMfaVerifyPost).mockResolvedValue(ok(token) as never)

    await expect(verifyMfaChallenge(payload)).resolves.toEqual(token)
    expect(gen.verifyMfaChallengeApiV1AuthMfaVerifyPost).toHaveBeenCalledWith({
      body: payload,
      throwOnError: true,
    })
  })

  it("requestStepUpChallenge posts with throwOnError and returns the step-up response", async () => {
    const stepUp = { challenge_id: "su1", methods: [] }
    vi.mocked(gen.requestStepUpApiV1AuthMfaStepUpPost).mockResolvedValue(ok(stepUp) as never)

    await expect(requestStepUpChallenge()).resolves.toEqual(stepUp)
    expect(gen.requestStepUpApiV1AuthMfaStepUpPost).toHaveBeenCalledWith({ throwOnError: true })
  })
})

describe("api/mfa — email OTP wrappers", () => {
  it("starts email verification and enablement with fail-closed SDK errors", async () => {
    const challenge = { method: "email_otp", challenge_token: "ct" }
    vi.mocked(gen.startEmailVerificationApiV1AuthMfaEmailVerificationStartPost).mockResolvedValue(
      ok(challenge) as never
    )
    vi.mocked(gen.startEmailMfaEnablementApiV1AuthMfaEmailEnablePost).mockResolvedValue(
      ok(challenge) as never
    )

    await expect(startEmailVerification()).resolves.toEqual(challenge)
    await expect(startEmailMfaEnablement()).resolves.toEqual(challenge)
    expect(gen.startEmailVerificationApiV1AuthMfaEmailVerificationStartPost).toHaveBeenCalledWith({
      throwOnError: true,
    })
    expect(gen.startEmailMfaEnablementApiV1AuthMfaEmailEnablePost).toHaveBeenCalledWith({
      throwOnError: true,
    })
  })

  it("resends by current challenge token and returns the rotated challenge", async () => {
    const rotated = { method: "email_otp", challenge_token: "rotated" }
    vi.mocked(gen.resendEmailMfaChallengeApiV1AuthMfaEmailResendPost).mockResolvedValue(
      ok(rotated) as never
    )

    await expect(resendEmailMfaChallenge("current-token")).resolves.toEqual(rotated)
    expect(gen.resendEmailMfaChallengeApiV1AuthMfaEmailResendPost).toHaveBeenCalledWith({
      body: { challenge_token: "current-token" },
      throwOnError: true,
    })
  })

  it("disables email MFA and returns the resulting factor state", async () => {
    const state = { disabled: true, mfa_default_method: "totp" }
    vi.mocked(gen.disableEmailMfaEndpointApiV1AuthMfaEmailDelete).mockResolvedValue(
      ok(state) as never
    )

    await expect(disableEmailMfa()).resolves.toEqual(state)
    expect(gen.disableEmailMfaEndpointApiV1AuthMfaEmailDelete).toHaveBeenCalledWith({
      throwOnError: true,
    })
  })
})

describe("api/mfa — recovery codes", () => {
  it("generateRecoveryCodes posts with throwOnError and returns the codes", async () => {
    const codes = { codes: ["aaa-111", "bbb-222"] }
    vi.mocked(gen.generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost).mockResolvedValue(
      ok(codes) as never
    )

    await expect(generateRecoveryCodes()).resolves.toEqual(codes)
    expect(gen.generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost).toHaveBeenCalledWith({
      throwOnError: true,
    })
  })

  it("propagates rejection when the underlying endpoint throws", async () => {
    const boom = new Error("network down")
    vi.mocked(gen.generateRecoveryCodesEndpointApiV1AuthMfaRecoveryCodesPost).mockRejectedValue(
      boom
    )
    await expect(generateRecoveryCodes()).rejects.toBe(boom)
  })
})
