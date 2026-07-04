import type { PendingMfaResponse, WebAuthnAuthenticationOptionsOut } from "@/api/generated"
import type { User } from "@/types/User"
import type { Dispatch, SetStateAction } from "react"

export type { WebAuthnAuthenticationOptionsOut }

export type UserState = User | null
export type SetUserArg = SetStateAction<UserState>

export type PendingMfaState = PendingMfaResponse & { reason: "login" | "step-up" }

export type SubmitMfaChallengePayload = {
  method?: "totp" | "webauthn" | "recovery_code"
  code?: string
  webauthnResponse?: unknown
  challengeToken?: string
  trustDevice?: boolean
}

export type AuthContextType = {
  isAuth: boolean
  login: (email: string, password: string, trustDevice?: boolean) => Promise<PendingMfaState | null>
  logout: () => Promise<void>
  user: UserState
  loading: boolean
  authOperation: boolean
  setUser: Dispatch<SetUserArg>
  refresh: () => Promise<void>
  pendingMfa: PendingMfaState | null
  submitMfaChallenge: (payload: SubmitMfaChallengePayload) => Promise<void>
  requireMfa: () => Promise<PendingMfaState | null>
  loginWithPasskey: (email: string, trustDevice?: boolean) => Promise<void>
  resetEtagCache: () => void
}

export class ChallengeLockedError extends Error {
  refreshable: boolean

  constructor(message: string, options?: { refreshable?: boolean }) {
    super(message)
    this.name = "ChallengeLockedError"
    this.refreshable = Boolean(options?.refreshable)
    Object.setPrototypeOf(this, ChallengeLockedError.prototype)
  }
}
