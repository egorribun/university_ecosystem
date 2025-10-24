export type MfaMethod = "totp" | "webauthn" | "recovery"

export interface MfaMethodChallenge {
  method: MfaMethod
  challenge_token: string
  challenge_expires_at: string
  options?: Record<string, unknown> | null
}

export interface PendingMfaResponse {
  status: "mfa_required"
  user_id: number
  session_id: number | null
  default_method: MfaMethod | null
  methods: MfaMethodChallenge[]
}

export interface MfaTotpEnrollment {
  id: number
  user_id: number
  label: string | null
  is_active: boolean
  confirmed_at: string | null
  revoked_at: string | null
  created_at: string
}

export interface MfaWebAuthnCredential {
  id: number
  user_id: number
  credential_id: string
  device_name: string | null
  sign_count: number
  transports: string[] | null
  backed_up: boolean
  clone_warning: boolean
  created_at: string
  last_used_at: string | null
  is_active: boolean
}

export interface MfaRecoveryCode {
  id: number
  user_id: number
  used_at: string | null
  created_at: string
  label: string | null
}

export interface MfaChallenge {
  id: number
  user_id: number
  session_id: number | null
  challenge_type: string
  token: string
  expires_at: string
  consumed_at: string | null
  created_at: string
  payload: Record<string, unknown> | null
}

export interface TotpEnrollmentStartResponse {
  enrollment: MfaTotpEnrollment
  secret: string
  otpauth_url: string
}

export type TotpEnrollmentStartPayload = {
  label?: string | null
}

export interface TotpEnrollmentConfirmPayload {
  enrollment_id: number
  code: string
}

export interface WebAuthnAttestationStartResponse {
  options: Record<string, unknown>
  challenge_token: string
  challenge_expires_at: string
}

export interface WebAuthnAttestationFinishPayload {
  challenge_token: string
  credential: Record<string, unknown>
  device_name?: string | null
}

export interface WebAuthnAssertionStartResponse {
  options: Record<string, unknown>
  challenge_token: string
  challenge_expires_at: string
}

export type MfaVerifyPayload =
  | {
      method: "totp" | "recovery"
      challenge_token: string
      code: string
      credential?: never
    }
  | {
      method: "webauthn"
      challenge_token: string
      credential: Record<string, unknown>
      code?: never
    }

