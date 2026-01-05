import type { PendingMfaResponse } from "@/types/Mfa"
import type { User } from "@/types/User"
import type { Dispatch, SetStateAction } from "react"

export type UserState = User | null
export type SetUserArg = SetStateAction<UserState>

export type PendingMfaState = PendingMfaResponse & { reason: "login" | "step-up" }

export type SubmitMfaChallengePayload = {
  method?: "totp" | "webauthn"
  code?: string
  webauthnResponse?: any
  challengeToken?: string
  trustDevice?: boolean
}

export type WebAuthnAuthenticationOptionsOut = {
  publicKey: any
  challenge_token: string
}

export type AuthContextType = {
  isAuth: boolean
  login: (email: string, password: string, trustDevice?: boolean) => Promise<PendingMfaState | null>
  logout: () => Promise<void>
  user: UserState
  loading: boolean
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
