import type { PendingMfaResponse } from "@/api/generated"
import type { User } from "@/types/User"
import type { Dispatch, SetStateAction } from "react"

export type UserState = User | null
export type SetUserArg = SetStateAction<UserState>

export type PendingMfaState = PendingMfaResponse & { reason: "login" | "step-up" }

export type SubmitMfaChallengePayload = {
  method?: "totp" | "email_otp" | "recovery_code"
  code?: string
  challengeToken?: string
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
