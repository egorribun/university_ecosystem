import type {
  MfaChallenge,
  MfaMethod,
  MfaRecoveryCode,
  MfaTotpEnrollment,
  MfaWebAuthnCredential,
} from "./Mfa"

export interface User {
  id: number
  email: string
  full_name: string | null
  role: string | null
  group_id: number | null
  avatar_url: string | null
  cover_url: string | null
  about: string | null
  record_book_number: string | null
  status: string | null
  institute: string | null
  course: string | null
  education_level: string | null
  track: string | null
  program: string | null
  telegram: string | null
  achievements: string | null
  department: string | null
  position: string | null
  spotify_connected: boolean
  spotify_display_name: string | null
  spotify_is_connected?: boolean | null
  dnd_enabled: boolean
  dnd_start: string | null
  dnd_end: string | null
  is_active: boolean
  mfa_required: boolean
  mfa_default_method: MfaMethod | null
  mfa_last_verified_at: string | null
  mfa_recovery_codes_generated_at: string | null
  totp_enrollments: MfaTotpEnrollment[]
  webauthn_credentials: MfaWebAuthnCredential[]
  recovery_codes: MfaRecoveryCode[]
  mfa_challenges: MfaChallenge[]
}
